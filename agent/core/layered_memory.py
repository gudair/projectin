"""
Layered Memory System (FinMem-inspired)

Implements hierarchical memory for trading decisions:
- Working Memory: Recent hours (high weight, fast context)
- Short-term Memory: Last week (patterns, recent performance)
- Deep Memory: Months/quarters (seasonal, earnings cycles)

Each layer contributes differently to decision-making.
"""
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio


@dataclass
class MemoryItem:
    """A single memory item"""
    id: str
    timestamp: datetime
    memory_type: str  # price, trade, news, pattern, earnings
    symbol: Optional[str]
    content: Dict[str, Any]
    importance: float  # 0-1, affects retention
    tags: List[str] = field(default_factory=list)

    def age_hours(self) -> float:
        """Age in hours"""
        return (datetime.now() - self.timestamp).total_seconds() / 3600

    def age_days(self) -> float:
        """Age in days"""
        return self.age_hours() / 24

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "memory_type": self.memory_type,
            "symbol": self.symbol,
            "content": self.content,
            "importance": self.importance,
            "tags": self.tags,
        }


@dataclass
class LayeredMemoryQuery:
    """Result of querying layered memory"""
    symbol: str
    query_time: datetime

    # Working memory (recent hours)
    working_memories: List[MemoryItem]
    working_summary: str

    # Short-term memory (recent days)
    shortterm_memories: List[MemoryItem]
    shortterm_patterns: List[Dict]
    shortterm_win_rate: Optional[float]

    # Deep memory (weeks/months)
    deep_memories: List[MemoryItem]
    deep_patterns: List[Dict]
    seasonal_context: Optional[str]
    earnings_context: Optional[str]

    # Combined score adjustment
    memory_score_adjustment: float
    memory_confidence_factor: float
    memory_summary: str

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "query_time": self.query_time.isoformat(),
            "working": {
                "count": len(self.working_memories),
                "summary": self.working_summary,
            },
            "shortterm": {
                "count": len(self.shortterm_memories),
                "patterns": self.shortterm_patterns,
                "win_rate": self.shortterm_win_rate,
            },
            "deep": {
                "count": len(self.deep_memories),
                "patterns": self.deep_patterns,
                "seasonal": self.seasonal_context,
                "earnings": self.earnings_context,
            },
            "adjustments": {
                "score": self.memory_score_adjustment,
                "confidence": self.memory_confidence_factor,
            },
            "summary": self.memory_summary,
        }


