"""
ATR Dynamic Stops - Volatility-Based Stop Loss Management

Uses Average True Range (ATR) to set dynamic stop-losses that adapt
to market volatility instead of fixed percentages.

Benefits:
- Wider stops in volatile markets (avoid premature exits)
- Tighter stops in calm markets (protect gains)
- Adapts automatically to each stock's behavior
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import asyncio


@dataclass
class ATRResult:
    """ATR calculation result for a symbol"""
    symbol: str
    atr: float                    # Current ATR value
    atr_percent: float            # ATR as percentage of price
    volatility_regime: str        # LOW, NORMAL, HIGH, EXTREME
    suggested_stop_pct: float     # Suggested stop-loss percentage
    suggested_multiplier: float   # ATR multiplier used
    calculation_time: datetime

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "atr": round(self.atr, 4),
            "atr_percent": round(self.atr_percent, 4),
            "volatility_regime": self.volatility_regime,
            "suggested_stop_pct": round(self.suggested_stop_pct, 4),
            "suggested_multiplier": self.suggested_multiplier,
        }


@dataclass
class DynamicStopLevels:
    """Dynamic stop and target levels based on ATR"""
    symbol: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    trailing_stop_distance: float  # Distance for trailing stop
    atr_used: float
    multiplier_used: float

    @property
    def risk_amount(self) -> float:
        """Dollar risk per share"""
        return self.entry_price - self.stop_loss

    @property
    def reward_1(self) -> float:
        """Reward to target 1"""
        return self.target_1 - self.entry_price

    @property
    def risk_reward_1(self) -> float:
        """Risk/reward ratio to target 1"""
        if self.risk_amount <= 0:
            return 0
        return self.reward_1 / self.risk_amount


class ATRStopManager:
    """
    Manages dynamic stop-losses based on ATR (Average True Range).

    Key features:
    - Calculates ATR from recent price bars
    - Classifies volatility regime
    - Adjusts stop multiplier based on regime
    - Provides trailing stop distances
    """

    # Volatility regime thresholds (ATR as % of price)
    VOLATILITY_THRESHOLDS = {
        'LOW': 0.01,      # < 1% ATR = low volatility
        'NORMAL': 0.02,   # 1-2% ATR = normal
        'HIGH': 0.035,    # 2-3.5% ATR = high volatility
        'EXTREME': 0.05,  # > 3.5% ATR = extreme (meme stocks, earnings)
    }

    # ATR multipliers by regime (higher = wider stops)
    REGIME_MULTIPLIERS = {
        'LOW': 1.5,       # Tight stops in calm markets
        'NORMAL': 2.0,    # Standard 2x ATR
        'HIGH': 2.5,      # Wider stops for volatile stocks
        'EXTREME': 3.0,   # Very wide for extreme volatility
    }

    # Target multipliers (relative to ATR)
    TARGET_MULTIPLIERS = {
        'target_1': 1.5,  # First target at 1.5x ATR
        'target_2': 2.5,  # Second target at 2.5x ATR
        'target_3': 4.0,  # Third target at 4x ATR
    }

    def __init__(
        self,
        alpaca_client,
        atr_period: int = 14,
        cache_minutes: int = 5,
        min_stop_pct: float = 0.01,   # Minimum 1% stop
        max_stop_pct: float = 0.05,   # Maximum 5% stop
    ):
        self.alpaca = alpaca_client
        self.atr_period = atr_period
        self.cache_minutes = cache_minutes
        self.min_stop_pct = min_stop_pct
        self.max_stop_pct = max_stop_pct
        self.logger = logging.getLogger(__name__)

        # Cache ATR calculations
        self._cache: Dict[str, Tuple[ATRResult, datetime]] = {}

    async def get_atr(self, symbol: str, force_refresh: bool = False) -> Optional[ATRResult]:
        """
        Get ATR for a symbol with caching.

        Args:
            symbol: Stock ticker
            force_refresh: Bypass cache

        Returns:
            ATRResult with ATR data and volatility classification
        """
        # Check cache
        if not force_refresh and symbol in self._cache:
            result, cached_at = self._cache[symbol]
            age_minutes = (datetime.now() - cached_at).total_seconds() / 60
            if age_minutes < self.cache_minutes:
                return result

        # Calculate fresh ATR
        result = await self._calculate_atr(symbol)

        if result:
            self._cache[symbol] = (result, datetime.now())

        return result

    async def _calculate_atr(self, symbol: str) -> Optional[ATRResult]:
        """Calculate ATR from price bars"""
        try:
            # Get daily bars for ATR calculation (need ATR_period + 1 bars)
            bars = await self.alpaca.get_bars(
                symbol,
                timeframe='1Day',
                limit=self.atr_period + 5  # Extra buffer
            )

            if not bars or len(bars) < self.atr_period:
                self.logger.debug(f"{symbol}: Not enough bars for ATR ({len(bars) if bars else 0})")
                return None

            # Calculate True Range for each bar
            true_ranges = []
            for i in range(1, len(bars)):
                high = bars[i].get('high', 0)
                low = bars[i].get('low', 0)
                prev_close = bars[i-1].get('close', 0)

                if high <= 0 or low <= 0 or prev_close <= 0:
                    continue

                # True Range = max of:
                # 1. High - Low (current bar range)
                # 2. |High - Previous Close| (gap up)
                # 3. |Low - Previous Close| (gap down)
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)

            if len(true_ranges) < self.atr_period:
                return None

            # ATR = Simple Moving Average of True Range
            atr = sum(true_ranges[-self.atr_period:]) / self.atr_period

            # Current price for percentage calculation
            current_price = bars[-1].get('close', 0)
            if current_price <= 0:
                return None

            atr_percent = atr / current_price

            # Classify volatility regime
            regime = self._classify_regime(atr_percent)

            # Get multiplier for this regime
            multiplier = self.REGIME_MULTIPLIERS.get(regime, 2.0)

            # Calculate suggested stop percentage
            suggested_stop = atr_percent * multiplier

            # Clamp to min/max
            suggested_stop = max(self.min_stop_pct, min(self.max_stop_pct, suggested_stop))

            return ATRResult(
                symbol=symbol,
                atr=atr,
                atr_percent=atr_percent,
                volatility_regime=regime,
                suggested_stop_pct=suggested_stop,
                suggested_multiplier=multiplier,
                calculation_time=datetime.now(),
            )

        except Exception as e:
            self.logger.debug(f"Error calculating ATR for {symbol}: {e}")
            return None

    def _classify_regime(self, atr_percent: float) -> str:
        """Classify volatility regime based on ATR percentage"""
        if atr_percent < self.VOLATILITY_THRESHOLDS['LOW']:
            return 'LOW'
        elif atr_percent < self.VOLATILITY_THRESHOLDS['NORMAL']:
            return 'NORMAL'
        elif atr_percent < self.VOLATILITY_THRESHOLDS['HIGH']:
            return 'HIGH'
        else:
            return 'EXTREME'

    async def calculate_dynamic_levels(
        self,
        symbol: str,
        entry_price: float,
        direction: str = 'LONG',  # LONG or SHORT
    ) -> Optional[DynamicStopLevels]:
        """
        Calculate dynamic stop-loss and target levels based on ATR.

        Args:
            symbol: Stock ticker
            entry_price: Planned entry price
            direction: Trade direction (LONG or SHORT)

        Returns:
            DynamicStopLevels with stop and target prices
        """
        atr_result = await self.get_atr(symbol)

        if not atr_result:
            # Fallback to default 2% stop (this is normal for new/low-volume stocks)
            self.logger.debug(f"{symbol}: ATR unavailable, using default 2% stop")
            return self._default_levels(symbol, entry_price, direction)

        atr = atr_result.atr
        multiplier = atr_result.suggested_multiplier

        if direction == 'LONG':
            stop_loss = entry_price - (atr * multiplier)
            target_1 = entry_price + (atr * self.TARGET_MULTIPLIERS['target_1'])
            target_2 = entry_price + (atr * self.TARGET_MULTIPLIERS['target_2'])
            target_3 = entry_price + (atr * self.TARGET_MULTIPLIERS['target_3'])
        else:  # SHORT
            stop_loss = entry_price + (atr * multiplier)
            target_1 = entry_price - (atr * self.TARGET_MULTIPLIERS['target_1'])
            target_2 = entry_price - (atr * self.TARGET_MULTIPLIERS['target_2'])
            target_3 = entry_price - (atr * self.TARGET_MULTIPLIERS['target_3'])

        self.logger.info(
            f"📊 {symbol} ATR Levels: "
            f"Regime={atr_result.volatility_regime} | "
            f"ATR=${atr:.2f} ({atr_result.atr_percent*100:.1f}%) | "
            f"Stop=${stop_loss:.2f} | "
            f"Targets=${target_1:.2f}/${target_2:.2f}/${target_3:.2f}"
        )

        return DynamicStopLevels(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            trailing_stop_distance=atr * multiplier,
            atr_used=atr,
            multiplier_used=multiplier,
        )

    def _default_levels(
        self,
        symbol: str,
        entry_price: float,
        direction: str,
    ) -> DynamicStopLevels:
        """Fallback to fixed percentage levels"""
        stop_pct = 0.02  # 2%

        if direction == 'LONG':
            return DynamicStopLevels(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=entry_price * (1 - stop_pct),
                target_1=entry_price * 1.015,
                target_2=entry_price * 1.025,
                target_3=entry_price * 1.04,
                trailing_stop_distance=entry_price * stop_pct,
                atr_used=0,
                multiplier_used=2.0,
            )
        else:
            return DynamicStopLevels(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=entry_price * (1 + stop_pct),
                target_1=entry_price * 0.985,
                target_2=entry_price * 0.975,
                target_3=entry_price * 0.96,
                trailing_stop_distance=entry_price * stop_pct,
                atr_used=0,
                multiplier_used=2.0,
            )

    async def get_batch_atr(self, symbols: List[str]) -> Dict[str, ATRResult]:
        """Get ATR for multiple symbols concurrently"""
        tasks = [self.get_atr(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        atr_map = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, ATRResult):
                atr_map[symbol] = result

        return atr_map

    def update_trailing_stop(
        self,
        current_price: float,
        current_stop: float,
        atr: float,
        multiplier: float,
        direction: str = 'LONG',
    ) -> float:
        """
        Calculate updated trailing stop based on current price.

        Only moves stop in favorable direction (never widens).
        """
        trailing_distance = atr * multiplier

        if direction == 'LONG':
            new_stop = current_price - trailing_distance
            # Only raise stop, never lower
            return max(current_stop, new_stop)
        else:
            new_stop = current_price + trailing_distance
            # Only lower stop, never raise
            return min(current_stop, new_stop)

    def format_for_log(self, atr_result: ATRResult) -> str:
        """Format ATR result for logging"""
        return (
            f"ATR: ${atr_result.atr:.2f} ({atr_result.atr_percent*100:.2f}%) | "
            f"Regime: {atr_result.volatility_regime} | "
            f"Suggested Stop: {atr_result.suggested_stop_pct*100:.1f}%"
        )
