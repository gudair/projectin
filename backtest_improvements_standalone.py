"""
Standalone Backtest for Improvements (Jan-Feb 2026)
Uses cached data only - no external dependencies needed
"""

import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

# Inline simplified data loader (cache-only)
@dataclass
class DailyBar:
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float = 0.0


class CachedDataLoader:
    """Simplified loader - cache only"""

    def __init__(self, cache_dir: str = "backtest/cache/daily"):
        self.cache_dir = Path(cache_dir)
        self._data: Dict[str, Dict[str, DailyBar]] = {}

    async def load(self, symbols: List[str], start_date: datetime, end_date: datetime):
        """Load from cache only"""
        for symbol in symbols:
            cache_path = self._get_cache_path(symbol, start_date, end_date)
            if cache_path and cache_path.exists():
                try:
                    self._data[symbol] = self._load_cache(cache_path)
                    print(f"  ✓ {symbol}: {cache_path.name}")
                except Exception as e:
                    print(f"  ✗ {symbol}: Failed to load - {e}")
            else:
                print(f"  ✗ {symbol}: No cache file found")

        print(f"\nLoaded {len(self._data)} symbols from cache")
        return self._data

    def get_bars(self, symbol: str, end_date: datetime, lookback: int = 30) -> List[DailyBar]:
        if symbol not in self._data:
            return []

        end_str = end_date.strftime('%Y-%m-%d')
        all_dates = sorted(self._data[symbol].keys())

        end_idx = None
        for i, d in enumerate(all_dates):
            if d <= end_str:
                end_idx = i

        if end_idx is None:
            return []

        start_idx = max(0, end_idx - lookback + 1)
        return [self._data[symbol][d] for d in all_dates[start_idx:end_idx + 1]]

    def get_price(self, symbol: str, date: datetime) -> Optional[float]:
        date_str = date.strftime('%Y-%m-%d')
        if symbol in self._data and date_str in self._data[symbol]:
            return self._data[symbol][date_str].close
        return None

    def get_bar(self, symbol: str, date: datetime) -> Optional[DailyBar]:
        date_str = date.strftime('%Y-%m-%d')
        if symbol in self._data and date_str in self._data[symbol]:
            return self._data[symbol][date_str]
        return None

    def get_trading_days(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        ref_symbol = 'SPY' if 'SPY' in self._data else list(self._data.keys())[0] if self._data else None
        if not ref_symbol:
            return []

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        days = []
        for date_str in sorted(self._data[ref_symbol].keys()):
            if start_str <= date_str <= end_str:
                days.append(datetime.strptime(date_str, '%Y-%m-%d'))

        return days

    def _get_cache_path(self, symbol: str, start: datetime, end: datetime) -> Optional[Path]:
        """Find cache file that overlaps with requested date range"""
        # List all cache files for this symbol
        pattern = f"{symbol}_*.json"
        matching_files = list(self.cache_dir.glob(pattern))

        if not matching_files:
            return None

        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')

        # Try exact match first
        exact_path = self.cache_dir / f"{symbol}_{start_str}_{end_str}.json"
        if exact_path.exists():
            return exact_path

        # Find file with best overlap
        best_file = None
        best_overlap = 0

        for cache_file in matching_files:
            # Parse dates from filename: SYMBOL_YYYYMMDD_YYYYMMDD.json
            parts = cache_file.stem.split('_')
            if len(parts) != 3:
                continue

            try:
                cache_start = datetime.strptime(parts[1], '%Y%m%d')
                cache_end = datetime.strptime(parts[2], '%Y%m%d')

                # Calculate overlap
                overlap_start = max(start, cache_start)
                overlap_end = min(end, cache_end)

                if overlap_start <= overlap_end:
                    overlap_days = (overlap_end - overlap_start).days
                    if overlap_days > best_overlap:
                        best_overlap = overlap_days
                        best_file = cache_file
            except ValueError:
                continue

        return best_file

    def _load_cache(self, path: Path) -> Dict[str, DailyBar]:
        with open(path, 'r') as f:
            cache_data = json.load(f)

        return {
            date_str: DailyBar(
                date=datetime.fromisoformat(bar['date']),
                open=bar['open'],
                high=bar['high'],
                low=bar['low'],
                close=bar['close'],
                volume=bar['volume'],
                vwap=bar.get('vwap', 0.0),
            )
            for date_str, bar in cache_data.items()
        }


# Inline simplified strategy (no numpy)
@dataclass
class Signal:
    symbol: str
    action: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float


class SimpleAggressiveStrategy:
    """Simplified aggressive dip strategy"""

    def __init__(self, min_prev_day_drop=-0.01, min_day_range=0.02, max_rsi=45.0,
                 stop_loss_pct=0.02, take_profit_pct=0.10, trailing_stop_pct=0.02):
        self.min_prev_day_drop = min_prev_day_drop
        self.min_day_range = min_day_range
        self.max_rsi = max_rsi
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct

    def calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """Calculate RSI without numpy"""
        if len(closes) < period + 1:
            return 50.0

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def generate_signal(self, symbol: str, closes: List[float], highs: List[float],
                       lows: List[float]) -> Signal:
        if len(closes) < 15:
            return Signal(symbol, 'HOLD', 0.5, closes[-1] if closes else 0, 0, 0)

        current_price = closes[-1]
        prev_day_change = (closes[-2] - closes[-3]) / closes[-3] if len(closes) >= 3 else 0
        day_range = (highs[-1] - lows[-1]) / closes[-1] if closes[-1] > 0 else 0
        rsi = self.calculate_rsi(closes)

        # Entry logic
        buy_score = 0

        if prev_day_change <= self.min_prev_day_drop:
            buy_score += 3
        else:
            return Signal(symbol, 'HOLD', 0.5, current_price, 0, 0)

        if day_range >= self.min_day_range:
            buy_score += 2

        if rsi <= self.max_rsi:
            buy_score += 2

        buy_score += 1  # High-beta bonus

        if buy_score >= 6:
            confidence = min(0.95, 0.6 + buy_score * 0.05)
            stop_loss = current_price * (1 - self.stop_loss_pct)
            take_profit = current_price * (1 + self.take_profit_pct)
            return Signal(symbol, 'BUY', confidence, current_price, stop_loss, take_profit)

        return Signal(symbol, 'HOLD', 0.5, current_price, 0, 0)


# Main backtest engine
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
    pnl_pct: float
    exit_reason: str


class BacktestEngine:
    def __init__(self, name, use_dynamic_stops=False, use_volume_filter=False):
        self.name = name
        self.use_dynamic_stops = use_dynamic_stops
        self.use_volume_filter = use_volume_filter

        self.cash = 100_000.0
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []

        self.loader = CachedDataLoader()
        self.strategy = SimpleAggressiveStrategy()

        self.symbols = ['SOXL', 'SMCI', 'MARA', 'COIN', 'MU', 'AMD', 'NVDA', 'TSLA']

    async def run(self, start_date, end_date):
        print(f"\n{'='*80}")
        print(f"BACKTEST: {self.name}")
        print(f"{'='*80}")

        # Load data
        load_start = start_date - timedelta(days=30)
        await self.loader.load(self.symbols + ['SPY'], load_start, end_date)

        trading_days = self.loader.get_trading_days(start_date, end_date)
        print(f"Trading days: {len(trading_days)}")

        # Process each day
        for day in trading_days:
            self._process_day(day)

        # Close remaining positions
        if self.positions and trading_days:
            last_day = trading_days[-1]
            for symbol in list(self.positions.keys()):
                exit_price = self.loader.get_price(symbol, last_day)
                if exit_price:
                    self._close_position(symbol, last_day, exit_price, "END")

        return self._get_results()

    def _process_day(self, day):
        # Check existing positions
        for symbol in list(self.positions.keys()):
            self._check_position(symbol, day)

        # Check for new entries
        if len(self.positions) < 2:  # Max 2 positions
            self._check_entries(day)

    def _check_position(self, symbol, day):
        pos = self.positions[symbol]
        pos.days_held += 1

        bar = self.loader.get_bar(symbol, day)
        if not bar:
            return

        # Update high
        if bar.high > pos.high_since_entry:
            pos.high_since_entry = bar.high

        # Check stop loss
        if bar.low <= pos.stop_loss:
            self._close_position(symbol, day, pos.stop_loss, "STOP_LOSS")
            return

        # Check trailing stop
        trailing_stop = pos.high_since_entry * (1 - pos.trailing_stop_pct)
        if bar.low <= trailing_stop:
            self._close_position(symbol, day, trailing_stop, "TRAILING_STOP")
            return

        # Check take profit
        if bar.high >= pos.take_profit:
            self._close_position(symbol, day, pos.take_profit, "TAKE_PROFIT")
            return

        # Max hold days
        if pos.days_held >= 4:
            self._close_position(symbol, day, bar.close, "MAX_HOLD")

    def _check_entries(self, day):
        for symbol in self.symbols:
            if symbol in self.positions:
                continue

            bars = self.loader.get_bars(symbol, day, 20)
            if len(bars) < 15:
                continue

            closes = [b.close for b in bars]
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]

            signal = self.strategy.generate_signal(symbol, closes, highs, lows)

            if signal.action != 'BUY' or signal.confidence < 0.7:
                continue

            # Volume filter
            if self.use_volume_filter:
                current_vol = bars[-1].volume
                avg_vol = sum(b.volume for b in bars[:-1]) / (len(bars) - 1)
                vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

                if vol_ratio < 0.5:  # Reject low volume
                    continue

            # Dynamic stops
            stop_loss_pct = self.strategy.stop_loss_pct
            if self.use_dynamic_stops:
                # Simple dynamic: widen stops in volatile markets
                vix = self.loader.get_price('VIX', day) or 20.0
                if vix > 25:
                    stop_loss_pct *= 1.15
                elif vix < 15:
                    stop_loss_pct *= 0.90

            position_value = self.cash * 0.50  # 50% per position
            qty = position_value / signal.entry_price

            stop_loss = signal.entry_price * (1 - stop_loss_pct)

            self.positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                entry_price=signal.entry_price,
                entry_date=day,
                stop_loss=stop_loss,
                take_profit=signal.entry_price * 1.10,
                trailing_stop_pct=0.02,
                high_since_entry=signal.entry_price,
            )

            self.cash -= position_value
            print(f"  BUY {symbol} @ ${signal.entry_price:.2f}")
            break  # One trade per day

    def _close_position(self, symbol, day, exit_price, reason):
        pos = self.positions.pop(symbol)
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price

        self.cash += exit_price * pos.qty

        self.trades.append(Trade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        ))

        print(f"  SELL {symbol} @ ${exit_price:.2f} ({pnl_pct:+.1%}) - {reason}")

    def _get_results(self):
        final_equity = self.cash
        for pos in self.positions.values():
            final_equity += pos.qty * pos.entry_price

        total_return_pct = (final_equity - 100_000.0) / 100_000.0 * 100

        winning_trades = [t for t in self.trades if t.pnl_pct > 0]
        win_rate = len(winning_trades) / len(self.trades) * 100 if self.trades else 0

        return {
            'name': self.name,
            'return_pct': total_return_pct,
            'trades': len(self.trades),
            'win_rate': win_rate,
        }


async def main():
    start = datetime(2026, 1, 2)
    end = datetime(2026, 2, 28)

    print("\n" + "="*80)
    print("BACKTEST: Jan-Feb 2026 (Rule-Based, No AI)")
    print("="*80)

    configs = [
        ('Baseline', False, False),
        ('Dynamic Stops', True, False),
        ('Volume Filter', False, True),
        ('Both', True, True),
    ]

    results = []
    for name, dynamic, volume in configs:
        engine = BacktestEngine(name, dynamic, volume)
        result = await engine.run(start, end)
        results.append(result)

    # Print comparison
    print("\n" + "="*80)
    print("RESULTS SUMMARY")
    print("="*80)

    baseline_return = results[0]['return_pct']

    for result in results:
        improvement = result['return_pct'] - baseline_return
        print(f"\n{result['name']}")
        print(f"  Return: {result['return_pct']:+.2f}% (vs baseline: {improvement:+.2f}%)")
        print(f"  Trades: {result['trades']} | Win Rate: {result['win_rate']:.1f}%")

    best = max(results, key=lambda x: x['return_pct'])
    print(f"\n{'='*80}")
    print(f"🏆 BEST: {best['name']} with {best['return_pct']:+.2f}%")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
