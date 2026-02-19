"""
Analyst Ratings - Yahoo Finance Integration

Fetches professional analyst recommendations to inform trading decisions.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass
import asyncio


@dataclass
class AnalystRating:
    """Analyst rating data for a stock"""
    symbol: str

    # Recommendation counts
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0

    # Derived metrics
    total_analysts: int = 0
    recommendation_mean: float = 0  # 1=Strong Buy, 5=Strong Sell
    recommendation_key: str = ""    # "buy", "hold", "sell", etc.

    # Price targets
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_mean: Optional[float] = None
    target_median: Optional[float] = None
    current_price: Optional[float] = None

    # Upside potential
    upside_percent: Optional[float] = None

    # Timestamp
    fetched_at: str = ""

    @property
    def bullish_percent(self) -> float:
        """Percentage of analysts that are bullish (buy + strong buy)"""
        if self.total_analysts == 0:
            return 0
        return (self.strong_buy + self.buy) / self.total_analysts * 100

    @property
    def bearish_percent(self) -> float:
        """Percentage of analysts that are bearish (sell + strong sell)"""
        if self.total_analysts == 0:
            return 0
        return (self.strong_sell + self.sell) / self.total_analysts * 100

    @property
    def signal(self) -> str:
        """Simple signal based on analyst consensus"""
        if self.bullish_percent >= 70:
            return "STRONG_BUY"
        elif self.bullish_percent >= 50:
            return "BUY"
        elif self.bearish_percent >= 50:
            return "SELL"
        elif self.bearish_percent >= 70:
            return "STRONG_SELL"
        else:
            return "HOLD"

    @property
    def score_adjustment(self) -> float:
        """
        Score adjustment for momentum scanner (-1 to +1).
        Positive = bullish consensus, Negative = bearish
        """
        if self.total_analysts == 0:
            return 0

        # Weighted score: Strong buy=2, Buy=1, Hold=0, Sell=-1, Strong Sell=-2
        weighted = (
            self.strong_buy * 2 +
            self.buy * 1 +
            self.hold * 0 +
            self.sell * -1 +
            self.strong_sell * -2
        )

        # Normalize to -1 to +1 range
        max_possible = self.total_analysts * 2
        return weighted / max_possible if max_possible > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            "symbol": self.symbol,
            "total_analysts": self.total_analysts,
            "strong_buy": self.strong_buy,
            "buy": self.buy,
            "hold": self.hold,
            "sell": self.sell,
            "strong_sell": self.strong_sell,
            "recommendation_key": self.recommendation_key,
            "bullish_percent": round(self.bullish_percent, 1),
            "bearish_percent": round(self.bearish_percent, 1),
            "signal": self.signal,
            "target_mean": self.target_mean,
            "target_median": self.target_median,
            "upside_percent": self.upside_percent,
            "score_adjustment": round(self.score_adjustment, 2),
        }


class AnalystRatingsProvider:
    """
    Fetches analyst ratings from Yahoo Finance.

    Uses yfinance library (free, no API key needed).
    """

    def __init__(self, cache_minutes: int = 60):
        self.logger = logging.getLogger(__name__)
        self.cache_minutes = cache_minutes
        self._cache: Dict[str, tuple[AnalystRating, datetime]] = {}
        self._yf = None

    def _get_yfinance(self):
        """Lazy load yfinance"""
        if self._yf is None:
            try:
                import yfinance as yf
                self._yf = yf
            except ImportError:
                self.logger.warning(
                    "yfinance not installed. Run: pip install yfinance"
                )
                return None
        return self._yf

    async def get_rating(self, symbol: str) -> Optional[AnalystRating]:
        """
        Get analyst rating for a symbol.

        Returns cached data if available and fresh.
        """
        # Check cache
        if symbol in self._cache:
            rating, cached_at = self._cache[symbol]
            age = (datetime.now() - cached_at).total_seconds() / 60
            if age < self.cache_minutes:
                return rating

        # Fetch fresh data
        return await self._fetch_rating(symbol)

    async def _fetch_rating(self, symbol: str) -> Optional[AnalystRating]:
        """Fetch rating from Yahoo Finance"""
        yf = self._get_yfinance()
        if yf is None:
            return None

        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            rating = await loop.run_in_executor(
                None, self._fetch_sync, symbol
            )

            if rating:
                self._cache[symbol] = (rating, datetime.now())
                self.logger.debug(
                    f"📊 Analyst rating for {symbol}: "
                    f"{rating.signal} ({rating.bullish_percent:.0f}% bullish)"
                )

            return rating

        except Exception as e:
            self.logger.debug(f"Could not fetch analyst rating for {symbol}: {e}")
            return None

    def _fetch_sync(self, symbol: str) -> Optional[AnalystRating]:
        """Synchronous fetch (runs in executor)"""
        yf = self._get_yfinance()
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)

            # Get recommendations
            recommendations = {}
            try:
                rec_data = ticker.recommendations
                if rec_data is not None and not rec_data.empty:
                    # Get most recent recommendations (last row typically has totals)
                    latest = rec_data.iloc[-1] if len(rec_data) > 0 else None
                    if latest is not None:
                        recommendations = {
                            'strongBuy': int(latest.get('strongBuy', 0) or 0),
                            'buy': int(latest.get('buy', 0) or 0),
                            'hold': int(latest.get('hold', 0) or 0),
                            'sell': int(latest.get('sell', 0) or 0),
                            'strongSell': int(latest.get('strongSell', 0) or 0),
                        }
            except Exception:
                pass

            # Get recommendation summary
            rec_key = ""
            rec_mean = 0
            try:
                info = ticker.info
                rec_key = info.get('recommendationKey', '')
                rec_mean = info.get('recommendationMean', 0) or 0
            except Exception:
                pass

            # Get price targets
            target_high = None
            target_low = None
            target_mean = None
            target_median = None
            current_price = None

            try:
                info = ticker.info
                target_high = info.get('targetHighPrice')
                target_low = info.get('targetLowPrice')
                target_mean = info.get('targetMeanPrice')
                target_median = info.get('targetMedianPrice')
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            except Exception:
                pass

            # Calculate upside
            upside = None
            if target_mean and current_price and current_price > 0:
                upside = ((target_mean / current_price) - 1) * 100

            # Calculate totals
            total = sum(recommendations.values())

            rating = AnalystRating(
                symbol=symbol,
                strong_buy=recommendations.get('strongBuy', 0),
                buy=recommendations.get('buy', 0),
                hold=recommendations.get('hold', 0),
                sell=recommendations.get('sell', 0),
                strong_sell=recommendations.get('strongSell', 0),
                total_analysts=total,
                recommendation_mean=rec_mean,
                recommendation_key=rec_key,
                target_high=target_high,
                target_low=target_low,
                target_mean=target_mean,
                target_median=target_median,
                current_price=current_price,
                upside_percent=upside,
                fetched_at=datetime.now().isoformat(),
            )

            return rating

        except Exception as e:
            self.logger.debug(f"Error fetching {symbol}: {e}")
            return None

    async def get_ratings_batch(
        self,
        symbols: list[str],
        max_concurrent: int = 5
    ) -> Dict[str, AnalystRating]:
        """
        Fetch ratings for multiple symbols concurrently.

        Args:
            symbols: List of stock symbols
            max_concurrent: Max concurrent fetches

        Returns:
            Dict mapping symbol to rating
        """
        results = {}

        # Process in batches to avoid overwhelming the API
        for i in range(0, len(symbols), max_concurrent):
            batch = symbols[i:i + max_concurrent]
            tasks = [self.get_rating(s) for s in batch]
            ratings = await asyncio.gather(*tasks, return_exceptions=True)

            for symbol, rating in zip(batch, ratings):
                if isinstance(rating, AnalystRating):
                    results[symbol] = rating

            # Small delay between batches
            if i + max_concurrent < len(symbols):
                await asyncio.sleep(0.5)

        return results

    def format_for_prompt(self, rating: AnalystRating) -> str:
        """Format rating data for LLM prompt"""
        if not rating or rating.total_analysts == 0:
            return "No analyst coverage"

        parts = [
            f"Analyst Consensus: {rating.signal}",
            f"  - {rating.total_analysts} analysts total",
            f"  - {rating.bullish_percent:.0f}% bullish (Buy/Strong Buy)",
            f"  - {rating.bearish_percent:.0f}% bearish (Sell/Strong Sell)",
        ]

        if rating.target_mean:
            parts.append(f"  - Price Target: ${rating.target_mean:.2f}")
            if rating.upside_percent is not None:
                direction = "upside" if rating.upside_percent > 0 else "downside"
                parts.append(f"  - {abs(rating.upside_percent):.1f}% {direction} potential")

        return "\n".join(parts)
