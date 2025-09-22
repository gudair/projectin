import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from data.collectors.market_data import MarketDataCollector
from data.collectors.news_collector import NewsCollector
from data.processors.sentiment_analyzer import SentimentAnalyzer
from config.settings import SIGNAL_WEIGHTS, WATCHLIST, INITIAL_STOCK

class SignalType(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WEAK_BUY = "weak_buy"
    HOLD = "hold"
    WEAK_SELL = "weak_sell"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

@dataclass
class TradingSignal:
    symbol: str
    signal_type: SignalType
    confidence: float  # 0.0 - 1.0
    strength: float    # 0.0 - 1.0
    target_price: Optional[float]
    stop_loss: Optional[float]
    reasoning: str
    components: Dict[str, float]  # Individual signal component scores
    timestamp: datetime

class SignalGenerator:
    def __init__(self):
        self.market_data = MarketDataCollector()
        self.news_collector = NewsCollector()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.logger = logging.getLogger(__name__)

    def generate_signal(self, symbol: str) -> TradingSignal:
        """Generate comprehensive trading signal for a symbol"""
        try:
            # Collect all necessary data
            market_snapshot = self.market_data.get_market_snapshot()
            technical_indicators = market_snapshot.get(symbol, {})

            if not technical_indicators:
                return self._get_hold_signal(symbol, "No market data available")

            # Get news and sentiment
            news_articles = self.news_collector.get_stock_news(symbol, hours_back=24)
            news_sentiment = self.sentiment_analyzer.analyze_news_batch(news_articles)

            # Generate individual signal components
            technical_signal = self._generate_technical_signal(technical_indicators)
            news_signal = self._generate_news_signal(news_sentiment)
            volume_signal = self._generate_volume_signal(technical_indicators)
            momentum_signal = self._generate_momentum_signal(technical_indicators)

            # Combine signals using weights
            components = {
                'technical': technical_signal['score'],
                'news_sentiment': news_signal['score'],
                'volume': volume_signal['score'],
                'momentum': momentum_signal['score']
            }

            # Calculate weighted score
            weighted_score = (
                components['technical'] * SIGNAL_WEIGHTS['technical'] +
                components['news_sentiment'] * SIGNAL_WEIGHTS['news_sentiment'] +
                components['volume'] * SIGNAL_WEIGHTS['volume'] +
                components['momentum'] * SIGNAL_WEIGHTS.get('momentum', 0.1)
            )

            # Determine signal type and confidence
            signal_type, confidence = self._score_to_signal_type(weighted_score)

            # Calculate target price and stop loss
            current_price = technical_indicators.get('current_price', 0)
            target_price, stop_loss = self._calculate_price_targets(
                current_price, signal_type, technical_indicators
            )

            # Create reasoning
            reasoning = self._create_reasoning(
                technical_signal, news_signal, volume_signal, momentum_signal, weighted_score
            )

            return TradingSignal(
                symbol=symbol,
                signal_type=signal_type,
                confidence=confidence,
                strength=abs(weighted_score),
                target_price=target_price,
                stop_loss=stop_loss,
                reasoning=reasoning,
                components=components,
                timestamp=datetime.now()
            )

        except Exception as e:
            self.logger.error(f"Error generating signal for {symbol}: {e}")
            return self._get_hold_signal(symbol, f"Error in signal generation: {str(e)}")

    def _generate_technical_signal(self, indicators: Dict) -> Dict:
        """Generate signal based on technical indicators"""
        score = 0.0
        signals = []

        try:
            current_price = indicators.get('current_price', 0)
            rsi = indicators.get('rsi', 50)
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            sma_20 = indicators.get('sma_20', current_price)
            sma_50 = indicators.get('sma_50', current_price)
            bb_upper = indicators.get('bb_upper', current_price)
            bb_lower = indicators.get('bb_lower', current_price)

            # RSI signals
            if rsi < 30:
                score += 0.3  # Oversold
                signals.append("RSI oversold")
            elif rsi > 70:
                score -= 0.3  # Overbought
                signals.append("RSI overbought")
            elif rsi < 40:
                score += 0.1  # Slightly oversold
            elif rsi > 60:
                score -= 0.1  # Slightly overbought

            # MACD signals
            if macd > macd_signal and macd > 0:
                score += 0.2  # Bullish MACD
                signals.append("MACD bullish")
            elif macd < macd_signal and macd < 0:
                score -= 0.2  # Bearish MACD
                signals.append("MACD bearish")

            # Moving average signals
            if current_price > sma_20 > sma_50:
                score += 0.2  # Uptrend
                signals.append("Price above moving averages")
            elif current_price < sma_20 < sma_50:
                score -= 0.2  # Downtrend
                signals.append("Price below moving averages")

            # Bollinger Bands signals
            if current_price <= bb_lower:
                score += 0.15  # Oversold
                signals.append("Price at lower Bollinger Band")
            elif current_price >= bb_upper:
                score -= 0.15  # Overbought
                signals.append("Price at upper Bollinger Band")

            # Normalize score to [-1, 1] range
            score = max(-1.0, min(1.0, score))

            return {
                'score': score,
                'signals': signals,
                'details': {
                    'rsi': rsi,
                    'macd_bullish': macd > macd_signal,
                    'price_vs_sma20': current_price / sma_20 if sma_20 > 0 else 1,
                    'bb_position': (current_price - bb_lower) / (bb_upper - bb_lower) if bb_upper > bb_lower else 0.5
                }
            }

        except Exception as e:
            self.logger.error(f"Error in technical signal generation: {e}")
            return {'score': 0.0, 'signals': [], 'details': {}}

    def _generate_news_signal(self, news_sentiment: Dict) -> Dict:
        """Generate signal based on news sentiment"""
        try:
            if news_sentiment['article_count'] == 0:
                return {'score': 0.0, 'signals': ['No news available'], 'details': news_sentiment}

            # Base score from overall sentiment
            score = news_sentiment['overall_score']

            # Adjust based on confidence and impact
            confidence_factor = news_sentiment['confidence']
            impact_factor = news_sentiment['average_impact']

            # Boost score if high confidence and impact
            score *= (0.5 + confidence_factor * 0.5)  # Min 50% of original score
            score *= (1 + impact_factor)  # Boost by impact

            signals = []
            if news_sentiment['overall_sentiment'] == 'positive':
                signals.append(f"Positive news sentiment ({news_sentiment['positive_count']} articles)")
            elif news_sentiment['overall_sentiment'] == 'negative':
                signals.append(f"Negative news sentiment ({news_sentiment['negative_count']} articles)")
            else:
                signals.append("Neutral news sentiment")

            if news_sentiment['high_impact_count'] > 0:
                signals.append(f"{news_sentiment['high_impact_count']} high-impact articles")

            return {
                'score': max(-1.0, min(1.0, score)),
                'signals': signals,
                'details': news_sentiment
            }

        except Exception as e:
            self.logger.error(f"Error in news signal generation: {e}")
            return {'score': 0.0, 'signals': [], 'details': {}}

    def _generate_volume_signal(self, indicators: Dict) -> Dict:
        """Generate signal based on volume analysis"""
        try:
            volume_ratio = indicators.get('volume_ratio', 1.0)
            daily_change = indicators.get('daily_change', 0)

            score = 0.0
            signals = []

            # High volume with price increase = bullish
            if volume_ratio > 2.0 and daily_change > 0.02:
                score += 0.4
                signals.append("High volume with price increase")
            # High volume with price decrease = bearish
            elif volume_ratio > 2.0 and daily_change < -0.02:
                score -= 0.4
                signals.append("High volume with price decrease")
            # Moderate volume signals
            elif volume_ratio > 1.5 and daily_change > 0.01:
                score += 0.2
                signals.append("Above average volume with price gain")
            elif volume_ratio > 1.5 and daily_change < -0.01:
                score -= 0.2
                signals.append("Above average volume with price decline")
            # Low volume = uncertain
            elif volume_ratio < 0.5:
                signals.append("Low volume - limited conviction")

            return {
                'score': max(-1.0, min(1.0, score)),
                'signals': signals,
                'details': {
                    'volume_ratio': volume_ratio,
                    'daily_change': daily_change
                }
            }

        except Exception as e:
            self.logger.error(f"Error in volume signal generation: {e}")
            return {'score': 0.0, 'signals': [], 'details': {}}

    def _generate_momentum_signal(self, indicators: Dict) -> Dict:
        """Generate signal based on momentum indicators"""
        try:
            daily_change = indicators.get('daily_change', 0)
            current_price = indicators.get('current_price', 0)
            sma_20 = indicators.get('sma_20', current_price)

            score = 0.0
            signals = []

            # Price momentum
            if daily_change > 0.03:
                score += 0.3
                signals.append("Strong positive momentum")
            elif daily_change > 0.01:
                score += 0.1
                signals.append("Positive momentum")
            elif daily_change < -0.03:
                score -= 0.3
                signals.append("Strong negative momentum")
            elif daily_change < -0.01:
                score -= 0.1
                signals.append("Negative momentum")

            # Trend momentum
            if current_price > sma_20 * 1.02:
                score += 0.2
                signals.append("Price well above trend")
            elif current_price < sma_20 * 0.98:
                score -= 0.2
                signals.append("Price well below trend")

            return {
                'score': max(-1.0, min(1.0, score)),
                'signals': signals,
                'details': {
                    'daily_change_percent': daily_change * 100,
                    'price_vs_trend': (current_price / sma_20 - 1) * 100 if sma_20 > 0 else 0
                }
            }

        except Exception as e:
            self.logger.error(f"Error in momentum signal generation: {e}")
            return {'score': 0.0, 'signals': [], 'details': {}}

    def _score_to_signal_type(self, score: float) -> Tuple[SignalType, float]:
        """Convert numerical score to signal type and confidence"""
        abs_score = abs(score)
        confidence = min(1.0, abs_score * 2)  # Higher absolute score = higher confidence

        if score >= 0.6:
            return SignalType.STRONG_BUY, confidence
        elif score >= 0.3:
            return SignalType.BUY, confidence
        elif score >= 0.1:
            return SignalType.WEAK_BUY, confidence
        elif score <= -0.6:
            return SignalType.STRONG_SELL, confidence
        elif score <= -0.3:
            return SignalType.SELL, confidence
        elif score <= -0.1:
            return SignalType.WEAK_SELL, confidence
        else:
            return SignalType.HOLD, 0.5

    def _calculate_price_targets(self, current_price: float, signal_type: SignalType, indicators: Dict) -> Tuple[Optional[float], Optional[float]]:
        """Calculate target price and stop loss based on signal and technical levels"""
        if current_price <= 0:
            return None, None

        # Get technical levels
        bb_upper = indicators.get('bb_upper', current_price * 1.02)
        bb_lower = indicators.get('bb_lower', current_price * 0.98)
        sma_20 = indicators.get('sma_20', current_price)

        target_price = None
        stop_loss = None

        if signal_type in [SignalType.STRONG_BUY, SignalType.BUY]:
            # Target: Bollinger Band upper or 3-5% gain
            target_price = max(bb_upper, current_price * 1.03)
            # Stop loss: Below 20-day SMA or 2% loss
            stop_loss = min(sma_20 * 0.99, current_price * 0.98)

        elif signal_type == SignalType.WEAK_BUY:
            # Conservative targets
            target_price = current_price * 1.02
            stop_loss = current_price * 0.99

        elif signal_type in [SignalType.STRONG_SELL, SignalType.SELL]:
            # For short positions (if implemented)
            target_price = min(bb_lower, current_price * 0.97)
            stop_loss = max(sma_20 * 1.01, current_price * 1.02)

        elif signal_type == SignalType.WEAK_SELL:
            target_price = current_price * 0.98
            stop_loss = current_price * 1.01

        return target_price, stop_loss

    def _create_reasoning(self, technical: Dict, news: Dict, volume: Dict, momentum: Dict, final_score: float) -> str:
        """Create human-readable reasoning for the signal"""
        reasoning_parts = []

        # Technical analysis reasoning
        if technical['signals']:
            reasoning_parts.append(f"Technical: {', '.join(technical['signals'])}")

        # News sentiment reasoning
        if news['signals']:
            reasoning_parts.append(f"News: {', '.join(news['signals'])}")

        # Volume reasoning
        if volume['signals']:
            reasoning_parts.append(f"Volume: {', '.join(volume['signals'])}")

        # Momentum reasoning
        if momentum['signals']:
            reasoning_parts.append(f"Momentum: {', '.join(momentum['signals'])}")

        # Overall assessment
        if final_score > 0.3:
            reasoning_parts.append("Overall assessment: Bullish sentiment")
        elif final_score < -0.3:
            reasoning_parts.append("Overall assessment: Bearish sentiment")
        else:
            reasoning_parts.append("Overall assessment: Neutral/Mixed signals")

        return " | ".join(reasoning_parts) if reasoning_parts else "No clear signals available"

    def _get_hold_signal(self, symbol: str, reason: str) -> TradingSignal:
        """Create a default HOLD signal"""
        return TradingSignal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            confidence=0.5,
            strength=0.0,
            target_price=None,
            stop_loss=None,
            reasoning=reason,
            components={'technical': 0.0, 'news_sentiment': 0.0, 'volume': 0.0, 'momentum': 0.0},
            timestamp=datetime.now()
        )

    def generate_watchlist_signals(self) -> Dict[str, TradingSignal]:
        """Generate signals for all symbols in watchlist"""
        signals = {}
        symbols = [INITIAL_STOCK] + WATCHLIST

        for symbol in symbols:
            try:
                signal = self.generate_signal(symbol)
                signals[symbol] = signal
                self.logger.info(f"Generated signal for {symbol}: {signal.signal_type.value} (confidence: {signal.confidence:.2f})")
            except Exception as e:
                self.logger.error(f"Error generating signal for {symbol}: {e}")
                signals[symbol] = self._get_hold_signal(symbol, f"Error: {str(e)}")

        return signals

    def get_top_opportunities(self, signals: Dict[str, TradingSignal], limit: int = 3) -> List[TradingSignal]:
        """Get top trading opportunities sorted by signal strength and confidence"""
        # Filter out HOLD signals
        actionable_signals = [
            signal for signal in signals.values()
            if signal.signal_type != SignalType.HOLD
        ]

        # Sort by combined score of strength and confidence
        actionable_signals.sort(
            key=lambda x: x.strength * x.confidence,
            reverse=True
        )

        return actionable_signals[:limit]

if __name__ == "__main__":
    # Test signal generation
    generator = SignalGenerator()

    print("Generating signal for TSLA...")
    signal = generator.generate_signal("TSLA")

    print(f"Signal: {signal.signal_type.value}")
    print(f"Confidence: {signal.confidence:.2f}")
    print(f"Strength: {signal.strength:.2f}")
    print(f"Target: ${signal.target_price:.2f}" if signal.target_price else "Target: N/A")
    print(f"Stop Loss: ${signal.stop_loss:.2f}" if signal.stop_loss else "Stop Loss: N/A")
    print(f"Reasoning: {signal.reasoning}")
    print(f"Components: {signal.components}")

    print("\nGenerating watchlist signals...")
    all_signals = generator.generate_watchlist_signals()

    top_opportunities = generator.get_top_opportunities(all_signals)
    print(f"\nTop {len(top_opportunities)} opportunities:")
    for i, opp in enumerate(top_opportunities, 1):
        print(f"{i}. {opp.symbol}: {opp.signal_type.value} (strength: {opp.strength:.2f}, confidence: {opp.confidence:.2f})")