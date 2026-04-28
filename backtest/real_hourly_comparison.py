"""
REAL Hourly vs Daily Entry Comparison

Using actual hourly data from yfinance (not fake simulated data).

Compares:
1. DAILY: Entry once per day at 15:45 (near close)
2. HOURLY: Entry checks every hour during market hours
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.WARNING)


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    trailing_stop_pct: float
    high_since_entry: float


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl_pct: float
    exit_reason: str


class RealHourlyBacktest:
    """
    Backtest with REAL hourly data from yfinance.

    entry_mode:
    - "daily": Check entries only at 15:00-16:00 (near close)
    - "hourly": Check entries every hour
    """

    def __init__(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        entry_mode: str = "daily",
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.entry_mode = entry_mode

        # Strategy config (same as agent)
        self.max_positions = 2
        self.position_size_pct = 0.50
        self.stop_loss_pct = 0.02
        self.take_profit_pct = 0.10
        self.trailing_stop_pct = 0.02
        self.min_prev_day_drop = -0.01
        self.min_day_range = 0.02
        self.max_rsi = 45.0

        # State
        self.initial_capital = 100_000.0
        self.cash = self.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []

        # Data
        self.hourly_data: Dict[str, pd.DataFrame] = {}
        self.daily_data: Dict[str, pd.DataFrame] = {}

    def load_data(self):
        """Load hourly and daily data from yfinance"""
        print(f"Loading data for {len(self.symbols)} symbols...")

        for symbol in self.symbols:
            try:
                ticker = yf.Ticker(symbol)

                # Hourly data
                df_hourly = ticker.history(
                    start=self.start_date - timedelta(days=30),
                    end=self.end_date + timedelta(days=1),
                    interval='1h',
                )
                if not df_hourly.empty:
                    # Convert index to tz-naive for easier comparison
                    df_hourly.index = df_hourly.index.tz_convert('America/New_York')
                    self.hourly_data[symbol] = df_hourly

                # Daily data (for previous day check)
                df_daily = ticker.history(
                    start=self.start_date - timedelta(days=60),
                    end=self.end_date + timedelta(days=1),
                    interval='1d',
                )
                if not df_daily.empty:
                    df_daily.index = df_daily.index.tz_convert('America/New_York')
                    self.daily_data[symbol] = df_daily

            except Exception as e:
                print(f"  Error loading {symbol}: {e}")

        print(f"Loaded {len(self.hourly_data)} symbols")

    def calculate_rsi(self, closes: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        if len(closes) < period + 1:
            return 50.0

        deltas = closes.diff()
        gains = deltas.where(deltas > 0, 0)
        losses = (-deltas).where(deltas < 0, 0)

        avg_gain = gains.rolling(window=period).mean().iloc[-1]
        avg_loss = losses.rolling(window=period).mean().iloc[-1]

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def was_prev_day_red(self, symbol: str, current_time) -> tuple:
        """Check if previous trading day was red"""
        if symbol not in self.daily_data:
            return False, 0

        df = self.daily_data[symbol]
        # Get bars before current time (handle timezone-aware index)
        current_date = current_time.date() if hasattr(current_time, 'date') else current_time
        prev_bars = df[df.index.date < current_date]

        if len(prev_bars) < 2:
            return False, 0

        prev_day = prev_bars.iloc[-1]
        prev_return = (prev_day['Close'] - prev_day['Open']) / prev_day['Open']

        return prev_return < self.min_prev_day_drop, prev_return

    def get_day_range(self, symbol: str, current_time) -> float:
        """Get current day's range so far"""
        if symbol not in self.hourly_data:
            return 0

        df = self.hourly_data[symbol]
        current_date = current_time.date() if hasattr(current_time, 'date') else current_time
        today_bars = df[df.index.date == current_date]

        if today_bars.empty:
            return 0

        high = today_bars['High'].max()
        low = today_bars['Low'].min()
        close = today_bars['Close'].iloc[-1]

        return (high - low) / close if close > 0 else 0

    def should_check_entry(self, current_time: datetime) -> bool:
        """Determine if we should check for entries at this hour"""
        hour = current_time.hour

        if self.entry_mode == "daily":
            # Only check between 15:00-16:00 (near close)
            return 15 <= hour < 16
        else:
            # Check every hour during market hours (9:30-16:00)
            return 9 <= hour < 16

    def run(self) -> Dict:
        """Run the backtest"""
        self.load_data()

        if not self.hourly_data:
            return {'total_return': 0, 'trades': 0}

        # Get all unique hours across all symbols
        all_hours = set()
        for df in self.hourly_data.values():
            # Convert naive datetime to timezone-aware for comparison
            start_tz = pd.Timestamp(self.start_date).tz_localize('America/New_York')
            end_tz = pd.Timestamp(self.end_date).tz_localize('America/New_York')
            mask = (df.index >= start_tz) & (df.index <= end_tz)
            all_hours.update(df[mask].index.tolist())

        all_hours = sorted(list(all_hours))

        for current_time in all_hours:
            # Skip non-market hours
            if current_time.hour < 9 or current_time.hour >= 16:
                continue

            # Check exits first
            self._check_exits(current_time)

            # Check entries
            if self.should_check_entry(current_time):
                self._check_entries(current_time)

        # Close remaining positions
        if self.positions and all_hours:
            for symbol in list(self.positions.keys()):
                self._close_position(symbol, all_hours[-1], "backtest_end")

        return self._generate_results()

    def _check_exits(self, current_time: datetime):
        """Check all positions for exit conditions"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            if symbol not in self.hourly_data:
                continue

            df = self.hourly_data[symbol]
            if current_time not in df.index:
                continue

            bar = df.loc[current_time]
            current_price = bar['Close']
            high = bar['High']
            low = bar['Low']

            # Update high since entry
            if high > pos.high_since_entry:
                pos.high_since_entry = high

            # Stop loss
            if low <= pos.stop_loss:
                self._close_position(symbol, current_time, "stop_loss", pos.stop_loss)
                continue

            # Trailing stop
            if pos.high_since_entry > pos.entry_price:
                trailing_stop = pos.high_since_entry * (1 - pos.trailing_stop_pct)
                if low <= trailing_stop:
                    self._close_position(symbol, current_time, "trailing_stop", trailing_stop)
                    continue

            # Take profit
            if high >= pos.take_profit:
                self._close_position(symbol, current_time, "take_profit", pos.take_profit)
                continue

    def _check_entries(self, current_time: datetime):
        """Check for entry signals"""
        if len(self.positions) >= self.max_positions:
            return

        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.max_positions:
                break

            if symbol not in self.hourly_data:
                continue

            df = self.hourly_data[symbol]
            if current_time not in df.index:
                continue

            # Entry criteria
            was_red, prev_return = self.was_prev_day_red(symbol, current_time)
            if not was_red:
                continue

            day_range = self.get_day_range(symbol, current_time)
            if day_range < self.min_day_range:
                continue

            # RSI check
            closes = df[df.index <= current_time]['Close'].tail(20)
            rsi = self.calculate_rsi(closes)
            if rsi > self.max_rsi:
                continue

            # Entry signal confirmed
            entry_price = df.loc[current_time, 'Close']
            self._open_position(symbol, current_time, entry_price)

    def _open_position(self, symbol: str, entry_time: datetime, price: float):
        """Open a new position"""
        position_value = self.cash * self.position_size_pct
        if position_value < 100:
            return

        qty = position_value / price

        self.positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            entry_time=entry_time,
            stop_loss=price * (1 - self.stop_loss_pct),
            take_profit=price * (1 + self.take_profit_pct),
            trailing_stop_pct=self.trailing_stop_pct,
            high_since_entry=price,
        )

        self.cash -= position_value

    def _close_position(
        self,
        symbol: str,
        exit_time: datetime,
        reason: str,
        price: float = None,
    ):
        """Close a position"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        if price is None:
            if symbol in self.hourly_data and exit_time in self.hourly_data[symbol].index:
                price = self.hourly_data[symbol].loc[exit_time, 'Close']
            else:
                price = pos.entry_price

        pnl_pct = (price - pos.entry_price) / pos.entry_price

        self.trades.append(Trade(
            symbol=symbol,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=price,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        ))

        self.cash += pos.qty * price
        del self.positions[symbol]

    def _generate_results(self) -> Dict:
        """Generate results"""
        final_equity = self.cash
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100

        winning = [t for t in self.trades if t.pnl_pct > 0]
        losing = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0

        return {
            'total_return': total_return,
            'trades': len(self.trades),
            'win_rate': win_rate,
            'winning': len(winning),
            'losing': len(losing),
        }


