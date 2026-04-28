"""
Adaptive Timing Engine - Circuit Breakers for Bad Market Conditions

Key mechanisms:
1. Circuit Breaker: Stop trading after N consecutive losses
2. Cool-down Period: Wait X days after circuit breaker triggers
3. Position Scaling: Reduce size after losses, increase after wins
4. Momentum Re-check: Verify conditions before each trade
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

from backtest.daily_data import DailyDataLoader

logging.basicConfig(level=logging.WARNING)


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive timing"""
    # Basic strategy params
    initial_capital: float = 100_000.0
    base_position_size_pct: float = 0.50
    max_positions: int = 2
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.10
    trailing_stop_pct: float = 0.02
    max_hold_days: int = 4

    # Circuit breaker params
    max_consecutive_losses: int = 2  # Stop after this many consecutive losses
    cooldown_days: int = 3  # Days to wait after circuit breaker

    # Position scaling
    scale_down_after_loss: float = 0.5  # Scale factor after a loss
    scale_up_after_win: float = 1.25  # Scale factor after a win
    min_position_scale: float = 0.25  # Minimum position size multiplier
    max_position_scale: float = 1.5  # Maximum position size multiplier

    # Momentum requirements
    min_spy_momentum_3d: float = -1.0  # Minimum 3-day momentum to trade
    max_atr_pct: float = 1.8  # Maximum ATR% to trade

    # Entry requirements
    require_prev_red: bool = True
    min_day_range_pct: float = 0.02


@dataclass
class Position:
    symbol: str
    entry_date: datetime
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    trailing_stop: float
    high_since_entry: float


@dataclass
class TradeResult:
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: str


