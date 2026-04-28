"""
Historical Data Loader

Fetches and caches historical market data from Alpaca for backtesting.
Uses the project's existing AlpacaClient.
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# Use the project's existing AlpacaClient
from alpaca.client import AlpacaClient

logger = logging.getLogger(__name__)


@dataclass
class BarData:
    """Single bar of OHLCV data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float = 0.0
    trade_count: int = 0


@dataclass
class DayData:
    """All data for a single trading day"""
    date: datetime
    bars: List[BarData]  # 1-minute bars throughout the day
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    total_volume: int
    pre_market_high: float = 0.0
    pre_market_low: float = 0.0
    pre_market_volume: int = 0


class HistoricalDataLoader:
    """
    Loads and caches historical data from Alpaca.

    Data is cached locally to avoid repeated API calls.
    """

    # Popular stocks for discovery simulation
    UNIVERSE = [
        # Big Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # Semiconductors
        'AMD', 'INTC', 'MU', 'AVGO', 'QCOM', 'MRVL',
        # Growth/Momentum
        'NFLX', 'CRM', 'ADBE', 'SHOP', 'SQ', 'PYPL', 'COIN',
        # EV
        'RIVN', 'LCID', 'NIO', 'LI', 'XPEV',
        # Fintech
        'SOFI', 'HOOD', 'AFRM', 'UPST',
        # China
        'BABA', 'JD', 'PDD', 'BIDU',
        # Energy
        'XOM', 'CVX', 'OXY', 'DVN', 'SLB',
        # Airlines/Travel
        'UAL', 'DAL', 'AAL', 'LUV', 'ABNB',
        # Biotech
        'MRNA', 'BNTX', 'BIIB', 'REGN',
        # Retail
        'WMT', 'TGT', 'COST', 'HD', 'LOW',
        # Financial
        'JPM', 'BAC', 'WFC', 'GS', 'MS',
        # Healthcare
        'UNH', 'JNJ', 'PFE', 'ABBV', 'MRK',
        # ETFs for context
        'SPY', 'QQQ', 'IWM', 'DIA',
        # Meme/Volatile
        'GME', 'AMC', 'PLTR', 'MARA', 'RIOT',
        # AI plays
        'SMCI', 'DELL', 'ORCL',
        # Telecom
        'VZ', 'T', 'TMUS',
        # Consumer
        'KO', 'PEP', 'MCD', 'SBUX', 'NKE',
    ]

    def __init__(
        self,
        cache_dir: str = "backtest/cache",
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Use the project's existing AlpacaClient
        self.client = AlpacaClient()
        self._data_cache: Dict[str, Dict[str, DayData]] = {}

    def get_cache_path(self, symbol: str, start_date: datetime, end_date: datetime) -> Path:
        """Get cache file path for a symbol and date range"""
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        return self.cache_dir / f"{symbol}_{start_str}_{end_str}.json"

    async def load_data(
        self,
        symbols: Optional[List[str]] = None,
        start_date: datetime = None,
        end_date: datetime = None,
        use_cache: bool = True,
    ) -> Dict[str, Dict[str, DayData]]:
        """
        Load historical data for symbols.

        Returns:
            Dict[symbol, Dict[date_str, DayData]]
        """
        symbols = symbols or self.UNIVERSE
        start_date = start_date or datetime(2025, 10, 1)
        end_date = end_date or datetime(2025, 12, 31)

        logger.info(f"Loading historical data for {len(symbols)} symbols from {start_date.date()} to {end_date.date()}")

        all_data = {}
        loaded_from_cache = 0
        fetched_from_api = 0

        for symbol in symbols:
            cache_path = self.get_cache_path(symbol, start_date, end_date)

            if use_cache and cache_path.exists():
                # Load from cache
                try:
                    symbol_data = self._load_from_cache(cache_path)
                    if symbol_data:
                        all_data[symbol] = symbol_data
                        loaded_from_cache += 1
                        continue
                except Exception as e:
                    logger.warning(f"Cache load failed for {symbol}: {e}")

            # Fetch from API
            try:
                symbol_data = await self._fetch_symbol_data(symbol, start_date, end_date)
                if symbol_data:
                    all_data[symbol] = symbol_data
                    fetched_from_api += 1
                    # Save to cache
                    self._save_to_cache(cache_path, symbol_data)
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")

            # Small delay to avoid rate limits
            if fetched_from_api > 0 and fetched_from_api % 10 == 0:
                await asyncio.sleep(1)
                logger.info(f"  Progress: {fetched_from_api + loaded_from_cache}/{len(symbols)} symbols loaded")

        logger.info(f"Data loaded: {loaded_from_cache} from cache, {fetched_from_api} from API")
        self._data_cache = all_data

        # Close the client
        await self.client.close()

        return all_data

    async def _fetch_symbol_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, DayData]:
        """Fetch data for a single symbol from Alpaca using existing client"""
        try:
            # Use the existing AlpacaClient's get_bars method
            # Alpaca max limit is 10000, but 1 day has ~390 1-min bars
            bars = await self.client.get_bars(
                symbol=symbol,
                timeframe='1Min',  # 1-minute bars
                start=start_date,
                end=end_date + timedelta(days=1),  # Include end date
                limit=10000,  # Alpaca max limit
            )

            if not bars:
                return {}

            # Group bars by date
            daily_data = {}
            current_date = None
            current_bars = []

            for bar in bars:
                bar_date = bar.timestamp.date()

                if current_date is None:
                    current_date = bar_date

                if bar_date != current_date:
                    # Save previous day's data
                    if current_bars:
                        daily_data[current_date.isoformat()] = self._create_day_data(
                            current_date, current_bars
                        )
                    current_date = bar_date
                    current_bars = []

                current_bars.append(BarData(
                    timestamp=bar.timestamp,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=int(bar.volume),
                    vwap=float(bar.vwap) if bar.vwap else 0.0,
                    trade_count=int(bar.trade_count) if bar.trade_count else 0,
                ))

            # Don't forget last day
            if current_bars:
                daily_data[current_date.isoformat()] = self._create_day_data(
                    current_date, current_bars
                )

            return daily_data

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return {}

    def _create_day_data(self, date: datetime, bars: List[BarData]) -> DayData:
        """Create DayData from list of bars"""
        if not bars:
            return None

        # Separate pre-market (before 9:30) and regular hours
        pre_market_bars = [b for b in bars if b.timestamp.hour < 9 or (b.timestamp.hour == 9 and b.timestamp.minute < 30)]
        regular_bars = [b for b in bars if not (b.timestamp.hour < 9 or (b.timestamp.hour == 9 and b.timestamp.minute < 30))]

        # Use regular bars for main stats, or all bars if no regular hours
        main_bars = regular_bars if regular_bars else bars

        return DayData(
            date=datetime.combine(date, datetime.min.time()) if isinstance(date, datetime) == False else date,
            bars=bars,
            open_price=main_bars[0].open if main_bars else bars[0].open,
            high_price=max(b.high for b in main_bars) if main_bars else max(b.high for b in bars),
            low_price=min(b.low for b in main_bars) if main_bars else min(b.low for b in bars),
            close_price=main_bars[-1].close if main_bars else bars[-1].close,
            total_volume=sum(b.volume for b in main_bars) if main_bars else sum(b.volume for b in bars),
            pre_market_high=max(b.high for b in pre_market_bars) if pre_market_bars else 0.0,
            pre_market_low=min(b.low for b in pre_market_bars) if pre_market_bars else 0.0,
            pre_market_volume=sum(b.volume for b in pre_market_bars) if pre_market_bars else 0,
        )

    def _save_to_cache(self, path: Path, data: Dict[str, DayData]):
        """Save data to cache file"""
        try:
            serializable = {}
            for date_str, day_data in data.items():
                serializable[date_str] = {
                    'date': day_data.date.isoformat() if isinstance(day_data.date, datetime) else day_data.date,
                    'open_price': day_data.open_price,
                    'high_price': day_data.high_price,
                    'low_price': day_data.low_price,
                    'close_price': day_data.close_price,
                    'total_volume': day_data.total_volume,
                    'pre_market_high': day_data.pre_market_high,
                    'pre_market_low': day_data.pre_market_low,
                    'pre_market_volume': day_data.pre_market_volume,
                    'bars': [
                        {
                            'timestamp': b.timestamp.isoformat(),
                            'open': b.open,
                            'high': b.high,
                            'low': b.low,
                            'close': b.close,
                            'volume': b.volume,
                            'vwap': b.vwap,
                            'trade_count': b.trade_count,
                        }
                        for b in day_data.bars
                    ]
                }

            with open(path, 'w') as f:
                json.dump(serializable, f)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _load_from_cache(self, path: Path) -> Dict[str, DayData]:
        """Load data from cache file"""
        with open(path, 'r') as f:
            serialized = json.load(f)

        data = {}
        for date_str, day_dict in serialized.items():
            bars = [
                BarData(
                    timestamp=datetime.fromisoformat(b['timestamp']),
                    open=b['open'],
                    high=b['high'],
                    low=b['low'],
                    close=b['close'],
                    volume=b['volume'],
                    vwap=b.get('vwap', 0.0),
                    trade_count=b.get('trade_count', 0),
                )
                for b in day_dict['bars']
            ]

            data[date_str] = DayData(
                date=datetime.fromisoformat(day_dict['date']) if isinstance(day_dict['date'], str) else day_dict['date'],
                bars=bars,
                open_price=day_dict['open_price'],
                high_price=day_dict['high_price'],
                low_price=day_dict['low_price'],
                close_price=day_dict['close_price'],
                total_volume=day_dict['total_volume'],
                pre_market_high=day_dict.get('pre_market_high', 0.0),
                pre_market_low=day_dict.get('pre_market_low', 0.0),
                pre_market_volume=day_dict.get('pre_market_volume', 0),
            )

        return data

    def get_top_movers(self, timestamp: datetime, top_n: int = 20) -> List[Dict[str, Any]]:
        """
        Get top gainers and losers at a specific time (intraday).
        Uses price at timestamp vs open price - NOT end of day data.
        """
        date_str = timestamp.date().isoformat()

        movers = []
        for symbol, daily_data in self._data_cache.items():
            if date_str not in daily_data:
                continue

            day = daily_data[date_str]
            if day.open_price <= 0:
                continue

            # Get current price at timestamp (NOT end of day close!)
            bar = self.get_bar_at_time(symbol, timestamp)
            if not bar:
                continue

            current_price = bar.close

            # Calculate change from open to current time
            change_pct = ((current_price - day.open_price) / day.open_price) * 100

            # Calculate volume up to this point
            # Convert simulation time (ET) to UTC for comparison
            target_utc = timestamp + timedelta(hours=4)
            volume_so_far = sum(
                b.volume for b in day.bars
                if b.timestamp.replace(tzinfo=None) <= target_utc
            )

            movers.append({
                'symbol': symbol,
                'open': day.open_price,
                'close': current_price,  # Current price, not end of day
                'high': bar.high,
                'low': bar.low,
                'change_pct': change_pct,
                'volume': volume_so_far,
                'pre_market_high': day.pre_market_high,
                'pre_market_low': day.pre_market_low,
            })

        # Sort by absolute change
        movers.sort(key=lambda x: abs(x['change_pct']), reverse=True)
        return movers[:top_n]

    def get_bar_at_time(self, symbol: str, dt: datetime) -> Optional[BarData]:
        """Get the bar data for a symbol at a specific datetime (ET)"""
        date_str = dt.date().isoformat()

        if symbol not in self._data_cache:
            return None
        if date_str not in self._data_cache[symbol]:
            return None

        day_data = self._data_cache[symbol][date_str]

        # Convert simulation time (ET) to UTC for comparison
        # ET is UTC-4 (EDT) during October
        # 9:30 AM ET = 13:30 UTC
        target_utc = dt + timedelta(hours=4)  # ET to UTC (EDT)
        target_utc = target_utc.replace(second=0, microsecond=0)

        best_bar = None

        for bar in day_data.bars:
            # Bar timestamps are in UTC (e.g., 2025-10-01T13:30:00+00:00)
            # Remove timezone info for comparison
            bar_time = bar.timestamp.replace(second=0, microsecond=0, tzinfo=None)

            if bar_time <= target_utc:
                best_bar = bar
            else:
                break

        return best_bar

    def get_price_at_time(self, symbol: str, dt: datetime) -> Optional[float]:
        """Get the price for a symbol at a specific datetime"""
        bar = self.get_bar_at_time(symbol, dt)
        return bar.close if bar else None

    def get_trading_days(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Get list of trading days in the data"""
        # Use SPY as reference for trading days
        if 'SPY' not in self._data_cache:
            # Use any symbol we have
            if not self._data_cache:
                return []
            symbol = list(self._data_cache.keys())[0]
        else:
            symbol = 'SPY'

        dates = []
        for date_str in sorted(self._data_cache[symbol].keys()):
            dt = datetime.fromisoformat(date_str)
            if start_date.date() <= dt.date() <= end_date.date():
                dates.append(dt)

        return dates
