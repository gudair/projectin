"""
Aggressive Dip Buyer Backtest Engine

Tests the aggressive strategy with:
- Market regime filtering
- Trailing stops
- Concentrated positions
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from backtest.daily_data import DailyDataLoader, DailyBar
from agent.strategies.aggressive_dip import AggressiveDipStrategy, AggressiveDipConfig, AggressiveSignal

logger = logging.getLogger(__name__)


@dataclass
class AggressivePosition:
    symbol: str
    qty: float
    entry_price: float
    entry_date: datetime
    stop_loss: float
    take_profit: float
    trailing_stop_pct: float
    high_since_entry: float  # For trailing stop


@dataclass
class AggressiveTrade:
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
    market_regime: str


@dataclass
class AggressiveBacktestConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 3  # Concentrated
    position_size_pct: float = 0.25  # 25% per position

    # Strategy params
    min_prev_day_drop: float = -0.015
    min_day_range: float = 0.025
    max_rsi: float = 40.0
    stop_loss_pct: float = 0.025
    take_profit_pct: float = 0.15
    trailing_stop_pct: float = 0.03
    max_hold_days: int = 5
    require_bullish_market: bool = True


class AggressiveBacktestEngine:
    """Backtest engine for aggressive dip buyer strategy"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: AggressiveBacktestConfig = None,
        symbols: List[str] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or AggressiveBacktestConfig()

        # Focus on high-beta symbols only
        self.symbols = symbols or [
            'AMD', 'NVDA', 'MU', 'MRVL',
            'TSLA', 'META', 'NFLX',
            'COIN', 'SQ', 'SHOP',
        ]

        self.data_loader = DailyDataLoader()
        self.strategy = AggressiveDipStrategy(AggressiveDipConfig(
            min_prev_day_drop=self.config.min_prev_day_drop,
            min_day_range=self.config.min_day_range,
            max_rsi=self.config.max_rsi,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            trailing_stop_pct=self.config.trailing_stop_pct,
            max_hold_days=self.config.max_hold_days,
            max_positions=self.config.max_positions,
            position_size_pct=self.config.position_size_pct,
            require_bullish_market=self.config.require_bullish_market,
        ))

        # State
        self.cash = self.config.initial_capital
        self.positions: Dict[str, AggressivePosition] = {}
        self.trades: List[AggressiveTrade] = []
        self.daily_equity: List[Dict] = []
        self.spy_closes: List[float] = []

        self.stats = {
            'signals_generated': 0,
            'buy_signals': 0,
            'filtered_by_regime': 0,
            'trades_executed': 0,
            'trailing_stop_exits': 0,
            'stop_loss_exits': 0,
            'take_profit_exits': 0,
        }

    async def run(self) -> Dict[str, Any]:
        """Run backtest"""
        logger.info(f"Starting Aggressive Dip Buyer Backtest")
        logger.info(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info(f"Position size: {self.config.position_size_pct:.0%}")
        logger.info(f"Max positions: {self.config.max_positions}")

        # Load data including SPY for regime detection
        load_start = self.start_date - timedelta(days=30)
        all_symbols = self.symbols + ['SPY']
        await self.data_loader.load(all_symbols, load_start, self.end_date)

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)
        logger.info(f"Trading days: {len(trading_days)}")

        if not trading_days:
            return self._generate_results()

        for i, day in enumerate(trading_days):
            await self._process_day(day)

            if (i + 1) % 5 == 0:
                equity = self._get_equity(day)
                pnl = equity - self.config.initial_capital
                regime = self._get_market_regime(day)
                logger.info(
                    f"Day {i+1}/{len(trading_days)}: Equity ${equity:,.0f} ({pnl:+,.0f}) | "
                    f"Regime: {regime} | Positions: {len(self.positions)}"
                )

        # Close remaining positions
        if self.positions:
            last_day = trading_days[-1]
            for symbol in list(self.positions.keys()):
                await self._close_position(symbol, last_day, "backtest_end", "N/A")

        return self._generate_results()

    def _get_equity(self, date: datetime) -> float:
        equity = self.cash
        for symbol, pos in self.positions.items():
            price = self.data_loader.get_price(symbol, date)
            if price:
                equity += pos.qty * price
        return equity

    def _get_market_regime(self, date: datetime) -> str:
        """Get market regime for a date"""
        spy_bars = self.data_loader.get_bars('SPY', date, 15)
        if len(spy_bars) < 15:
            return 'NEUTRAL'
        spy_closes = [b.close for b in spy_bars]
        return self.strategy.detect_market_regime(spy_closes, 10)

    async def _process_day(self, day: datetime):
        """Process a trading day"""
        equity = self._get_equity(day)
        self.daily_equity.append({
            'date': day.isoformat(),
            'equity': equity,
        })

        # Update SPY closes for regime detection
        spy_bars = self.data_loader.get_bars('SPY', day, 20)
        spy_closes = [b.close for b in spy_bars] if spy_bars else []

        # Check exits first (using high/low for realistic simulation)
        for symbol in list(self.positions.keys()):
            await self._check_exit(symbol, day)

        # Check entries
        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            await self._check_entry(symbol, day, spy_closes)

    async def _check_exit(self, symbol: str, day: datetime):
        """Check position for exit with trailing stop logic"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        bar = self.data_loader.get_bar(symbol, day)
        if not bar:
            return

        market_regime = self._get_market_regime(day)

        # Update high since entry (for trailing stop)
        if bar.high > pos.high_since_entry:
            pos.high_since_entry = bar.high

        # Check stop loss (using low)
        if bar.low <= pos.stop_loss:
            await self._close_position_at_price(
                symbol, day, pos.stop_loss,
                f"Stop loss (low ${bar.low:.2f})", market_regime
            )
            self.stats['stop_loss_exits'] += 1
            return

        # Check trailing stop (if we've had gains)
        if pos.high_since_entry > pos.entry_price:
            trailing_stop = pos.high_since_entry * (1 - pos.trailing_stop_pct)
            if bar.low <= trailing_stop:
                exit_price = max(trailing_stop, bar.low)
                await self._close_position_at_price(
                    symbol, day, exit_price,
                    f"Trailing stop (high: ${pos.high_since_entry:.2f})", market_regime
                )
                self.stats['trailing_stop_exits'] += 1
                return

        # Check take profit (using high)
        if bar.high >= pos.take_profit:
            await self._close_position_at_price(
                symbol, day, pos.take_profit,
                f"Take profit (high ${bar.high:.2f})", market_regime
            )
            self.stats['take_profit_exits'] += 1
            return

        # Check max hold
        hold_days = (day - pos.entry_date).days
        if hold_days >= self.config.max_hold_days:
            await self._close_position(symbol, day, f"Max hold ({hold_days}d)", market_regime)

    async def _check_entry(self, symbol: str, day: datetime, spy_closes: List[float]):
        """Check for entry signal"""
        bars = self.data_loader.get_bars(symbol, day, 20)
        if len(bars) < 15:
            return

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        signal = self.strategy.generate_signal(
            symbol=symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            spy_closes=spy_closes,
            has_position=False,
        )

        self.stats['signals_generated'] += 1

        if signal.action == 'BUY' and signal.confidence >= 0.7:
            self.stats['buy_signals'] += 1
            await self._open_position(symbol, day, signal)

    async def _open_position(self, symbol: str, day: datetime, signal: AggressiveSignal):
        """Open a position"""
        price = signal.entry_price
        position_value = self.cash * self.config.position_size_pct

        if position_value > self.cash:
            return

        qty = position_value / price

        self.positions[symbol] = AggressivePosition(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            entry_date=day,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            trailing_stop_pct=signal.trailing_stop_pct,
            high_since_entry=price,  # Start with entry price
        )

        self.cash -= position_value
        self.stats['trades_executed'] += 1

        logger.debug(
            f"BUY {symbol}: {qty:.2f} @ ${price:.2f} | "
            f"{signal.reasoning}"
        )

    async def _close_position(self, symbol: str, day: datetime, reason: str, market_regime: str):
        """Close position at close price"""
        price = self.data_loader.get_price(symbol, day)
        if price:
            await self._close_position_at_price(symbol, day, price, reason, market_regime)

    async def _close_position_at_price(
        self, symbol: str, day: datetime, price: float, reason: str, market_regime: str
    ):
        """Close position at specific price"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        pnl = (price - pos.entry_price) * pos.qty
        pnl_pct = (price - pos.entry_price) / pos.entry_price
        hold_days = (day - pos.entry_date).days

        self.trades.append(AggressiveTrade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=price,
            qty=pos.qty,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
            exit_reason=reason,
            market_regime=market_regime,
        ))

        self.cash += pos.qty * price
        del self.positions[symbol]

        logger.debug(f"SELL {symbol} @ ${price:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1%}) | {reason}")

    def _generate_results(self) -> Dict[str, Any]:
        """Generate results"""
        final_equity = self.cash
        for pos in self.positions.values():
            final_equity += pos.qty * pos.entry_price

        total_return = final_equity - self.config.initial_capital
        total_return_pct = total_return / self.config.initial_capital * 100

        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]

        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0
        avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0
        avg_loss = sum(t.pnl for t in losing) / len(losing) if losing else 0
        avg_win_pct = sum(t.pnl_pct for t in winning) / len(winning) * 100 if winning else 0
        avg_loss_pct = sum(t.pnl_pct for t in losing) / len(losing) * 100 if losing else 0

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999

        # Max drawdown
        max_dd = 0
        peak = self.config.initial_capital
        for day in self.daily_equity:
            eq = day['equity']
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Best and worst trades
        best_trade = max(self.trades, key=lambda t: t.pnl_pct) if self.trades else None
        worst_trade = min(self.trades, key=lambda t: t.pnl_pct) if self.trades else None

        return {
            'performance': {
                'final_equity': final_equity,
                'total_return': total_return,
                'total_return_pct': total_return_pct,
                'max_drawdown_pct': max_dd,
            },
            'trades': {
                'total': len(self.trades),
                'winning': len(winning),
                'losing': len(losing),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'avg_win_pct': avg_win_pct,
                'avg_loss_pct': avg_loss_pct,
                'profit_factor': profit_factor,
                'best_trade': {
                    'symbol': best_trade.symbol,
                    'pnl_pct': best_trade.pnl_pct * 100,
                    'pnl': best_trade.pnl,
                } if best_trade else None,
                'worst_trade': {
                    'symbol': worst_trade.symbol,
                    'pnl_pct': worst_trade.pnl_pct * 100,
                    'pnl': worst_trade.pnl,
                } if worst_trade else None,
            },
            'exits': {
                'stop_loss': self.stats['stop_loss_exits'],
                'trailing_stop': self.stats['trailing_stop_exits'],
                'take_profit': self.stats['take_profit_exits'],
            },
            'stats': self.stats,
            'trade_list': [
                {
                    'symbol': t.symbol,
                    'entry_date': t.entry_date.isoformat(),
                    'exit_date': t.exit_date.isoformat(),
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                    'hold_days': t.hold_days,
                    'exit_reason': t.exit_reason,
                    'market_regime': t.market_regime,
                }
                for t in self.trades
            ],
        }


