"""
Volatility Detector - Early Detection of High-Volatility Conditions

Scans pre-market data and market indicators to identify high-volatility days
where aggressive trading strategies have higher probability of success.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from alpaca.client import AlpacaClient


class VolatilityRegime(Enum):
    """Market volatility classification"""
    LOW = "low"           # VIX < 15, small gaps
    NORMAL = "normal"     # VIX 15-20, typical gaps
    ELEVATED = "elevated" # VIX 20-25, notable gaps
    HIGH = "high"         # VIX 25-30, large gaps
    EXTREME = "extreme"   # VIX > 30, crisis mode


class TradingMode(Enum):
    """Recommended trading mode based on volatility"""
    CONSERVATIVE = "conservative"  # Small positions, tight stops
    NORMAL = "normal"              # Standard parameters
    AGGRESSIVE = "aggressive"      # Larger positions on good setups
    VERY_AGGRESSIVE = "very_aggressive"  # Maximum position on A+ setups
    DEFENSIVE = "defensive"        # Reduce exposure, protect capital


@dataclass
class PreMarketData:
    """Pre-market analysis for a symbol"""
    symbol: str
    previous_close: float
    pre_market_price: float
    gap_pct: float
    pre_market_volume: int
    avg_volume: int
    volume_ratio: float
    is_gapping_up: bool
    is_gapping_down: bool
    gap_magnitude: str  # "small", "medium", "large", "huge"


@dataclass
class VolatilityAssessment:
    """Overall market volatility assessment"""
    timestamp: datetime
    vix_level: float
    vix_change_pct: float
    regime: VolatilityRegime
    recommended_mode: TradingMode
    spy_gap_pct: float
    qqq_gap_pct: float
    avg_watchlist_gap: float
    high_gap_count: int  # Stocks gapping > 3%
    explanation: str
    position_multiplier: float  # 0.5 - 1.5 based on conditions
    stop_multiplier: float  # Adjust stops based on volatility

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "vix_level": round(self.vix_level, 2),
            "regime": self.regime.value,
            "recommended_mode": self.recommended_mode.value,
            "spy_gap_pct": round(self.spy_gap_pct, 4),
            "position_multiplier": round(self.position_multiplier, 2),
            "stop_multiplier": round(self.stop_multiplier, 2),
            "explanation": self.explanation,
        }


class VolatilityDetector:
    """
    Detects market volatility conditions early in the trading day.

    Checks:
    1. VIX level and direction
    2. SPY/QQQ pre-market gaps
    3. Watchlist gaps and volume
    4. Overall market sentiment indicators
    """

    # VIX thresholds for regime classification
    VIX_THRESHOLDS = {
        VolatilityRegime.LOW: 15,
        VolatilityRegime.NORMAL: 20,
        VolatilityRegime.ELEVATED: 25,
        VolatilityRegime.HIGH: 30,
        VolatilityRegime.EXTREME: 100,
    }

    # Gap thresholds
    GAP_THRESHOLDS = {
        "small": 0.01,   # 1%
        "medium": 0.02,  # 2%
        "large": 0.03,   # 3%
        "huge": 0.05,    # 5%
    }

    def __init__(self, alpaca_client: AlpacaClient):
        self.alpaca = alpaca_client
        self.logger = logging.getLogger(__name__)

        # Cache
        self._last_assessment: Optional[VolatilityAssessment] = None
        self._last_check: Optional[datetime] = None
        self._premarket_data: Dict[str, PreMarketData] = {}

    async def assess_volatility(
        self,
        watchlist: List[str],
        force_refresh: bool = False,
    ) -> VolatilityAssessment:
        """
        Assess current market volatility conditions.

        Should be called at market open or slightly before.
        """
        # Check cache (valid for 5 minutes)
        if not force_refresh and self._last_assessment:
            if self._last_check:
                cache_age = (datetime.now() - self._last_check).total_seconds()
                if cache_age < 300:  # 5 minutes
                    return self._last_assessment

        self.logger.info("🔍 Assessing market volatility...")

        # Get VIX data
        vix_level, vix_change = await self._get_vix_data()

        # Get SPY and QQQ gaps
        spy_gap = await self._get_gap_pct("SPY")
        qqq_gap = await self._get_gap_pct("QQQ")

        # Analyze watchlist
        premarket_results = await self._analyze_premarket(watchlist)
        self._premarket_data = {pm.symbol: pm for pm in premarket_results}

        # Calculate statistics
        gaps = [pm.gap_pct for pm in premarket_results if pm.gap_pct != 0]
        avg_gap = sum(abs(g) for g in gaps) / len(gaps) if gaps else 0
        high_gap_count = sum(1 for g in gaps if abs(g) >= 0.03)

        # Classify regime
        regime = self._classify_regime(vix_level, avg_gap, spy_gap)

        # Determine trading mode
        mode, position_mult, stop_mult, explanation = self._determine_mode(
            regime, vix_change, avg_gap, high_gap_count, len(watchlist)
        )

        assessment = VolatilityAssessment(
            timestamp=datetime.now(timezone.utc),
            vix_level=vix_level,
            vix_change_pct=vix_change,
            regime=regime,
            recommended_mode=mode,
            spy_gap_pct=spy_gap,
            qqq_gap_pct=qqq_gap,
            avg_watchlist_gap=avg_gap,
            high_gap_count=high_gap_count,
            explanation=explanation,
            position_multiplier=position_mult,
            stop_multiplier=stop_mult,
        )

        self._last_assessment = assessment
        self._last_check = datetime.now()

        self._log_assessment(assessment)

        return assessment

    async def _get_vix_data(self) -> Tuple[float, float]:
        """Get VIX level and daily change"""
        try:
            # Try to get VIX quote
            # Note: Alpaca may not have VIX directly, use VIXY as proxy
            bars = await self.alpaca.get_bars("VIXY", timeframe='1Day', limit=2)

            if bars and len(bars) >= 2:
                prev_close = bars[-2].close if hasattr(bars[-2], 'close') else 20
                curr_close = bars[-1].close if hasattr(bars[-1], 'close') else 20
                change_pct = (curr_close - prev_close) / prev_close if prev_close > 0 else 0

                # VIXY is a proxy, estimate VIX level (rough approximation)
                estimated_vix = 15 + (curr_close - 10) * 0.5
                return max(10, min(50, estimated_vix)), change_pct

        except Exception as e:
            self.logger.debug(f"Could not get VIX data: {e}")

        # Default to normal VIX
        return 18.0, 0.0

    async def _get_gap_pct(self, symbol: str) -> float:
        """Get gap percentage for a symbol"""
        try:
            bars = await self.alpaca.get_bars(symbol, timeframe='1Day', limit=2)

            if bars and len(bars) >= 2:
                prev_close = bars[-2].close if hasattr(bars[-2], 'close') else 0
                curr_open = bars[-1].open if hasattr(bars[-1], 'open') else 0

                if prev_close > 0:
                    return (curr_open - prev_close) / prev_close

            # Try quote for more recent data
            quote = await self.alpaca.get_quote(symbol)
            if quote and bars and len(bars) >= 1:
                prev_close = bars[-1].close if hasattr(bars[-1], 'close') else 0
                curr_price = quote.last_price if hasattr(quote, 'last_price') else 0

                if prev_close > 0 and curr_price > 0:
                    return (curr_price - prev_close) / prev_close

        except Exception as e:
            self.logger.debug(f"Could not get gap for {symbol}: {e}")

        return 0.0

    async def _analyze_premarket(self, symbols: List[str]) -> List[PreMarketData]:
        """Analyze pre-market data for watchlist"""
        results = []

        tasks = [self._get_premarket_data(symbol) for symbol in symbols[:20]]  # Limit to 20
        premarket_results = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, result in zip(symbols[:20], premarket_results):
            if isinstance(result, PreMarketData):
                results.append(result)

        return results

    async def _get_premarket_data(self, symbol: str) -> Optional[PreMarketData]:
        """Get pre-market data for a single symbol"""
        try:
            # Get recent bars
            bars = await self.alpaca.get_bars(symbol, timeframe='1Day', limit=5)

            if not bars or len(bars) < 2:
                return None

            prev_bar = bars[-2] if len(bars) >= 2 else bars[-1]
            curr_bar = bars[-1]

            prev_close = prev_bar.close if hasattr(prev_bar, 'close') else 0
            curr_open = curr_bar.open if hasattr(curr_bar, 'open') else 0
            curr_volume = curr_bar.volume if hasattr(curr_bar, 'volume') else 0

            if prev_close <= 0:
                return None

            # Calculate average volume
            volumes = [b.volume for b in bars if hasattr(b, 'volume') and b.volume > 0]
            avg_volume = sum(volumes) / len(volumes) if volumes else 1

            gap_pct = (curr_open - prev_close) / prev_close
            volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1

            # Classify gap magnitude
            abs_gap = abs(gap_pct)
            if abs_gap >= self.GAP_THRESHOLDS["huge"]:
                magnitude = "huge"
            elif abs_gap >= self.GAP_THRESHOLDS["large"]:
                magnitude = "large"
            elif abs_gap >= self.GAP_THRESHOLDS["medium"]:
                magnitude = "medium"
            elif abs_gap >= self.GAP_THRESHOLDS["small"]:
                magnitude = "small"
            else:
                magnitude = "none"

            return PreMarketData(
                symbol=symbol,
                previous_close=prev_close,
                pre_market_price=curr_open,
                gap_pct=gap_pct,
                pre_market_volume=curr_volume,
                avg_volume=int(avg_volume),
                volume_ratio=volume_ratio,
                is_gapping_up=gap_pct >= self.GAP_THRESHOLDS["small"],
                is_gapping_down=gap_pct <= -self.GAP_THRESHOLDS["small"],
                gap_magnitude=magnitude,
            )

        except Exception as e:
            self.logger.debug(f"Error getting premarket data for {symbol}: {e}")
            return None

    def _classify_regime(
        self,
        vix_level: float,
        avg_gap: float,
        spy_gap: float,
    ) -> VolatilityRegime:
        """Classify the volatility regime"""
        # Primary: VIX level
        if vix_level >= self.VIX_THRESHOLDS[VolatilityRegime.HIGH]:
            return VolatilityRegime.EXTREME if vix_level >= 30 else VolatilityRegime.HIGH
        elif vix_level >= self.VIX_THRESHOLDS[VolatilityRegime.ELEVATED]:
            return VolatilityRegime.ELEVATED
        elif vix_level >= self.VIX_THRESHOLDS[VolatilityRegime.NORMAL]:
            return VolatilityRegime.NORMAL

        # Secondary: Gap analysis
        if avg_gap >= 0.03 or abs(spy_gap) >= 0.02:
            return VolatilityRegime.ELEVATED
        elif avg_gap >= 0.02 or abs(spy_gap) >= 0.01:
            return VolatilityRegime.NORMAL

        return VolatilityRegime.LOW

    def _determine_mode(
        self,
        regime: VolatilityRegime,
        vix_change: float,
        avg_gap: float,
        high_gap_count: int,
        watchlist_size: int,
    ) -> Tuple[TradingMode, float, float, str]:
        """
        Determine recommended trading mode based on conditions.

        Returns: (mode, position_multiplier, stop_multiplier, explanation)
        """
        # Default values
        mode = TradingMode.NORMAL
        pos_mult = 1.0
        stop_mult = 1.0
        reasons = []

        # Extreme volatility = defensive
        if regime == VolatilityRegime.EXTREME:
            return (
                TradingMode.DEFENSIVE,
                0.5,
                1.5,
                "EXTREME volatility - reduce exposure, widen stops"
            )

        # High volatility with VIX rising = defensive
        if regime == VolatilityRegime.HIGH and vix_change > 0.05:
            return (
                TradingMode.DEFENSIVE,
                0.6,
                1.3,
                "HIGH volatility with rising VIX - protect capital"
            )

        # High volatility with VIX falling = opportunity
        if regime == VolatilityRegime.HIGH and vix_change < -0.05:
            return (
                TradingMode.AGGRESSIVE,
                1.3,
                1.2,
                "HIGH volatility but VIX declining - opportunity for reversal plays"
            )

        # Elevated volatility with many gapping stocks = aggressive
        gap_ratio = high_gap_count / watchlist_size if watchlist_size > 0 else 0
        if regime == VolatilityRegime.ELEVATED and gap_ratio >= 0.3:
            return (
                TradingMode.AGGRESSIVE,
                1.25,
                1.1,
                f"ELEVATED volatility with {high_gap_count} stocks gapping >3% - aggressive on best setups"
            )

        # Normal volatility with some gaps = normal+
        if regime == VolatilityRegime.NORMAL and high_gap_count >= 3:
            return (
                TradingMode.NORMAL,
                1.1,
                1.0,
                f"NORMAL volatility with {high_gap_count} notable gaps - standard trading with selective aggression"
            )

        # Low volatility = conservative or skip
        if regime == VolatilityRegime.LOW:
            return (
                TradingMode.CONSERVATIVE,
                0.7,
                0.8,
                "LOW volatility - smaller positions, tighter stops, focus on quality setups only"
            )

        # Default normal
        return (
            TradingMode.NORMAL,
            1.0,
            1.0,
            "NORMAL conditions - standard trading parameters"
        )

    def _log_assessment(self, assessment: VolatilityAssessment):
        """Log the volatility assessment"""
        emoji_map = {
            VolatilityRegime.LOW: "😴",
            VolatilityRegime.NORMAL: "📊",
            VolatilityRegime.ELEVATED: "⚡",
            VolatilityRegime.HIGH: "🔥",
            VolatilityRegime.EXTREME: "🚨",
        }

        mode_emoji = {
            TradingMode.CONSERVATIVE: "🐢",
            TradingMode.NORMAL: "📈",
            TradingMode.AGGRESSIVE: "🚀",
            TradingMode.VERY_AGGRESSIVE: "💰",
            TradingMode.DEFENSIVE: "🛡️",
        }

        self.logger.info("=" * 60)
        self.logger.info(f"{emoji_map[assessment.regime]} VOLATILITY ASSESSMENT")
        self.logger.info("=" * 60)
        self.logger.info(f"VIX: {assessment.vix_level:.1f} ({assessment.vix_change_pct*100:+.1f}%)")
        self.logger.info(f"SPY Gap: {assessment.spy_gap_pct*100:+.2f}% | QQQ Gap: {assessment.qqq_gap_pct*100:+.2f}%")
        self.logger.info(f"Regime: {assessment.regime.value.upper()}")
        self.logger.info(f"Mode: {mode_emoji[assessment.recommended_mode]} {assessment.recommended_mode.value.upper()}")
        self.logger.info(f"Position Multiplier: {assessment.position_multiplier:.2f}x")
        self.logger.info(f"Stop Multiplier: {assessment.stop_multiplier:.2f}x")
        self.logger.info(f"📝 {assessment.explanation}")
        self.logger.info("=" * 60)

    def get_premarket_data(self, symbol: str) -> Optional[PreMarketData]:
        """Get cached pre-market data for a symbol"""
        return self._premarket_data.get(symbol)

    def get_gapping_symbols(self, direction: str = "up", min_gap: float = 0.02) -> List[str]:
        """Get symbols gapping in specified direction"""
        results = []
        for symbol, data in self._premarket_data.items():
            if direction == "up" and data.gap_pct >= min_gap:
                results.append(symbol)
            elif direction == "down" and data.gap_pct <= -min_gap:
                results.append(symbol)
        return sorted(results, key=lambda s: abs(self._premarket_data[s].gap_pct), reverse=True)

    def get_high_volume_symbols(self, min_ratio: float = 2.0) -> List[str]:
        """Get symbols with high pre-market volume"""
        return [
            symbol for symbol, data in self._premarket_data.items()
            if data.volume_ratio >= min_ratio
        ]
