"""
Weekly Circuit Breaker Strategy

Instead of a global circuit breaker, use a weekly reset:
- Stop trading for the rest of the WEEK after N consecutive losses
- Reset at the start of each new week
- This protects against terrible weeks without affecting good weeks
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np

from backtest.daily_data import DailyDataLoader


@dataclass
class WeeklyConfig:
    """Configuration for weekly circuit breaker strategy"""
    initial_capital: float = 100_000.0
    position_size_pct: float = 0.50
    max_positions: int = 2
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.10
    trailing_stop_pct: float = 0.02
    max_hold_days: int = 4

    # Weekly circuit breaker
    max_weekly_losses: int = 2  # Stop for rest of week after this many losses
    require_prev_red: bool = True


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
    week_num: int


class WeeklyCircuitBreakerEngine:
    """Backtest engine with weekly circuit breaker"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: WeeklyConfig = None,
        symbols: List[str] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or WeeklyConfig()
        self.symbols = symbols or ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
        self.data_loader = DailyDataLoader()

        # State
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[TradeResult] = []

        # Weekly tracking
        self.current_week = None
        self.weekly_losses = 0
        self.weekly_cb_triggered = False

    async def run(self) -> Dict:
        """Run the backtest"""
        all_symbols = self.symbols + ['SPY']
        await self.data_loader.load(
            all_symbols,
            self.start_date - timedelta(days=35),
            self.end_date
        )

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)

        for day in trading_days:
            await self._process_day(day)

        # Close remaining positions
        for symbol in list(self.positions.keys()):
            self._close_position(symbol, trading_days[-1], "END_OF_PERIOD")

        return self._generate_results()

    async def _process_day(self, date: datetime):
        """Process a single day"""
        week_num = date.isocalendar()[1]

        # Check for new week - reset circuit breaker
        if week_num != self.current_week:
            self.current_week = week_num
            self.weekly_losses = 0
            self.weekly_cb_triggered = False

        # Check existing positions (always, even if CB triggered)
        await self._check_positions(date)

        # Check for new entries (only if CB not triggered)
        if not self.weekly_cb_triggered:
            await self._check_entries(date)

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

            # Update trailing stop
            if high > pos.high_since_entry:
                pos.high_since_entry = high
                new_trailing = high * (1 - self.config.trailing_stop_pct)
                if new_trailing > pos.trailing_stop:
                    pos.trailing_stop = new_trailing

            # Check exits
            if low <= pos.stop_loss:
                self._close_position(symbol, date, "STOP_LOSS", pos.stop_loss)
            elif low <= pos.trailing_stop:
                self._close_position(symbol, date, "TRAILING_STOP", pos.trailing_stop)
            elif high >= pos.take_profit:
                self._close_position(symbol, date, "TAKE_PROFIT", pos.take_profit)
            elif (date - pos.entry_date).days >= self.config.max_hold_days:
                self._close_position(symbol, date, "MAX_HOLD", close)

    def _close_position(self, symbol: str, date: datetime, reason: str, exit_price: float = None):
        """Close position and update weekly tracking"""
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
            week_num=self.current_week,
        )
        self.trades.append(trade)
        self.cash += pos.shares * exit_price

        # Update weekly loss count
        if pnl < 0:
            self.weekly_losses += 1
            if self.weekly_losses >= self.config.max_weekly_losses:
                self.weekly_cb_triggered = True

        del self.positions[symbol]

    async def _check_entries(self, date: datetime):
        """Look for entry opportunities"""
        if len(self.positions) >= self.config.max_positions:
            return

        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            bars = self.data_loader.get_bars(symbol, date, 3)
            if len(bars) < 2:
                continue

            current_bar = bars[-1]
            prev_bar = bars[-2]

            # Check prev day red requirement
            if self.config.require_prev_red:
                if prev_bar.close >= prev_bar.open:
                    continue

            entry_price = current_bar.close
            position_value = self.cash * self.config.position_size_pct
            shares = int(position_value / entry_price)

            if shares < 1:
                continue

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

    def _generate_results(self) -> Dict:
        """Generate results"""
        total_pnl = sum(t.pnl for t in self.trades)
        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl <= 0]

        # Count CB triggers by week
        weeks_with_cb = set()
        loss_count_by_week = {}
        for t in self.trades:
            if t.pnl < 0:
                loss_count_by_week[t.week_num] = loss_count_by_week.get(t.week_num, 0) + 1
                if loss_count_by_week[t.week_num] >= self.config.max_weekly_losses:
                    weeks_with_cb.add(t.week_num)

        return {
            'performance': {
                'initial_capital': self.config.initial_capital,
                'final_value': self.config.initial_capital + total_pnl,
                'total_return': total_pnl,
                'total_return_pct': total_pnl / self.config.initial_capital * 100,
            },
            'trades': {
                'total': len(self.trades),
                'winners': len(winning),
                'losers': len(losing),
                'win_rate': len(winning) / len(self.trades) * 100 if self.trades else 0,
            },
            'circuit_breaker': {
                'weeks_triggered': len(weeks_with_cb),
                'weeks_list': sorted(weeks_with_cb),
            },
            'trade_list': self.trades,
        }


