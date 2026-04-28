"""
Hindsight Analyzer

Analyzes historical market data to find optimal trading scenarios
and extracts patterns to improve future agent decisions.
"""
import asyncio
import logging
from datetime import datetime, timedelta, time, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from alpaca.client import AlpacaClient, Bar


class PatternType(Enum):
    """Types of patterns detected around optimal points"""
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    VOLUME_SPIKE = "volume_spike"
    VWAP_RECLAIM = "vwap_reclaim"
    VWAP_REJECTION = "vwap_rejection"
    MORNING_MOMENTUM = "morning_momentum"
    REVERSAL = "reversal"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"
    CONSOLIDATION_BREAK = "consolidation_break"


@dataclass
class OptimalTrade:
    """Represents an optimal trade opportunity from hindsight analysis"""
    symbol: str
    optimal_buy_price: float
    optimal_buy_time: datetime
    optimal_sell_price: float
    optimal_sell_time: datetime
    max_gain_pct: float
    max_gain_dollars: float  # Based on $100 position
    patterns_at_entry: List[PatternType]
    patterns_at_exit: List[PatternType]
    volume_at_entry: int
    avg_volume: float
    volume_ratio: float
    time_held_minutes: int
    entry_session: str  # OPEN, MIDDAY, CLOSE

    @property
    def risk_reward_achieved(self) -> float:
        """Calculate achieved risk/reward assuming 2% stop"""
        risk = self.optimal_buy_price * 0.02
        reward = self.optimal_sell_price - self.optimal_buy_price
        return reward / risk if risk > 0 else 0


@dataclass
class AgentTradeComparison:
    """Comparison between agent's actual trade and optimal scenario"""
    symbol: str
    agent_entry_price: Optional[float]
    agent_entry_time: Optional[datetime]
    agent_exit_price: Optional[float]
    agent_exit_time: Optional[datetime]
    agent_pnl_pct: Optional[float]
    optimal_entry_price: float
    optimal_exit_price: float
    optimal_pnl_pct: float
    entry_gap_pct: float  # How far from optimal entry
    exit_gap_pct: float   # How far from optimal exit
    missed_opportunity: bool
    improvement_notes: List[str]


@dataclass
class HindsightPattern:
    """A learned pattern from hindsight analysis"""
    pattern_type: PatternType
    success_rate: float  # How often this pattern preceded optimal entries
    avg_gain_when_followed: float
    occurrence_count: int
    time_of_day_bias: str  # MORNING, MIDDAY, AFTERNOON
    volume_requirement: float  # Min volume ratio
    description: str


@dataclass
class DailyHindsightReport:
    """Complete hindsight analysis for a trading day"""
    date: datetime
    optimal_trades: List[OptimalTrade]
    agent_comparisons: List[AgentTradeComparison]
    total_optimal_gain: float  # If all optimal trades were taken
    agent_actual_gain: float
    performance_gap_pct: float
    top_patterns: List[HindsightPattern]
    lessons_learned: List[str]
    symbols_analyzed: int

    def to_memory_format(self) -> Dict:
        """Convert to format suitable for LayeredMemorySystem"""
        return {
            "date": self.date.isoformat(),
            "type": "hindsight_analysis",
            "optimal_trades": [
                {
                    "symbol": t.symbol,
                    "gain_pct": t.max_gain_pct,
                    "patterns": [p.value for p in t.patterns_at_entry],
                    "entry_session": t.entry_session,
                    "volume_ratio": t.volume_ratio,
                }
                for t in self.optimal_trades[:5]  # Top 5
            ],
            "top_patterns": [
                {
                    "pattern": p.pattern_type.value,
                    "success_rate": p.success_rate,
                    "avg_gain": p.avg_gain_when_followed,
                }
                for p in self.top_patterns
            ],
            "lessons": self.lessons_learned,
            "performance_gap": self.performance_gap_pct,
        }


