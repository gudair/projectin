"""
News & Sentiment Monitor

Monitors news throughout the day and analyzes sentiment for trading decisions.
Runs hourly during market hours to build context for the end-of-day entry decision.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import aiohttp
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


@dataclass
class NewsItem:
    """A single news article"""
    title: str
    summary: str
    source: str
    published: datetime
    url: str
    symbol: str


@dataclass
class SentimentAnalysis:
    """Sentiment analysis result for a symbol"""
    symbol: str
    sentiment: str  # POSITIVE, NEGATIVE, NEUTRAL
    confidence: float
    key_points: List[str]
    news_count: int
    analysis_time: datetime
    raw_summary: str  # For debugging


class NewsMonitor:
    """
    Monitors news and sentiment throughout the trading day.

    Features:
    - Hourly news scraping from Yahoo Finance
    - Groq-powered sentiment analysis
    - Caches sentiment for end-of-day decision
    - Clean, non-spammy logging
    """

    def __init__(self, symbols: List[str], groq_client=None):
        self.symbols = symbols
        self.groq_client = groq_client
        self.sentiment_cache: Dict[str, SentimentAnalysis] = {}
        self._running = False
        self._monitor_task = None

        # Configuration
        self.scan_start_hour = 8  # 8:00 AM ET
        self.scan_end_hour = 15   # 3:00 PM ET (last scan before entry at 15:45)
        self.scan_interval_minutes = 60  # Hourly

    async def start(self):
        """Start the news monitoring loop"""
        logger.info("📰 NewsMonitor.start() initializing...")
        if self._running:
            logger.warning("News monitor already running")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"📰 News Monitor: Ready (scans {self.scan_start_hour}:00 - {self.scan_end_hour}:00 ET, "
            f"every {self.scan_interval_minutes} min)"
        )

    async def stop(self):
        """Stop the news monitoring loop"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("📰 News Monitor: Stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - runs hourly during market hours"""
        last_scan_hour = None
        logged_waiting = False

        while self._running:
            try:
                now_et = datetime.now(ET)
                current_hour = now_et.hour

                # Only scan once per hour, during market hours
                if (self.scan_start_hour <= current_hour <= self.scan_end_hour and
                    current_hour != last_scan_hour):

                    scan_time = now_et.strftime('%I:%M %p ET')
                    print(f"📰 News Monitor: Starting hourly scan ({scan_time})")
                    logger.info(f"📰 News Monitor: Starting hourly scan ({scan_time})")
                    await self._run_scan()
                    last_scan_hour = current_hour
                    logged_waiting = False  # Reset for next wait period

                elif not logged_waiting:
                    # Log once when outside scanning hours
                    logger.info(
                        f"📰 News Monitor: Waiting for next scan hour "
                        f"({now_et.strftime('%I:%M %p ET')} - scans {self.scan_start_hour}:00 to {self.scan_end_hour}:00 ET)"
                    )
                    logged_waiting = True

                # Sleep for a minute before checking again
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in news monitor loop: {e}")
                await asyncio.sleep(300)  # Wait 5 min on error

    async def _run_scan(self):
        """Run a single scan cycle for all symbols"""
        symbols_with_news = 0

        for symbol in self.symbols:
            try:
                # Fetch news
                news_items = await self.fetch_news(symbol)

                if not news_items:
                    continue

                symbols_with_news += 1

                # Analyze sentiment with Groq
                if self.groq_client:
                    sentiment = await self.analyze_sentiment(symbol, news_items)
                    self.sentiment_cache[symbol] = sentiment

                    # Clean logging - one line per symbol
                    emoji = "📗" if sentiment.sentiment == "POSITIVE" else "📕" if sentiment.sentiment == "NEGATIVE" else "📘"
                    logger.info(
                        f"{emoji} {symbol}: {sentiment.news_count} articles | "
                        f"{sentiment.sentiment} ({sentiment.confidence:.0%}) - "
                        f"{sentiment.key_points[0] if sentiment.key_points else 'No key points'}"
                    )
                else:
                    # No AI - just count news
                    logger.info(f"📰 {symbol}: {len(news_items)} articles (no sentiment analysis)")

            except Exception as e:
                logger.warning(f"Failed to process news for {symbol}: {e}")

        summary = f"📰 Scan complete: {symbols_with_news}/{len(self.symbols)} symbols have recent news"
        print(summary)
        logger.info(summary)

    async def fetch_news(self, symbol: str, lookback_hours: int = 24) -> List[NewsItem]:
        """
        Fetch recent news for a symbol from Google News RSS.

        Uses Google News RSS feed (free, no API key needed).
        """
        try:
            import re
            from email.utils import parsedate_to_datetime

            # Google News RSS search
            url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.warning(f"Google News RSS returned {response.status} for {symbol}")
                        return []

                    text = await response.text()

                    news_items = []
                    cutoff_time = datetime.now(ET) - timedelta(hours=lookback_hours)

                    items = re.findall(r'<item>(.*?)</item>', text, re.DOTALL)
                    for item in items[:5]:  # Max 5 news items per symbol
                        title_match = re.search(r'<title>(.*?)</title>', item)
                        link_match = re.search(r'<link>(.*?)</link>', item)
                        pubdate_match = re.search(r'<pubDate>(.*?)</pubDate>', item)
                        desc_match = re.search(r'<description>(.*?)</description>', item)

                        if title_match:
                            title = title_match.group(1).strip()
                            link = link_match.group(1).strip() if link_match else ""

                            # Parse pubDate (format: "Wed, 05 Mar 2026 14:30:00 GMT")
                            published = datetime.now(ET)  # Default to now
                            if pubdate_match:
                                try:
                                    published = parsedate_to_datetime(pubdate_match.group(1).strip())
                                except Exception:
                                    pass

                            # Skip old news
                            if published.timestamp() < cutoff_time.timestamp():
                                continue

                            # Clean HTML from description
                            summary = desc_match.group(1).strip() if desc_match else title
                            summary = re.sub(r'<[^>]+>', '', summary)

                            news_items.append(NewsItem(
                                title=title,
                                summary=summary[:300],
                                source="Google News",
                                published=published,
                                url=link,
                                symbol=symbol
                            ))

                    return news_items

        except Exception as e:
            logger.warning(f"Failed to fetch news for {symbol}: {e}")
            return []

    async def analyze_sentiment(self, symbol: str, news_items: List[NewsItem]) -> SentimentAnalysis:
        """
        Analyze sentiment of news items using Groq.

        Returns a structured sentiment analysis with key points.
        """
        if not self.groq_client or not news_items:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="NEUTRAL",
                confidence=0.5,
                key_points=[],
                news_count=0,
                analysis_time=datetime.now(ET),
                raw_summary=""
            )

        # Prepare news summary for AI
        news_summary = f"Recent news for {symbol}:\n\n"
        for i, item in enumerate(news_items[:5], 1):  # Max 5 items
            news_summary += f"{i}. {item.title}\n   {item.summary[:200]}...\n\n"

        # Ask Groq to analyze sentiment
        prompt = f"""Analyze the sentiment of these news articles for {symbol} stock.

