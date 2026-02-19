"""
Day Trading Strategy

Intraday momentum and mean reversion strategy.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any

from agent.strategies.base import BaseStrategy, StrategySignal


class DayTradingStrategy(BaseStrategy):
    """
    Day trading strategy combining:
    - RSI oversold/overbought
    - MACD momentum
    - Volume confirmation
    - Bollinger Band mean reversion
    - Support/resistance levels
    """

    def __init__(
        self,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
        volume_threshold: float = 1.5,
        bb_squeeze_threshold: float = 0.02,
        min_confidence: float = 0.6,
    ):
        super().__init__(
            name="DayTrading",
            description="Intraday momentum and mean reversion strategy"
        )

        # Parameters
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.volume_threshold = volume_threshold
        self.bb_squeeze_threshold = bb_squeeze_threshold
        self.min_confidence = min_confidence

    def analyze(
        self,
        symbol: str,
        price_data: Dict[str, Any],
        technical_indicators: Dict[str, Any],
        market_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[StrategySignal]:
        """Analyze for day trading opportunities"""

        # Extract indicators
        current_price = technical_indicators.get('current_price', 0)
        rsi = technical_indicators.get('rsi', 50)
        macd = technical_indicators.get('macd', 0)
        macd_signal = technical_indicators.get('macd_signal', 0)
        volume_ratio = technical_indicators.get('volume_ratio', 1.0)
        bb_upper = technical_indicators.get('bb_upper', current_price * 1.02)
        bb_lower = technical_indicators.get('bb_lower', current_price * 0.98)
        sma_20 = technical_indicators.get('sma_20', current_price)

        if current_price <= 0:
            return None

        # Calculate signal components
        signals = []
        confidence_factors = []

        # RSI Analysis
        rsi_signal = self._analyze_rsi(rsi)
        if rsi_signal:
            signals.append(rsi_signal)
            confidence_factors.append(abs(rsi - 50) / 50)  # Stronger at extremes

        # MACD Analysis
        macd_signal_result = self._analyze_macd(macd, macd_signal)
        if macd_signal_result:
            signals.append(macd_signal_result)
            confidence_factors.append(0.3)

        # Volume Analysis
        volume_confirms = volume_ratio >= self.volume_threshold
        if volume_confirms:
            confidence_factors.append(min(0.3, (volume_ratio - 1) * 0.15))

        # Bollinger Band Analysis
        bb_signal = self._analyze_bollinger(current_price, bb_upper, bb_lower)
        if bb_signal:
            signals.append(bb_signal)
            confidence_factors.append(0.25)

        # Trend Analysis (price vs SMA)
        trend_signal = self._analyze_trend(current_price, sma_20)
        if trend_signal:
            signals.append(trend_signal)
            confidence_factors.append(0.2)

        # Market Context Adjustment
        regime_modifier = 1.0
        if market_context:
            regime = market_context.get('regime', 'neutral')
            regime_modifier = {
                'risk_on': 1.1,
                'neutral': 1.0,
                'risk_off': 0.8,
                'high_volatility': 0.6,
            }.get(regime, 1.0)

        # Aggregate signals
        if not signals:
            return None

        # Count buy vs sell signals
        buy_signals = [s for s in signals if s == 'BUY']
        sell_signals = [s for s in signals if s == 'SELL']

        if len(buy_signals) > len(sell_signals):
            action = 'BUY'
            signal_strength = len(buy_signals) / len(signals)
        elif len(sell_signals) > len(buy_signals):
            action = 'SELL'
            signal_strength = len(sell_signals) / len(signals)
        else:
            return None  # Conflicting signals

        # Calculate confidence
        base_confidence = sum(confidence_factors) / max(len(confidence_factors), 1)
        confidence = min(1.0, base_confidence * regime_modifier)

        if confidence < self.min_confidence:
            return None

        # Calculate price targets
        stop_loss, take_profit = self._calculate_targets(
            current_price, action, technical_indicators
        )

        # Build reasoning
        reasoning = self._build_reasoning(
            action, rsi, macd > macd_signal, volume_ratio, current_price, bb_lower, bb_upper
        )

        signal = StrategySignal(
            symbol=symbol,
            action=action,
            strength=signal_strength,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=reasoning,
            metadata={
                'rsi': rsi,
                'macd_bullish': macd > macd_signal,
                'volume_ratio': volume_ratio,
                'regime': market_context.get('regime') if market_context else None,
            },
            timestamp=datetime.now(),
        )

        if self.validate_signal(signal):
            self._record_signal()
            return signal

        return None

    def _analyze_rsi(self, rsi: float) -> Optional[str]:
        """Analyze RSI for signals"""
        if rsi < self.rsi_oversold:
            return 'BUY'
        elif rsi > self.rsi_overbought:
            return 'SELL'
        return None

    def _analyze_macd(self, macd: float, signal: float) -> Optional[str]:
        """Analyze MACD for signals"""
        if macd > signal and macd > 0:
            return 'BUY'
        elif macd < signal and macd < 0:
            return 'SELL'
        return None

    def _analyze_bollinger(
        self, price: float, upper: float, lower: float
    ) -> Optional[str]:
        """Analyze Bollinger Bands for signals"""
        bb_width = (upper - lower) / price

        if price <= lower * 1.01:  # Near or below lower band
            return 'BUY'
        elif price >= upper * 0.99:  # Near or above upper band
            return 'SELL'
        elif bb_width < self.bb_squeeze_threshold:
            # Squeeze - wait for breakout
            return None

        return None

    def _analyze_trend(self, price: float, sma: float) -> Optional[str]:
        """Analyze price vs SMA trend"""
        diff_pct = (price - sma) / sma

        if diff_pct > 0.02:  # Price well above SMA
            return 'BUY'
        elif diff_pct < -0.02:  # Price well below SMA
            return 'SELL'

        return None

    def _calculate_targets(
        self,
        price: float,
        action: str,
        indicators: Dict[str, Any],
    ) -> tuple:
        """Calculate stop loss and take profit"""
        bb_upper = indicators.get('bb_upper', price * 1.02)
        bb_lower = indicators.get('bb_lower', price * 0.98)
        sma_20 = indicators.get('sma_20', price)

        if action == 'BUY':
            # Stop below recent support / lower BB
            stop_loss = min(bb_lower, sma_20 * 0.98, price * 0.98)

            # Target at upper BB or 3% gain
            take_profit = max(bb_upper, price * 1.03)

        else:  # SELL
            # Stop above recent resistance / upper BB
            stop_loss = max(bb_upper, sma_20 * 1.02, price * 1.02)

            # Target at lower BB or 3% decline
            take_profit = min(bb_lower, price * 0.97)

        return stop_loss, take_profit

    def _build_reasoning(
        self,
        action: str,
        rsi: float,
        macd_bullish: bool,
        volume_ratio: float,
        price: float,
        bb_lower: float,
        bb_upper: float,
    ) -> str:
        """Build human-readable reasoning"""
        parts = []

        if action == 'BUY':
            if rsi < self.rsi_oversold:
                parts.append(f"RSI oversold at {rsi:.1f}")
            if macd_bullish:
                parts.append("bullish MACD crossover")
            if price <= bb_lower * 1.01:
                parts.append("price at lower Bollinger Band")
            if volume_ratio > self.volume_threshold:
                parts.append(f"high volume ({volume_ratio:.1f}x)")

        else:  # SELL
            if rsi > self.rsi_overbought:
                parts.append(f"RSI overbought at {rsi:.1f}")
            if not macd_bullish:
                parts.append("bearish MACD crossover")
            if price >= bb_upper * 0.99:
                parts.append("price at upper Bollinger Band")
            if volume_ratio > self.volume_threshold:
                parts.append(f"high volume ({volume_ratio:.1f}x)")

        if parts:
            return f"{action} signal: {', '.join(parts)}"

        return f"{action} signal based on technical confluence"

    def get_required_indicators(self) -> List[str]:
        return [
            'rsi',
            'macd',
            'macd_signal',
            'bb_upper',
            'bb_lower',
            'sma_20',
            'volume_ratio',
            'current_price',
        ]

    def get_parameters(self) -> Dict[str, Any]:
        return {
            'rsi_oversold': self.rsi_oversold,
            'rsi_overbought': self.rsi_overbought,
            'volume_threshold': self.volume_threshold,
            'bb_squeeze_threshold': self.bb_squeeze_threshold,
            'min_confidence': self.min_confidence,
        }

    def set_parameters(self, params: Dict[str, Any]):
        if 'rsi_oversold' in params:
            self.rsi_oversold = params['rsi_oversold']
        if 'rsi_overbought' in params:
            self.rsi_overbought = params['rsi_overbought']
        if 'volume_threshold' in params:
            self.volume_threshold = params['volume_threshold']
        if 'bb_squeeze_threshold' in params:
            self.bb_squeeze_threshold = params['bb_squeeze_threshold']
        if 'min_confidence' in params:
            self.min_confidence = params['min_confidence']