class HindsightAnalyzer:
    """
    Analyzes historical market data to find what would have been
    the optimal trading decisions, and extracts patterns to improve
    future agent performance.
    """

    def __init__(self, client: Optional[AlpacaClient] = None):
        self.client = client or AlpacaClient()
        self.logger = logging.getLogger(__name__)

        # Pattern statistics (accumulated over time)
        self._pattern_stats: Dict[PatternType, Dict] = {}

        # Historical reports
        self._reports: List[DailyHindsightReport] = []

    async def analyze_day(
        self,
        date: Optional[datetime] = None,
        symbols: Optional[List[str]] = None,
        agent_trades: Optional[List[Dict]] = None,
    ) -> DailyHindsightReport:
        """
        Analyze a trading day to find optimal scenarios.

        Args:
            date: Date to analyze (default: yesterday)
            symbols: Symbols to analyze (default: discover from movers)
            agent_trades: List of trades the agent actually made

        Returns:
            DailyHindsightReport with optimal trades and comparisons
        """
        if date is None:
            date = datetime.now() - timedelta(days=1)

        self.logger.info(f"📊 Running hindsight analysis for {date.strftime('%Y-%m-%d')}...")

        # Get symbols to analyze
        if symbols is None:
            symbols = await self._get_analysis_symbols(date)

        self.logger.info(f"  Analyzing {len(symbols)} symbols...")

        # Analyze each symbol
        optimal_trades = []
        for symbol in symbols:
            try:
                trade = await self._analyze_symbol(symbol, date)
                if trade and trade.max_gain_pct >= 1.0:  # Min 1% gain to be interesting
                    optimal_trades.append(trade)
            except Exception as e:
                self.logger.debug(f"  Error analyzing {symbol}: {e}")

        # Sort by gain potential
        optimal_trades.sort(key=lambda t: t.max_gain_pct, reverse=True)

        self.logger.info(f"  Found {len(optimal_trades)} optimal opportunities")

        # Compare with agent trades
        comparisons = []
        if agent_trades:
            comparisons = self._compare_with_agent(optimal_trades, agent_trades)

        # Extract patterns
        top_patterns = self._extract_patterns(optimal_trades)

        # Generate lessons learned
        lessons = self._generate_lessons(optimal_trades, comparisons)

        # Calculate totals
        total_optimal = sum(t.max_gain_pct for t in optimal_trades[:5])  # Top 5
        agent_actual = sum(c.agent_pnl_pct or 0 for c in comparisons)

        report = DailyHindsightReport(
            date=date,
            optimal_trades=optimal_trades,
            agent_comparisons=comparisons,
            total_optimal_gain=total_optimal,
            agent_actual_gain=agent_actual,
            performance_gap_pct=total_optimal - agent_actual,
            top_patterns=top_patterns,
            lessons_learned=lessons,
            symbols_analyzed=len(symbols),
        )

        self._reports.append(report)

        return report

    async def _get_analysis_symbols(self, date: datetime) -> List[str]:
        """Get symbols to analyze - top movers from that day"""
        # For now, use a list of popular day trading stocks
        # In production, this would fetch actual movers from the date
        base_symbols = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
            'AMD', 'NFLX', 'SPY', 'QQQ', 'RIVN', 'PLTR', 'SOFI',
            'NIO', 'LCID', 'COIN', 'MARA', 'RIOT', 'SQ', 'PYPL',
            'UBER', 'LYFT', 'SNAP', 'PINS', 'RBLX', 'U', 'DKNG',
        ]
        return base_symbols

    async def _analyze_symbol(self, symbol: str, date: datetime) -> Optional[OptimalTrade]:
        """
        Analyze a single symbol to find optimal entry/exit.
        """
        # Fetch intraday bars (5-minute)
        # Use US Eastern time for market hours, then convert to UTC for API
        # Market open is 9:30 ET, close is 16:00 ET
        # For simplicity, we use UTC and add 5 hours (EST offset) or just use date format
        start = datetime.combine(date.date(), time(14, 30), tzinfo=timezone.utc)  # 9:30 ET = 14:30 UTC
        end = datetime.combine(date.date(), time(21, 0), tzinfo=timezone.utc)     # 16:00 ET = 21:00 UTC

        bars = await self.client.get_bars(
            symbol=symbol,
            timeframe='5Min',
            start=start,
            end=end,
            limit=500,
        )

        if len(bars) < 10:
            return None

        # Find optimal buy point (lowest price)
        min_bar = min(bars, key=lambda b: b.low)
        min_idx = bars.index(min_bar)

        # Find optimal sell point (highest price AFTER the buy)
        bars_after_min = bars[min_idx:]
        if not bars_after_min:
            return None

        max_bar = max(bars_after_min, key=lambda b: b.high)

        optimal_buy = min_bar.low
        optimal_sell = max_bar.high

        if optimal_sell <= optimal_buy:
            return None

        # Calculate gain
        max_gain_pct = ((optimal_sell - optimal_buy) / optimal_buy) * 100
        max_gain_dollars = (max_gain_pct / 100) * 100  # $100 position

        # Calculate time held
        time_held = int((max_bar.timestamp - min_bar.timestamp).total_seconds() / 60)

        # Detect patterns at entry
        entry_patterns = self._detect_patterns_at_point(bars, min_idx, 'entry')
        exit_patterns = self._detect_patterns_at_point(bars, bars.index(max_bar), 'exit')

        # Calculate volume metrics
        avg_volume = sum(b.volume for b in bars) / len(bars)
        volume_at_entry = min_bar.volume
        volume_ratio = volume_at_entry / avg_volume if avg_volume > 0 else 1.0

        # Determine entry session
        entry_hour = min_bar.timestamp.hour
        if entry_hour < 10 or (entry_hour == 10 and min_bar.timestamp.minute < 30):
            entry_session = "OPEN"
        elif entry_hour < 14:
            entry_session = "MIDDAY"
        else:
            entry_session = "CLOSE"

        return OptimalTrade(
            symbol=symbol,
            optimal_buy_price=optimal_buy,
            optimal_buy_time=min_bar.timestamp,
            optimal_sell_price=optimal_sell,
            optimal_sell_time=max_bar.timestamp,
            max_gain_pct=max_gain_pct,
            max_gain_dollars=max_gain_dollars,
            patterns_at_entry=entry_patterns,
            patterns_at_exit=exit_patterns,
            volume_at_entry=volume_at_entry,
            avg_volume=avg_volume,
            volume_ratio=volume_ratio,
            time_held_minutes=time_held,
            entry_session=entry_session,
        )

    def _detect_patterns_at_point(
        self,
        bars: List[Bar],
        idx: int,
        point_type: str
    ) -> List[PatternType]:
        """Detect technical patterns around a specific point"""
        patterns = []

        if idx < 3 or idx >= len(bars) - 1:
            return patterns

        current = bars[idx]
        prev_bars = bars[max(0, idx-5):idx]

        # Volume spike detection
        avg_vol = sum(b.volume for b in prev_bars) / len(prev_bars) if prev_bars else 1
        if current.volume > avg_vol * 1.5:
            patterns.append(PatternType.VOLUME_SPIKE)

        # Gap detection (comparing to previous close)
        if idx > 0:
            prev_close = bars[idx-1].close
            gap_pct = ((current.open - prev_close) / prev_close) * 100
            if gap_pct > 1.0:
                patterns.append(PatternType.GAP_UP)
            elif gap_pct < -1.0:
                patterns.append(PatternType.GAP_DOWN)

        # VWAP detection (approximation using cumulative average)
        if current.vwap:
            if point_type == 'entry' and current.low < current.vwap < current.close:
                patterns.append(PatternType.VWAP_RECLAIM)
            elif point_type == 'exit' and current.high > current.vwap > current.close:
                patterns.append(PatternType.VWAP_REJECTION)

        # Morning momentum (first 30 min)
        if current.timestamp.hour == 9 or (current.timestamp.hour == 10 and current.timestamp.minute < 30):
            patterns.append(PatternType.MORNING_MOMENTUM)

        # Reversal detection
        if point_type == 'entry':
            # Look for lower lows then higher low
            recent_lows = [b.low for b in prev_bars[-3:]]
            if len(recent_lows) >= 2 and current.low > min(recent_lows):
                patterns.append(PatternType.REVERSAL)

        # Breakout detection
        if point_type == 'exit':
            recent_highs = [b.high for b in prev_bars]
            if recent_highs and current.high > max(recent_highs):
                patterns.append(PatternType.BREAKOUT)

        return patterns

    def _compare_with_agent(
        self,
        optimal_trades: List[OptimalTrade],
        agent_trades: List[Dict]
    ) -> List[AgentTradeComparison]:
        """Compare agent's actual trades with optimal scenarios"""
        comparisons = []

        # Create lookup by symbol
        optimal_by_symbol = {t.symbol: t for t in optimal_trades}
        agent_by_symbol = {}
        for trade in agent_trades:
            symbol = trade.get('symbol')
            if symbol:
                agent_by_symbol[symbol] = trade

        # Compare overlapping symbols
        all_symbols = set(optimal_by_symbol.keys()) | set(agent_by_symbol.keys())

        for symbol in all_symbols:
            optimal = optimal_by_symbol.get(symbol)
            agent = agent_by_symbol.get(symbol)

            if optimal and agent:
                # Both traded - compare
                agent_entry = agent.get('entry_price')
                agent_exit = agent.get('exit_price')
                agent_pnl = agent.get('pnl_pct')

                entry_gap = 0
                if agent_entry and optimal.optimal_buy_price:
                    entry_gap = ((agent_entry - optimal.optimal_buy_price) / optimal.optimal_buy_price) * 100

                exit_gap = 0
                if agent_exit and optimal.optimal_sell_price:
                    exit_gap = ((optimal.optimal_sell_price - agent_exit) / optimal.optimal_sell_price) * 100

                notes = []
                if entry_gap > 2:
                    notes.append(f"Entry was {entry_gap:.1f}% above optimal")
                if exit_gap > 2:
                    notes.append(f"Exit was {exit_gap:.1f}% below optimal")

                comparisons.append(AgentTradeComparison(
                    symbol=symbol,
                    agent_entry_price=agent_entry,
                    agent_entry_time=agent.get('entry_time'),
                    agent_exit_price=agent_exit,
                    agent_exit_time=agent.get('exit_time'),
                    agent_pnl_pct=agent_pnl,
                    optimal_entry_price=optimal.optimal_buy_price,
                    optimal_exit_price=optimal.optimal_sell_price,
                    optimal_pnl_pct=optimal.max_gain_pct,
                    entry_gap_pct=entry_gap,
                    exit_gap_pct=exit_gap,
                    missed_opportunity=False,
                    improvement_notes=notes,
                ))

            elif optimal and not agent:
                # Optimal opportunity missed
                comparisons.append(AgentTradeComparison(
                    symbol=symbol,
                    agent_entry_price=None,
                    agent_entry_time=None,
                    agent_exit_price=None,
                    agent_exit_time=None,
                    agent_pnl_pct=None,
                    optimal_entry_price=optimal.optimal_buy_price,
                    optimal_exit_price=optimal.optimal_sell_price,
                    optimal_pnl_pct=optimal.max_gain_pct,
                    entry_gap_pct=100,  # Missed entirely
                    exit_gap_pct=100,
                    missed_opportunity=True,
                    improvement_notes=[
                        f"Missed {optimal.max_gain_pct:.1f}% opportunity",
                        f"Patterns: {', '.join(p.value for p in optimal.patterns_at_entry)}",
                        f"Session: {optimal.entry_session}",
                    ],
                ))

        return comparisons

    def _extract_patterns(self, optimal_trades: List[OptimalTrade]) -> List[HindsightPattern]:
        """Extract and rank patterns from optimal trades"""
        pattern_counts: Dict[PatternType, Dict] = {}

        for trade in optimal_trades:
            for pattern in trade.patterns_at_entry:
                if pattern not in pattern_counts:
                    pattern_counts[pattern] = {
                        'count': 0,
                        'total_gain': 0,
                        'sessions': [],
                        'volume_ratios': [],
                    }
                pattern_counts[pattern]['count'] += 1
                pattern_counts[pattern]['total_gain'] += trade.max_gain_pct
                pattern_counts[pattern]['sessions'].append(trade.entry_session)
                pattern_counts[pattern]['volume_ratios'].append(trade.volume_ratio)

        # Convert to HindsightPattern objects
        patterns = []
        total_trades = len(optimal_trades)

        for pattern_type, stats in pattern_counts.items():
            count = stats['count']
            avg_gain = stats['total_gain'] / count if count > 0 else 0

            # Calculate most common session
            sessions = stats['sessions']
            session_counts = {}
            for s in sessions:
                session_counts[s] = session_counts.get(s, 0) + 1
            most_common_session = max(session_counts, key=session_counts.get) if session_counts else "ANY"

            # Average volume ratio
            avg_vol_ratio = sum(stats['volume_ratios']) / len(stats['volume_ratios']) if stats['volume_ratios'] else 1.0

            patterns.append(HindsightPattern(
                pattern_type=pattern_type,
                success_rate=count / total_trades if total_trades > 0 else 0,
                avg_gain_when_followed=avg_gain,
                occurrence_count=count,
                time_of_day_bias=most_common_session,
                volume_requirement=avg_vol_ratio * 0.8,  # 80% of avg as threshold
                description=self._get_pattern_description(pattern_type),
            ))

        # Sort by avg gain
        patterns.sort(key=lambda p: p.avg_gain_when_followed, reverse=True)

        return patterns[:5]  # Top 5 patterns

    def _get_pattern_description(self, pattern: PatternType) -> str:
        """Get human-readable description of pattern"""
        descriptions = {
            PatternType.GAP_UP: "Stock opened significantly higher than previous close",
            PatternType.GAP_DOWN: "Stock opened significantly lower - potential bounce",
            PatternType.VOLUME_SPIKE: "Unusual volume indicating institutional interest",
            PatternType.VWAP_RECLAIM: "Price reclaimed VWAP - bullish continuation",
            PatternType.VWAP_REJECTION: "Price rejected at VWAP - potential reversal",
            PatternType.MORNING_MOMENTUM: "Strong move in first 30 minutes",
            PatternType.REVERSAL: "Price formed higher low after downtrend",
            PatternType.BREAKOUT: "Price broke above recent resistance",
            PatternType.BREAKDOWN: "Price broke below recent support",
            PatternType.CONSOLIDATION_BREAK: "Price broke out of tight range",
        }
        return descriptions.get(pattern, "Pattern detected")

    def _generate_lessons(
        self,
        optimal_trades: List[OptimalTrade],
        comparisons: List[AgentTradeComparison]
    ) -> List[str]:
        """Generate actionable lessons from the analysis"""
        lessons = []

        if not optimal_trades:
            return ["No significant opportunities found for this day"]

        # Analyze entry timing
        open_entries = [t for t in optimal_trades if t.entry_session == "OPEN"]
        if len(open_entries) > len(optimal_trades) * 0.5:
            lessons.append(
                f"📈 {len(open_entries)}/{len(optimal_trades)} optimal entries were in OPEN session (9:30-10:30). "
                f"Consider being more aggressive during market open."
            )

        # Analyze patterns
        all_patterns = []
        for t in optimal_trades:
            all_patterns.extend(t.patterns_at_entry)

        if all_patterns:
            most_common = max(set(all_patterns), key=all_patterns.count)
            count = all_patterns.count(most_common)
            lessons.append(
                f"🔍 Pattern '{most_common.value}' appeared in {count}/{len(optimal_trades)} optimal entries. "
                f"Increase weight for this pattern in scoring."
            )

        # Analyze volume
        high_vol_trades = [t for t in optimal_trades if t.volume_ratio > 1.5]
        if high_vol_trades:
            avg_gain = sum(t.max_gain_pct for t in high_vol_trades) / len(high_vol_trades)
            lessons.append(
                f"📊 High volume entries (>1.5x avg) averaged {avg_gain:.1f}% gain. "
                f"Volume confirmation is valuable."
            )

        # Analyze missed opportunities
        missed = [c for c in comparisons if c.missed_opportunity]
        if missed:
            top_missed = sorted(missed, key=lambda c: c.optimal_pnl_pct, reverse=True)[:3]
            symbols = [c.symbol for c in top_missed]
            lessons.append(
                f"❌ Missed opportunities: {', '.join(symbols)}. "
                f"Review why these weren't detected."
            )

        # Analyze entry accuracy
        traded = [c for c in comparisons if not c.missed_opportunity and c.entry_gap_pct is not None]
        if traded:
            avg_entry_gap = sum(c.entry_gap_pct for c in traded) / len(traded)
            if avg_entry_gap > 2:
                lessons.append(
                    f"⚠️ Average entry was {avg_entry_gap:.1f}% above optimal. "
                    f"Consider waiting for better entries or using limit orders."
                )

        return lessons

    def format_report(self, report: DailyHindsightReport) -> str:
        """Format report for CLI display"""
        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"📊 HINDSIGHT ANALYSIS - {report.date.strftime('%Y-%m-%d')}")
        lines.append(f"{'='*70}\n")

        # Top opportunities
        lines.append("TOP OPTIMAL OPPORTUNITIES:")
        lines.append("-" * 70)
        lines.append(f"{'Symbol':<8} {'Buy @':<10} {'Sell @':<10} {'Gain':<8} {'Time':<8} {'Patterns'}")
        lines.append("-" * 70)

        for trade in report.optimal_trades[:10]:
            patterns_str = ', '.join(p.value for p in trade.patterns_at_entry[:2])
            lines.append(
                f"{trade.symbol:<8} "
                f"${trade.optimal_buy_price:<9.2f} "
                f"${trade.optimal_sell_price:<9.2f} "
                f"+{trade.max_gain_pct:<6.1f}% "
                f"{trade.time_held_minutes:<6}m "
                f"{patterns_str}"
            )

        lines.append("")

        # Agent comparison
        if report.agent_comparisons:
            lines.append("\nAGENT PERFORMANCE vs OPTIMAL:")
            lines.append("-" * 70)

            for comp in report.agent_comparisons[:5]:
                if comp.missed_opportunity:
                    lines.append(f"  ❌ {comp.symbol}: MISSED (+{comp.optimal_pnl_pct:.1f}% opportunity)")
                else:
                    diff = (comp.agent_pnl_pct or 0) - comp.optimal_pnl_pct
                    lines.append(
                        f"  {'✅' if diff > -2 else '⚠️'} {comp.symbol}: "
                        f"Agent {comp.agent_pnl_pct or 0:+.1f}% vs Optimal +{comp.optimal_pnl_pct:.1f}% "
                        f"(gap: {diff:+.1f}%)"
                    )

        # Top patterns
        if report.top_patterns:
            lines.append("\nTOP PATTERNS DETECTED:")
            lines.append("-" * 70)

            for pattern in report.top_patterns:
                lines.append(
                    f"  • {pattern.pattern_type.value}: "
                    f"{pattern.occurrence_count} occurrences, "
                    f"+{pattern.avg_gain_when_followed:.1f}% avg gain, "
                    f"best in {pattern.time_of_day_bias}"
                )

        # Lessons learned
        if report.lessons_learned:
            lines.append("\n📚 LESSONS LEARNED:")
            lines.append("-" * 70)
            for lesson in report.lessons_learned:
                lines.append(f"  {lesson}")

        # Summary
        lines.append(f"\n{'='*70}")
        lines.append(f"SUMMARY: Analyzed {report.symbols_analyzed} symbols")
        lines.append(f"  Total optimal gain (top 5): +{report.total_optimal_gain:.1f}%")
        lines.append(f"  Agent actual gain: +{report.agent_actual_gain:.1f}%")
        lines.append(f"  Performance gap: {report.performance_gap_pct:.1f}%")
        lines.append(f"{'='*70}\n")

        return '\n'.join(lines)

    async def run_and_learn(
        self,
        memory_system=None,
        date: Optional[datetime] = None,
        agent_trades: Optional[List[Dict]] = None,
    ) -> DailyHindsightReport:
        """
        Run analysis and store lessons in memory system for future learning.

        Args:
            memory_system: LayeredMemorySystem instance for storing patterns
            date: Date to analyze
            agent_trades: Agent's actual trades for comparison

        Returns:
            DailyHindsightReport
        """
        report = await self.analyze_day(date=date, agent_trades=agent_trades)

        # Store in memory system if provided
        if memory_system:
            try:
                # Store top patterns as "pattern" memory type
                for pattern in report.top_patterns:
                    memory_system.add_memory(
                        memory_type="pattern",
                        content={
                            "pattern_type": pattern.pattern_type.value,
                            "description": pattern.description,
                            "success_rate": pattern.success_rate,
                            "avg_gain": pattern.avg_gain_when_followed,
                            "time_of_day_bias": pattern.time_of_day_bias,
                            "date": report.date.isoformat(),
                            "source": "hindsight_analysis",
                        },
                        importance=min(0.9, 0.5 + pattern.success_rate),
                        tags=["hindsight", "pattern", pattern.pattern_type.value],
                    )

                # Store lessons learned as "news" type (general information)
                for lesson in report.lessons_learned:
                    memory_system.add_memory(
                        memory_type="news",
                        content={
                            "lesson": lesson,
                            "date": report.date.isoformat(),
                            "source": "hindsight_analysis",
                        },
                        importance=0.6,
                        tags=["hindsight", "lesson"],
                    )

                # Save memories to disk
                memory_system.save()

                self.logger.info(f"💾 Stored {len(report.top_patterns)} patterns and {len(report.lessons_learned)} lessons in memory")

            except Exception as e:
                self.logger.error(f"Failed to store in memory system: {e}")

        return report


# Convenience function for CLI usage
async def run_hindsight_analysis(
    date: Optional[datetime] = None,
    symbols: Optional[List[str]] = None,
) -> str:
    """
    Run hindsight analysis and return formatted report.

    Usage:
        from agent.core.hindsight import run_hindsight_analysis
        import asyncio
        print(asyncio.run(run_hindsight_analysis()))
    """
    analyzer = HindsightAnalyzer()
    report = await analyzer.analyze_day(date=date, symbols=symbols)
    return analyzer.format_report(report)