async def run_aggressive_backtest(
    start_date: datetime,
    end_date: datetime,
    config: AggressiveBacktestConfig = None,
) -> Dict[str, Any]:
    """Run aggressive dip buyer backtest"""
    engine = AggressiveBacktestEngine(start_date, end_date, config)
    return await engine.run()


async def compare_with_spy(
    start_date: datetime,
    end_date: datetime,
) -> None:
    """Compare aggressive strategy with SPY"""
    from backtest.daily_data import DailyDataLoader

    print(f"\n{'='*70}")
    print(f"AGGRESSIVE DIP BUYER vs SPY")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"{'='*70}")

    # Run aggressive backtest
    results = await run_aggressive_backtest(start_date, end_date)

    # Get SPY return
    loader = DailyDataLoader()
    await loader.load(['SPY'], start_date - timedelta(days=5), end_date)
    spy_start = loader.get_price('SPY', start_date)
    spy_end = loader.get_price('SPY', end_date)
    spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start else 0

    perf = results['performance']
    trades = results['trades']
    exits = results['exits']

    print(f"\n📊 RESULTS:")
    print(f"   Aggressive Return: {perf['total_return_pct']:+.2f}%")
    print(f"   SPY Return:        {spy_return:+.2f}%")
    print(f"   Alpha:             {perf['total_return_pct'] - spy_return:+.2f}%")

    print(f"\n📈 TRADE STATS:")
    print(f"   Trades: {trades['total']} (Win: {trades['winning']}, Loss: {trades['losing']})")
    print(f"   Win Rate: {trades['win_rate']:.1f}%")
    print(f"   Avg Win: {trades['avg_win_pct']:+.1f}% | Avg Loss: {trades['avg_loss_pct']:+.1f}%")
    print(f"   Profit Factor: {trades['profit_factor']:.2f}")
    print(f"   Max Drawdown: {perf['max_drawdown_pct']:.1f}%")

    print(f"\n🚪 EXIT TYPES:")
    print(f"   Stop Loss: {exits['stop_loss']}")
    print(f"   Trailing Stop: {exits['trailing_stop']}")
    print(f"   Take Profit: {exits['take_profit']}")

    if trades['best_trade']:
        print(f"\n🏆 BEST TRADE: {trades['best_trade']['symbol']} +{trades['best_trade']['pnl_pct']:.1f}%")
    if trades['worst_trade']:
        print(f"💀 WORST TRADE: {trades['worst_trade']['symbol']} {trades['worst_trade']['pnl_pct']:.1f}%")

    winner = "AGGRESSIVE" if perf['total_return_pct'] > spy_return else "SPY"
    print(f"\n🏁 WINNER: {winner}")

    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    async def main():
        # Test October 2025
        start = datetime(2025, 10, 1)
        end = datetime(2025, 10, 31)

        await compare_with_spy(start, end)

    asyncio.run(main())
