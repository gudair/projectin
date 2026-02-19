"""
Periodic Reflection Agent - Trade Performance Analysis

Analyzes trades every N executions to:
- Detect recurring mistakes
- Calibrate confidence (are we overconfident?)
- Identify winning/losing patterns
- Generate actionable improvements

Inspired by LLM-TradeBot's ReflectionAgent.
"""
import logging
import json
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ReflectionReport:
    """Report generated from periodic reflection"""
    report_id: str
    generated_at: datetime
    trades_analyzed: int
    period_start: datetime
    period_end: datetime

    # Performance metrics
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float  # Total wins / Total losses
    total_pnl_pct: float

    # Confidence calibration
    confidence_accuracy: float  # How well confidence predicts success
    overconfidence_score: float  # Positive = overconfident
    suggested_confidence_adjustment: float

    # Pattern analysis
    best_setup_types: List[Dict]
    worst_setup_types: List[Dict]
    best_market_regimes: List[str]
    worst_market_regimes: List[str]

    # Timing analysis
    best_entry_times: List[str]
    worst_entry_times: List[str]
    avg_hold_duration_winners: float  # minutes
    avg_hold_duration_losers: float

    # Issues detected
    recurring_mistakes: List[str]
    improvement_suggestions: List[str]

    # Adjustments to apply
    adjustments: Dict[str, float]

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "trades_analyzed": self.trades_analyzed,
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "performance": {
                "win_rate": round(self.win_rate, 3),
                "avg_win_pct": round(self.avg_win_pct, 3),
                "avg_loss_pct": round(self.avg_loss_pct, 3),
                "profit_factor": round(self.profit_factor, 2),
                "total_pnl_pct": round(self.total_pnl_pct, 3),
            },
            "confidence_calibration": {
                "accuracy": round(self.confidence_accuracy, 3),
                "overconfidence_score": round(self.overconfidence_score, 3),
                "adjustment": round(self.suggested_confidence_adjustment, 3),
            },
            "patterns": {
                "best_setups": self.best_setup_types,
                "worst_setups": self.worst_setup_types,
                "best_regimes": self.best_market_regimes,
                "worst_regimes": self.worst_market_regimes,
            },
            "timing": {
                "best_entry_times": self.best_entry_times,
                "worst_entry_times": self.worst_entry_times,
                "avg_hold_winners_min": round(self.avg_hold_duration_winners, 1),
                "avg_hold_losers_min": round(self.avg_hold_duration_losers, 1),
            },
            "insights": {
                "mistakes": self.recurring_mistakes,
                "suggestions": self.improvement_suggestions,
            },
            "adjustments": self.adjustments,
        }


