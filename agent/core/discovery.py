"""
Stock Discovery Module

Dynamically discovers stocks based on market activity, news, and technical criteria.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import aiohttp

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


@dataclass
class DiscoveredStock:
    """A discovered stock candidate"""
    symbol: str
    reason: str  # Why it was discovered
    score: float  # Priority score (higher = more interesting)
    price: float
    change_pct: float
    volume: int
    avg_volume: int
    market_cap: float
    discovered_at: datetime = field(default_factory=datetime.now)

    @property
    def volume_ratio(self) -> float:
        """Volume vs average"""
        return self.volume / self.avg_volume if self.avg_volume > 0 else 1.0


@dataclass
class DiscoveryConfig:
    """Configuration for stock discovery - 100% Dynamic Mode"""
    enabled: bool = True

    # Scanning intervals
    scan_interval_minutes: int = 15  # How often to scan (more frequent)

    # Filters
    min_price: float = 5.0           # Minimum stock price
    max_price: float = 500.0         # Maximum stock price
    min_volume: int = 500_000        # Minimum daily volume
    min_market_cap: float = 1e9      # Minimum market cap ($1B)
    min_change_pct: float = 2.0      # Minimum % change to be interesting

    # Quality-based limits
    min_score: float = 3.0           # Minimum quality score to include
    max_discovered: int = 50         # Soft limit - keeps best opportunities
    max_total_watchlist: int = 50    # Quality-based, not hard limit

    # Sources
    scan_top_gainers: bool = True
    scan_top_losers: bool = True
    scan_unusual_volume: bool = True
    scan_news_mentions: bool = True

    # Exclusions
    excluded_symbols: List[str] = field(default_factory=lambda: [
        'SPY', 'QQQ', 'IWM', 'DIA',  # ETFs we use for context
        'VXX', 'UVXY', 'SVXY',        # Volatility products
    ])


class StockDiscovery:
    """
    Discovers interesting stocks dynamically.

    Sources:
    - Top gainers/losers of the day
    - Unusual volume stocks
    - News-mentioned tickers
    - Pre-market movers
    """

    def __init__(self, config: Optional[DiscoveryConfig] = None, alpaca_client=None):
        self.config = config or DiscoveryConfig()
        self.alpaca = alpaca_client
        self.logger = logging.getLogger(__name__)

        self._discovered: Dict[str, DiscoveredStock] = {}
        self._last_scan: Optional[datetime] = None
        self._base_watchlist: Set[str] = set()

    def set_base_watchlist(self, symbols: List[str]):
        """Set the base watchlist (always included)"""
        self._base_watchlist = set(symbols)

    async def discover(self, force: bool = False) -> List[DiscoveredStock]:
        """
        Run discovery scan and return interesting stocks.

        Args:
            force: Force scan even if interval hasn't passed

        Returns:
            List of discovered stocks sorted by score
        """
        if not self.config.enabled:
            return []

        # Check if we should scan
        now = datetime.now()
        if not force and self._last_scan:
            elapsed = (now - self._last_scan).total_seconds() / 60
            if elapsed < self.config.scan_interval_minutes:
                return list(self._discovered.values())

        self.logger.info("Starting stock discovery scan...")
        discovered = []

        # Run discovery sources in parallel
        tasks = []

        if self.config.scan_top_gainers:
            tasks.append(self._scan_top_movers('gainers'))

        if self.config.scan_top_losers:
            tasks.append(self._scan_top_movers('losers'))

        if self.config.scan_unusual_volume:
            tasks.append(self._scan_unusual_volume())

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    discovered.extend(result)
                elif isinstance(result, Exception):
                    self.logger.error(f"Discovery error: {result}")

        # Deduplicate and filter
        unique = {}
        for stock in discovered:
            if stock.symbol not in unique:
                unique[stock.symbol] = stock
            else:
                # Keep higher score
                if stock.score > unique[stock.symbol].score:
                    unique[stock.symbol] = stock

        # Apply filters and exclusions
        filtered = []
        for symbol, stock in unique.items():
            if self._passes_filters(stock):
                filtered.append(stock)

        # Sort by score and limit
        filtered.sort(key=lambda s: s.score, reverse=True)
        filtered = filtered[:self.config.max_discovered]

        # Update cache
        self._discovered = {s.symbol: s for s in filtered}
        self._last_scan = now

        # Write candidates to Supabase for human review (non-blocking)
        try:
            from agent.core.supabase_logger import add_discovered_candidate
            for stock in filtered[:10]:  # top 10 by score
                add_discovered_candidate(
                    symbol=stock.symbol,
                    reason=stock.reason,
                    score=stock.score,
                    change_pct=stock.change_pct,
                )
        except Exception:
            pass

        self.logger.info(f"Discovery found {len(filtered)} interesting stocks")
        return filtered

    async def _scan_top_movers(self, mover_type: str) -> List[DiscoveredStock]:
        """Scan for top gainers or losers"""
        discovered = []

        try:
            if self.alpaca:
                # Use Alpaca's snapshot endpoint
                movers = await self._get_alpaca_movers(mover_type)
                discovered.extend(movers)

            if YFINANCE_AVAILABLE:
                # Supplement with yfinance
                yf_movers = await self._get_yfinance_movers(mover_type)
                discovered.extend(yf_movers)

        except Exception as e:
            self.logger.error(f"Error scanning {mover_type}: {e}")

        return discovered

    async def _get_alpaca_movers(self, mover_type: str) -> List[DiscoveredStock]:
        """Get movers from Alpaca API"""
        discovered = []

        try:
            # Get market movers from Alpaca
            # Note: This requires the screener endpoint
            url = f"https://data.alpaca.markets/v1beta1/screener/stocks/movers"
            params = {'top': 20}

            headers = {
                'APCA-API-KEY-ID': self.alpaca._api_key if self.alpaca else '',
                'APCA-API-SECRET-KEY': self.alpaca._secret_key if self.alpaca else '',
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        # Parse gainers or losers
                        movers_key = 'gainers' if mover_type == 'gainers' else 'losers'
                        movers = data.get(movers_key, [])

                        for mover in movers[:10]:
                            symbol = mover.get('symbol', '')
                            price = mover.get('price', 0)
                            change_pct = mover.get('change_percentage', 0) or mover.get('percent_change', 0)
                            volume = mover.get('volume', 0)

                            if symbol and price > 0:
                                score = abs(change_pct) * (1 + min(volume / 10_000_000, 2))

                                discovered.append(DiscoveredStock(
                                    symbol=symbol,
                                    reason=f"Top {mover_type[:-1]}",
                                    score=score,
                                    price=price,
                                    change_pct=change_pct,
                                    volume=volume,
                                    avg_volume=volume,  # Will be updated
                                    market_cap=0,  # Will be updated
                                ))
        except Exception as e:
            self.logger.debug(f"Alpaca movers not available: {e}")

        return discovered

    async def _get_yfinance_movers(self, mover_type: str) -> List[DiscoveredStock]:
        """Get movers using yfinance"""
        discovered = []

        if not YFINANCE_AVAILABLE:
            return discovered

        try:
            # Get popular/active stocks to check
            # These are commonly traded and likely to show movement
            scan_symbols = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
                'AMD', 'NFLX', 'COIN', 'PLTR', 'SOFI', 'RIVN', 'LCID',
                'NIO', 'BABA', 'JD', 'PDD', 'SNAP', 'UBER', 'LYFT',
                'SQ', 'PYPL', 'SHOP', 'ROKU', 'ZM', 'DKNG', 'HOOD',
                'MARA', 'RIOT', 'CLSK', 'HIVE', 'BITF',  # Crypto-related
                'XOM', 'CVX', 'OXY', 'DVN', 'HAL',  # Energy
                'JPM', 'BAC', 'WFC', 'C', 'GS',  # Banks
            ]

            # Remove already in base watchlist
            scan_symbols = [s for s in scan_symbols if s not in self._base_watchlist]

            # Run in thread pool to not block
            loop = asyncio.get_event_loop()

            def fetch_data():
                results = []
                for symbol in scan_symbols[:30]:  # Limit to avoid rate limits
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info

                        price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
                        prev_close = info.get('previousClose', price)
                        change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0
                        volume = info.get('volume', 0)
                        avg_volume = info.get('averageVolume', volume)
                        market_cap = info.get('marketCap', 0)

                        # Check if it qualifies as mover
                        if mover_type == 'gainers' and change_pct > 2:
                            results.append((symbol, price, change_pct, volume, avg_volume, market_cap))
                        elif mover_type == 'losers' and change_pct < -2:
                            results.append((symbol, price, change_pct, volume, avg_volume, market_cap))

                    except Exception:
                        continue
                return results

            results = await loop.run_in_executor(None, fetch_data)

            for symbol, price, change_pct, volume, avg_volume, market_cap in results:
                score = abs(change_pct) * (1 + min(volume / avg_volume if avg_volume > 0 else 1, 3))

                discovered.append(DiscoveredStock(
                    symbol=symbol,
                    reason=f"YF {mover_type[:-1]}",
                    score=score,
                    price=price,
                    change_pct=change_pct,
                    volume=volume,
                    avg_volume=avg_volume,
                    market_cap=market_cap,
                ))

        except Exception as e:
            self.logger.error(f"Error in yfinance movers: {e}")

        return discovered

    async def _scan_unusual_volume(self) -> List[DiscoveredStock]:
        """Scan for stocks with unusual volume"""
        discovered = []

        if not YFINANCE_AVAILABLE:
            return discovered

        try:
            # Stocks to check for volume anomalies
            volume_scan_symbols = [
                'GME', 'AMC', 'BBBY', 'KOSS', 'BB', 'NOK',  # Meme stocks
                'SPCE', 'PLUG', 'FCEL', 'BLNK', 'QS',  # Speculative
                'MRNA', 'BNTX', 'PFE', 'JNJ', 'ABBV',  # Pharma
                'DIS', 'NFLX', 'WBD', 'CMCSA',  # Media
            ]

            # Remove already watching
            volume_scan_symbols = [s for s in volume_scan_symbols if s not in self._base_watchlist]

            loop = asyncio.get_event_loop()

            def check_volume():
                results = []
                for symbol in volume_scan_symbols[:20]:
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info

                        volume = info.get('volume', 0)
                        avg_volume = info.get('averageVolume', 1)
                        volume_ratio = volume / avg_volume if avg_volume > 0 else 1

                        # Unusual volume = 2x average
                        if volume_ratio >= 2.0:
                            price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
                            prev_close = info.get('previousClose', price)
                            change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0
                            market_cap = info.get('marketCap', 0)

                            results.append((symbol, price, change_pct, volume, avg_volume, market_cap, volume_ratio))

                    except Exception:
                        continue
                return results

            results = await loop.run_in_executor(None, check_volume)

            for symbol, price, change_pct, volume, avg_volume, market_cap, volume_ratio in results:
                # Higher score for higher volume ratio
                score = volume_ratio * (1 + abs(change_pct) / 10)

                discovered.append(DiscoveredStock(
                    symbol=symbol,
                    reason=f"Unusual volume ({volume_ratio:.1f}x)",
                    score=score,
                    price=price,
                    change_pct=change_pct,
                    volume=volume,
                    avg_volume=avg_volume,
                    market_cap=market_cap,
                ))

        except Exception as e:
            self.logger.error(f"Error scanning unusual volume: {e}")

        return discovered

    def _passes_filters(self, stock: DiscoveredStock) -> bool:
        """Check if stock passes all filters (quality-based)"""
        # Exclusion list
        if stock.symbol in self.config.excluded_symbols:
            return False

        # Already in base watchlist
        if stock.symbol in self._base_watchlist:
            return False

        # Price filters
        if stock.price < self.config.min_price:
            return False
        if stock.price > self.config.max_price:
            return False

        # Volume filter
        if stock.volume < self.config.min_volume:
            return False

        # Market cap filter (if available)
        if stock.market_cap > 0 and stock.market_cap < self.config.min_market_cap:
            return False

        # Change filter
        if abs(stock.change_pct) < self.config.min_change_pct:
            return False

        # Quality score filter (key for dynamic mode)
        min_score = getattr(self.config, 'min_score', 3.0)
        if stock.score < min_score:
            return False

        return True

    def get_dynamic_watchlist(self) -> List[str]:
        """Get combined watchlist (base + discovered)"""
        watchlist = list(self._base_watchlist)

        # Add discovered stocks up to limit
        for symbol in self._discovered:
            if len(watchlist) >= self.config.max_total_watchlist:
                break
            if symbol not in watchlist:
                watchlist.append(symbol)

        return watchlist

    def get_discovery_summary(self) -> Dict:
        """Get summary of discovered stocks"""
        return {
            'last_scan': self._last_scan.isoformat() if self._last_scan else None,
            'discovered_count': len(self._discovered),
            'stocks': [
                {
                    'symbol': s.symbol,
                    'reason': s.reason,
                    'score': round(s.score, 2),
                    'change_pct': round(s.change_pct, 2),
                    'volume_ratio': round(s.volume_ratio, 2),
                }
                for s in sorted(self._discovered.values(), key=lambda x: x.score, reverse=True)
            ]
        }

    def clear_discovered(self):
        """Clear discovered stocks cache"""
        self._discovered.clear()
        self._last_scan = None
