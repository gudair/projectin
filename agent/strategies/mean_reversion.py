"""
Mean Reversion Swing Trading Strategy

Based on statistical evidence that prices tend to revert to their mean.
Uses RSI + Bollinger Bands for entry/exit signals.

Entry Conditions (BUY):
- RSI < 30 (oversold)
- Price touches or breaks below lower Bollinger Band
- Volume confirms (above average)

Exit Conditions (SELL):
- RSI > 70 (overbought)
- Price touches upper Bollinger Band
- Stop loss: -3%
- Max hold time: 5 days

Risk Management:
- Max 2% of portfolio per trade
- Max 5 concurrent positions
- Strict stop loss
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Container for technical indicators"""
    rsi: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_percent: float  # Where price is within bands (0 = lower, 1 = upper)
    sma_20: float
    volume_ratio: float  # Current volume / average volume
    atr: float  # Average True Range for volatility


@dataclass
class SwingSignal:
    """A swing trading signal"""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0-1
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning: str
    indicators: TechnicalIndicators


class MeanReversionStrategy:
    """
    Mean Reversion Strategy for Swing Trading

    Statistically-backed strategy that profits from price returning to mean.
    Best in sideways/ranging markets.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        stop_loss_pct: float = 0.03,  # 3% stop loss
        take_profit_pct: float = 0.05,  # 5% take profit
        max_hold_days: int = 5,
        min_volume_ratio: float = 1.0,  # At least average volume
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_hold_days = max_hold_days
        self.min_volume_ratio = min_volume_ratio

    def calculate_rsi(self, closes: List[float]) -> float:
        """Calculate RSI from closing prices"""
        if len(closes) < self.rsi_period + 1:
            return 50.0  # Neutral if not enough data

        # Calculate price changes
        deltas = np.diff(closes)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gains and losses (Wilder's smoothing)
        avg_gain = np.mean(gains[-self.rsi_period:])
        avg_loss = np.mean(losses[-self.rsi_period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_bollinger_bands(
        self, closes: List[float]
    ) -> Tuple[float, float, float, float]:
        """
        Calculate Bollinger Bands

        Returns: (upper, middle, lower, percent_b)
        """
        if len(closes) < self.bb_period:
            price = closes[-1] if closes else 0
            return price * 1.02, price, price * 0.98, 0.5

        # Get last bb_period closes
        recent = closes[-self.bb_period:]

        # Calculate middle band (SMA)
        middle = np.mean(recent)

        # Calculate standard deviation
        std = np.std(recent)

        # Calculate bands
        upper = middle + (self.bb_std * std)
        lower = middle - (self.bb_std * std)

        # Calculate %B (where price is within bands)
        current_price = closes[-1]
        if upper - lower > 0:
            percent_b = (current_price - lower) / (upper - lower)
        else:
            percent_b = 0.5

        return upper, middle, lower, percent_b

    def calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Calculate Average True Range"""
        if len(closes) < period + 1:
            return 0.0

        true_ranges = []
        for i in range(1, min(period + 1, len(closes))):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i - 1])
            low_close = abs(lows[i] - closes[i - 1])
            true_ranges.append(max(high_low, high_close, low_close))

        return np.mean(true_ranges) if true_ranges else 0.0

    def calculate_indicators(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[int],
    ) -> TechnicalIndicators:
        """Calculate all technical indicators for a symbol"""

        rsi = self.calculate_rsi(closes)
        bb_upper, bb_middle, bb_lower, bb_percent = self.calculate_bollinger_bands(closes)
        atr = self.calculate_atr(highs, lows, closes)

        # Volume ratio
        avg_volume = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        current_volume = volumes[-1] if volumes else 0
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        return TechnicalIndicators(
            rsi=rsi,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_percent=bb_percent,
            sma_20=bb_middle,  # Same as BB middle
            volume_ratio=volume_ratio,
            atr=atr,
        )

    def generate_signal(
        self,
        symbol: str,
        current_price: float,
        indicators: TechnicalIndicators,
        has_position: bool = False,
        position_entry_price: float = 0,
        position_entry_date: datetime = None,
        current_date: datetime = None,
    ) -> SwingSignal:
        """
        Generate trading signal based on mean reversion logic

        Returns SwingSignal with BUY, SELL, or HOLD recommendation
        """

        # Default to HOLD
        action = 'HOLD'
        confidence = 0.5
        reasoning_parts = []

        # Calculate stop loss and take profit levels
        stop_loss = current_price * (1 - self.stop_loss_pct)
        take_profit = current_price * (1 + self.take_profit_pct)

        if has_position:
            # Check EXIT conditions
            pnl_pct = (current_price - position_entry_price) / position_entry_price

            # 1. Stop loss hit
            if pnl_pct <= -self.stop_loss_pct:
                action = 'SELL'
                confidence = 1.0
                reasoning_parts.append(f"Stop loss triggered ({pnl_pct:.1%})")

            # 2. Take profit hit
            elif pnl_pct >= self.take_profit_pct:
                action = 'SELL'
                confidence = 0.9
                reasoning_parts.append(f"Take profit reached ({pnl_pct:.1%})")

            # 3. RSI overbought (mean reversion complete)
            elif indicators.rsi >= self.rsi_overbought:
                action = 'SELL'
                confidence = 0.8
                reasoning_parts.append(f"RSI overbought ({indicators.rsi:.0f})")

            # 4. Price at upper Bollinger Band
            elif indicators.bb_percent >= 0.95:
                action = 'SELL'
                confidence = 0.75
                reasoning_parts.append(f"Price at upper BB ({indicators.bb_percent:.0%})")

            # 5. Max hold time exceeded
            elif position_entry_date and current_date:
                hold_days = (current_date - position_entry_date).days
                if hold_days >= self.max_hold_days:
                    action = 'SELL'
                    confidence = 0.7
                    reasoning_parts.append(f"Max hold time ({hold_days} days)")

        else:
            # Check ENTRY conditions for BUY
            buy_signals = 0

            # 1. RSI oversold
            if indicators.rsi <= self.rsi_oversold:
                buy_signals += 2
                reasoning_parts.append(f"RSI oversold ({indicators.rsi:.0f})")
            elif indicators.rsi <= 40:
                buy_signals += 1
                reasoning_parts.append(f"RSI low ({indicators.rsi:.0f})")

            # 2. Price at or below lower Bollinger Band
            if indicators.bb_percent <= 0.05:
                buy_signals += 2
                reasoning_parts.append(f"Price below lower BB ({indicators.bb_percent:.0%})")
            elif indicators.bb_percent <= 0.20:
                buy_signals += 1
                reasoning_parts.append(f"Price near lower BB ({indicators.bb_percent:.0%})")

            # 3. Volume confirmation
            if indicators.volume_ratio >= self.min_volume_ratio:
                buy_signals += 1
                reasoning_parts.append(f"Volume OK ({indicators.volume_ratio:.1f}x)")

            # Decision
            if buy_signals >= 4:
                action = 'BUY'
                confidence = min(0.9, 0.5 + (buy_signals * 0.1))
            elif buy_signals >= 3:
                action = 'BUY'
                confidence = 0.7

            # Adjust stop loss based on ATR if available
            if indicators.atr > 0:
                atr_stop = current_price - (2 * indicators.atr)
                stop_loss = max(stop_loss, atr_stop)  # Use tighter of the two

        return SwingSignal(
            symbol=symbol,
            action=action,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=" | ".join(reasoning_parts) if reasoning_parts else "No signal",
            indicators=indicators,
        )


def calculate_indicators_from_daily_bars(
    daily_closes: List[float],
    daily_highs: List[float],
    daily_lows: List[float],
    daily_volumes: List[int],
) -> Optional[TechnicalIndicators]:
    """
    Helper function to calculate indicators from daily OHLCV data

    Requires at least 20 days of data for reliable indicators.
    """
    if len(daily_closes) < 20:
        return None

    strategy = MeanReversionStrategy()
    return strategy.calculate_indicators(
        closes=daily_closes,
        highs=daily_highs,
        lows=daily_lows,
        volumes=daily_volumes,
    )
