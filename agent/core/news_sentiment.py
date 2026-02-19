"""
News Sentiment Analyzer - Alpaca News API + Ollama Analysis

Fetches news from Alpaca (FREE with account) and analyzes sentiment
using Ollama for efficient, batched processing.
"""
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import json
import os


@dataclass
class NewsArticle:
    """A single news article"""
    id: str
    headline: str
    summary: str
    source: str
    url: str
    symbols: List[str]
    published_at: datetime
    sentiment: Optional[str] = None  # positive, negative, neutral
    sentiment_score: Optional[float] = None  # -1 to +1


@dataclass
class NewsSentiment:
    """Aggregated sentiment for a symbol"""
    symbol: str
    article_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    overall_sentiment: str  # BULLISH, BEARISH, NEUTRAL
    overall_score: float  # -1 to +1
    key_headlines: List[str]
    latest_article_time: Optional[datetime]
    analysis_summary: str = ""

    @property
    def sentiment_signal(self) -> str:
        """Trading signal based on sentiment"""
        if self.overall_score > 0.3:
            return "BULLISH"
        elif self.overall_score < -0.3:
            return "BEARISH"
        return "NEUTRAL"

    @property
    def score_adjustment(self) -> float:
        """Score adjustment for momentum scanner (-0.5 to +0.5)"""
        return self.overall_score * 0.5

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "article_count": self.article_count,
            "positive": self.positive_count,
            "negative": self.negative_count,
            "neutral": self.neutral_count,
            "overall_sentiment": self.overall_sentiment,
            "overall_score": round(self.overall_score, 2),
            "signal": self.sentiment_signal,
            "key_headlines": self.key_headlines[:3],
        }


