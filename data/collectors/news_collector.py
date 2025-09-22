import requests
import feedparser
import yfinance as yf
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional
from config.settings import NEWS_API_KEY
import time

class NewsCollector:
    def __init__(self):
        self.news_api_key = NEWS_API_KEY
        self.logger = logging.getLogger(__name__)

    def get_stock_news(self, symbol: str, hours_back: int = 24) -> List[Dict]:
        """Get news for specific stock from multiple sources"""
        all_news = []

        # Try multiple sources
        all_news.extend(self._get_newsapi_articles(symbol, hours_back))
        all_news.extend(self._get_yahoo_news(symbol))
        all_news.extend(self._get_rss_feeds(symbol))

        # Remove duplicates and sort by date
        seen_titles = set()
        unique_news = []

        for article in all_news:
            title_lower = article['title'].lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_news.append(article)

        # Sort by published date (newest first)
        unique_news.sort(key=lambda x: x['published_at'], reverse=True)

        return unique_news[:20]  # Return top 20 most recent

    def _get_newsapi_articles(self, symbol: str, hours_back: int) -> List[Dict]:
        """Get news from NewsAPI"""
        articles = []

        if self.news_api_key == 'demo':
            return articles

        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(hours=hours_back)

            # Search terms for the company
            company_map = {
                'TSLA': 'Tesla',
                'AAPL': 'Apple',
                'MSFT': 'Microsoft',
                'GOOGL': 'Google OR Alphabet',
                'AMZN': 'Amazon',
                'NVDA': 'NVIDIA',
                'META': 'Meta OR Facebook',
                'NFLX': 'Netflix',
                'AMD': 'AMD'
            }

            query = company_map.get(symbol, symbol)

            url = f"https://newsapi.org/v2/everything"
            params = {
                'q': f"{query} AND (stock OR trading OR earnings OR revenue)",
                'language': 'en',
                'sortBy': 'publishedAt',
                'from': start_date.strftime('%Y-%m-%d'),
                'to': end_date.strftime('%Y-%m-%d'),
                'apiKey': self.news_api_key
            }

            response = requests.get(url, params=params)
            data = response.json()

            if data.get('status') == 'ok':
                for article in data.get('articles', []):
                    articles.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', ''),
                        'source': article.get('source', {}).get('name', 'NewsAPI'),
                        'published_at': datetime.strptime(article.get('publishedAt', ''), '%Y-%m-%dT%H:%M:%SZ'),
                        'symbol': symbol
                    })

        except Exception as e:
            self.logger.error(f"Error fetching NewsAPI articles for {symbol}: {e}")

        return articles

    def _get_yahoo_news(self, symbol: str) -> List[Dict]:
        """Get news from Yahoo Finance"""
        articles = []

        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news

            for article in news:
                # Parse timestamp (Yahoo provides Unix timestamp)
                published_at = datetime.fromtimestamp(article.get('providerPublishTime', 0))

                articles.append({
                    'title': article.get('title', ''),
                    'description': article.get('summary', ''),
                    'url': article.get('link', ''),
                    'source': article.get('publisher', 'Yahoo Finance'),
                    'published_at': published_at,
                    'symbol': symbol
                })

        except Exception as e:
            self.logger.error(f"Error fetching Yahoo news for {symbol}: {e}")

        return articles

    def _get_rss_feeds(self, symbol: str) -> List[Dict]:
        """Get news from financial RSS feeds"""
        articles = []

        feeds = [
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
            "https://feeds.marketwatch.com/marketwatch/topstories/",
            "https://www.cnbc.com/id/100727362/device/rss/rss.html"
        ]

        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)

                for entry in feed.entries:
                    # Check if article is relevant to our symbol
                    if self._is_relevant_article(entry.title + " " + entry.get('summary', ''), symbol):
                        published_at = datetime.now()
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            published_at = datetime(*entry.published_parsed[:6])

                        articles.append({
                            'title': entry.title,
                            'description': entry.get('summary', ''),
                            'url': entry.get('link', ''),
                            'source': feed.feed.get('title', 'RSS Feed'),
                            'published_at': published_at,
                            'symbol': symbol
                        })

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                self.logger.error(f"Error fetching RSS feed {feed_url}: {e}")

        return articles

    def _is_relevant_article(self, text: str, symbol: str) -> bool:
        """Check if article is relevant to the symbol"""
        text_lower = text.lower()

        # Company keywords mapping
        keywords_map = {
            'TSLA': ['tesla', 'elon musk', 'electric vehicle', 'ev'],
            'AAPL': ['apple', 'iphone', 'ipad', 'mac', 'tim cook'],
            'MSFT': ['microsoft', 'windows', 'office', 'azure', 'satya nadella'],
            'GOOGL': ['google', 'alphabet', 'search', 'youtube', 'android'],
            'AMZN': ['amazon', 'aws', 'prime', 'bezos'],
            'NVDA': ['nvidia', 'gpu', 'ai chip', 'graphics'],
            'META': ['meta', 'facebook', 'instagram', 'metaverse'],
            'NFLX': ['netflix', 'streaming'],
            'AMD': ['amd', 'processor', 'ryzen']
        }

        keywords = keywords_map.get(symbol, [symbol.lower()])
        return any(keyword in text_lower for keyword in keywords)

    def get_market_sentiment_news(self) -> List[Dict]:
        """Get general market sentiment news"""
        articles = []

        try:
            if self.news_api_key != 'demo':
                url = "https://newsapi.org/v2/top-headlines"
                params = {
                    'category': 'business',
                    'country': 'us',
                    'pageSize': 20,
                    'apiKey': self.news_api_key
                }

                response = requests.get(url, params=params)
                data = response.json()

                if data.get('status') == 'ok':
                    for article in data.get('articles', []):
                        articles.append({
                            'title': article.get('title', ''),
                            'description': article.get('description', ''),
                            'url': article.get('url', ''),
                            'source': article.get('source', {}).get('name', 'NewsAPI'),
                            'published_at': datetime.strptime(article.get('publishedAt', ''), '%Y-%m-%dT%H:%M:%SZ'),
                            'symbol': 'MARKET'
                        })

        except Exception as e:
            self.logger.error(f"Error fetching market sentiment news: {e}")

        return articles

    def get_earnings_calendar(self, symbol: str) -> Dict:
        """Get upcoming earnings information"""
        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar

            if calendar is not None and not calendar.empty:
                next_earnings = calendar.iloc[0]
                return {
                    'earnings_date': next_earnings.name,
                    'eps_estimate': next_earnings.get('EPS Estimate', None),
                    'revenue_estimate': next_earnings.get('Revenue Estimate', None),
                    'days_until': (next_earnings.name - datetime.now().date()).days
                }

        except Exception as e:
            self.logger.error(f"Error getting earnings calendar for {symbol}: {e}")

        return {}

    def get_insider_activity(self, symbol: str) -> List[Dict]:
        """Get insider trading activity"""
        insider_data = []

        try:
            ticker = yf.Ticker(symbol)
            insiders = ticker.insider_transactions

            if insiders is not None and not insiders.empty:
                for _, transaction in insiders.head(10).iterrows():
                    insider_data.append({
                        'date': transaction.get('Start Date'),
                        'insider': transaction.get('Insider'),
                        'transaction': transaction.get('Transaction'),
                        'shares': transaction.get('Shares'),
                        'value': transaction.get('Value')
                    })

        except Exception as e:
            self.logger.error(f"Error getting insider activity for {symbol}: {e}")

        return insider_data

if __name__ == "__main__":
    # Test the news collector
    collector = NewsCollector()
    print("Testing TSLA news collection...")

    news = collector.get_stock_news("TSLA", hours_back=24)
    print(f"Found {len(news)} TSLA news articles")

    if news:
        print(f"Latest article: {news[0]['title']}")
        print(f"Source: {news[0]['source']}")
        print(f"Published: {news[0]['published_at']}")

    market_news = collector.get_market_sentiment_news()
    print(f"Found {len(market_news)} market sentiment articles")