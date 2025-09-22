from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import logging
from typing import Dict, List, Optional, Tuple
import re

class SentimentAnalyzer:
    def __init__(self):
        self.vader = SentimentIntensityAnalyzer()
        self.logger = logging.getLogger(__name__)

        # Financial keywords for enhanced sentiment analysis
        self.bullish_keywords = [
            'bullish', 'buy', 'strong buy', 'upgrade', 'outperform', 'positive',
            'growth', 'increase', 'profit', 'revenue beat', 'earnings beat',
            'expansion', 'partnership', 'acquisition', 'breakthrough', 'innovation',
            'rally', 'surge', 'moon', 'rocket', 'gain', 'up', 'rise', 'soar'
        ]

        self.bearish_keywords = [
            'bearish', 'sell', 'strong sell', 'downgrade', 'underperform', 'negative',
            'decline', 'decrease', 'loss', 'revenue miss', 'earnings miss',
            'contraction', 'lawsuit', 'investigation', 'scandal', 'problem',
            'crash', 'plunge', 'dump', 'drop', 'fall', 'down', 'sink', 'dive'
        ]

        # High impact financial terms
        self.high_impact_terms = [
            'earnings', 'revenue', 'guidance', 'merger', 'acquisition', 'ipo',
            'bankruptcy', 'delisting', 'sec investigation', 'fda approval',
            'clinical trial', 'patent', 'lawsuit', 'dividend', 'split'
        ]

    def analyze_text(self, text: str) -> Dict:
        """Comprehensive sentiment analysis of text"""
        if not text:
            return self._get_neutral_sentiment()

        try:
            # Clean text
            clean_text = self._clean_text(text)

            # Multiple sentiment analysis approaches
            textblob_sentiment = self._textblob_analysis(clean_text)
            vader_sentiment = self._vader_analysis(clean_text)
            keyword_sentiment = self._keyword_analysis(clean_text)

            # Combine sentiments with weights
            combined_score = (
                textblob_sentiment['polarity'] * 0.3 +
                vader_sentiment['compound'] * 0.4 +
                keyword_sentiment['score'] * 0.3
            )

            # Determine overall sentiment
            if combined_score >= 0.1:
                sentiment_label = 'positive'
            elif combined_score <= -0.1:
                sentiment_label = 'negative'
            else:
                sentiment_label = 'neutral'

            # Calculate confidence based on agreement between methods
            confidence = self._calculate_confidence([
                textblob_sentiment['polarity'],
                vader_sentiment['compound'],
                keyword_sentiment['score']
            ])

            # Check for high impact terms
            impact_score = self._calculate_impact(clean_text)

            return {
                'sentiment': sentiment_label,
                'score': combined_score,
                'confidence': confidence,
                'impact': impact_score,
                'methods': {
                    'textblob': textblob_sentiment,
                    'vader': vader_sentiment,
                    'keywords': keyword_sentiment
                }
            }

        except Exception as e:
            self.logger.error(f"Error analyzing sentiment: {e}")
            return self._get_neutral_sentiment()

    def _clean_text(self, text: str) -> str:
        """Clean and preprocess text"""
        # Remove URLs
        text = re.sub(r'http\S+|www.\S+', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text.lower()

    def _textblob_analysis(self, text: str) -> Dict:
        """TextBlob sentiment analysis"""
        blob = TextBlob(text)
        return {
            'polarity': blob.sentiment.polarity,
            'subjectivity': blob.sentiment.subjectivity
        }

    def _vader_analysis(self, text: str) -> Dict:
        """VADER sentiment analysis"""
        scores = self.vader.polarity_scores(text)
        return scores

    def _keyword_analysis(self, text: str) -> Dict:
        """Custom keyword-based sentiment analysis"""
        bullish_count = sum(1 for word in self.bullish_keywords if word in text)
        bearish_count = sum(1 for word in self.bearish_keywords if word in text)

        total_keywords = bullish_count + bearish_count
        if total_keywords == 0:
            return {'score': 0, 'bullish_count': 0, 'bearish_count': 0}

        # Calculate sentiment score
        score = (bullish_count - bearish_count) / total_keywords

        return {
            'score': score,
            'bullish_count': bullish_count,
            'bearish_count': bearish_count
        }

    def _calculate_confidence(self, scores: List[float]) -> float:
        """Calculate confidence based on agreement between methods"""
        if len(scores) < 2:
            return 0.5

        # Calculate standard deviation (lower = more agreement = higher confidence)
        mean_score = sum(scores) / len(scores)
        variance = sum((x - mean_score) ** 2 for x in scores) / len(scores)
        std_dev = variance ** 0.5

        # Convert to confidence (inverse relationship with std_dev)
        confidence = max(0.1, min(1.0, 1 - std_dev))
        return confidence

    def _calculate_impact(self, text: str) -> float:
        """Calculate potential market impact based on keywords"""
        impact_count = sum(1 for term in self.high_impact_terms if term in text)
        return min(1.0, impact_count * 0.2)  # Max impact = 1.0

    def _get_neutral_sentiment(self) -> Dict:
        """Return neutral sentiment when analysis fails"""
        return {
            'sentiment': 'neutral',
            'score': 0.0,
            'confidence': 0.5,
            'impact': 0.0,
            'methods': {
                'textblob': {'polarity': 0, 'subjectivity': 0},
                'vader': {'compound': 0, 'pos': 0, 'neu': 1, 'neg': 0},
                'keywords': {'score': 0, 'bullish_count': 0, 'bearish_count': 0}
            }
        }

    def analyze_news_batch(self, news_articles: List[Dict]) -> Dict:
        """Analyze sentiment for a batch of news articles"""
        if not news_articles:
            return {
                'overall_sentiment': 'neutral',
                'overall_score': 0.0,
                'confidence': 0.5,
                'article_count': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'high_impact_count': 0
            }

        sentiments = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        high_impact_count = 0
        total_impact = 0

        for article in news_articles:
            # Analyze title and description together
            text = f"{article.get('title', '')} {article.get('description', '')}"
            sentiment_result = self.analyze_text(text)

            sentiments.append(sentiment_result)

            # Count sentiment categories
            if sentiment_result['sentiment'] == 'positive':
                positive_count += 1
            elif sentiment_result['sentiment'] == 'negative':
                negative_count += 1
            else:
                neutral_count += 1

            # Count high impact articles
            if sentiment_result['impact'] > 0.5:
                high_impact_count += 1

            total_impact += sentiment_result['impact']

        # Calculate overall metrics
        overall_score = sum(s['score'] for s in sentiments) / len(sentiments)
        overall_confidence = sum(s['confidence'] for s in sentiments) / len(sentiments)
        average_impact = total_impact / len(sentiments)

        # Determine overall sentiment
        if overall_score >= 0.1:
            overall_sentiment = 'positive'
        elif overall_score <= -0.1:
            overall_sentiment = 'negative'
        else:
            overall_sentiment = 'neutral'

        return {
            'overall_sentiment': overall_sentiment,
            'overall_score': overall_score,
            'confidence': overall_confidence,
            'average_impact': average_impact,
            'article_count': len(news_articles),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'high_impact_count': high_impact_count,
            'sentiment_distribution': {
                'positive_ratio': positive_count / len(news_articles),
                'negative_ratio': negative_count / len(news_articles),
                'neutral_ratio': neutral_count / len(news_articles)
            }
        }

    def get_sentiment_signal(self, news_analysis: Dict) -> Dict:
        """Convert sentiment analysis to trading signal"""
        if news_analysis['article_count'] == 0:
            return {'signal': 'hold', 'strength': 0, 'reason': 'No news available'}

        score = news_analysis['overall_score']
        confidence = news_analysis['confidence']
        impact = news_analysis['average_impact']

        # Calculate signal strength (0-1)
        strength = abs(score) * confidence * (1 + impact)
        strength = min(1.0, strength)

        # Determine signal
        if score > 0.2 and confidence > 0.6:
            signal = 'buy'
            reason = f"Strong positive sentiment (score: {score:.2f}, conf: {confidence:.2f})"
        elif score < -0.2 and confidence > 0.6:
            signal = 'sell'
            reason = f"Strong negative sentiment (score: {score:.2f}, conf: {confidence:.2f})"
        elif abs(score) > 0.1 and confidence > 0.5:
            signal = 'weak_buy' if score > 0 else 'weak_sell'
            reason = f"Moderate sentiment (score: {score:.2f}, conf: {confidence:.2f})"
        else:
            signal = 'hold'
            reason = f"Neutral/uncertain sentiment (score: {score:.2f}, conf: {confidence:.2f})"

        return {
            'signal': signal,
            'strength': strength,
            'reason': reason,
            'details': {
                'sentiment_score': score,
                'confidence': confidence,
                'impact': impact,
                'high_impact_articles': news_analysis['high_impact_count']
            }
        }

if __name__ == "__main__":
    # Test the sentiment analyzer
    analyzer = SentimentAnalyzer()

    # Test individual text analysis
    test_texts = [
        "Tesla reports record quarterly earnings, beating estimates",
        "Tesla stock plunges on disappointing delivery numbers",
        "Tesla announces new gigafactory expansion plans"
    ]

    for text in test_texts:
        result = analyzer.analyze_text(text)
        print(f"Text: {text}")
        print(f"Sentiment: {result['sentiment']} (score: {result['score']:.2f})")
        print(f"Confidence: {result['confidence']:.2f}, Impact: {result['impact']:.2f}")
        print("-" * 50)