class AdaptiveTimingEngine:
    """Backtest engine with adaptive timing and circuit breakers"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: AdaptiveConfig = None,
        symbols: List[str] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or AdaptiveConfig()
        self.symbols = symbols or ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
        self.data_loader = DailyDataLoader()

        # Trading state
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[TradeResult] = []

        # Adaptive state
        self.consecutive_losses = 0
        self.cooldown_until: Optional[datetime] = None
        self.position_scale = 1.0
        self.circuit_breaker_triggered = False

        # Logging
        self.daily_log: List[Dict] = []

    async def run(self) -> Dict:
        """Run the adaptive backtest"""
        # Load data
        all_symbols = self.symbols + ['SPY']
        await self.data_loader.load(
            all_symbols,
            self.start_date - timedelta(days=35),
            self.end_date
        )

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)

        for day in trading_days:
            await self._process_day(day)

        # Close any remaining positions at end
        for symbol in list(self.positions.keys()):
            self._close_position(symbol, trading_days[-1], "END_OF_PERIOD")

        return self._generate_results()

    async def _process_day(self, date: datetime):
        """Process a single trading day"""
        log_entry = {
            'date': date,
            'cash': self.cash,
            'positions': len(self.positions),
            'consecutive_losses': self.consecutive_losses,
            'position_scale': self.position_scale,
            'circuit_breaker': self.circuit_breaker_triggered,
            'trades_today': [],
            'reason': '',
        }

        # Check cooldown
        if self.cooldown_until and date < self.cooldown_until:
            log_entry['reason'] = f"COOLDOWN until {self.cooldown_until.strftime('%Y-%m-%d')}"
            self.daily_log.append(log_entry)
            # Still need to check existing positions for stops
            await self._check_positions(date)
            return

        # Reset circuit breaker if cooldown ended
        if self.cooldown_until and date >= self.cooldown_until:
            self.cooldown_until = None
            self.circuit_breaker_triggered = False
            self.consecutive_losses = 0
            self.position_scale = 1.0  # Reset scale

        # Check market conditions
        should_trade, reason = await self._check_market_conditions(date)
        if not should_trade:
            log_entry['reason'] = reason
            self.daily_log.append(log_entry)
            await self._check_positions(date)
            return

        # Check existing positions
        await self._check_positions(date)

        # Look for new entries
        await self._check_entries(date, log_entry)

        self.daily_log.append(log_entry)

    async def _check_market_conditions(self, date: datetime) -> Tuple[bool, str]:
        """Check if market conditions are favorable"""
        spy_bars = self.data_loader.get_bars('SPY', date, 15)
        if len(spy_bars) < 10:
            return False, "Insufficient SPY data"

        closes = [b.close for b in spy_bars]
        highs = [b.high for b in spy_bars]
        lows = [b.low for b in spy_bars]

        current = closes[-1]

        # 3-day momentum
        mom_3d = (closes[-1] - closes[-4]) / closes[-4] * 100 if len(closes) >= 4 else 0

        # ATR%
        true_ranges = []
        for i in range(1, len(spy_bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        atr = np.mean(true_ranges[-10:]) if true_ranges else 0
        atr_pct = atr / current * 100

        # Check thresholds
        if mom_3d < self.config.min_spy_momentum_3d:
            return False, f"Weak momentum: {mom_3d:+.2f}% < {self.config.min_spy_momentum_3d}%"

        if atr_pct > self.config.max_atr_pct:
            return False, f"High volatility: ATR {atr_pct:.2f}% > {self.config.max_atr_pct}%"

        return True, "OK"

    async def _check_positions(self, date: datetime):
        """Check existing positions for exits"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            bars = self.data_loader.get_bars(symbol, date, 2)
            if not bars:
                continue

            current_bar = bars[-1]
            high = current_bar.high
            low = current_bar.low
            close = current_bar.close

            # Update high since entry
            if high > pos.high_since_entry:
                pos.high_since_entry = high
                # Update trailing stop
                new_trailing = high * (1 - self.config.trailing_stop_pct)
                if new_trailing > pos.trailing_stop:
                    pos.trailing_stop = new_trailing

            # Check stop loss
            if low <= pos.stop_loss:
                self._close_position(symbol, date, "STOP_LOSS", pos.stop_loss)
                continue

            # Check trailing stop
            if low <= pos.trailing_stop:
                self._close_position(symbol, date, "TRAILING_STOP", pos.trailing_stop)
                continue

            # Check take profit
            if high >= pos.take_profit:
                self._close_position(symbol, date, "TAKE_PROFIT", pos.take_profit)
                continue

            # Check max hold
            days_held = (date - pos.entry_date).days
            if days_held >= self.config.max_hold_days:
                self._close_position(symbol, date, "MAX_HOLD", close)
                continue

    def _close_position(
        self,
        symbol: str,
        date: datetime,
        reason: str,
        exit_price: float = None
    ):
        """Close a position and record the trade"""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        if exit_price is None:
            bars = self.data_loader.get_bars(symbol, date, 1)
            exit_price = bars[-1].close if bars else pos.entry_price

        pnl = (exit_price - pos.entry_price) * pos.shares
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100

        trade = TradeResult(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=date,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            shares=pos.shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        )
        self.trades.append(trade)
        self.cash += pos.shares * exit_price

        # Update adaptive state
        if pnl < 0:
            self.consecutive_losses += 1
            self.position_scale = max(
                self.config.min_position_scale,
                self.position_scale * self.config.scale_down_after_loss
            )

            # Check circuit breaker
            if self.consecutive_losses >= self.config.max_consecutive_losses:
                self.circuit_breaker_triggered = True
                self.cooldown_until = date + timedelta(days=self.config.cooldown_days)
        else:
            self.consecutive_losses = 0
            self.position_scale = min(
                self.config.max_position_scale,
                self.position_scale * self.config.scale_up_after_win
            )

        del self.positions[symbol]

    async def _check_entries(self, date: datetime, log_entry: Dict):
        """Look for new entry opportunities"""
        if len(self.positions) >= self.config.max_positions:
            return

        if self.circuit_breaker_triggered:
            log_entry['reason'] = "Circuit breaker active"
            return

        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            bars = self.data_loader.get_bars(symbol, date, 5)
            if len(bars) < 3:
                continue

            current_bar = bars[-1]
            prev_bar = bars[-2]

            # Check if previous day was red (if required)
            if self.config.require_prev_red:
                prev_return = (prev_bar.close - prev_bar.open) / prev_bar.open
                if prev_return >= 0:
                    continue

            # Check minimum daily range
            day_range = (current_bar.high - current_bar.low) / current_bar.low
            if day_range < self.config.min_day_range_pct:
                continue

            # Entry signal: buying on dip
            entry_price = current_bar.close

            # Calculate position size with scaling
            scaled_size_pct = self.config.base_position_size_pct * self.position_scale
            position_value = self.cash * scaled_size_pct
            shares = int(position_value / entry_price)

            if shares < 1:
                continue

            # Create position
            pos = Position(
                symbol=symbol,
                entry_date=date,
                entry_price=entry_price,
                shares=shares,
                stop_loss=entry_price * (1 - self.config.stop_loss_pct),
                take_profit=entry_price * (1 + self.config.take_profit_pct),
                trailing_stop=entry_price * (1 - self.config.trailing_stop_pct),
                high_since_entry=current_bar.high,
            )

            self.positions[symbol] = pos
            self.cash -= shares * entry_price

            log_entry['trades_today'].append({
                'symbol': symbol,
                'action': 'BUY',
                'price': entry_price,
                'shares': shares,
                'scale': self.position_scale,
            })

    def _generate_results(self) -> Dict:
        """Generate backtest results"""
        total_pnl = sum(t.pnl for t in self.trades)
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        # Count circuit breaker triggers
        cb_triggers = sum(1 for log in self.daily_log if log.get('circuit_breaker', False))

        return {
            'performance': {
                'initial_capital': self.config.initial_capital,
                'final_value': self.config.initial_capital + total_pnl,
                'total_return': total_pnl,
                'total_return_pct': total_pnl / self.config.initial_capital * 100,
            },
            'trades': {
                'total': len(self.trades),
                'winners': len(winning_trades),
                'losers': len(losing_trades),
                'win_rate': len(winning_trades) / len(self.trades) * 100 if self.trades else 0,
                'avg_win': np.mean([t.pnl for t in winning_trades]) if winning_trades else 0,
                'avg_loss': np.mean([t.pnl for t in losing_trades]) if losing_trades else 0,
            },
            'adaptive': {
                'circuit_breaker_triggers': cb_triggers,
                'cooldown_days_total': cb_triggers * self.config.cooldown_days,
            },
            'trade_list': self.trades,
            'daily_log': self.daily_log,
        }