class NewsSentimentAnalyzer:
    """
    Analyzes news sentiment using Alpaca News API + Ollama.

    Optimizations:
    - Batch multiple symbols in single Ollama call
    - Cache results (news doesn't change every second)
    - Quick keyword-based pre-filter before LLM
    - Compact prompts for efficiency
    """

    # Keywords for quick sentiment pre-filter (before LLM)
    BULLISH_KEYWORDS = [
        'upgrade', 'beat', 'surge', 'soar', 'rally', 'breakthrough',
        'profit', 'growth', 'buy', 'bullish', 'outperform', 'record',
        'positive', 'strong', 'exceeds', 'raises', 'boost', 'gains'
    ]
    BEARISH_KEYWORDS = [
        'downgrade', 'miss', 'plunge', 'crash', 'fall', 'warning',
        'loss', 'decline', 'sell', 'bearish', 'underperform', 'cut',
        'negative', 'weak', 'disappoints', 'lowers', 'concern', 'risk'
    ]

    def __init__(
        self,
        alpaca_api_key: Optional[str] = None,
        alpaca_secret_key: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
        cache_minutes: int = 15,
    ):
        self.logger = logging.getLogger(__name__)

        # Alpaca credentials
        self.api_key = alpaca_api_key or os.getenv('ALPACA_API_KEY')
        self.secret_key = alpaca_secret_key or os.getenv('ALPACA_SECRET_KEY')
        self.news_url = "https://data.alpaca.markets/v1beta1/news"

        # Ollama config
        self.ollama_url = ollama_url
        self.ollama_model = "llama3.2"  # Fast, good at sentiment

        # Cache
        self.cache_minutes = cache_minutes
        self._cache: Dict[str, Tuple[NewsSentiment, datetime]] = {}

    async def get_sentiment(self, symbol: str, hours_back: int = 24) -> Optional[NewsSentiment]:
        """
        Get news sentiment for a symbol.

        Uses cache if available and fresh.
        """
        # Check cache
        if symbol in self._cache:
            sentiment, cached_at = self._cache[symbol]
            age_minutes = (datetime.now() - cached_at).total_seconds() / 60
            if age_minutes < self.cache_minutes:
                return sentiment

        # Fetch and analyze
        return await self._analyze_symbol(symbol, hours_back)

    async def get_sentiment_batch(
        self,
        symbols: List[str],
        hours_back: int = 24
    ) -> Dict[str, NewsSentiment]:
        """
        Get sentiment for multiple symbols efficiently.

        Batches Ollama calls to reduce overhead.
        """
        results = {}
        symbols_to_analyze = []

        # Check cache first
        for symbol in symbols:
            if symbol in self._cache:
                sentiment, cached_at = self._cache[symbol]
                age_minutes = (datetime.now() - cached_at).total_seconds() / 60
                if age_minutes < self.cache_minutes:
                    results[symbol] = sentiment
                    continue
            symbols_to_analyze.append(symbol)

        if not symbols_to_analyze:
            return results

        # Fetch news for all symbols
        all_articles = {}
        for symbol in symbols_to_analyze:
            articles = await self._fetch_alpaca_news(symbol, hours_back)
            if articles:
                all_articles[symbol] = articles

        # Batch analyze with Ollama (OPTIMIZED - single call for all)
        if all_articles:
            batch_results = await self._batch_analyze_sentiment(all_articles)
            results.update(batch_results)

            # Cache results
            for symbol, sentiment in batch_results.items():
                self._cache[symbol] = (sentiment, datetime.now())

        return results

    async def _fetch_alpaca_news(
        self,
        symbol: str,
        hours_back: int = 24
    ) -> List[NewsArticle]:
        """Fetch news from Alpaca News API"""
        if not self.api_key or not self.secret_key:
            self.logger.warning("Alpaca API keys not configured")
            return []

        try:
            start_time = datetime.utcnow() - timedelta(hours=hours_back)

            headers = {
                'APCA-API-KEY-ID': self.api_key,
                'APCA-API-SECRET-KEY': self.secret_key,
            }

            params = {
                'symbols': symbol,
                'start': start_time.isoformat() + 'Z',
                'limit': 10,  # Limit to most relevant
                'sort': 'desc',
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.news_url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        self.logger.debug(f"Alpaca news API returned {resp.status}")
                        return []

                    data = await resp.json()
                    articles = []

                    for item in data.get('news', []):
                        try:
                            articles.append(NewsArticle(
                                id=item.get('id', ''),
                                headline=item.get('headline', ''),
                                summary=item.get('summary', '')[:500],  # Limit for efficiency
                                source=item.get('source', ''),
                                url=item.get('url', ''),
                                symbols=item.get('symbols', []),
                                published_at=datetime.fromisoformat(
                                    item.get('created_at', '').replace('Z', '+00:00')
                                ),
                            ))
                        except Exception as e:
                            self.logger.debug(f"Error parsing article: {e}")

                    return articles

        except Exception as e:
            self.logger.debug(f"Error fetching Alpaca news for {symbol}: {e}")
            return []

    async def _analyze_symbol(
        self,
        symbol: str,
        hours_back: int
    ) -> Optional[NewsSentiment]:
        """Analyze a single symbol"""
        articles = await self._fetch_alpaca_news(symbol, hours_back)

        if not articles:
            return NewsSentiment(
                symbol=symbol,
                article_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                overall_sentiment="NEUTRAL",
                overall_score=0,
                key_headlines=[],
                latest_article_time=None,
                analysis_summary="No recent news"
            )

        # Quick keyword analysis first
        keyword_scores = self._quick_keyword_analysis(articles)

        # If clear signal from keywords, skip LLM (optimization)
        if abs(keyword_scores['avg_score']) > 0.5:
            return self._build_sentiment_from_keywords(symbol, articles, keyword_scores)

        # Use LLM for nuanced analysis
        return await self._llm_analyze_sentiment(symbol, articles)

    def _quick_keyword_analysis(self, articles: List[NewsArticle]) -> Dict:
        """Quick keyword-based sentiment without LLM"""
        positive = 0
        negative = 0
        neutral = 0

        for article in articles:
            text = (article.headline + " " + article.summary).lower()

            bull_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text)
            bear_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text)

            if bull_count > bear_count:
                positive += 1
            elif bear_count > bull_count:
                negative += 1
            else:
                neutral += 1

        total = len(articles)
        avg_score = (positive - negative) / total if total > 0 else 0

        return {
            'positive': positive,
            'negative': negative,
            'neutral': neutral,
            'avg_score': avg_score,
        }

    def _build_sentiment_from_keywords(
        self,
        symbol: str,
        articles: List[NewsArticle],
        keyword_scores: Dict
    ) -> NewsSentiment:
        """Build sentiment result from keyword analysis"""
        score = keyword_scores['avg_score']

        if score > 0.3:
            sentiment = "BULLISH"
        elif score < -0.3:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        return NewsSentiment(
            symbol=symbol,
            article_count=len(articles),
            positive_count=keyword_scores['positive'],
            negative_count=keyword_scores['negative'],
            neutral_count=keyword_scores['neutral'],
            overall_sentiment=sentiment,
            overall_score=score,
            key_headlines=[a.headline for a in articles[:3]],
            latest_article_time=articles[0].published_at if articles else None,
            analysis_summary=f"Keyword analysis: {sentiment} ({score:+.2f})"
        )

    async def _llm_analyze_sentiment(
        self,
        symbol: str,
        articles: List[NewsArticle]
    ) -> NewsSentiment:
        """Use Ollama for detailed sentiment analysis"""
        # Build compact prompt
        headlines = "\n".join([
            f"- {a.headline}" for a in articles[:5]
        ])

        prompt = f"""Analyze sentiment for {symbol} stock based on these headlines:
{headlines}

Respond ONLY with JSON:
{{"sentiment": "BULLISH/BEARISH/NEUTRAL", "score": -1.0 to 1.0, "reason": "brief reason"}}"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 100}
                    },
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return self._build_sentiment_from_keywords(
                            symbol, articles, self._quick_keyword_analysis(articles)
                        )

                    data = await resp.json()
                    response_text = data.get('response', '')

                    # Parse JSON from response
                    result = self._parse_llm_response(response_text)

                    return NewsSentiment(
                        symbol=symbol,
                        article_count=len(articles),
                        positive_count=1 if result['sentiment'] == 'BULLISH' else 0,
                        negative_count=1 if result['sentiment'] == 'BEARISH' else 0,
                        neutral_count=1 if result['sentiment'] == 'NEUTRAL' else 0,
                        overall_sentiment=result['sentiment'],
                        overall_score=result['score'],
                        key_headlines=[a.headline for a in articles[:3]],
                        latest_article_time=articles[0].published_at if articles else None,
                        analysis_summary=result.get('reason', '')
                    )

        except Exception as e:
            self.logger.debug(f"LLM sentiment analysis failed: {e}")
            return self._build_sentiment_from_keywords(
                symbol, articles, self._quick_keyword_analysis(articles)
            )

    async def _batch_analyze_sentiment(
        self,
        all_articles: Dict[str, List[NewsArticle]]
    ) -> Dict[str, NewsSentiment]:
        """
        OPTIMIZED: Analyze multiple symbols in a single Ollama call.

        This reduces Ollama overhead significantly.
        """
        if not all_articles:
            return {}

        # Build batch prompt
        batch_parts = []
        for symbol, articles in all_articles.items():
            headlines = " | ".join([a.headline for a in articles[:3]])
            batch_parts.append(f"{symbol}: {headlines}")

        batch_text = "\n".join(batch_parts)

        prompt = f"""Analyze news sentiment for each stock. Headlines by symbol:
{batch_text}