{news_summary}

Provide:
1. Overall sentiment: POSITIVE, NEGATIVE, or NEUTRAL
2. Confidence: 0-100%
3. Key points: 1-2 most important takeaways (concise)

Format your response as:
SENTIMENT: [POSITIVE/NEGATIVE/NEUTRAL]
CONFIDENCE: [0-100]%
KEY_POINTS:
- [point 1]
- [point 2]
"""

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.groq_client.BASE_URL,
                    headers=self.groq_client.headers,
                    json={
                        "model": self.groq_client.MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 200,
                    }
                )
                if response.status_code != 200:
                    logger.warning(f"Groq API error for {symbol} sentiment: {response.status_code}")
                    return SentimentAnalysis(
                        symbol=symbol, sentiment="NEUTRAL", confidence=0.5,
                        key_points=[], news_count=len(news_items),
                        analysis_time=datetime.now(ET), raw_summary=""
                    )
                data = response.json()
            analysis_text = data["choices"][0]["message"]["content"].strip()

            # Parse response
            sentiment = "NEUTRAL"
            confidence = 0.5
            key_points = []

            if "POSITIVE" in analysis_text:
                sentiment = "POSITIVE"
            elif "NEGATIVE" in analysis_text:
                sentiment = "NEGATIVE"

            # Extract confidence
            import re
            conf_match = re.search(r'CONFIDENCE:\s*(\d+)', analysis_text)
            if conf_match:
                confidence = int(conf_match.group(1)) / 100.0

            # Extract key points
            key_points_section = re.search(r'KEY_POINTS:(.*)', analysis_text, re.DOTALL)
            if key_points_section:
                points_text = key_points_section.group(1)
                points = re.findall(r'[-•]\s*(.+)', points_text)
                key_points = [p.strip() for p in points[:2]]  # Max 2 points

            return SentimentAnalysis(
                symbol=symbol,
                sentiment=sentiment,
                confidence=confidence,
                key_points=key_points,
                news_count=len(news_items),
                analysis_time=datetime.now(ET),
                raw_summary=analysis_text
            )

        except Exception as e:
            logger.warning(f"Sentiment analysis failed for {symbol}: {e}")
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="NEUTRAL",
                confidence=0.5,
                key_points=[f"Error: {str(e)}"],
                news_count=len(news_items),
                analysis_time=datetime.now(ET),
                raw_summary=""
            )

    def get_sentiment(self, symbol: str) -> Optional[SentimentAnalysis]:
        """Get cached sentiment for a symbol"""
        return self.sentiment_cache.get(symbol)

    def get_all_sentiments(self) -> Dict[str, SentimentAnalysis]:
        """Get all cached sentiments"""
        return self.sentiment_cache.copy()

    def clear_cache(self):
        """Clear sentiment cache (useful for testing)"""
        self.sentiment_cache.clear()