async def compare_adaptive_vs_basic():
    """Compare adaptive timing vs basic approach"""
    from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
    ]

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    print(f"\n{'='*100}")
    print(f"ADAPTIVE TIMING vs BASIC STRATEGY")
    print(f"Circuit Breaker: Stop after 2 consecutive losses, cooldown 3 days")
    print(f"Position Scaling: 0.5x after loss, 1.25x after win")
    print(f"Market Check: SPY 3d momentum > -1.0%, ATR < 1.8%")
    print(f"{'='*100}")

    loader = DailyDataLoader()

    print(f"\n{'Period':<12} | {'SPY':>8} | {'Basic':>10} | {'Adaptive':>10} | {'Improvement':>12} | {'CB Triggers':>11}")
    print("-" * 85)

    total_spy = 0
    total_basic = 0
    total_adaptive = 0

    for start, end, name in periods:
        # SPY return
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

        # Basic strategy
        basic_config = AggressiveBacktestConfig(
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,
        )
        basic_engine = AggressiveBacktestEngine(start, end, basic_config, symbols=symbols)
        basic_results = await basic_engine.run()
        basic_return = basic_results['performance']['total_return_pct']

        # Adaptive strategy
        adaptive_config = AdaptiveConfig(
            base_position_size_pct=0.50,
            max_positions=2,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            max_consecutive_losses=2,
            cooldown_days=3,
            min_spy_momentum_3d=-1.0,
            max_atr_pct=1.8,
        )
        adaptive_engine = AdaptiveTimingEngine(start, end, adaptive_config, symbols=symbols)
        adaptive_results = await adaptive_engine.run()
        adaptive_return = adaptive_results['performance']['total_return_pct']
        cb_triggers = adaptive_results['adaptive']['circuit_breaker_triggers']

        improvement = adaptive_return - basic_return

        print(
            f"{name:<12} | {spy_return:>+7.2f}% | {basic_return:>+9.2f}% | "
            f"{adaptive_return:>+9.2f}% | {improvement:>+11.2f}% | {cb_triggers:>11}"
        )

        total_spy += spy_return
        total_basic += basic_return
        total_adaptive += adaptive_return

    print("-" * 85)
    avg_spy = total_spy / len(periods)
    avg_basic = total_basic / len(periods)
    avg_adaptive = total_adaptive / len(periods)
    avg_improvement = avg_adaptive - avg_basic

    print(
        f"{'AVERAGE':<12} | {avg_spy:>+7.2f}% | {avg_basic:>+9.2f}% | "
        f"{avg_adaptive:>+9.2f}% | {avg_improvement:>+11.2f}% |"
    )

    print(f"\n📊 SUMMARY:")
    print(f"   Basic alpha vs SPY:    {avg_basic - avg_spy:+.2f}%")
    print(f"   Adaptive alpha vs SPY: {avg_adaptive - avg_spy:+.2f}%")

    if avg_adaptive > avg_basic:
        print(f"\n   ✅ Adaptive timing IMPROVES returns by {avg_improvement:+.2f}%")
    else:
        print(f"\n   ❌ Adaptive timing REDUCES returns by {avg_improvement:.2f}%")


