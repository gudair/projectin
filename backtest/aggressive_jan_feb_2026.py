"""
Aggressive Agent Backtest - January & February 2026

Uses the same parameters as the aggressive agent:
- 8 symbols: SOXL, SMCI, MARA, COIN, MU, AMD, NVDA, TSLA
- 50% position size, max 2 positions
- Stop Loss: 2% | Trailing Stop: 2% | Take Profit: 10%
- Entry: Daily at close after red day + 2% volatility + RSI < 45
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List
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


class AggressiveBacktest:
    """
    Backtest with REAL hourly data from yfinance.
    Matches the aggressive agent parameters exactly.
    """

    def __init__(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date

        # Strategy config - MUST MATCH aggressive agent
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
        """Only check entries at 15:00-16:00 (near close) - DAILY mode"""
        hour = current_time.hour
        return 15 <= hour < 16

    def run(self) -> Dict:
        """Run the backtest"""
        self.load_data()

        if not self.hourly_data:
            return {'total_return': 0, 'trades': 0}

        # Get all unique hours across all symbols
        all_hours = set()
        for df in self.hourly_data.values():
            start_tz = pd.Timestamp(self.start_date).tz_localize('America/New_York')
            end_tz = pd.Timestamp(self.end_date).tz_localize('America/New_York')
            mask = (df.index >= start_tz) & (df.index <= end_tz)
            all_hours.update(df[mask].index.tolist())

        all_hours = sorted(list(all_hours))

        for current_time in all_hours:
            # Skip non-market hours
            if current_time.hour < 9 or current_time.hour >= 16:
                continue

            # Check exits first (every hour)
            self._check_exits(current_time)

            # Check entries (only at close)
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
        avg_win = np.mean([t.pnl_pct for t in winning]) * 100 if winning else 0
        avg_loss = np.mean([t.pnl_pct for t in losing]) * 100 if losing else 0

        return {
            'total_return': total_return,
            'trades': len(self.trades),
            'win_rate': win_rate,
            'winning': len(winning),
            'losing': len(losing),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'final_equity': final_equity,
        }


def run_backtest():
    """Run the aggressive agent backtest for Jan-Feb 2026"""
    SYMBOLS = ['SOXL', 'SMCI', 'MARA', 'COIN', 'MU', 'AMD', 'NVDA', 'TSLA']

    print("=" * 80)
    print("AGGRESSIVE AGENT BACKTEST - January & February 2026")
    print("=" * 80)
    print(f"Symbols: {SYMBOLS}")
    print("Parameters: 50% position | 2 max positions | 2% SL | 2% TS | 10% TP")
    print("Entry: Daily at close after red day + 2% range + RSI < 45")
    print("=" * 80)

    # Test periods
    periods = [
        (datetime(2026, 1, 1), datetime(2026, 1, 31), "Jan 2026"),
        (datetime(2026, 2, 1), datetime(2026, 2, 25), "Feb 2026"),
    ]

    total_return = 0
    total_trades = 0
    all_trades = []

    print(f"\n{'Period':<12} | {'Return':>10} | {'Trades':>7} | {'Win Rate':>9} | {'Avg Win':>9} | {'Avg Loss':>9}")
    print("-" * 80)

    for start, end, label in periods:
        bt = AggressiveBacktest(SYMBOLS, start, end)
        results = bt.run()

        total_return += results['total_return']
        total_trades += results['trades']
        all_trades.extend(bt.trades)

        print(
            f"{label:<12} | {results['total_return']:>+9.1f}% | "
            f"{results['trades']:>7} | {results['win_rate']:>8.1f}% | "
            f"{results['avg_win']:>+8.1f}% | {results['avg_loss']:>+8.1f}%"
        )

    print("-" * 80)

    # Calculate combined stats
    winning = [t for t in all_trades if t.pnl_pct > 0]
    losing = [t for t in all_trades if t.pnl_pct <= 0]
    win_rate = len(winning) / len(all_trades) * 100 if all_trades else 0
    avg_win = np.mean([t.pnl_pct for t in winning]) * 100 if winning else 0
    avg_loss = np.mean([t.pnl_pct for t in losing]) * 100 if losing else 0

    print(
        f"{'TOTAL':<12} | {total_return:>+9.1f}% | "
        f"{total_trades:>7} | {win_rate:>8.1f}% | "
        f"{avg_win:>+8.1f}% | {avg_loss:>+8.1f}%"
    )

    # Print individual trades
    print("\n" + "=" * 80)
    print("INDIVIDUAL TRADES")
    print("=" * 80)
    print(f"{'Symbol':<6} | {'Entry Date':<12} | {'Exit Date':<12} | {'Entry $':>9} | {'Exit $':>9} | {'P&L':>8} | {'Reason':<12}")
    print("-" * 80)

    for trade in sorted(all_trades, key=lambda t: t.entry_time):
        print(
            f"{trade.symbol:<6} | {trade.entry_time.strftime('%Y-%m-%d'):<12} | "
            f"{trade.exit_time.strftime('%Y-%m-%d'):<12} | "
            f"${trade.entry_price:>8.2f} | ${trade.exit_price:>8.2f} | "
            f"{trade.pnl_pct*100:>+7.1f}% | {trade.exit_reason:<12}"
        )

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Return (Jan-Feb 2026): {total_return:+.1f}%")
    print(f"Monthly Average: {total_return/2:+.1f}%")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Wins: {len(winning)} | Losses: {len(losing)}")


if __name__ == "__main__":
    run_backtest()
