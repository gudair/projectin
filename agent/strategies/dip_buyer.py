"""
Dip Buyer Strategy

Based on analysis of optimal trades, this strategy:
1. Buys after a red day (> 1% down)
2. Confirms with high intraday range (volatility)
3. Focuses on high-beta tech/semiconductor stocks
4. Holds for 3-4 days

This is different from mean reversion (RSI oversold) - it's "buy the dip"
with momentum confirmation.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DipSignal:
    """A dip buying signal"""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning: str
    # Key metrics
    prev_day_change: float
    day_range_pct: float
    is_high_beta: bool


@dataclass
class DipBuyerConfig:
    """Configuration for dip buyer strategy"""
    # Entry criteria
    min_prev_day_drop: float = -0.01  # Previous day must be down at least 1%
    min_day_range: float = 0.02  # Current day range must be > 2%

    # Exit criteria
    stop_loss_pct: float = 0.03  # 3% stop loss
    take_profit_pct: float = 0.08  # 8% take profit (based on avg optimal gain)
    max_hold_days: int = 4  # Optimal hold time from analysis

    # High-beta sectors (semiconductors, tech)
    high_beta_symbols: List[str] = None

    def __post_init__(self):
        if self.high_beta_symbols is None:
            # Semiconductors and high-beta tech (best performers in analysis)
            self.high_beta_symbols = [
                'AMD', 'NVDA', 'QCOM', 'MU', 'INTC', 'AVGO', 'MRVL', 'AMAT',
                'TSLA', 'META', 'NFLX', 'CRM', 'ORCL', 'AMZN', 'GOOGL',
                'COIN', 'MSTR', 'RIOT', 'SQ', 'SHOP', 'SNOW', 'PLTR',
            ]


class DipBuyerStrategy:
    """
    Dip Buyer Strategy

    Based on optimal trade analysis:
    - Best entries: after a down day > 1%
    - Best hold time: 3-4 days
    - Best performers: high-beta tech/semiconductors
    """

    def __init__(self, config: DipBuyerConfig = None):
        self.config = config or DipBuyerConfig()

    def calculate_metrics(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Tuple[float, float]:
        """
        Calculate key metrics for dip detection

        Returns:
            (prev_day_change_pct, today_range_pct)
        """
        if len(closes) < 2:
            return 0.0, 0.0

        # Previous day change
        prev_day_change = (closes[-2] - closes[-3]) / closes[-3] if len(closes) >= 3 else 0

        # Today's range as percentage
        today_range = (highs[-1] - lows[-1]) / closes[-1] if closes[-1] > 0 else 0

        return prev_day_change, today_range

    def is_high_beta(self, symbol: str) -> bool:
        """Check if symbol is in high-beta category"""
        return symbol.upper() in self.config.high_beta_symbols

    def generate_signal(
        self,
        symbol: str,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        has_position: bool = False,
        position_entry_price: float = 0,
        position_entry_date: datetime = None,
        current_date: datetime = None,
    ) -> DipSignal:
        """
        Generate trading signal based on dip buying logic
        """
        if len(closes) < 3:
            return self._hold_signal(symbol, closes[-1] if closes else 0)

        current_price = closes[-1]
        prev_day_change, day_range = self.calculate_metrics(closes, highs, lows)
        is_high_beta = self.is_high_beta(symbol)

        # Calculate stop/target
        stop_loss = current_price * (1 - self.config.stop_loss_pct)
        take_profit = current_price * (1 + self.config.take_profit_pct)

        if has_position:
            # === EXIT LOGIC ===
            pnl_pct = (current_price - position_entry_price) / position_entry_price

            # Stop loss
            if pnl_pct <= -self.config.stop_loss_pct:
                return DipSignal(
                    symbol=symbol,
                    action='SELL',
                    confidence=1.0,
                    entry_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reasoning=f"Stop loss hit ({pnl_pct:.1%})",
                    prev_day_change=prev_day_change,
                    day_range_pct=day_range,
                    is_high_beta=is_high_beta,
                )

            # Take profit
            if pnl_pct >= self.config.take_profit_pct:
                return DipSignal(
                    symbol=symbol,
                    action='SELL',
                    confidence=0.95,
                    entry_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reasoning=f"Take profit reached ({pnl_pct:.1%})",
                    prev_day_change=prev_day_change,
                    day_range_pct=day_range,
                    is_high_beta=is_high_beta,
                )

            # Max hold time
            if position_entry_date and current_date:
                hold_days = (current_date - position_entry_date).days
                if hold_days >= self.config.max_hold_days:
                    return DipSignal(
                        symbol=symbol,
                        action='SELL',
                        confidence=0.8,
                        entry_price=current_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        reasoning=f"Max hold time ({hold_days} days)",
                        prev_day_change=prev_day_change,
                        day_range_pct=day_range,
                        is_high_beta=is_high_beta,
                    )

            return self._hold_signal(symbol, current_price, prev_day_change, day_range, is_high_beta)

        else:
            # === ENTRY LOGIC ===
            buy_signals = 0
            reasons = []

            # 1. Previous day was red (KEY SIGNAL)
            if prev_day_change <= self.config.min_prev_day_drop:
                buy_signals += 3  # Strong signal
                reasons.append(f"Prev day red ({prev_day_change:.1%})")

            # 2. High intraday range (volatility = opportunity)
            if day_range >= self.config.min_day_range:
                buy_signals += 2
                reasons.append(f"High range ({day_range:.1%})")

            # 3. High-beta stock (bonus)
            if is_high_beta:
                buy_signals += 1
                reasons.append("High-beta sector")

            # Decision
            if buy_signals >= 4:
                confidence = min(0.9, 0.5 + buy_signals * 0.08)
                return DipSignal(
                    symbol=symbol,
                    action='BUY',
                    confidence=confidence,
                    entry_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reasoning=" | ".join(reasons),
                    prev_day_change=prev_day_change,
                    day_range_pct=day_range,
                    is_high_beta=is_high_beta,
                )

            return self._hold_signal(symbol, current_price, prev_day_change, day_range, is_high_beta)

    def _hold_signal(
        self,
        symbol: str,
        price: float,
        prev_day_change: float = 0,
        day_range: float = 0,
        is_high_beta: bool = False,
    ) -> DipSignal:
        """Return a HOLD signal"""
        return DipSignal(
            symbol=symbol,
            action='HOLD',
            confidence=0.5,
            entry_price=price,
            stop_loss=price * 0.97,
            take_profit=price * 1.08,
            reasoning="No signal",
            prev_day_change=prev_day_change,
            day_range_pct=day_range,
            is_high_beta=is_high_beta,
        )


def screen_for_dips(
    symbols: List[str],
    data_loader,
    as_of_date: datetime,
    config: DipBuyerConfig = None,
) -> List[DipSignal]:
    """
    Screen symbols for dip buying opportunities

    Returns list of BUY signals sorted by confidence
    """
    config = config or DipBuyerConfig()
    strategy = DipBuyerStrategy(config)

    signals = []

    for symbol in symbols:
        bars = data_loader.get_bars(symbol, as_of_date, 10)
        if len(bars) < 5:
            continue

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        signal = strategy.generate_signal(
            symbol=symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            has_position=False,
        )

        if signal.action == 'BUY':
            signals.append(signal)

    # Sort by confidence
    signals.sort(key=lambda s: s.confidence, reverse=True)

    return signals