async def analyze_november_with_adaptive():
    """Detailed November analysis with adaptive timing"""

    print(f"\n{'='*100}")
    print(f"NOVEMBER 2025 - DETAILED ADAPTIVE ANALYSIS")
    print(f"{'='*100}")

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    adaptive_config = AdaptiveConfig(
        base_position_size_pct=0.50,
        max_positions=2,
        stop_loss_pct=0.02,
        take_profit_pct=0.10,
        trailing_stop_pct=0.02,
        max_hold_days=4,
        max_consecutive_losses=2,
        cooldown_days=3,
        min_spy_momentum_3d=-1.0,
        max_atr_pct=1.8,
    )

    engine = AdaptiveTimingEngine(
        datetime(2025, 11, 1),
        datetime(2025, 11, 30),
        adaptive_config,
        symbols=symbols
    )
    results = await engine.run()

    print(f"\n📈 PERFORMANCE:")
    print(f"   Total Return: {results['performance']['total_return_pct']:+.2f}%")
    print(f"   Trades: {results['trades']['total']}")
    print(f"   Win Rate: {results['trades']['win_rate']:.1f}%")
    print(f"   Circuit Breakers: {results['adaptive']['circuit_breaker_triggers']}")

    print(f"\n📋 TRADES:")
    for trade in results['trade_list']:
        marker = "✅" if trade.pnl > 0 else "❌"
        print(
            f"   {marker} {trade.symbol:<5} "
            f"{trade.entry_date.strftime('%m/%d')} → {trade.exit_date.strftime('%m/%d')} | "
            f"${trade.entry_price:.2f} → ${trade.exit_price:.2f} | "
            f"{trade.pnl_pct:+.2f}% | {trade.exit_reason}"
        )

    print(f"\n📊 DAILY LOG (key events):")
    for log in results['daily_log']:
        if log.get('circuit_breaker') or log.get('trades_today') or 'COOLDOWN' in log.get('reason', ''):
            marker = "🛑" if log.get('circuit_breaker') else ("⏸️" if 'COOLDOWN' in log.get('reason', '') else "📈")
            print(
                f"   {marker} {log['date'].strftime('%Y-%m-%d')} | "
                f"Scale: {log['position_scale']:.2f}x | "
                f"Losses: {log['consecutive_losses']} | "
                f"{log.get('reason', 'Trading')}"
            )


if __name__ == "__main__":
    asyncio.run(compare_adaptive_vs_basic())
    asyncio.run(analyze_november_with_adaptive())
