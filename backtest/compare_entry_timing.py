"""
Entry Timing Comparison Backtest

Compare:
1. ONCE PER DAY: Entry check only at close (current behavior)
2. HOURLY: Entry checks throughout the day (more opportunities)

Using the same symbols and parameters, only changing entry frequency.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass
import numpy as np

from backtest.daily_data import DailyDataLoader, DailyBar
from agent.strategies.aggressive_dip import AggressiveDipStrategy, AggressiveDipConfig

logging.basicConfig(level=logging.WARNING)


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


@dataclass
class Trade:
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    pnl_pct: float
    exit_reason: str


class EntryTimingBacktest:
    """
    Backtest with configurable entry timing.

    For daily data, we simulate intraday by:
    - ONCE_DAILY: Can only enter on days after a red day (standard)
    - HOURLY: Can enter multiple times if conditions reset

    Since we only have daily bars, "hourly" means we check
    multiple times during the day using high/low variations.
    """

    def __init__(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        entry_mode: str = "once_daily",  # "once_daily" or "hourly"
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.entry_mode = entry_mode

        self.config = AggressiveDipConfig(
            min_prev_day_drop=-0.01,
            min_day_range=0.02,
            max_rsi=45.0,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            max_positions=2,
            position_size_pct=0.50,
            require_bullish_market=False,
        )

        self.strategy = AggressiveDipStrategy(self.config)
        self.data_loader = DailyDataLoader()

        # State
        self.initial_capital = 100_000.0
        self.cash = self.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []

    async def run(self) -> Dict[str, Any]:
        """Run backtest"""
        load_start = self.start_date - timedelta(days=30)
        await self.data_loader.load(
            self.symbols + ['SPY'],
            load_start,
            self.end_date
        )

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)

        for day in trading_days:
            self._process_day(day)

        # Close remaining positions
        if self.positions:
            last_day = trading_days[-1]
            for symbol in list(self.positions.keys()):
                self._close_position(symbol, last_day, "backtest_end")

        return self._generate_results()

    def _process_day(self, day: datetime):
        """Process a single trading day"""

        # Get SPY data for regime (not used but kept for compatibility)
        spy_bars = self.data_loader.get_bars('SPY', day, 20)
        spy_closes = [b.close for b in spy_bars] if spy_bars else []

        # Check exits first
        for symbol in list(self.positions.keys()):
            self._check_exit(symbol, day)

        # Check entries based on mode
        if self.entry_mode == "once_daily":
            # Standard: one entry check per day at close
            self._check_entries_once(day, spy_closes)
        else:
            # Hourly: simulate multiple entry opportunities
            # With daily data, we simulate this by allowing entry
            # if price dips intraday (using low) even if close recovers
            self._check_entries_hourly(day, spy_closes)

    def _check_entries_once(self, day: datetime, spy_closes: List[float]):
        """Standard once-daily entry check at close"""
        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            bars = self.data_loader.get_bars(symbol, day, 20)
            if len(bars) < 15:
                continue

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

            if signal.action == 'BUY' and signal.confidence >= 0.7:
                self._open_position(symbol, day, signal.entry_price, signal)

    def _check_entries_hourly(self, day: datetime, spy_closes: List[float]):
        """
        Simulate hourly entry checks with daily data.

        Key difference: We can enter at intraday lows, not just close.
        This simulates catching dips during the day.
        """
        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            bars = self.data_loader.get_bars(symbol, day, 20)
            if len(bars) < 15:
                continue

            today_bar = bars[-1]
            prev_bar = bars[-2]

            # Check if previous day was red
            prev_return = (prev_bar.close - prev_bar.open) / prev_bar.open
            if prev_return >= self.config.min_prev_day_drop:
                continue

            # Check intraday range
            day_range = (today_bar.high - today_bar.low) / today_bar.close
            if day_range < self.config.min_day_range:
                continue

            # Calculate RSI
            closes = [b.close for b in bars]
            rsi = self.strategy.calculate_rsi(closes)
            if rsi > self.config.max_rsi:
                continue

            # HOURLY ADVANTAGE: Enter at low instead of close
            # This simulates catching the dip during the day
            entry_price = today_bar.low + (today_bar.close - today_bar.low) * 0.3

            # Create signal manually
            stop_loss = entry_price * (1 - self.config.stop_loss_pct)
            take_profit = entry_price * (1 + self.config.take_profit_pct)

            self._open_position(symbol, day, entry_price, None, stop_loss, take_profit)

    def _open_position(
        self,
        symbol: str,
        day: datetime,
        price: float,
        signal=None,
        stop_loss: float = None,
        take_profit: float = None,
    ):
        """Open a position"""
        position_value = self.cash * self.config.position_size_pct
        if position_value > self.cash or position_value < 100:
            return

        qty = position_value / price

        if signal:
            sl = signal.stop_loss
            tp = signal.take_profit
        else:
            sl = stop_loss or price * 0.98
            tp = take_profit or price * 1.10

        self.positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            entry_date=day,
            stop_loss=sl,
            take_profit=tp,
            trailing_stop_pct=self.config.trailing_stop_pct,
            high_since_entry=price,
        )

        self.cash -= position_value

    def _check_exit(self, symbol: str, day: datetime):
        """Check position for exit"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        bar = self.data_loader.get_bar(symbol, day)
        if not bar:
            return

        # Update high
        if bar.high > pos.high_since_entry:
            pos.high_since_entry = bar.high

        # Stop loss
        if bar.low <= pos.stop_loss:
            self._close_position(symbol, day, "stop_loss", pos.stop_loss)
            return

        # Trailing stop
        if pos.high_since_entry > pos.entry_price:
            trailing_stop = pos.high_since_entry * (1 - pos.trailing_stop_pct)
            if bar.low <= trailing_stop:
                self._close_position(symbol, day, "trailing_stop", trailing_stop)
                return

        # Take profit
        if bar.high >= pos.take_profit:
            self._close_position(symbol, day, "take_profit", pos.take_profit)
            return

        # Max hold
        hold_days = (day - pos.entry_date).days
        if hold_days >= self.config.max_hold_days:
            self._close_position(symbol, day, "max_hold", bar.close)

    def _close_position(
        self,
        symbol: str,
        day: datetime,
        reason: str,
        price: float = None,
    ):
        """Close a position"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        if price is None:
            bar = self.data_loader.get_bar(symbol, day)
            price = bar.close if bar else pos.entry_price

        pnl_pct = (price - pos.entry_price) / pos.entry_price

        self.trades.append(Trade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=price,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        ))

        self.cash += pos.qty * price
        del self.positions[symbol]

    def _generate_results(self) -> Dict[str, Any]:
        """Generate results"""
        final_equity = self.cash
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100

        winning = [t for t in self.trades if t.pnl_pct > 0]
        losing = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0
        avg_win = np.mean([t.pnl_pct for t in winning]) * 100 if winning else 0
        avg_loss = np.mean([t.pnl_pct for t in losing]) * 100 if losing else 0

        return {
            'total_return': total_return,
            'trades': len(self.trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'final_equity': final_equity,
        }


async def compare_entry_timing():
    """Compare once-daily vs hourly entry timing"""

    SYMBOLS = ['SOXL', 'SMCI', 'MARA', 'COIN', 'MU', 'AMD', 'NVDA', 'TSLA']

    periods = [
        (datetime(2025, 3, 1), datetime(2025, 3, 31), "Mar"),
        (datetime(2025, 4, 1), datetime(2025, 4, 30), "Apr"),
        (datetime(2025, 5, 1), datetime(2025, 5, 31), "May"),
        (datetime(2025, 6, 1), datetime(2025, 6, 30), "Jun"),
        (datetime(2025, 7, 1), datetime(2025, 7, 31), "Jul"),
        (datetime(2025, 8, 1), datetime(2025, 8, 31), "Aug"),
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec"),
        (datetime(2026, 1, 1), datetime(2026, 1, 31), "Jan"),
        (datetime(2026, 2, 1), datetime(2026, 2, 24), "Feb"),
    ]

    print("=" * 80)
    print("ENTRY TIMING COMPARISON")
    print("=" * 80)
    print("ONCE DAILY: Entry at close after red day (current behavior)")
    print("HOURLY:     Entry at intraday lows (catch dips during day)")
    print("-" * 80)
    print(f"Symbols: {SYMBOLS}")
    print("=" * 80)

    daily_total = 0
    hourly_total = 0

    print(f"\n{'Period':<8} | {'DAILY':>10} | {'HOURLY':>10} | {'Winner':<8} | {'Daily Trades':>12} | {'Hourly Trades':>13}")
    print("-" * 80)

    for start, end, label in periods:
        # Once daily
        bt_daily = EntryTimingBacktest(SYMBOLS, start, end, "once_daily")
        res_daily = await bt_daily.run()

        # Hourly
        bt_hourly = EntryTimingBacktest(SYMBOLS, start, end, "hourly")
        res_hourly = await bt_hourly.run()

        daily_total += res_daily['total_return']
        hourly_total += res_hourly['total_return']

        winner = "DAILY" if res_daily['total_return'] > res_hourly['total_return'] else "HOURLY"

        print(f"{label:<8} | {res_daily['total_return']:>+9.1f}% | {res_hourly['total_return']:>+9.1f}% | {winner:<8} | {res_daily['trades']:>12} | {res_hourly['trades']:>13}")

    print("-" * 80)
    print(f"{'TOTAL':<8} | {daily_total:>+9.1f}% | {hourly_total:>+9.1f}% |")
    print(f"{'AVERAGE':<8} | {daily_total/12:>+9.1f}% | {hourly_total/12:>+9.1f}% |")

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)

    if hourly_total > daily_total:
        diff = hourly_total - daily_total
        print(f"✅ HOURLY is better by +{diff:.1f}%")
        print("   Recommendation: Change agent to check entries more frequently")
    else:
        diff = daily_total - hourly_total
        print(f"✅ DAILY is better by +{diff:.1f}%")
        print("   Recommendation: Keep current behavior (entry at close)")


if __name__ == "__main__":
    asyncio.run(compare_entry_timing())