async def compare_weekly_cb():
    """Compare weekly circuit breaker vs basic"""
    from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
    loader = DailyDataLoader()

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
    ]

    print(f"\n{'='*100}")
    print(f"WEEKLY CIRCUIT BREAKER vs BASIC")
    print(f"Stop trading for rest of week after 2 consecutive losses, then reset next week")
    print(f"{'='*100}")

    print(f"\n{'Period':<12} | {'SPY':>8} | {'Basic':>10} | {'Weekly CB':>10} | {'Winner':>10} | {'CB Weeks':>10}")
    print("-" * 80)

    total_basic = 0
    total_weekly = 0

    for start, end, name in periods:
        # SPY
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

        # Basic
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

        # Weekly CB
        weekly_config = WeeklyConfig(
            position_size_pct=0.50,
            max_positions=2,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            max_weekly_losses=2,
        )
        weekly_engine = WeeklyCircuitBreakerEngine(start, end, weekly_config, symbols=symbols)
        weekly_results = await weekly_engine.run()
        weekly_return = weekly_results['performance']['total_return_pct']
        cb_weeks = weekly_results['circuit_breaker']['weeks_triggered']

        winner = "WEEKLY CB" if weekly_return > basic_return else "BASIC"

        total_basic += basic_return
        total_weekly += weekly_return

        print(
            f"{name:<12} | {spy_return:>+7.2f}% | {basic_return:>+9.2f}% | "
            f"{weekly_return:>+9.2f}% | {winner:>10} | {cb_weeks:>10}"
        )

    print("-" * 80)
    avg_basic = total_basic / len(periods)
    avg_weekly = total_weekly / len(periods)

    print(
        f"{'AVERAGE':<12} | {'':>8} | {avg_basic:>+9.2f}% | "
        f"{avg_weekly:>+9.2f}% | {'':>10} |"
    )

    if avg_weekly > avg_basic:
        print(f"\n✅ Weekly CB IMPROVES returns by {avg_weekly - avg_basic:+.2f}%")
    else:
        print(f"\n❌ Weekly CB REDUCES returns by {avg_weekly - avg_basic:.2f}%")

    # Test different thresholds
    print(f"\n{'='*100}")
    print(f"TESTING DIFFERENT WEEKLY LOSS THRESHOLDS")
    print(f"{'='*100}")

    for max_losses in [1, 2, 3, 4]:
        total = 0
        for start, end, _ in periods:
            config = WeeklyConfig(
                max_weekly_losses=max_losses,
            )
            engine = WeeklyCircuitBreakerEngine(start, end, config, symbols=symbols)
            results = await engine.run()
            total += results['performance']['total_return_pct']

        avg = total / len(periods)
        diff = avg - avg_basic
        marker = "✅" if diff > 0 else "❌"
        print(f"   Max {max_losses} losses/week: {avg:+.2f}% ({diff:+.2f}% vs basic) {marker}")


async def detailed_november_analysis():
    """Show detailed November analysis with weekly CB"""

    print(f"\n{'='*100}")
    print(f"NOVEMBER DETAILED ANALYSIS WITH WEEKLY CB")
    print(f"{'='*100}")

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    config = WeeklyConfig(
        position_size_pct=0.50,
        max_positions=2,
        stop_loss_pct=0.02,
        take_profit_pct=0.10,
        trailing_stop_pct=0.02,
        max_hold_days=4,
        max_weekly_losses=2,
    )

    engine = WeeklyCircuitBreakerEngine(
        datetime(2025, 11, 1),
        datetime(2025, 11, 30),
        config,
        symbols=symbols
    )
    results = await engine.run()

    print(f"\n📈 PERFORMANCE:")
    print(f"   Total Return: {results['performance']['total_return_pct']:+.2f}%")
    print(f"   Trades: {results['trades']['total']}")
    print(f"   Win Rate: {results['trades']['win_rate']:.1f}%")
    print(f"   CB Triggered Weeks: {results['circuit_breaker']['weeks_list']}")

    # Group trades by week
    by_week = {}
    for trade in results['trade_list']:
        week = trade.week_num
        if week not in by_week:
            by_week[week] = []
        by_week[week].append(trade)

    print(f"\n📅 TRADES BY WEEK:")
    for week in sorted(by_week.keys()):
        trades = by_week[week]
        week_pnl = sum(t.pnl for t in trades)
        wins = sum(1 for t in trades if t.pnl > 0)
        losses = sum(1 for t in trades if t.pnl <= 0)

        cb_marker = "🛑" if week in results['circuit_breaker']['weeks_list'] else ""
        print(f"\n   Week {week} {cb_marker}")
        print(f"   Trades: {len(trades)} | W/L: {wins}/{losses} | P&L: ${week_pnl:+,.0f}")

        for t in trades:
            marker = "✅" if t.pnl > 0 else "❌"
            print(
                f"      {marker} {t.symbol:<5} {t.entry_date.strftime('%m/%d')} | "
                f"{t.pnl_pct:+.2f}% | {t.exit_reason}"
            )


if __name__ == "__main__":
    asyncio.run(compare_weekly_cb())
    asyncio.run(detailed_november_analysis())
