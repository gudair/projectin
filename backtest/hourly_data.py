"""
Hourly Data Loader for Backtesting

Loads 1-hour bars from Alpaca for proper intraday analysis.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from alpaca.client import AlpacaClient, Bar

logger = logging.getLogger(__name__)


@dataclass
class HourlyBar:
    """A single hourly bar"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class HourlyDataLoader:
    """Load and cache hourly bar data from Alpaca"""

    def __init__(self):
        self.client = AlpacaClient()
        self.data: Dict[str, List[HourlyBar]] = {}

    async def load(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
    ):
        """Load hourly data for symbols"""
        logger.info(f"Loading hourly data for {len(symbols)} symbols...")

        for symbol in symbols:
            try:
                bars = await self.client.get_bars(
                    symbol=symbol,
                    timeframe='1Hour',  # HOURLY DATA
                    start=start_date,
                    end=end_date,
                    limit=10000,  # Get lots of bars
                )

                if bars:
                    self.data[symbol] = [
                        HourlyBar(
                            symbol=symbol,
                            timestamp=b.timestamp,
                            open=b.open,
                            high=b.high,
                            low=b.low,
                            close=b.close,
                            volume=b.volume,
                        )
                        for b in bars
                    ]
                    logger.debug(f"  {symbol}: {len(bars)} hourly bars")

            except Exception as e:
                logger.error(f"Failed to load {symbol}: {e}")

        await self.client.close()
        logger.info(f"Loaded hourly data for {len(self.data)} symbols")

    def get_bars(
        self,
        symbol: str,
        end_time: datetime,
        count: int = 20,
    ) -> List[HourlyBar]:
        """Get the last N bars before end_time"""
        if symbol not in self.data:
            return []

        bars = [b for b in self.data[symbol] if b.timestamp <= end_time]
        return bars[-count:] if len(bars) >= count else bars

    def get_all_bars(self, symbol: str) -> List[HourlyBar]:
        """Get all bars for a symbol"""
        return self.data.get(symbol, [])

    def get_trading_hours(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> List[datetime]:
        """Get all unique trading hours in the data"""
        all_times = set()
        for symbol_bars in self.data.values():
            for bar in symbol_bars:
                if start_date <= bar.timestamp <= end_date:
                    all_times.add(bar.timestamp)
        return sorted(list(all_times))


async def test_hourly_data():
    """Test loading hourly data"""
    loader = HourlyDataLoader()

    # Load 1 month of hourly data
    end = datetime.now()
    start = end - timedelta(days=30)

    await loader.load(['AMD', 'NVDA'], start, end)

    for symbol in ['AMD', 'NVDA']:
        bars = loader.get_all_bars(symbol)
        if bars:
            print(f"\n{symbol}: {len(bars)} hourly bars")
            print(f"  First: {bars[0].timestamp} @ ${bars[0].close:.2f}")
            print(f"  Last:  {bars[-1].timestamp} @ ${bars[-1].close:.2f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_hourly_data())