def run_comparison():
    """Run the real hourly vs daily comparison"""
    SYMBOLS = ['SOXL', 'SMCI', 'MARA', 'COIN', 'MU', 'AMD', 'NVDA', 'TSLA']

    # Test periods (monthly)
    periods = [
        (datetime(2025, 3, 1), datetime(2025, 3, 31), "Mar 25"),
        (datetime(2025, 4, 1), datetime(2025, 4, 30), "Apr 25"),
        (datetime(2025, 5, 1), datetime(2025, 5, 31), "May 25"),
        (datetime(2025, 6, 1), datetime(2025, 6, 30), "Jun 25"),
        (datetime(2025, 7, 1), datetime(2025, 7, 31), "Jul 25"),
        (datetime(2025, 8, 1), datetime(2025, 8, 31), "Aug 25"),
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 25"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 25"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 25"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 25"),
        (datetime(2026, 1, 1), datetime(2026, 1, 31), "Jan 26"),
        (datetime(2026, 2, 1), datetime(2026, 2, 24), "Feb 26"),
    ]

    print("=" * 90)
    print("REAL HOURLY vs DAILY COMPARISON (using yfinance hourly data)")
    print("=" * 90)
    print(f"Symbols: {SYMBOLS}")
    print("-" * 90)
    print("DAILY:  Entry only at 15:00-16:00 (near close)")
    print("HOURLY: Entry checks every hour during market")
    print("=" * 90)

    daily_total = 0
    hourly_total = 0
    daily_wins = 0
    hourly_wins = 0

    print(f"\n{'Period':<10} | {'DAILY':>10} | {'HOURLY':>10} | {'Winner':<8} | {'Daily Trades':>12} | {'Hourly Trades':>13}")
    print("-" * 90)

    for start, end, label in periods:
        # Run daily backtest
        bt_daily = RealHourlyBacktest(SYMBOLS, start, end, "daily")
        res_daily = bt_daily.run()

        # Run hourly backtest
        bt_hourly = RealHourlyBacktest(SYMBOLS, start, end, "hourly")
        res_hourly = bt_hourly.run()

        daily_ret = res_daily['total_return']
        hourly_ret = res_hourly['total_return']

        daily_total += daily_ret
        hourly_total += hourly_ret

        if daily_ret > hourly_ret:
            winner = "DAILY"
            daily_wins += 1
        elif hourly_ret > daily_ret:
            winner = "HOURLY"
            hourly_wins += 1
        else:
            winner = "TIE"

        print(f"{label:<10} | {daily_ret:>+9.1f}% | {hourly_ret:>+9.1f}% | {winner:<8} | {res_daily['trades']:>12} | {res_hourly['trades']:>13}")

    print("-" * 90)
    print(f"{'TOTAL':<10} | {daily_total:>+9.1f}% | {hourly_total:>+9.1f}% |")
    print(f"{'AVERAGE':<10} | {daily_total/12:>+9.1f}% | {hourly_total/12:>+9.1f}% |")
    print(f"{'MONTHS WON':<10} | {daily_wins:>10} | {hourly_wins:>10} |")

    print("\n" + "=" * 90)
    print("CONCLUSION")
    print("=" * 90)

    diff = hourly_total - daily_total
    if hourly_total > daily_total:
        print(f"✅ HOURLY is better by +{diff:.1f}%")
        print("   Recommendation: Use hourly entry checks")
    else:
        print(f"✅ DAILY is better by +{abs(diff):.1f}%")
        print("   Recommendation: Keep daily entry at close")


if __name__ == "__main__":
    run_comparison()