class LayeredMemorySystem:
    """
    Hierarchical memory system for trading.

    Memory Layers:
    1. Working Memory (0-4 hours): Recent prices, news, trades
       - High weight (0.5), fast decay
       - Used for immediate context

    2. Short-term Memory (1-7 days): Recent patterns, performance
       - Medium weight (0.3)
       - Pattern recognition, recent success/failure

    3. Deep Memory (1-6 months): Historical patterns, earnings cycles
       - Low but stable weight (0.2)
       - Seasonal patterns, fundamental events

    Each query combines all layers with weighted contributions.
    """

    # Memory layer configurations
    LAYERS = {
        'working': {
            'max_age_hours': 4,
            'weight': 0.5,
            'max_items': 100,
            'decay_rate': 0.3,  # Faster decay
        },
        'shortterm': {
            'max_age_days': 7,
            'weight': 0.3,
            'max_items': 500,
            'decay_rate': 0.1,
        },
        'deep': {
            'max_age_days': 180,  # 6 months
            'weight': 0.2,
            'max_items': 1000,
            'decay_rate': 0.02,
        },
    }

    # Importance multipliers by memory type
    IMPORTANCE_MULTIPLIERS = {
        'trade_win': 1.0,
        'trade_loss': 1.2,  # Losses are slightly more important to remember
        'earnings': 1.5,
        'major_news': 1.3,
        'price_extreme': 1.1,
        'pattern': 0.8,
        'routine': 0.5,
    }

    def __init__(
        self,
        memory_dir: str = "data/memory",
        persist: bool = True,
    ):
        self.memory_dir = Path(memory_dir)
        self.persist = persist
        self.logger = logging.getLogger(__name__)

        # Memory storage by layer
        self._working: List[MemoryItem] = []
        self._shortterm: List[MemoryItem] = []
        self._deep: List[MemoryItem] = []

        # Indexes for fast lookup
        self._by_symbol: Dict[str, List[MemoryItem]] = defaultdict(list)
        self._by_type: Dict[str, List[MemoryItem]] = defaultdict(list)

        # Pattern cache
        self._pattern_cache: Dict[str, Dict] = {}

        # Load persisted memories
        if persist:
            self._load_memories()

    def add_memory(
        self,
        memory_type: str,
        content: Dict[str, Any],
        symbol: Optional[str] = None,
        importance: float = 0.5,
        tags: List[str] = None,
    ) -> MemoryItem:
        """
        Add a new memory item.

        Args:
            memory_type: Type of memory (trade_win, trade_loss, news, price, pattern)
            content: Memory content
            symbol: Associated stock symbol
            importance: Base importance (0-1)
            tags: Optional tags for filtering

        Returns:
            Created MemoryItem
        """
        # Apply importance multiplier
        multiplier = self.IMPORTANCE_MULTIPLIERS.get(memory_type, 1.0)
        adjusted_importance = min(1.0, importance * multiplier)

        item = MemoryItem(
            id=f"mem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            timestamp=datetime.now(),
            memory_type=memory_type,
            symbol=symbol,
            content=content,
            importance=adjusted_importance,
            tags=tags or [],
        )

        # Add to working memory (will be promoted later)
        self._working.append(item)

        # Update indexes
        if symbol:
            self._by_symbol[symbol].append(item)
        self._by_type[memory_type].append(item)

        # Invalidate pattern cache for symbol
        if symbol and symbol in self._pattern_cache:
            del self._pattern_cache[symbol]

        self.logger.debug(
            f"Memory added: {memory_type} for {symbol or 'general'} "
            f"(importance: {adjusted_importance:.2f})"
        )

        return item

    def record_trade(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        outcome: Optional[Dict] = None,
        setup_type: str = "unknown",
        technical_data: Optional[Dict] = None,
        market_regime: str = "unknown",
    ):
        """Record a trade as memory"""
        is_win = outcome.get('profitable', False) if outcome else None

        memory_type = 'trade_win' if is_win else 'trade_loss' if is_win is False else 'trade_pending'

        content = {
            'action': action,
            'entry_price': entry_price,
            'setup_type': setup_type,
            'technical_data': technical_data or {},
            'market_regime': market_regime,
            'outcome': outcome,
        }

        # Higher importance for completed trades
        importance = 0.8 if outcome else 0.5

        self.add_memory(
            memory_type=memory_type,
            content=content,
            symbol=symbol,
            importance=importance,
            tags=[setup_type, market_regime, action],
        )

    def record_price_event(
        self,
        symbol: str,
        event_type: str,  # gap_up, gap_down, breakout, breakdown, high, low
        price: float,
        change_pct: float,
        volume_ratio: float = 1.0,
    ):
        """Record significant price events"""
        importance = 0.6
        if abs(change_pct) > 5:
            importance = 0.8
            memory_type = 'price_extreme'
        else:
            memory_type = 'price_event'

        self.add_memory(
            memory_type=memory_type,
            content={
                'event_type': event_type,
                'price': price,
                'change_pct': change_pct,
                'volume_ratio': volume_ratio,
            },
            symbol=symbol,
            importance=importance,
            tags=[event_type],
        )

    def record_news(
        self,
        symbol: str,
        headline: str,
        sentiment: str,
        sentiment_score: float,
        source: str = "unknown",
    ):
        """Record news as memory"""
        memory_type = 'major_news' if abs(sentiment_score) > 0.5 else 'news'

        self.add_memory(
            memory_type=memory_type,
            content={
                'headline': headline[:200],  # Truncate
                'sentiment': sentiment,
                'score': sentiment_score,
                'source': source,
            },
            symbol=symbol,
            importance=0.6 + abs(sentiment_score) * 0.3,
            tags=[sentiment, source],
        )

    def record_earnings(
        self,
        symbol: str,
        eps_actual: float,
        eps_expected: float,
        revenue_actual: float,
        revenue_expected: float,
        price_reaction_pct: float,
    ):
        """Record earnings as deep memory"""
        beat_eps = eps_actual > eps_expected
        beat_rev = revenue_actual > revenue_expected

        self.add_memory(
            memory_type='earnings',
            content={
                'eps_actual': eps_actual,
                'eps_expected': eps_expected,
                'eps_beat': beat_eps,
                'revenue_actual': revenue_actual,
                'revenue_expected': revenue_expected,
                'revenue_beat': beat_rev,
                'price_reaction_pct': price_reaction_pct,
            },
            symbol=symbol,
            importance=0.9,  # Earnings are very important
            tags=['earnings', 'beat' if beat_eps and beat_rev else 'miss'],
        )

    async def query(self, symbol: str) -> LayeredMemoryQuery:
        """
        Query all memory layers for a symbol.

        Returns comprehensive memory context for decision-making.
        """
        now = datetime.now()

        # Promote/demote memories between layers
        self._manage_layers()

        # Get memories for this symbol from each layer
        working_memories = self._get_layer_memories('working', symbol)
        shortterm_memories = self._get_layer_memories('shortterm', symbol)
        deep_memories = self._get_layer_memories('deep', symbol)

        # Analyze each layer
        working_summary = self._summarize_working(working_memories)
        shortterm_patterns, shortterm_win_rate = self._analyze_shortterm(shortterm_memories)
        deep_patterns, seasonal, earnings = self._analyze_deep(deep_memories, symbol)

        # Calculate combined adjustments
        score_adj, confidence_factor = self._calculate_adjustments(
            working_memories, shortterm_patterns, deep_patterns,
            shortterm_win_rate
        )

        # Generate summary
        summary = self._generate_summary(
            symbol, working_summary, shortterm_patterns, deep_patterns,
            shortterm_win_rate, seasonal, earnings
        )

        return LayeredMemoryQuery(
            symbol=symbol,
            query_time=now,
            working_memories=working_memories,
            working_summary=working_summary,
            shortterm_memories=shortterm_memories,
            shortterm_patterns=shortterm_patterns,
            shortterm_win_rate=shortterm_win_rate,
            deep_memories=deep_memories,
            deep_patterns=deep_patterns,
            seasonal_context=seasonal,
            earnings_context=earnings,
            memory_score_adjustment=score_adj,
            memory_confidence_factor=confidence_factor,
            memory_summary=summary,
        )

    def _get_layer_memories(
        self,
        layer: str,
        symbol: Optional[str] = None
    ) -> List[MemoryItem]:
        """Get memories from a specific layer, optionally filtered by symbol"""
        if layer == 'working':
            memories = self._working
        elif layer == 'shortterm':
            memories = self._shortterm
        else:
            memories = self._deep

        if symbol:
            return [m for m in memories if m.symbol == symbol]
        return memories

    def _manage_layers(self):
        """Promote/demote memories between layers based on age"""
        now = datetime.now()

        # Working → Short-term (after 4 hours)
        working_cutoff = now - timedelta(hours=self.LAYERS['working']['max_age_hours'])
        promoted = [m for m in self._working if m.timestamp < working_cutoff]

        for m in promoted:
            self._working.remove(m)
            if m.importance > 0.3:  # Only keep moderately important
                self._shortterm.append(m)

        # Short-term → Deep (after 7 days)
        shortterm_cutoff = now - timedelta(days=self.LAYERS['shortterm']['max_age_days'])
        promoted = [m for m in self._shortterm if m.timestamp < shortterm_cutoff]

        for m in promoted:
            self._shortterm.remove(m)
            if m.importance > 0.5:  # Only keep important memories long-term
                self._deep.append(m)

        # Expire deep memories (after 6 months)
        deep_cutoff = now - timedelta(days=self.LAYERS['deep']['max_age_days'])
        self._deep = [m for m in self._deep if m.timestamp > deep_cutoff]

        # Enforce max items per layer
        self._working = sorted(self._working, key=lambda m: m.importance, reverse=True)
        self._working = self._working[:self.LAYERS['working']['max_items']]

        self._shortterm = sorted(self._shortterm, key=lambda m: m.importance, reverse=True)
        self._shortterm = self._shortterm[:self.LAYERS['shortterm']['max_items']]

        self._deep = sorted(self._deep, key=lambda m: m.importance, reverse=True)
        self._deep = self._deep[:self.LAYERS['deep']['max_items']]

    def _summarize_working(self, memories: List[MemoryItem]) -> str:
        """Summarize working memory (recent context)"""
        if not memories:
            return "No recent activity"

        parts = []

        # Recent trades
        trades = [m for m in memories if m.memory_type.startswith('trade')]
        if trades:
            wins = len([t for t in trades if t.memory_type == 'trade_win'])
            losses = len([t for t in trades if t.memory_type == 'trade_loss'])
            parts.append(f"Recent trades: {wins}W/{losses}L")

        # Recent news sentiment
        news = [m for m in memories if 'news' in m.memory_type]
        if news:
            avg_sentiment = sum(m.content.get('score', 0) for m in news) / len(news)
            sentiment_label = "bullish" if avg_sentiment > 0.2 else "bearish" if avg_sentiment < -0.2 else "neutral"
            parts.append(f"News: {sentiment_label}")

        # Price events
        price_events = [m for m in memories if 'price' in m.memory_type]
        if price_events:
            latest = max(price_events, key=lambda m: m.timestamp)
            parts.append(f"Recent: {latest.content.get('event_type', 'price move')}")

        return " | ".join(parts) if parts else "No significant recent activity"

    def _analyze_shortterm(
        self,
        memories: List[MemoryItem]
    ) -> Tuple[List[Dict], Optional[float]]:
        """Analyze short-term memory for patterns"""
        patterns = []

        # Trade performance
        trades = [m for m in memories if m.memory_type.startswith('trade')]
        wins = [t for t in trades if t.memory_type == 'trade_win']
        losses = [t for t in trades if t.memory_type == 'trade_loss']

        win_rate = len(wins) / len(trades) if trades else None

        if trades:
            # Group by setup type
            by_setup = defaultdict(lambda: {'wins': 0, 'losses': 0})
            for t in trades:
                setup = t.content.get('setup_type', 'unknown')
                if t.memory_type == 'trade_win':
                    by_setup[setup]['wins'] += 1
                else:
                    by_setup[setup]['losses'] += 1

            for setup, stats in by_setup.items():
                total = stats['wins'] + stats['losses']
                if total >= 2:
                    patterns.append({
                        'type': 'setup_performance',
                        'setup': setup,
                        'win_rate': stats['wins'] / total,
                        'count': total,
                    })

        # Price patterns
        price_events = [m for m in memories if 'price' in m.memory_type]
        if len(price_events) >= 3:
            # Check for repeating patterns
            event_types = [m.content.get('event_type') for m in price_events]
            for event_type in set(event_types):
                count = event_types.count(event_type)
                if count >= 2:
                    patterns.append({
                        'type': 'recurring_event',
                        'event': event_type,
                        'frequency': count,
                    })

        return patterns, win_rate

    def _analyze_deep(
        self,
        memories: List[MemoryItem],
        symbol: str
    ) -> Tuple[List[Dict], Optional[str], Optional[str]]:
        """Analyze deep memory for long-term patterns"""
        patterns = []
        seasonal_context = None
        earnings_context = None

        # Earnings history
        earnings = [m for m in memories if m.memory_type == 'earnings']
        if earnings:
            beats = len([e for e in earnings if e.content.get('eps_beat')])
            total = len(earnings)
            avg_reaction = sum(e.content.get('price_reaction_pct', 0) for e in earnings) / total

            earnings_context = (
                f"Earnings history: {beats}/{total} beats, "
                f"avg reaction: {avg_reaction:+.1f}%"
            )

            patterns.append({
                'type': 'earnings_history',
                'beat_rate': beats / total,
                'avg_reaction': avg_reaction,
            })

        # Seasonal patterns (by month)
        if len(memories) >= 10:
            by_month = defaultdict(lambda: {'positive': 0, 'negative': 0})
            for m in memories:
                month = m.timestamp.month
                if m.memory_type == 'trade_win' or (
                    'price' in m.memory_type and m.content.get('change_pct', 0) > 0
                ):
                    by_month[month]['positive'] += 1
                elif m.memory_type == 'trade_loss' or (
                    'price' in m.memory_type and m.content.get('change_pct', 0) < 0
                ):
                    by_month[month]['negative'] += 1

            current_month = datetime.now().month
            if current_month in by_month:
                data = by_month[current_month]
                total = data['positive'] + data['negative']
                if total >= 3:
                    win_rate = data['positive'] / total
                    if win_rate > 0.6:
                        seasonal_context = f"Historically positive month ({win_rate*100:.0f}%)"
                    elif win_rate < 0.4:
                        seasonal_context = f"Historically weak month ({win_rate*100:.0f}%)"

        return patterns, seasonal_context, earnings_context

    def _calculate_adjustments(
        self,
        working: List[MemoryItem],
        shortterm_patterns: List[Dict],
        deep_patterns: List[Dict],
        shortterm_win_rate: Optional[float],
    ) -> Tuple[float, float]:
        """Calculate score and confidence adjustments from memory"""
        score_adj = 0.0
        confidence_factor = 1.0

        # Working memory influence (recent momentum)
        recent_wins = len([m for m in working if m.memory_type == 'trade_win'])
        recent_losses = len([m for m in working if m.memory_type == 'trade_loss'])

        if recent_wins + recent_losses >= 2:
            recent_win_rate = recent_wins / (recent_wins + recent_losses)
            # Recent hot streak = slight boost
            if recent_win_rate > 0.7:
                score_adj += 0.3
                confidence_factor *= 1.1
            # Recent cold streak = caution
            elif recent_win_rate < 0.3:
                score_adj -= 0.5
                confidence_factor *= 0.9

        # Short-term pattern influence
        if shortterm_win_rate is not None:
            if shortterm_win_rate > 0.6:
                score_adj += 0.2
            elif shortterm_win_rate < 0.4:
                score_adj -= 0.3
                confidence_factor *= 0.95

        # Deep memory influence (earnings, seasonal)
        for pattern in deep_patterns:
            if pattern.get('type') == 'earnings_history':
                beat_rate = pattern.get('beat_rate', 0.5)
                if beat_rate > 0.7:
                    score_adj += 0.1  # Consistently beats
                elif beat_rate < 0.3:
                    score_adj -= 0.2  # Consistently misses

        return score_adj, confidence_factor

    def _generate_summary(
        self,
        symbol: str,
        working_summary: str,
        shortterm_patterns: List[Dict],
        deep_patterns: List[Dict],
        shortterm_win_rate: Optional[float],
        seasonal: Optional[str],
        earnings: Optional[str],
    ) -> str:
        """Generate human-readable memory summary"""
        parts = [f"Memory context for {symbol}:"]

        # Working
        parts.append(f"• Recent: {working_summary}")

        # Short-term
        if shortterm_win_rate is not None:
            parts.append(f"• Week performance: {shortterm_win_rate*100:.0f}% win rate")

        # Patterns
        setup_patterns = [p for p in shortterm_patterns if p['type'] == 'setup_performance']
        if setup_patterns:
            best = max(setup_patterns, key=lambda p: p['win_rate'])
            parts.append(f"• Best setup: {best['setup']} ({best['win_rate']*100:.0f}%)")

        # Deep context
        if seasonal:
            parts.append(f"• Seasonal: {seasonal}")
        if earnings:
            parts.append(f"• Earnings: {earnings}")

        return "\n".join(parts)

    def _save_memories(self):
        """Persist memories to disk"""
        if not self.persist:
            return

        self.memory_dir.mkdir(parents=True, exist_ok=True)

        data = {
            'working': [m.to_dict() for m in self._working],
            'shortterm': [m.to_dict() for m in self._shortterm],
            'deep': [m.to_dict() for m in self._deep],
            'saved_at': datetime.now().isoformat(),
        }

        memory_file = self.memory_dir / "layered_memory.json"
        with open(memory_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_memories(self):
        """Load persisted memories"""
        memory_file = self.memory_dir / "layered_memory.json"

        if not memory_file.exists():
            return

        try:
            with open(memory_file, 'r') as f:
                data = json.load(f)

            for layer_name in ['working', 'shortterm', 'deep']:
                layer_data = data.get(layer_name, [])
                layer_list = getattr(self, f'_{layer_name}')

                for item_data in layer_data:
                    try:
                        item = MemoryItem(
                            id=item_data['id'],
                            timestamp=datetime.fromisoformat(item_data['timestamp']),
                            memory_type=item_data['memory_type'],
                            symbol=item_data.get('symbol'),
                            content=item_data['content'],
                            importance=item_data['importance'],
                            tags=item_data.get('tags', []),
                        )
                        layer_list.append(item)

                        # Rebuild indexes
                        if item.symbol:
                            self._by_symbol[item.symbol].append(item)
                        self._by_type[item.memory_type].append(item)
                    except Exception:
                        continue

            self.logger.info(
                f"Loaded memories: {len(self._working)} working, "
                f"{len(self._shortterm)} short-term, {len(self._deep)} deep"
            )

        except Exception as e:
            self.logger.warning(f"Error loading memories: {e}")

    def get_stats(self) -> Dict:
        """Get memory system statistics"""
        return {
            'working_count': len(self._working),
            'shortterm_count': len(self._shortterm),
            'deep_count': len(self._deep),
            'symbols_tracked': len(self._by_symbol),
            'memory_types': list(self._by_type.keys()),
        }

    def clear_symbol(self, symbol: str):
        """Clear all memories for a symbol"""
        self._working = [m for m in self._working if m.symbol != symbol]
        self._shortterm = [m for m in self._shortterm if m.symbol != symbol]
        self._deep = [m for m in self._deep if m.symbol != symbol]

        if symbol in self._by_symbol:
            del self._by_symbol[symbol]

        if symbol in self._pattern_cache:
            del self._pattern_cache[symbol]

    def save(self):
        """Save memories to disk"""
        self._save_memories()
