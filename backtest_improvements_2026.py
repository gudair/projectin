"""
Backtest Improvements for Jan-Feb 2026

Tests:
1. Baseline (current aggressive strategy - no AI filter)
2. Dynamic Stop Losses (volatility-adjusted)
3. Volume Filter (reject low-volume dips)
4. Combined (both improvements)

IMPORTANT: No AI filter used (rule-based only) to avoid data leakage
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import json

from backtest.daily_data import DailyDataLoader, DailyBar
from agent.strategies.aggressive_dip import AggressiveDipStrategy, AggressiveDipConfig, AggressiveSignal

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_date: datetime
    stop_loss: float
    take_profit: float
    trailing_stop_pct: float
    high_since_entry: float
    days_held: int = 0


@dataclass
class Trade:
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str


@dataclass
class BacktestConfig:
    """Configuration for backtest"""
    name: str

    # Baseline aggressive strategy params
    initial_capital: float = 100_000.0
    max_positions: int = 2
    position_size_pct: float = 0.50

    # Strategy params (from aggressive_dip.py)
    min_prev_day_drop: float = -0.01
    min_day_range: float = 0.02
    max_rsi: float = 45.0
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.10
    trailing_stop_pct: float = 0.02
    max_hold_days: int = 4

    # Improvements flags
    use_dynamic_stops: bool = False
    use_volume_filter: bool = False

    # Dynamic stops params
    vix_high_threshold: float = 25.0
    vix_low_threshold: float = 15.0
    vix_high_multiplier: float = 1.25
    vix_low_multiplier: float = 0.85
    symbol_vol_threshold: float = 0.05
    symbol_vol_multiplier: float = 1.15

    # Volume filter params
    volume_reject_threshold: float = 0.5  # Reject if < 0.5x average
    volume_boost_threshold: float = 2.0   # Boost confidence if > 2x average
    volume_boost_amount: float = 0.05     # How much to boost


class ImprovementsBacktestEngine:
    """Backtest engine for testing improvements"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: BacktestConfig,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config

        # Symbols from aggressive agent config
        self.symbols = [
            'SOXL', 'SMCI', 'MARA', 'COIN',
            'MU', 'AMD', 'NVDA', 'TSLA'
        ]

        self.data_loader = DailyDataLoader()
        self.strategy = AggressiveDipStrategy(AggressiveDipConfig(
            min_prev_day_drop=config.min_prev_day_drop,
            min_day_range=config.min_day_range,
            max_rsi=config.max_rsi,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            trailing_stop_pct=config.trailing_stop_pct,
            max_hold_days=config.max_hold_days,
            require_bullish_market=False,  # Trade in all conditions
        ))

        # State
        self.cash = config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_equity: List[Dict] = []

        self.stats = {
            'signals_generated': 0,
            'buy_signals': 0,
            'volume_rejections': 0,
            'trades_executed': 0,
            'stop_loss_exits': 0,
            'trailing_stop_exits': 0,
            'take_profit_exits': 0,
            'max_hold_exits': 0,
        }

    async def run(self) -> Dict[str, Any]:
        """Run backtest"""
        logger.info("=" * 80)
        logger.info(f"BACKTEST: {self.config.name}")
        logger.info("=" * 80)
        logger.info(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info(f"Initial capital: ${self.config.initial_capital:,.0f}")
        logger.info(f"Position size: {self.config.position_size_pct:.0%} per trade")
        logger.info(f"Max positions: {self.config.max_positions}")

        if self.config.use_dynamic_stops:
            logger.info(f"✓ Dynamic Stops enabled (VIX {self.config.vix_low_threshold}-{self.config.vix_high_threshold})")
        if self.config.use_volume_filter:
            logger.info(f"✓ Volume Filter enabled (reject < {self.config.volume_reject_threshold:.1f}x avg)")

        logger.info("-" * 80)

        # Load data
        load_start = self.start_date - timedelta(days=30)
        symbols_to_load = self.symbols + ['SPY']

        # Try to load VIX if using dynamic stops
        if self.config.use_dynamic_stops:
            symbols_to_load.append('VIX')

        await self.data_loader.load(symbols_to_load, load_start, self.end_date)

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)
        logger.info(f"Trading days: {len(trading_days)}")

        if not trading_days:
            return self._generate_results()

        # Process each day
        for day in trading_days:
            await self._process_day(day)

        # Close remaining positions
        last_day = trading_days[-1]
        if self.positions:
            logger.info(f"\nClosing {len(self.positions)} remaining positions at end...")
            for symbol in list(self.positions.keys()):
                exit_price = self.data_loader.get_price(symbol, last_day)
                self._close_position(symbol, last_day, exit_price, "END_OF_BACKTEST")

        return self._generate_results()

    async def _process_day(self, day: datetime):
        """Process a single trading day"""
        # Update existing positions (check stops, take profits)
        for symbol in list(self.positions.keys()):
            await self._check_position(symbol, day)

        # Check for new entries (if have available slots)
        if len(self.positions) < self.config.max_positions:
            await self._check_entries(day)

    async def _check_position(self, symbol: str, day: datetime):
        """Check position for exits"""
        pos = self.positions[symbol]
        pos.days_held += 1

        # Get today's bar
        bar = self.data_loader.get_bar(symbol, day)
        if not bar:
            return

        current_price = bar.close
        high_today = bar.high
        low_today = bar.low

        # Update high since entry
        if high_today > pos.high_since_entry:
            pos.high_since_entry = high_today

        # Check stop loss
        if low_today <= pos.stop_loss:
            self.stats['stop_loss_exits'] += 1
            self._close_position(symbol, day, pos.stop_loss, "STOP_LOSS")
            return

        # Check trailing stop
        trailing_stop = pos.high_since_entry * (1 - pos.trailing_stop_pct)
        if low_today <= trailing_stop:
            self.stats['trailing_stop_exits'] += 1
            self._close_position(symbol, day, trailing_stop, "TRAILING_STOP")
            return

        # Check take profit
        if high_today >= pos.take_profit:
            self.stats['take_profit_exits'] += 1
            self._close_position(symbol, day, pos.take_profit, "TAKE_PROFIT")
            return

        # Check max hold days
        if pos.days_held >= self.config.max_hold_days:
            self.stats['max_hold_exits'] += 1
            self._close_position(symbol, day, current_price, "MAX_HOLD")
            return

    async def _check_entries(self, day: datetime):
        """Check for new entry signals"""
        # Get SPY closes for market context
        spy_bars = self.data_loader.get_bars('SPY', day, 20)
        spy_closes = [b.close for b in spy_bars] if spy_bars else []

        for symbol in self.symbols:
            if symbol in self.positions:
                continue

            # Get bars
            bars = self.data_loader.get_bars(symbol, day, 20)
            if len(bars) < 15:
                continue

            closes = [b.close for b in bars]
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]

            # Generate signal
            signal = self.strategy.generate_signal(
                symbol=symbol,
                closes=closes,
                highs=highs,
                lows=lows,
                spy_closes=spy_closes,
                has_position=False,
            )

            self.stats['signals_generated'] += 1

            if signal.action != 'BUY' or signal.confidence < 0.7:
                continue

            self.stats['buy_signals'] += 1

            # Apply volume filter if enabled
            if self.config.use_volume_filter:
                vol_status, vol_ratio = self._analyze_volume(symbol, day)

                if vol_status == "LOW":
                    self.stats['volume_rejections'] += 1
                    logger.debug(f"  {symbol}: Volume too low ({vol_ratio:.1f}x), skipping")
                    continue

                # Optionally boost confidence for high volume
                if vol_status == "UNUSUALLY_HIGH":
                    signal.confidence = min(0.95, signal.confidence + self.config.volume_boost_amount)

            # Calculate position size
            position_value = self.cash * self.config.position_size_pct
            qty = position_value / signal.entry_price

            # Calculate stop loss (dynamic or fixed)
            if self.config.use_dynamic_stops:
                stop_loss_pct = self._calculate_dynamic_stop(symbol, day)
            else:
                stop_loss_pct = self.config.stop_loss_pct

            stop_loss = signal.entry_price * (1 - stop_loss_pct)
            take_profit = signal.entry_price * (1 + self.config.take_profit_pct)

            # Open position
            self.positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                entry_price=signal.entry_price,
                entry_date=day,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop_pct=self.config.trailing_stop_pct,
                high_since_entry=signal.entry_price,
            )

            self.cash -= position_value
            self.stats['trades_executed'] += 1

            logger.info(
                f"  BUY {symbol} @ ${signal.entry_price:.2f} | "
                f"Stop: ${stop_loss:.2f} ({stop_loss_pct:.1%}) | "
                f"Target: ${take_profit:.2f} | Conf: {signal.confidence:.0%}"
            )

            # Only 1 trade per day (conservative)
            break

    def _analyze_volume(self, symbol: str, day: datetime) -> tuple:
        """Analyze volume vs average"""
        bars = self.data_loader.get_bars(symbol, day, 21)
        if len(bars) < 21:
            return "NORMAL", 1.0

        current_volume = bars[-1].volume
        avg_volume = sum(b.volume for b in bars[:-1]) / 20

        if avg_volume == 0:
            return "NORMAL", 1.0

        volume_ratio = current_volume / avg_volume

        if volume_ratio < self.config.volume_reject_threshold:
            return "LOW", volume_ratio
        elif volume_ratio > self.config.volume_boost_threshold:
            return "UNUSUALLY_HIGH", volume_ratio
        elif volume_ratio > 1.5:
            return "HIGH", volume_ratio
        else:
            return "NORMAL", volume_ratio

    def _calculate_dynamic_stop(self, symbol: str, day: datetime) -> float:
        """Calculate dynamic stop loss based on volatility"""
        base_stop = self.config.stop_loss_pct

        # Get VIX (market volatility)
        vix = self._get_vix(day)

        # Calculate multiplier based on VIX
        if vix > self.config.vix_high_threshold:
            vix_multiplier = self.config.vix_high_multiplier
        elif vix < self.config.vix_low_threshold:
            vix_multiplier = self.config.vix_low_multiplier
        else:
            vix_multiplier = 1.0

        # Get symbol-specific volatility (ATR)
        symbol_vol = self._get_symbol_volatility(symbol, day)

        # Adjust for symbol volatility
        if symbol_vol > self.config.symbol_vol_threshold:
            symbol_multiplier = self.config.symbol_vol_multiplier
        else:
            symbol_multiplier = 1.0

        return base_stop * vix_multiplier * symbol_multiplier

    def _get_vix(self, day: datetime) -> float:
        """Get VIX for the day (or use default if not available)"""
        try:
            vix = self.data_loader.get_price('VIX', day)
            return vix if vix else 20.0  # Default if missing
        except:
            return 20.0  # Default VIX

    def _get_symbol_volatility(self, symbol: str, day: datetime) -> float:
        """Calculate symbol volatility (ATR / price)"""
        bars = self.data_loader.get_bars(symbol, day, 20)
        if len(bars) < 15:
            return 0.03  # Default

        # Calculate ATR
        trs = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)

        atr = sum(trs[-14:]) / 14
        current_price = bars[-1].close

        return atr / current_price if current_price > 0 else 0.03

    def _close_position(self, symbol: str, day: datetime, exit_price: float, reason: str):
        """Close a position"""
        pos = self.positions.pop(symbol)

        pnl = (exit_price - pos.entry_price) * pos.qty
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price

        self.cash += exit_price * pos.qty

        trade = Trade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.qty,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=pos.days_held,
            exit_reason=reason,
        )

        self.trades.append(trade)

        logger.info(
            f"  SELL {symbol} @ ${exit_price:.2f} | "
            f"P&L: ${pnl:+,.0f} ({pnl_pct:+.1%}) | "
            f"Reason: {reason} | Days: {pos.days_held}"
        )

    def _get_equity(self, day: datetime) -> float:
        """Calculate total equity"""
        equity = self.cash
        for symbol, pos in self.positions.items():
            current_price = self.data_loader.get_price(symbol, day)
            if current_price:
                equity += current_price * pos.qty
        return equity

    def _generate_results(self) -> Dict[str, Any]:
        """Generate backtest results"""
        final_equity = self.cash
        for pos in self.positions.values():
            final_equity += pos.qty * pos.entry_price  # Rough estimate

        total_return_pct = (final_equity - self.config.initial_capital) / self.config.initial_capital * 100

        # Calculate trade statistics
        if self.trades:
            winning_trades = [t for t in self.trades if t.pnl > 0]
            losing_trades = [t for t in self.trades if t.pnl <= 0]

            win_rate = len(winning_trades) / len(self.trades) * 100

            avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

            total_wins = sum(t.pnl for t in winning_trades)
            total_losses = abs(sum(t.pnl for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0

            avg_hold = sum(t.hold_days for t in self.trades) / len(self.trades)
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
            avg_hold = 0

        return {
            'config_name': self.config.name,
            'period': f"{self.start_date.date()} to {self.end_date.date()}",
            'performance': {
                'initial_capital': self.config.initial_capital,
                'final_equity': final_equity,
                'total_return_pct': total_return_pct,
            },
            'trades': {
                'total': len(self.trades),
                'wins': len(winning_trades) if self.trades else 0,
                'losses': len(losing_trades) if self.trades else 0,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'avg_hold_days': avg_hold,
            },
            'stats': self.stats,
        }


async def run_comparison():
    """Run comparison of all configurations"""

    # Test period: Jan-Feb 2026
    start = datetime(2026, 1, 2)
    end = datetime(2026, 2, 28)

    print("\n" + "=" * 80)
    print("BACKTEST COMPARISON: Jan-Feb 2026 (NO AI FILTER)")
    print("=" * 80)
    print(f"Period: {start.date()} to {end.date()}")
    print("Strategy: Aggressive Dip Buyer (rule-based only)")
    print("=" * 80)
    print()

    # Define configurations to test
    configs = [
        BacktestConfig(
            name="1. Baseline (Current Strategy)",
            use_dynamic_stops=False,
            use_volume_filter=False,
        ),
        BacktestConfig(
            name="2. Dynamic Stops (Conservative)",
            use_dynamic_stops=True,
            use_volume_filter=False,
            vix_high_multiplier=1.15,  # Conservative widening
            vix_low_multiplier=0.90,   # Conservative tightening
        ),
        BacktestConfig(
            name="3. Dynamic Stops (Aggressive)",
            use_dynamic_stops=True,
            use_volume_filter=False,
            vix_high_multiplier=1.25,  # More aggressive widening
            vix_low_multiplier=0.85,   # More aggressive tightening
        ),
        BacktestConfig(
            name="4. Volume Filter (Conservative)",
            use_dynamic_stops=False,
            use_volume_filter=True,
            volume_reject_threshold=0.5,  # Reject < 0.5x average
            volume_boost_threshold=999,   # Don't boost (conservative)
        ),
        BacktestConfig(
            name="5. Volume Filter (Moderate)",
            use_dynamic_stops=False,
            use_volume_filter=True,
            volume_reject_threshold=0.6,
            volume_boost_threshold=2.0,
            volume_boost_amount=0.05,
        ),
        BacktestConfig(
            name="6. Combined (Dynamic Stops + Volume Filter)",
            use_dynamic_stops=True,
            use_volume_filter=True,
            vix_high_multiplier=1.15,
            vix_low_multiplier=0.90,
            volume_reject_threshold=0.6,
            volume_boost_threshold=2.0,
            volume_boost_amount=0.05,
        ),
    ]

    results = []
    for config in configs:
        print()
        engine = ImprovementsBacktestEngine(start, end, config)
        result = await engine.run()
        results.append(result)
        print()

    # Print summary comparison
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()

    baseline_return = results[0]['performance']['total_return_pct']

    for result in results:
        perf = result['performance']
        trades_stats = result['trades']

        return_pct = perf['total_return_pct']
        improvement = return_pct - baseline_return

        print(f"{result['config_name']}")
        print(f"  Return: {return_pct:+.2f}% (vs baseline: {improvement:+.2f}%)")
        print(f"  Trades: {trades_stats['total']} | Win Rate: {trades_stats['win_rate']:.1f}%")
        print(f"  Profit Factor: {trades_stats['profit_factor']:.2f} | Avg Hold: {trades_stats['avg_hold_days']:.1f} days")

        if result['stats'].get('volume_rejections'):
            print(f"  Volume Rejections: {result['stats']['volume_rejections']}")

        print()

    # Find best configuration
    best = max(results, key=lambda x: x['performance']['total_return_pct'])
    print("=" * 80)
    print(f"🏆 BEST CONFIG: {best['config_name']}")
    print(f"   Return: {best['performance']['total_return_pct']:+.2f}%")
    print(f"   Improvement vs Baseline: {best['performance']['total_return_pct'] - baseline_return:+.2f}%")
    print("=" * 80)

    # Save results to file
    with open('backtest/results_improvements_2026_jan_feb.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print("\n✅ Results saved to: backtest/results_improvements_2026_jan_feb.json")

    return results


if __name__ == "__main__":
    asyncio.run(run_comparison())
