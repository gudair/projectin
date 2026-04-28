"""
Daily Data Loader for Swing Trading

Fetches daily OHLCV bars from Alpaca (much more efficient than 1-min bars).
10,000 daily bars = ~40 years of data, plenty for backtesting.
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DailyBar:
    """A single daily OHLCV bar"""
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float = 0.0


class DailyDataLoader:
    """
    Loads daily OHLCV data from Alpaca for swing trading backtests.

    Uses daily timeframe instead of 1-minute for efficiency.
    """

    def __init__(self, cache_dir: str = "backtest/cache/daily"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Dict[str, DailyBar]] = {}

    async def load(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Dict[str, DailyBar]]:
        """
        Load daily data for symbols

        Returns:
            Dict[symbol, Dict[date_str, DailyBar]]
        """
        from alpaca.client import AlpacaClient

        client = AlpacaClient()

        for i, symbol in enumerate(symbols):
            if i > 0 and i % 10 == 0:
                logger.info(f"  Progress: {i}/{len(symbols)} symbols")
                await asyncio.sleep(0.5)  # Rate limit

            # Check cache
            cache_path = self._get_cache_path(symbol, start_date, end_date)
            if cache_path.exists():
                try:
                    self._data[symbol] = self._load_cache(cache_path)
                    continue
                except Exception:
                    pass

            # Fetch from API
            try:
                bars = await client.get_bars(
                    symbol=symbol,
                    timeframe='1Day',  # Daily bars
                    start=start_date,
                    end=end_date + timedelta(days=1),
                    limit=10000,
                )

                if not bars:
                    continue

                symbol_data = {}
                for bar in bars:
                    date_str = bar.timestamp.strftime('%Y-%m-%d')
                    symbol_data[date_str] = DailyBar(
                        date=bar.timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=int(bar.volume),
                        vwap=float(bar.vwap) if bar.vwap else 0.0,
                    )

                self._data[symbol] = symbol_data
                self._save_cache(cache_path, symbol_data)

            except Exception as e:
                logger.warning(f"Failed to load {symbol}: {e}")

        await client.close()
        logger.info(f"Loaded daily data for {len(self._data)} symbols")

        return self._data

    def get_bars(self, symbol: str, end_date: datetime, lookback: int = 30) -> List[DailyBar]:
        """Get the last N bars ending at end_date"""
        if symbol not in self._data:
            return []

        end_str = end_date.strftime('%Y-%m-%d')
        all_dates = sorted(self._data[symbol].keys())

        # Find end index
        end_idx = None
        for i, d in enumerate(all_dates):
            if d <= end_str:
                end_idx = i

        if end_idx is None:
            return []

        start_idx = max(0, end_idx - lookback + 1)
        return [self._data[symbol][d] for d in all_dates[start_idx:end_idx + 1]]

    def get_price(self, symbol: str, date: datetime) -> Optional[float]:
        """Get closing price for a symbol on a date"""
        date_str = date.strftime('%Y-%m-%d')
        if symbol in self._data and date_str in self._data[symbol]:
            return self._data[symbol][date_str].close
        return None

    def get_bar(self, symbol: str, date: datetime) -> Optional[DailyBar]:
        """Get the full daily bar (OHLCV) for a symbol on a date"""
        date_str = date.strftime('%Y-%m-%d')
        if symbol in self._data and date_str in self._data[symbol]:
            return self._data[symbol][date_str]
        return None

    def get_trading_days(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Get list of trading days"""
        # Use SPY as reference
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

    def _get_cache_path(self, symbol: str, start: datetime, end: datetime) -> Path:
        """Generate cache file path"""
        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')
        return self.cache_dir / f"{symbol}_{start_str}_{end_str}.json"

    def _save_cache(self, path: Path, data: Dict[str, DailyBar]):
        """Save data to cache"""
        cache_data = {
            date_str: {
                'date': bar.date.isoformat(),
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
                'vwap': bar.vwap,
            }
            for date_str, bar in data.items()
        }
        with open(path, 'w') as f:
            json.dump(cache_data, f)

    def _load_cache(self, path: Path) -> Dict[str, DailyBar]:
        """Load data from cache"""
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