class PeriodicReflectionAgent:
    """
    Analyzes trading performance every N trades.

    Key features:
    - Automatic reflection after N trades
    - Confidence calibration (detects overconfidence)
    - Pattern detection (what works, what doesn't)
    - Actionable adjustments

    Uses Ollama for deeper analysis when available.
    """

    def __init__(
        self,
        trade_log_dir: str = "logs/trades",
        reflection_interval: int = 10,  # Reflect every 10 trades
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.2",
    ):
        self.trade_log_dir = Path(trade_log_dir)
        self.reflection_interval = reflection_interval
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.logger = logging.getLogger(__name__)

        # Track reflection state
        self._trades_since_reflection: int = 0
        self._last_reflection: Optional[datetime] = None
        self._current_adjustments: Dict[str, float] = {}

        # Reflection history
        self._reflection_history: List[ReflectionReport] = []

        # Load any existing adjustments
        self._load_adjustments()

    def record_trade(self):
        """Record that a trade was executed. Returns True if reflection needed."""
        self._trades_since_reflection += 1
        return self._trades_since_reflection >= self.reflection_interval

    def should_reflect(self) -> bool:
        """Check if it's time for periodic reflection"""
        return self._trades_since_reflection >= self.reflection_interval

    def get_current_adjustments(self) -> Dict[str, float]:
        """Get current adjustments from last reflection"""
        return self._current_adjustments.copy()

    async def run_reflection(self, force: bool = False) -> Optional[ReflectionReport]:
        """
        Run periodic reflection analysis.

        Args:
            force: Run even if interval not reached

        Returns:
            ReflectionReport with insights and adjustments
        """
        if not force and not self.should_reflect():
            return None

        self.logger.info(
            f"🔍 Running periodic reflection "
            f"({self._trades_since_reflection} trades since last)"
        )

        # Load recent trades with outcomes
        trades = self._load_recent_trades()

        if len(trades) < 5:
            self.logger.info("Not enough trades with outcomes for reflection")
            return None

        # Calculate metrics
        report = await self._analyze_trades(trades)

        if report:
            # Store report
            self._reflection_history.append(report)
            self._current_adjustments = report.adjustments
            self._save_adjustments()

            # Reset counter
            self._trades_since_reflection = 0
            self._last_reflection = datetime.now()

            # Log summary
            self._log_reflection_summary(report)

        return report

    def _load_recent_trades(self, days_back: int = 30) -> List[Dict]:
        """Load trades with outcomes from log files"""
        trades = []

        if not self.trade_log_dir.exists():
            return trades

        for i in range(days_back):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = self.trade_log_dir / f"trades_{date}.jsonl"

            if log_file.exists():
                try:
                    with open(log_file, 'r') as f:
                        for line in f:
                            try:
                                trade = json.loads(line)
                                # Only include trades with outcomes
                                if trade.get('outcome'):
                                    trades.append(trade)
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    self.logger.debug(f"Error loading {log_file}: {e}")

        return trades

    async def _analyze_trades(self, trades: List[Dict]) -> Optional[ReflectionReport]:
        """Analyze trades and generate reflection report"""
        if not trades:
            return None

        # Separate winners and losers
        winners = [t for t in trades if t['outcome'].get('profitable', False)]
        losers = [t for t in trades if not t['outcome'].get('profitable', False)]

        # Basic metrics
        win_rate = len(winners) / len(trades) if trades else 0

        avg_win_pct = 0
        if winners:
            avg_win_pct = sum(
                t['outcome'].get('pnl_percent', 0) for t in winners
            ) / len(winners)

        avg_loss_pct = 0
        if losers:
            avg_loss_pct = sum(
                t['outcome'].get('pnl_percent', 0) for t in losers
            ) / len(losers)

        total_wins = sum(t['outcome'].get('pnl_dollars', 0) for t in winners)
        total_losses = abs(sum(t['outcome'].get('pnl_dollars', 0) for t in losers))
        profit_factor = total_wins / total_losses if total_losses > 0 else 999

        total_pnl_pct = sum(t['outcome'].get('pnl_percent', 0) for t in trades)

        # Confidence calibration
        confidence_data = self._analyze_confidence(trades)

        # Pattern analysis
        setup_analysis = self._analyze_setups(trades)
        regime_analysis = self._analyze_regimes(trades)
        timing_analysis = self._analyze_timing(trades, winners, losers)

        # Detect recurring mistakes
        mistakes = self._detect_mistakes(trades, losers)

        # Generate suggestions (optionally with Ollama)
        suggestions = await self._generate_suggestions(
            trades, winners, losers, mistakes
        )

        # Calculate adjustments
        adjustments = self._calculate_adjustments(
            win_rate, confidence_data, setup_analysis
        )

        # Build report
        period_dates = [
            datetime.fromisoformat(t.get('timestamp', datetime.now().isoformat()))
            for t in trades if t.get('timestamp')
        ]

        report = ReflectionReport(
            report_id=f"reflection_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            generated_at=datetime.now(),
            trades_analyzed=len(trades),
            period_start=min(period_dates) if period_dates else datetime.now(),
            period_end=max(period_dates) if period_dates else datetime.now(),
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            profit_factor=profit_factor,
            total_pnl_pct=total_pnl_pct,
            confidence_accuracy=confidence_data['accuracy'],
            overconfidence_score=confidence_data['overconfidence'],
            suggested_confidence_adjustment=confidence_data['adjustment'],
            best_setup_types=setup_analysis['best'],
            worst_setup_types=setup_analysis['worst'],
            best_market_regimes=regime_analysis['best'],
            worst_market_regimes=regime_analysis['worst'],
            best_entry_times=timing_analysis['best_times'],
            worst_entry_times=timing_analysis['worst_times'],
            avg_hold_duration_winners=timing_analysis['avg_hold_winners'],
            avg_hold_duration_losers=timing_analysis['avg_hold_losers'],
            recurring_mistakes=mistakes,
            improvement_suggestions=suggestions,
            adjustments=adjustments,
        )

        # Save report
        self._save_report(report)

        return report

    def _analyze_confidence(self, trades: List[Dict]) -> Dict:
        """Analyze confidence calibration"""
        # Group trades by confidence level
        high_conf = [t for t in trades if t.get('confidence', 0) >= 0.7]
        med_conf = [t for t in trades if 0.5 <= t.get('confidence', 0) < 0.7]
        low_conf = [t for t in trades if t.get('confidence', 0) < 0.5]

        # Win rates by confidence
        high_win = len([t for t in high_conf if t['outcome'].get('profitable')]) / len(high_conf) if high_conf else 0
        med_win = len([t for t in med_conf if t['outcome'].get('profitable')]) / len(med_conf) if med_conf else 0
        low_win = len([t for t in low_conf if t['outcome'].get('profitable')]) / len(low_conf) if low_conf else 0

        # Accuracy = correlation between confidence and outcomes
        # If high_conf trades win more than low_conf, calibration is good
        accuracy = 0.5  # Neutral
        if high_conf and low_conf:
            if high_win > low_win:
                accuracy = 0.7 + (high_win - low_win) * 0.3
            else:
                accuracy = 0.3 - (low_win - high_win) * 0.3

        # Overconfidence = average confidence - actual win rate
        avg_confidence = sum(t.get('confidence', 0.5) for t in trades) / len(trades)
        actual_win_rate = len([t for t in trades if t['outcome'].get('profitable')]) / len(trades)
        overconfidence = avg_confidence - actual_win_rate

        # Adjustment to apply
        adjustment = -overconfidence * 0.5  # Reduce confidence if overconfident

        return {
            'accuracy': accuracy,
            'overconfidence': overconfidence,
            'adjustment': max(-0.2, min(0.2, adjustment)),  # Clamp to ±20%
            'by_level': {
                'high': {'count': len(high_conf), 'win_rate': high_win},
                'medium': {'count': len(med_conf), 'win_rate': med_win},
                'low': {'count': len(low_conf), 'win_rate': low_win},
            }
        }

    def _analyze_setups(self, trades: List[Dict]) -> Dict:
        """Analyze performance by setup type"""
        by_setup = {}

        for trade in trades:
            setup = trade.get('setup_type', 'unknown')
            if setup not in by_setup:
                by_setup[setup] = {'wins': 0, 'losses': 0, 'total_pnl': 0}

            if trade['outcome'].get('profitable'):
                by_setup[setup]['wins'] += 1
            else:
                by_setup[setup]['losses'] += 1
            by_setup[setup]['total_pnl'] += trade['outcome'].get('pnl_percent', 0)

        # Calculate win rates
        setup_stats = []
        for setup, data in by_setup.items():
            total = data['wins'] + data['losses']
            if total >= 3:  # Minimum sample size
                setup_stats.append({
                    'setup': setup,
                    'win_rate': data['wins'] / total,
                    'avg_pnl': data['total_pnl'] / total,
                    'count': total,
                })

        # Sort by win rate
        setup_stats.sort(key=lambda x: x['win_rate'], reverse=True)

        return {
            'best': setup_stats[:3],
            'worst': setup_stats[-3:] if len(setup_stats) > 3 else [],
        }

    def _analyze_regimes(self, trades: List[Dict]) -> Dict:
        """Analyze performance by market regime"""
        by_regime = {}

        for trade in trades:
            regime = trade.get('market_context', {}).get('regime', 'unknown')
            if regime not in by_regime:
                by_regime[regime] = {'wins': 0, 'losses': 0}

            if trade['outcome'].get('profitable'):
                by_regime[regime]['wins'] += 1
            else:
                by_regime[regime]['losses'] += 1

        # Sort by win rate
        regime_stats = []
        for regime, data in by_regime.items():
            total = data['wins'] + data['losses']
            if total >= 2:
                regime_stats.append({
                    'regime': regime,
                    'win_rate': data['wins'] / total,
                    'count': total,
                })

        regime_stats.sort(key=lambda x: x['win_rate'], reverse=True)

        return {
            'best': [r['regime'] for r in regime_stats[:2]],
            'worst': [r['regime'] for r in regime_stats[-2:]],
        }

    def _analyze_timing(
        self,
        trades: List[Dict],
        winners: List[Dict],
        losers: List[Dict]
    ) -> Dict:
        """Analyze entry timing and hold durations"""
        # Entry times
        time_performance = {}
        for trade in trades:
            ts = trade.get('timestamp', '')
            if ts:
                try:
                    hour = datetime.fromisoformat(ts).hour
                    time_bucket = f"{hour:02d}:00"
                    if time_bucket not in time_performance:
                        time_performance[time_bucket] = {'wins': 0, 'total': 0}
                    time_performance[time_bucket]['total'] += 1
                    if trade['outcome'].get('profitable'):
                        time_performance[time_bucket]['wins'] += 1
                except:
                    pass

        # Sort by win rate
        time_stats = [
            (time, data['wins'] / data['total'])
            for time, data in time_performance.items()
            if data['total'] >= 2
        ]
        time_stats.sort(key=lambda x: x[1], reverse=True)

        best_times = [t[0] for t in time_stats[:3]]
        worst_times = [t[0] for t in time_stats[-3:]]

        # Hold durations
        def avg_hold(trades_list):
            durations = [
                t['outcome'].get('hold_duration_minutes', 0)
                for t in trades_list
                if t['outcome'].get('hold_duration_minutes')
            ]
            return sum(durations) / len(durations) if durations else 0

        return {
            'best_times': best_times,
            'worst_times': worst_times,
            'avg_hold_winners': avg_hold(winners),
            'avg_hold_losers': avg_hold(losers),
        }

    def _detect_mistakes(self, trades: List[Dict], losers: List[Dict]) -> List[str]:
        """Detect recurring mistakes in losing trades"""
        mistakes = []

        if not losers:
            return mistakes

        # Check for overtrading
        trades_per_day = {}
        for trade in trades:
            day = trade.get('timestamp', '')[:10]
            trades_per_day[day] = trades_per_day.get(day, 0) + 1

        avg_per_day = sum(trades_per_day.values()) / len(trades_per_day) if trades_per_day else 0
        if avg_per_day > 5:
            mistakes.append(f"Possible overtrading: {avg_per_day:.1f} trades/day average")

        # Check for chasing (entering after big moves)
        big_move_losses = [
            t for t in losers
            if t.get('technical_data', {}).get('change_pct', 0) > 5
        ]
        if len(big_move_losses) > len(losers) * 0.3:
            mistakes.append("Chasing: Many losses after entering >5% movers")

        # Check for holding losers too long
        long_hold_losses = [
            t for t in losers
            if t['outcome'].get('hold_duration_minutes', 0) > 120
        ]
        if len(long_hold_losses) > len(losers) * 0.4:
            mistakes.append("Holding losers too long: >40% held > 2 hours")

        # Check for cutting winners short
        short_hold_wins = [
            t for t in trades
            if t['outcome'].get('profitable') and
               t['outcome'].get('hold_duration_minutes', 999) < 30
        ]
        if short_hold_wins and len(short_hold_wins) > len(trades) * 0.3:
            mistakes.append("Cutting winners short: Many profitable trades held < 30 min")

        # Check for low volume entries
        low_vol_losses = [
            t for t in losers
            if t.get('technical_data', {}).get('volume_ratio', 999) < 1.5
        ]
        if len(low_vol_losses) > len(losers) * 0.4:
            mistakes.append("Low volume entries: Many losses with volume ratio < 1.5x")

        return mistakes[:5]  # Limit to top 5 mistakes

    async def _generate_suggestions(
        self,
        trades: List[Dict],
        winners: List[Dict],
        losers: List[Dict],
        mistakes: List[str]
    ) -> List[str]:
        """Generate improvement suggestions, optionally using Ollama"""
        suggestions = []

        # Rule-based suggestions
        win_rate = len(winners) / len(trades) if trades else 0

        if win_rate < 0.4:
            suggestions.append("Focus on higher quality setups (score >= 6)")

        if win_rate > 0.6 and len(winners) > 5:
            avg_win = sum(t['outcome'].get('pnl_percent', 0) for t in winners) / len(winners)
            avg_loss = abs(sum(t['outcome'].get('pnl_percent', 0) for t in losers) / len(losers)) if losers else 0
            if avg_loss > avg_win:
                suggestions.append("Wins are good but losses are larger - tighten stop losses")

        for mistake in mistakes:
            if "overtrading" in mistake.lower():
                suggestions.append("Reduce trade frequency - wait for A+ setups only")
            if "chasing" in mistake.lower():
                suggestions.append("Avoid entries after >4% moves - wait for pullbacks")
            if "holding losers" in mistake.lower():
                suggestions.append("Honor stop losses faster - set automatic exits")

        # Try Ollama for deeper analysis
        try:
            ollama_suggestions = await self._get_ollama_suggestions(
                trades, winners, losers, mistakes
            )
            if ollama_suggestions:
                suggestions.extend(ollama_suggestions)
        except Exception as e:
            self.logger.debug(f"Ollama suggestions failed: {e}")

        return suggestions[:7]  # Limit suggestions

    async def _get_ollama_suggestions(
        self,
        trades: List[Dict],
        winners: List[Dict],
        losers: List[Dict],
        mistakes: List[str]
    ) -> List[str]:
        """Get improvement suggestions from Ollama"""
        win_rate = len(winners) / len(trades) if trades else 0

        prompt = f"""Analyze this trading performance and provide 3 specific improvement suggestions:

Performance:
- Trades: {len(trades)}
- Win rate: {win_rate*100:.1f}%
- Avg winner: {sum(t['outcome'].get('pnl_percent', 0) for t in winners) / len(winners) if winners else 0:.2f}%
- Avg loser: {sum(t['outcome'].get('pnl_percent', 0) for t in losers) / len(losers) if losers else 0:.2f}%

Detected issues: {', '.join(mistakes) if mistakes else 'None obvious'}

Respond with a JSON array of exactly 3 short suggestions:
["suggestion 1", "suggestion 2", "suggestion 3"]"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 200}
                    },
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get('response', '')

                        # Parse JSON array
                        start = text.find('[')
                        end = text.rfind(']') + 1
                        if start >= 0 and end > start:
                            suggestions = json.loads(text[start:end])
                            return suggestions[:3]
        except Exception:
            pass

        return []

    def _calculate_adjustments(
        self,
        win_rate: float,
        confidence_data: Dict,
        setup_analysis: Dict
    ) -> Dict[str, float]:
        """Calculate adjustments to apply to future trades"""
        adjustments = {}

        # Confidence adjustment
        adjustments['confidence_multiplier'] = 1.0 + confidence_data['adjustment']

        # Score threshold adjustment based on win rate
        if win_rate < 0.4:
            adjustments['min_score_adjustment'] = 0.5  # Increase min score
        elif win_rate > 0.6:
            adjustments['min_score_adjustment'] = -0.25  # Can be slightly more aggressive

        # Setup type multipliers
        if setup_analysis['best']:
            for setup in setup_analysis['best']:
                if setup['win_rate'] > 0.65:
                    adjustments[f"setup_{setup['setup']}_boost"] = 0.5

        if setup_analysis['worst']:
            for setup in setup_analysis['worst']:
                if setup['win_rate'] < 0.35:
                    adjustments[f"setup_{setup['setup']}_penalty"] = -0.5

        return adjustments

    def _save_report(self, report: ReflectionReport):
        """Save reflection report to file"""
        reports_dir = self.trade_log_dir / "reflections"
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_file = reports_dir / f"{report.report_id}.json"
        with open(report_file, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)

    def _save_adjustments(self):
        """Save current adjustments"""
        adjustments_file = self.trade_log_dir / "current_adjustments.json"
        adjustments_file.parent.mkdir(parents=True, exist_ok=True)

        with open(adjustments_file, 'w') as f:
            json.dump({
                'adjustments': self._current_adjustments,
                'last_reflection': self._last_reflection.isoformat() if self._last_reflection else None,
                'updated_at': datetime.now().isoformat(),
            }, f, indent=2)

    def _load_adjustments(self):
        """Load saved adjustments"""
        adjustments_file = self.trade_log_dir / "current_adjustments.json"

        if adjustments_file.exists():
            try:
                with open(adjustments_file, 'r') as f:
                    data = json.load(f)
                    self._current_adjustments = data.get('adjustments', {})
                    if data.get('last_reflection'):
                        self._last_reflection = datetime.fromisoformat(data['last_reflection'])
            except Exception as e:
                self.logger.debug(f"Error loading adjustments: {e}")

    def _log_reflection_summary(self, report: ReflectionReport):
        """Log reflection summary"""
        self.logger.info("=" * 60)
        self.logger.info("📊 PERIODIC REFLECTION REPORT")
        self.logger.info("=" * 60)
        self.logger.info(f"Trades analyzed: {report.trades_analyzed}")
        self.logger.info(f"Win rate: {report.win_rate*100:.1f}%")
        self.logger.info(f"Profit factor: {report.profit_factor:.2f}")
        self.logger.info(f"Total P&L: {report.total_pnl_pct:+.2f}%")
        self.logger.info("")
        self.logger.info(f"Confidence calibration: {report.confidence_accuracy*100:.0f}% accurate")
        self.logger.info(f"Overconfidence score: {report.overconfidence_score:+.2f}")
        self.logger.info("")

        if report.recurring_mistakes:
            self.logger.info("🚨 Recurring mistakes:")
            for mistake in report.recurring_mistakes:
                self.logger.info(f"  - {mistake}")

        if report.improvement_suggestions:
            self.logger.info("")
            self.logger.info("💡 Suggestions:")
            for suggestion in report.improvement_suggestions:
                self.logger.info(f"  - {suggestion}")

        if report.adjustments:
            self.logger.info("")
            self.logger.info("🔧 Adjustments applied:")
            for key, value in report.adjustments.items():
                self.logger.info(f"  {key}: {value:+.2f}")

        self.logger.info("=" * 60)

    def apply_adjustments_to_confidence(self, base_confidence: float) -> float:
        """Apply learned adjustments to confidence score"""
        multiplier = self._current_adjustments.get('confidence_multiplier', 1.0)
        return max(0.1, min(1.0, base_confidence * multiplier))

    def apply_adjustments_to_score(self, base_score: float, setup_type: str) -> float:
        """Apply learned adjustments to setup score"""
        # Base score adjustment
        score_adj = self._current_adjustments.get('min_score_adjustment', 0)

        # Setup-specific adjustments
        boost = self._current_adjustments.get(f"setup_{setup_type}_boost", 0)
        penalty = self._current_adjustments.get(f"setup_{setup_type}_penalty", 0)

        return base_score + score_adj + boost + penalty
