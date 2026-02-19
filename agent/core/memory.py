"""
Trading Memory

Stores and retrieves past trading decisions for learning.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import defaultdict
import statistics

from config.agent_config import DEFAULT_CONFIG


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    id: str
    symbol: str
    action: str  # BUY or SELL
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    entry_time: datetime
    exit_time: Optional[datetime]
    stop_loss: float
    take_profit: float
    confidence: float
    reasoning: str
    technical_signals: Dict[str, Any]
    market_regime: str
    outcome: Optional[str] = None  # WIN, LOSS, OPEN
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_duration_minutes: Optional[int] = None
    lessons_learned: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        d = asdict(self)
        d['entry_time'] = self.entry_time.isoformat()
        d['exit_time'] = self.exit_time.isoformat() if self.exit_time else None
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> 'TradeRecord':
        """Create from dictionary"""
        data['entry_time'] = datetime.fromisoformat(data['entry_time'])
        if data.get('exit_time'):
            data['exit_time'] = datetime.fromisoformat(data['exit_time'])
        return cls(**data)


@dataclass
class PatternMatch:
    """A matched pattern from memory"""
    pattern_id: str
    symbol: str
    similarity_score: float
    historical_win_rate: float
    avg_pnl_pct: float
    sample_size: int
    relevant_trades: List[TradeRecord]


@dataclass
class TradingStats:
    """Aggregated trading statistics"""
    total_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    avg_hold_duration: float
    best_performing_symbols: List[Tuple[str, float]]
    worst_performing_symbols: List[Tuple[str, float]]
    performance_by_regime: Dict[str, Dict]


class TradingMemory:
    """
    Persistent memory of trading decisions and outcomes.

    Features:
    - Store trade records with full context
    - Pattern matching for similar setups
    - Performance analytics
    - Learning from past mistakes
    """

    def __init__(self, memory_file: Optional[str] = None):
        self.memory_file = memory_file or DEFAULT_CONFIG.memory_file
        self.logger = logging.getLogger(__name__)

        self._trades: List[TradeRecord] = []
        self._patterns: Dict[str, List[str]] = {}  # Pattern -> trade IDs
        self._symbol_stats: Dict[str, Dict] = defaultdict(dict)

        self._load_memory()

    def _load_memory(self):
        """Load memory from file"""
        try:
            path = Path(self.memory_file)
            if path.exists():
                with open(path, 'r') as f:
                    data = json.load(f)

                self._trades = [TradeRecord.from_dict(t) for t in data.get('trades', [])]
                self._patterns = data.get('patterns', {})

                self.logger.info(f"Loaded {len(self._trades)} trades from memory")
            else:
                self.logger.info("No existing memory file, starting fresh")

        except Exception as e:
            self.logger.error(f"Error loading memory: {e}")

    def _save_memory(self):
        """Save memory to file"""
        try:
            path = Path(self.memory_file)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'trades': [t.to_dict() for t in self._trades[-DEFAULT_CONFIG.max_memory_trades:]],
                'patterns': self._patterns,
                'last_updated': datetime.now().isoformat(),
            }

            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)

        except Exception as e:
            self.logger.error(f"Error saving memory: {e}")

    def record_trade(self, trade: TradeRecord):
        """Record a new trade"""
        self._trades.append(trade)

        # Extract pattern
        pattern_key = self._extract_pattern_key(trade)
        if pattern_key:
            if pattern_key not in self._patterns:
                self._patterns[pattern_key] = []
            self._patterns[pattern_key].append(trade.id)

        self._save_memory()
        self.logger.info(f"Recorded trade {trade.id}: {trade.action} {trade.symbol}")

    def update_trade_outcome(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime,
        lessons: str = ""
    ):
        """Update trade with outcome"""
        for trade in self._trades:
            if trade.id == trade_id:
                trade.exit_price = exit_price
                trade.exit_time = exit_time
                trade.lessons_learned = lessons

                # Calculate P&L
                if trade.action == 'BUY':
                    trade.pnl = (exit_price - trade.entry_price) * trade.quantity
                    trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                else:
                    trade.pnl = (trade.entry_price - exit_price) * trade.quantity
                    trade.pnl_pct = ((trade.entry_price - exit_price) / trade.entry_price) * 100

                trade.outcome = 'WIN' if trade.pnl > 0 else 'LOSS'
                trade.hold_duration_minutes = int((exit_time - trade.entry_time).total_seconds() / 60)

                self._save_memory()
                self.logger.info(f"Updated trade {trade_id}: {trade.outcome} ({trade.pnl_pct:+.2f}%)")
                return

        self.logger.warning(f"Trade {trade_id} not found in memory")

    def find_similar_setups(
        self,
        symbol: str,
        technical_signals: Dict[str, Any],
        market_regime: str,
        min_similarity: float = 0.6,
        limit: int = 10
    ) -> List[PatternMatch]:
        """Find historically similar trading setups"""
        matches = []

        # Get pattern key for current setup
        current_pattern = self._create_pattern_fingerprint(
            symbol, technical_signals, market_regime
        )

        # Find matching patterns
        for pattern_key, trade_ids in self._patterns.items():
            similarity = self._calculate_pattern_similarity(current_pattern, pattern_key)

            if similarity >= min_similarity:
                # Get trades for this pattern
                pattern_trades = [t for t in self._trades if t.id in trade_ids and t.outcome]

                if pattern_trades:
                    wins = [t for t in pattern_trades if t.outcome == 'WIN']
                    win_rate = len(wins) / len(pattern_trades)
                    avg_pnl = statistics.mean([t.pnl_pct for t in pattern_trades])

                    matches.append(PatternMatch(
                        pattern_id=pattern_key,
                        symbol=symbol,
                        similarity_score=similarity,
                        historical_win_rate=win_rate,
                        avg_pnl_pct=avg_pnl,
                        sample_size=len(pattern_trades),
                        relevant_trades=pattern_trades[:5],  # Top 5 examples
                    ))

        # Sort by similarity and return top matches
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches[:limit]

    def _extract_pattern_key(self, trade: TradeRecord) -> str:
        """Extract pattern key from trade for indexing"""
        return self._create_pattern_fingerprint(
            trade.symbol,
            trade.technical_signals,
            trade.market_regime
        )

    def _create_pattern_fingerprint(
        self,
        symbol: str,
        technical_signals: Dict[str, Any],
        market_regime: str
    ) -> str:
        """Create fingerprint for pattern matching"""
        # Extract key technical characteristics
        rsi = technical_signals.get('rsi', 50)
        rsi_bucket = 'oversold' if rsi < 30 else 'overbought' if rsi > 70 else 'neutral'

        macd_bullish = technical_signals.get('macd_bullish', False)
        macd_state = 'bullish' if macd_bullish else 'bearish'

        volume_ratio = technical_signals.get('volume_ratio', 1.0)
        volume_state = 'high' if volume_ratio > 1.5 else 'low' if volume_ratio < 0.5 else 'normal'

        return f"{rsi_bucket}_{macd_state}_{volume_state}_{market_regime}"

    def _calculate_pattern_similarity(self, pattern1: str, pattern2: str) -> float:
        """Calculate similarity between two patterns"""
        parts1 = pattern1.split('_')
        parts2 = pattern2.split('_')

        if len(parts1) != len(parts2):
            return 0.0

        matches = sum(1 for p1, p2 in zip(parts1, parts2) if p1 == p2)
        return matches / len(parts1)

    def get_symbol_performance(self, symbol: str) -> Dict:
        """Get performance stats for a symbol"""
        symbol_trades = [t for t in self._trades if t.symbol == symbol and t.outcome]

        if not symbol_trades:
            return {'trades': 0, 'win_rate': 0, 'avg_pnl': 0}

        wins = [t for t in symbol_trades if t.outcome == 'WIN']
        win_rate = len(wins) / len(symbol_trades) if symbol_trades else 0
        avg_pnl = statistics.mean([t.pnl_pct for t in symbol_trades]) if symbol_trades else 0

        return {
            'trades': len(symbol_trades),
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'last_trade': symbol_trades[-1].entry_time.isoformat() if symbol_trades else None,
        }

    def get_overall_stats(self) -> TradingStats:
        """Get overall trading statistics"""
        closed_trades = [t for t in self._trades if t.outcome]

        if not closed_trades:
            return TradingStats(
                total_trades=0,
                win_rate=0,
                avg_win_pct=0,
                avg_loss_pct=0,
                profit_factor=0,
                avg_hold_duration=0,
                best_performing_symbols=[],
                worst_performing_symbols=[],
                performance_by_regime={},
            )

        wins = [t for t in closed_trades if t.outcome == 'WIN']
        losses = [t for t in closed_trades if t.outcome == 'LOSS']

        win_rate = len(wins) / len(closed_trades)
        avg_win = statistics.mean([t.pnl_pct for t in wins]) if wins else 0
        avg_loss = statistics.mean([t.pnl_pct for t in losses]) if losses else 0

        total_wins = sum(t.pnl for t in wins) if wins else 0
        total_losses = abs(sum(t.pnl for t in losses)) if losses else 1
        profit_factor = total_wins / total_losses if total_losses > 0 else total_wins

        durations = [t.hold_duration_minutes for t in closed_trades if t.hold_duration_minutes]
        avg_duration = statistics.mean(durations) if durations else 0

        # Symbol performance
        symbol_pnl = defaultdict(list)
        for trade in closed_trades:
            symbol_pnl[trade.symbol].append(trade.pnl_pct)

        symbol_avg = [(s, statistics.mean(pnls)) for s, pnls in symbol_pnl.items()]
        symbol_avg.sort(key=lambda x: x[1], reverse=True)

        # Regime performance
        regime_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': []})
        for trade in closed_trades:
            regime = trade.market_regime
            regime_stats[regime]['trades'] += 1
            if trade.outcome == 'WIN':
                regime_stats[regime]['wins'] += 1
            regime_stats[regime]['pnl'].append(trade.pnl_pct)

        performance_by_regime = {
            regime: {
                'trades': stats['trades'],
                'win_rate': stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0,
                'avg_pnl': statistics.mean(stats['pnl']) if stats['pnl'] else 0,
            }
            for regime, stats in regime_stats.items()
        }

        return TradingStats(
            total_trades=len(closed_trades),
            win_rate=win_rate,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            profit_factor=profit_factor,
            avg_hold_duration=avg_duration,
            best_performing_symbols=symbol_avg[:5],
            worst_performing_symbols=symbol_avg[-5:] if len(symbol_avg) > 5 else [],
            performance_by_regime=performance_by_regime,
        )

    def get_recent_trades(self, limit: int = 20) -> List[TradeRecord]:
        """Get recent trades"""
        return self._trades[-limit:]

    def get_open_trades(self) -> List[TradeRecord]:
        """Get trades without exit"""
        return [t for t in self._trades if t.exit_time is None]

    def get_lessons_for_symbol(self, symbol: str) -> List[str]:
        """Get lessons learned from past trades of a symbol"""
        lessons = []
        for trade in self._trades:
            if trade.symbol == symbol and trade.lessons_learned:
                lessons.append(trade.lessons_learned)
        return lessons

    def generate_reflection_prompt(self, symbol: str) -> str:
        """Generate a reflection prompt based on past performance"""
        stats = self.get_symbol_performance(symbol)
        lessons = self.get_lessons_for_symbol(symbol)

        prompt = f"""Based on past trading history for {symbol}:
- Total trades: {stats['trades']}
- Win rate: {stats['win_rate']*100:.1f}%
- Average P&L: {stats['avg_pnl']:.2f}%

"""
        if lessons:
            prompt += "Lessons learned from past trades:\n"
            for lesson in lessons[-5:]:  # Last 5 lessons
                prompt += f"- {lesson}\n"

        return prompt
