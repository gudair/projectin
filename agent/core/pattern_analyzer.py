"""
Pattern Analyzer - Statistical Analysis of Trading Patterns

Analyzes 30-60 days of historical data to find patterns with proven win rates.
Only patterns with >60% success rate are recommended for trading.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from alpaca.client import AlpacaClient


class PatternType(Enum):
    """Detectable pattern types"""
    GAP_UP = "gap_up"               # Opens > 2% above previous close
    GAP_DOWN = "gap_down"           # Opens > 2% below previous close
    VOLUME_SPIKE = "volume_spike"   # Volume > 2x average in first 30 min
    MORNING_MOMENTUM = "morning_momentum"  # Strong move in first hour
    VWAP_RECLAIM = "vwap_reclaim"   # Price reclaims VWAP after dip
    REVERSAL = "reversal"           # Price reverses from extreme
    BREAKOUT = "breakout"           # Price breaks key level
    RANGE_BOUND = "range_bound"     # Low volatility, tight range


@dataclass
class PatternInstance:
    """Single occurrence of a pattern"""
    symbol: str
    date: datetime
    pattern_type: PatternType
    entry_price: float
    optimal_exit_price: float
    actual_high: float
    actual_low: float
    max_gain_pct: float
    max_loss_pct: float
    entry_time_minutes: int  # Minutes after market open
    optimal_hold_minutes: int  # How long to hold for max gain
    volume_ratio: float  # Volume vs average


@dataclass
class PatternStats:
    """Statistical analysis of a pattern type"""
    pattern_type: PatternType
    total_occurrences: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_gain_pct: float = 0.0
    avg_loss_pct: float = 0.0
    max_gain_pct: float = 0.0
    max_loss_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0  # Total gains / Total losses
    avg_hold_minutes: int = 0
    best_entry_minute: int = 0  # Optimal entry time after market open
    avg_volume_ratio: float = 0.0
    instances: List[PatternInstance] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "pattern_type": self.pattern_type.value,
            "total_occurrences": self.total_occurrences,
            "win_rate": round(self.win_rate, 3),
            "avg_gain_pct": round(self.avg_gain_pct, 4),
            "avg_loss_pct": round(self.avg_loss_pct, 4),
            "profit_factor": round(self.profit_factor, 2),
            "avg_hold_minutes": self.avg_hold_minutes,
            "best_entry_minute": self.best_entry_minute,
            "recommended": self.win_rate >= 0.60,
        }


@dataclass
class SetupQuality:
    """Quality score for a trading setup"""
    symbol: str
    pattern: PatternType
    quality_grade: str  # A+, A, B, C
    confidence: float  # 0.0 - 1.0
    recommended_position_pct: float  # Suggested position size
    expected_gain_pct: float
    expected_loss_pct: float
    historical_win_rate: float
    entry_timing: str  # "immediate", "wait_dip", "wait_breakout"
    stop_loss_pct: float
    take_profit_pct: float
    max_hold_minutes: int

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "pattern": self.pattern.value,
            "quality_grade": self.quality_grade,
            "confidence": round(self.confidence, 2),
            "recommended_position_pct": round(self.recommended_position_pct, 3),
            "expected_gain_pct": round(self.expected_gain_pct, 4),
            "historical_win_rate": round(self.historical_win_rate, 3),
            "stop_loss_pct": round(self.stop_loss_pct, 4),
            "take_profit_pct": round(self.take_profit_pct, 4),
        }


class PatternAnalyzer:
    """
    Analyzes historical data to find statistically profitable patterns.

    Process:
    1. Fetch 30-60 days of intraday data
    2. Detect all pattern occurrences
    3. Calculate win rates and optimal parameters
    4. Return only patterns with >60% win rate
    """

    # Pattern detection thresholds
    GAP_THRESHOLD = 0.02  # 2% gap
    VOLUME_SPIKE_THRESHOLD = 2.0  # 2x average volume
    MOMENTUM_THRESHOLD = 0.015  # 1.5% move in first hour
    MIN_PROFIT_TARGET = 0.01  # 1% minimum target

    def __init__(
        self,
        alpaca_client: AlpacaClient,
        analysis_days: int = 30,
        min_win_rate: float = 0.60,
    ):
        self.alpaca = alpaca_client
        self.analysis_days = analysis_days
        self.min_win_rate = min_win_rate
        self.logger = logging.getLogger(__name__)

        # Cache for analysis results
        self._pattern_stats: Dict[PatternType, PatternStats] = {}
        self._symbol_patterns: Dict[str, List[PatternInstance]] = defaultdict(list)
        self._last_analysis: Optional[datetime] = None
        self._analyzed_symbols: set = set()

    async def analyze_symbols(
        self,
        symbols: List[str],
        force_refresh: bool = False,
    ) -> Dict[PatternType, PatternStats]:
        """
        Analyze multiple symbols to find profitable patterns.

        Returns dict of PatternType -> PatternStats for patterns with >60% win rate.
        """
        # Check cache
        if not force_refresh and self._last_analysis:
            cache_age = datetime.now() - self._last_analysis
            if cache_age.total_seconds() < 3600:  # 1 hour cache
                if set(symbols).issubset(self._analyzed_symbols):
                    return {k: v for k, v in self._pattern_stats.items()
                            if v.win_rate >= self.min_win_rate}

        self.logger.info(f"📊 Analyzing {len(symbols)} symbols over {self.analysis_days} days...")

        # Reset stats
        self._pattern_stats = {pt: PatternStats(pattern_type=pt) for pt in PatternType}
        self._symbol_patterns = defaultdict(list)

        # Analyze each symbol
        tasks = [self._analyze_symbol(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                self.logger.debug(f"Error analyzing {symbol}: {result}")
                continue
            if result:
                self._symbol_patterns[symbol].extend(result)
                for instance in result:
                    self._pattern_stats[instance.pattern_type].instances.append(instance)

        # Calculate statistics for each pattern
        for pattern_type, stats in self._pattern_stats.items():
            self._calculate_pattern_stats(stats)

        self._last_analysis = datetime.now()
        self._analyzed_symbols = set(symbols)

        # Return only profitable patterns
        profitable = {k: v for k, v in self._pattern_stats.items()
                      if v.win_rate >= self.min_win_rate and v.total_occurrences >= 5}

        self._log_analysis_results(profitable)

        return profitable

    async def _analyze_symbol(self, symbol: str) -> List[PatternInstance]:
        """Analyze a single symbol for pattern occurrences"""
        instances = []

        # Get daily bars for gap detection
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=self.analysis_days + 10)

        try:
            daily_bars = await self.alpaca.get_bars(
                symbol,
                timeframe='1Day',
                start=start_date,
                end=end_date,
                limit=self.analysis_days + 10
            )

            if not daily_bars or len(daily_bars) < 5:
                return instances

            # Calculate average volume
            volumes = [b.volume for b in daily_bars if hasattr(b, 'volume')]
            avg_volume = sum(volumes) / len(volumes) if volumes else 0

            # Analyze each day
            for i in range(1, len(daily_bars)):
                prev_bar = daily_bars[i-1]
                curr_bar = daily_bars[i]

                # Skip if missing data
                if not all([
                    hasattr(prev_bar, 'close'), hasattr(curr_bar, 'open'),
                    hasattr(curr_bar, 'high'), hasattr(curr_bar, 'low'),
                    hasattr(curr_bar, 'close'), hasattr(curr_bar, 'volume')
                ]):
                    continue

                prev_close = prev_bar.close
                curr_open = curr_bar.open
                curr_high = curr_bar.high
                curr_low = curr_bar.low
                curr_close = curr_bar.close
                curr_volume = curr_bar.volume

                if prev_close <= 0:
                    continue

                # Detect patterns
                gap_pct = (curr_open - prev_close) / prev_close
                day_range_pct = (curr_high - curr_low) / curr_low if curr_low > 0 else 0
                volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1

                # Calculate max potential gain/loss from open
                max_gain_from_open = (curr_high - curr_open) / curr_open if curr_open > 0 else 0
                max_loss_from_open = (curr_open - curr_low) / curr_open if curr_open > 0 else 0

                # GAP UP pattern
                if gap_pct >= self.GAP_THRESHOLD:
                    # For gap up: check if it continued higher or faded
                    if curr_close > curr_open:  # Continued
                        win = True
                        gain = (curr_high - curr_open) / curr_open
                        loss = (curr_open - curr_low) / curr_open
                    else:  # Faded
                        win = False
                        gain = max_gain_from_open
                        loss = max_loss_from_open

                    instances.append(PatternInstance(
                        symbol=symbol,
                        date=curr_bar.timestamp if hasattr(curr_bar, 'timestamp') else datetime.now(),
                        pattern_type=PatternType.GAP_UP,
                        entry_price=curr_open,
                        optimal_exit_price=curr_high,
                        actual_high=curr_high,
                        actual_low=curr_low,
                        max_gain_pct=gain,
                        max_loss_pct=loss,
                        entry_time_minutes=0,  # At open
                        optimal_hold_minutes=120,  # Estimate
                        volume_ratio=volume_ratio,
                    ))

                # GAP DOWN pattern
                elif gap_pct <= -self.GAP_THRESHOLD:
                    # For gap down: check for reversal
                    if curr_close > curr_open:  # Reversal (bullish)
                        win = True
                        gain = (curr_high - curr_open) / curr_open
                        loss = (curr_open - curr_low) / curr_open
                    else:  # Continued down
                        win = False
                        gain = max_gain_from_open
                        loss = max_loss_from_open

                    instances.append(PatternInstance(
                        symbol=symbol,
                        date=curr_bar.timestamp if hasattr(curr_bar, 'timestamp') else datetime.now(),
                        pattern_type=PatternType.GAP_DOWN,
                        entry_price=curr_low,  # Buy the dip
                        optimal_exit_price=curr_high,
                        actual_high=curr_high,
                        actual_low=curr_low,
                        max_gain_pct=(curr_high - curr_low) / curr_low if curr_low > 0 else 0,
                        max_loss_pct=0.02,  # Assume 2% stop
                        entry_time_minutes=30,  # Wait for bottom
                        optimal_hold_minutes=180,
                        volume_ratio=volume_ratio,
                    ))

                # VOLUME SPIKE pattern
                if volume_ratio >= self.VOLUME_SPIKE_THRESHOLD:
                    # High volume days often continue in direction of move
                    if curr_close > curr_open:  # Up day
                        win = True
                        gain = max_gain_from_open
                        loss = max_loss_from_open
                    else:
                        win = False
                        gain = max_gain_from_open
                        loss = max_loss_from_open

                    instances.append(PatternInstance(
                        symbol=symbol,
                        date=curr_bar.timestamp if hasattr(curr_bar, 'timestamp') else datetime.now(),
                        pattern_type=PatternType.VOLUME_SPIKE,
                        entry_price=curr_open,
                        optimal_exit_price=curr_high if curr_close > curr_open else curr_open,
                        actual_high=curr_high,
                        actual_low=curr_low,
                        max_gain_pct=gain,
                        max_loss_pct=loss,
                        entry_time_minutes=15,  # Early entry
                        optimal_hold_minutes=90,
                        volume_ratio=volume_ratio,
                    ))

                # MORNING MOMENTUM pattern
                morning_move = abs(gap_pct) + day_range_pct * 0.3  # Rough estimate
                if morning_move >= self.MOMENTUM_THRESHOLD and gap_pct > 0:
                    instances.append(PatternInstance(
                        symbol=symbol,
                        date=curr_bar.timestamp if hasattr(curr_bar, 'timestamp') else datetime.now(),
                        pattern_type=PatternType.MORNING_MOMENTUM,
                        entry_price=curr_open * 1.005,  # Entry slightly above open
                        optimal_exit_price=curr_high,
                        actual_high=curr_high,
                        actual_low=curr_low,
                        max_gain_pct=max_gain_from_open * 0.8,  # Realistic capture
                        max_loss_pct=max_loss_from_open,
                        entry_time_minutes=5,
                        optimal_hold_minutes=60,
                        volume_ratio=volume_ratio,
                    ))

                # REVERSAL pattern (big down then recovery)
                if gap_pct < -0.01 and curr_close > prev_close:
                    reversal_gain = (curr_close - curr_low) / curr_low if curr_low > 0 else 0
                    instances.append(PatternInstance(
                        symbol=symbol,
                        date=curr_bar.timestamp if hasattr(curr_bar, 'timestamp') else datetime.now(),
                        pattern_type=PatternType.REVERSAL,
                        entry_price=curr_low * 1.005,
                        optimal_exit_price=curr_high,
                        actual_high=curr_high,
                        actual_low=curr_low,
                        max_gain_pct=reversal_gain,
                        max_loss_pct=0.02,
                        entry_time_minutes=60,  # Wait for reversal confirmation
                        optimal_hold_minutes=180,
                        volume_ratio=volume_ratio,
                    ))

            return instances

        except Exception as e:
            self.logger.debug(f"Error analyzing {symbol}: {e}")
            return instances

    def _calculate_pattern_stats(self, stats: PatternStats):
        """Calculate statistics from pattern instances"""
        if not stats.instances:
            return

        stats.total_occurrences = len(stats.instances)

        # Define win as >1% gain achievable
        wins = [i for i in stats.instances if i.max_gain_pct >= self.MIN_PROFIT_TARGET]
        losses = [i for i in stats.instances if i.max_gain_pct < self.MIN_PROFIT_TARGET]

        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        stats.win_rate = len(wins) / len(stats.instances) if stats.instances else 0

        # Calculate averages
        if wins:
            stats.avg_gain_pct = sum(i.max_gain_pct for i in wins) / len(wins)
            stats.max_gain_pct = max(i.max_gain_pct for i in wins)

        if losses:
            stats.avg_loss_pct = sum(i.max_loss_pct for i in losses) / len(losses)
            stats.max_loss_pct = max(i.max_loss_pct for i in losses)

        # Profit factor
        total_gains = sum(i.max_gain_pct for i in wins) if wins else 0
        total_losses = sum(i.max_loss_pct for i in losses) if losses else 0.01
        stats.profit_factor = total_gains / total_losses if total_losses > 0 else 0

        # Timing analysis
        if stats.instances:
            stats.avg_hold_minutes = int(sum(i.optimal_hold_minutes for i in stats.instances) / len(stats.instances))
            stats.best_entry_minute = int(sum(i.entry_time_minutes for i in stats.instances) / len(stats.instances))
            stats.avg_volume_ratio = sum(i.volume_ratio for i in stats.instances) / len(stats.instances)

    def _log_analysis_results(self, profitable: Dict[PatternType, PatternStats]):
        """Log analysis summary"""
        self.logger.info("=" * 60)
        self.logger.info("📈 PATTERN ANALYSIS RESULTS")
        self.logger.info("=" * 60)

        if not profitable:
            self.logger.info("⚠️ No patterns found with >60% win rate")
            return

        for pattern_type, stats in sorted(profitable.items(), key=lambda x: x[1].win_rate, reverse=True):
            self.logger.info(
                f"✅ {pattern_type.value.upper()}: "
                f"Win Rate={stats.win_rate*100:.1f}% | "
                f"Avg Gain={stats.avg_gain_pct*100:.2f}% | "
                f"Profit Factor={stats.profit_factor:.1f}x | "
                f"Occurrences={stats.total_occurrences}"
            )

        self.logger.info("=" * 60)

    def evaluate_setup(
        self,
        symbol: str,
        current_pattern: PatternType,
        current_price: float,
        volume_ratio: float = 1.0,
    ) -> Optional[SetupQuality]:
        """
        Evaluate a potential trade setup based on historical pattern performance.

        Returns SetupQuality with recommended position size and parameters.
        """
        if current_pattern not in self._pattern_stats:
            return None

        stats = self._pattern_stats[current_pattern]

        if stats.win_rate < self.min_win_rate:
            return None

        # Calculate quality grade
        if stats.win_rate >= 0.75 and stats.profit_factor >= 2.0:
            grade = "A+"
            confidence = 0.9
            position_pct = 0.35  # 35% position
        elif stats.win_rate >= 0.65 and stats.profit_factor >= 1.5:
            grade = "A"
            confidence = 0.75
            position_pct = 0.25  # 25% position
        elif stats.win_rate >= 0.60:
            grade = "B"
            confidence = 0.6
            position_pct = 0.15  # 15% position
        else:
            grade = "C"
            confidence = 0.4
            position_pct = 0.10  # 10% position

        # Adjust for volume
        if volume_ratio >= 2.0:
            confidence = min(1.0, confidence + 0.1)
            position_pct = min(0.40, position_pct + 0.05)

        # Determine entry timing
        if stats.best_entry_minute <= 5:
            entry_timing = "immediate"
        elif stats.best_entry_minute <= 30:
            entry_timing = "wait_dip"
        else:
            entry_timing = "wait_breakout"

        return SetupQuality(
            symbol=symbol,
            pattern=current_pattern,
            quality_grade=grade,
            confidence=confidence,
            recommended_position_pct=position_pct,
            expected_gain_pct=stats.avg_gain_pct,
            expected_loss_pct=stats.avg_loss_pct,
            historical_win_rate=stats.win_rate,
            entry_timing=entry_timing,
            stop_loss_pct=stats.avg_loss_pct * 1.2,  # Slightly wider stop
            take_profit_pct=stats.avg_gain_pct * 0.8,  # Conservative target
            max_hold_minutes=stats.avg_hold_minutes,
        )

    def get_recommended_patterns(self) -> List[PatternType]:
        """Get list of patterns with >60% win rate"""
        return [
            pt for pt, stats in self._pattern_stats.items()
            if stats.win_rate >= self.min_win_rate and stats.total_occurrences >= 5
        ]

    def get_pattern_summary(self) -> Dict:
        """Get summary of all analyzed patterns"""
        return {
            "analysis_date": self._last_analysis.isoformat() if self._last_analysis else None,
            "days_analyzed": self.analysis_days,
            "symbols_analyzed": len(self._analyzed_symbols),
            "patterns": {
                pt.value: stats.to_dict()
                for pt, stats in self._pattern_stats.items()
                if stats.total_occurrences > 0
            },
            "recommended_patterns": [pt.value for pt in self.get_recommended_patterns()],
        }