Respond ONLY with JSON array:
[{{"symbol": "XXX", "sentiment": "BULLISH/BEARISH/NEUTRAL", "score": -1.0 to 1.0}}]"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 300}
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    results = {}

                    if resp.status == 200:
                        data = await resp.json()
                        response_text = data.get('response', '')
                        parsed = self._parse_batch_response(response_text, list(all_articles.keys()))

                        for symbol, sentiment_data in parsed.items():
                            articles = all_articles.get(symbol, [])
                            results[symbol] = NewsSentiment(
                                symbol=symbol,
                                article_count=len(articles),
                                positive_count=1 if sentiment_data['sentiment'] == 'BULLISH' else 0,
                                negative_count=1 if sentiment_data['sentiment'] == 'BEARISH' else 0,
                                neutral_count=1 if sentiment_data['sentiment'] == 'NEUTRAL' else 0,
                                overall_sentiment=sentiment_data['sentiment'],
                                overall_score=sentiment_data['score'],
                                key_headlines=[a.headline for a in articles[:3]],
                                latest_article_time=articles[0].published_at if articles else None,
                            )

                    # Fallback to keyword analysis for missing
                    for symbol, articles in all_articles.items():
                        if symbol not in results:
                            keyword_scores = self._quick_keyword_analysis(articles)
                            results[symbol] = self._build_sentiment_from_keywords(
                                symbol, articles, keyword_scores
                            )

                    return results

        except Exception as e:
            self.logger.debug(f"Batch sentiment analysis failed: {e}")
            # Fallback to keyword analysis
            results = {}
            for symbol, articles in all_articles.items():
                keyword_scores = self._quick_keyword_analysis(articles)
                results[symbol] = self._build_sentiment_from_keywords(
                    symbol, articles, keyword_scores
                )
            return results

    def _parse_llm_response(self, text: str) -> Dict:
        """Parse LLM JSON response"""
        try:
            # Find JSON in response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)
                return {
                    'sentiment': data.get('sentiment', 'NEUTRAL').upper(),
                    'score': float(data.get('score', 0)),
                    'reason': data.get('reason', ''),
                }
        except Exception:
            pass

        return {'sentiment': 'NEUTRAL', 'score': 0, 'reason': 'Parse error'}

    def _parse_batch_response(self, text: str, symbols: List[str]) -> Dict[str, Dict]:
        """Parse batch LLM response"""
        results = {}

        try:
            # Find JSON array in response
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)

                for item in data:
                    symbol = item.get('symbol', '').upper()
                    if symbol in symbols:
                        results[symbol] = {
                            'sentiment': item.get('sentiment', 'NEUTRAL').upper(),
                            'score': float(item.get('score', 0)),
                        }
        except Exception:
            pass

        return results

    def format_for_prompt(self, sentiment: NewsSentiment) -> str:
        """Format sentiment for LLM prompt"""
        if sentiment.article_count == 0:
            return "No recent news"

        return (
            f"News Sentiment: {sentiment.overall_sentiment} "
            f"(score: {sentiment.overall_score:+.2f}, {sentiment.article_count} articles)\n"
            f"Key headlines: {', '.join(sentiment.key_headlines[:2])}"
        )
