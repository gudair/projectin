"""
Trade Intelligence - Self-Reflection & Bull/Bear Debate

Advanced AI features for trade decision making:
1. Self-Reflection: Learn from past trades
2. Bull/Bear Debate: Two perspectives argue before each trade

Optimized for Ollama:
- Batched calls where possible
- Compact prompts
- Cached patterns
- Fallback to rule-based if LLM unavailable
"""
import logging
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TradePattern:
    """A learned pattern from past trades"""
    pattern_type: str  # "winning" or "losing"
    setup_type: str
    conditions: Dict  # Technical conditions
    success_rate: float
    avg_pnl_pct: float
    sample_size: int
    description: str


@dataclass
class ReflectionInsight:
    """Insight from self-reflection"""
    symbol: str
    insight_type: str  # "pattern_match", "warning", "opportunity"
    confidence: float
    description: str
    historical_context: str
    recommendation: str  # "proceed", "caution", "avoid"


@dataclass
class DebateResult:
    """Result of Bull vs Bear debate"""
    symbol: str
    bull_argument: str
    bear_argument: str
    bull_score: float  # 0-10
    bear_score: float  # 0-10
    winner: str  # "BULL", "BEAR", or "TIE"
    consensus: str  # "STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"
    key_risks: List[str]
    key_opportunities: List[str]
    final_recommendation: str

    @property
    def score_adjustment(self) -> float:
        """Score adjustment based on debate outcome"""
        diff = self.bull_score - self.bear_score
        # Normalize to -1 to +1
        return diff / 10.0


class TradeIntelligence:
    """
    Advanced trade analysis combining:
    - Self-reflection from past trades
    - Bull/Bear debate for balanced perspective

    Optimized for Ollama efficiency.
    """

    def __init__(
        self,
        trade_log_dir: str = "logs/trades",
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.2",
    ):
        self.logger = logging.getLogger(__name__)
        self.trade_log_dir = Path(trade_log_dir)
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model

        # Cached patterns from past trades
        self._learned_patterns: List[TradePattern] = []
        self._last_pattern_update: Optional[datetime] = None

        # Cache for recent analyses
        self._reflection_cache: Dict[str, Tuple[ReflectionInsight, datetime]] = {}
        self._debate_cache: Dict[str, Tuple[DebateResult, datetime]] = {}

    # ==================== SELF-REFLECTION ====================

    async def reflect_on_trade(
        self,
        symbol: str,
        setup_type: str,
        technical_data: Dict,
        confidence: float,
    ) -> Optional[ReflectionInsight]:
        """
        Reflect on a potential trade using past experience.

        Checks if similar setups have been profitable/unprofitable.
        """
        # Load patterns if needed
        if not self._learned_patterns or self._should_update_patterns():
            await self._load_patterns_from_logs()

        # Find matching patterns
        matching_patterns = self._find_matching_patterns(setup_type, technical_data)

        if not matching_patterns:
            return ReflectionInsight(
                symbol=symbol,
                insight_type="no_history",
                confidence=0.5,
                description="No similar past trades found",
                historical_context="First time seeing this setup",
                recommendation="proceed"
            )

        # Analyze matches
        winning_patterns = [p for p in matching_patterns if p.pattern_type == "winning"]
        losing_patterns = [p for p in matching_patterns if p.pattern_type == "losing"]

        total = len(matching_patterns)
        win_rate = len(winning_patterns) / total if total > 0 else 0.5

        # Determine recommendation
        if win_rate >= 0.7 and len(winning_patterns) >= 3:
            recommendation = "proceed"
            insight_type = "pattern_match"
            description = f"Strong historical success: {win_rate*100:.0f}% win rate on {total} similar trades"
        elif win_rate <= 0.3 and len(losing_patterns) >= 3:
            recommendation = "avoid"
            insight_type = "warning"
            description = f"Poor historical results: {win_rate*100:.0f}% win rate on {total} similar trades"
        else:
            recommendation = "caution"
            insight_type = "mixed"
            description = f"Mixed results: {win_rate*100:.0f}% win rate on {total} similar trades"

        # Build historical context
        if winning_patterns:
            avg_win = sum(p.avg_pnl_pct for p in winning_patterns) / len(winning_patterns)
            context = f"Avg winning trade: +{avg_win:.1f}%"
        elif losing_patterns:
            avg_loss = sum(p.avg_pnl_pct for p in losing_patterns) / len(losing_patterns)
            context = f"Avg losing trade: {avg_loss:.1f}%"
        else:
            context = "Insufficient data"

        return ReflectionInsight(
            symbol=symbol,
            insight_type=insight_type,
            confidence=win_rate,
            description=description,
            historical_context=context,
            recommendation=recommendation
        )

    async def _load_patterns_from_logs(self):
        """Load and analyze patterns from trade logs"""
        self._learned_patterns = []

        if not self.trade_log_dir.exists():
            return

        # Load recent trade logs (last 30 days)
        trades = []
        for i in range(30):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = self.trade_log_dir / f"trades_{date}.jsonl"

            if log_file.exists():
                try:
                    with open(log_file, 'r') as f:
                        for line in f:
                            try:
                                trade = json.loads(line)
                                if trade.get('outcome'):
                                    trades.append(trade)
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    self.logger.debug(f"Error loading {log_file}: {e}")

        if not trades:
            return

        # Group by setup type
        by_setup = {}
        for trade in trades:
            setup = trade.get('setup_type', 'unknown')
            if setup not in by_setup:
                by_setup[setup] = {'winning': [], 'losing': []}

            outcome = trade.get('outcome', {})
            if outcome.get('profitable'):
                by_setup[setup]['winning'].append(trade)
            else:
                by_setup[setup]['losing'].append(trade)

        # Create patterns
        for setup_type, results in by_setup.items():
            winning = results['winning']
            losing = results['losing']

            if winning:
                avg_pnl = sum(t['outcome']['pnl_percent'] for t in winning) / len(winning)
                self._learned_patterns.append(TradePattern(
                    pattern_type="winning",
                    setup_type=setup_type,
                    conditions=self._extract_common_conditions(winning),
                    success_rate=len(winning) / (len(winning) + len(losing)),
                    avg_pnl_pct=avg_pnl,
                    sample_size=len(winning),
                    description=f"Winning {setup_type} pattern"
                ))

            if losing:
                avg_pnl = sum(t['outcome']['pnl_percent'] for t in losing) / len(losing)
                self._learned_patterns.append(TradePattern(
                    pattern_type="losing",
                    setup_type=setup_type,
                    conditions=self._extract_common_conditions(losing),
                    success_rate=len(winning) / (len(winning) + len(losing)) if (winning or losing) else 0,
                    avg_pnl_pct=avg_pnl,
                    sample_size=len(losing),
                    description=f"Losing {setup_type} pattern"
                ))

        self._last_pattern_update = datetime.now()
        self.logger.info(f"📚 Loaded {len(self._learned_patterns)} patterns from {len(trades)} past trades")

    def _extract_common_conditions(self, trades: List[Dict]) -> Dict:
        """Extract common technical conditions from trades"""
        if not trades:
            return {}

        # Average technical indicators
        conditions = {}
        indicator_sums = {}
        count = 0

        for trade in trades:
            tech = trade.get('technical_data', {})
            for key, value in tech.items():
                if isinstance(value, (int, float)):
                    indicator_sums[key] = indicator_sums.get(key, 0) + value
            count += 1

        if count > 0:
            for key, total in indicator_sums.items():
                conditions[key] = total / count

        return conditions

    def _find_matching_patterns(
        self,
        setup_type: str,
        technical_data: Dict
    ) -> List[TradePattern]:
        """Find patterns that match current conditions"""
        matching = []

        for pattern in self._learned_patterns:
            # Match by setup type first
            if pattern.setup_type != setup_type:
                continue

            # Could add more sophisticated matching here
            # For now, just match by setup type
            matching.append(pattern)

        return matching

    def _should_update_patterns(self) -> bool:
        """Check if patterns should be reloaded"""
        if not self._last_pattern_update:
            return True
        age = (datetime.now() - self._last_pattern_update).total_seconds()
        return age > 3600  # Update every hour

    # ==================== BULL/BEAR DEBATE ====================

    async def debate_trade(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        technical_data: Dict,
        analyst_data: Optional[Dict] = None,
        news_sentiment: Optional[Dict] = None,
        market_context: Optional[Dict] = None,
    ) -> DebateResult:
        """
        Run a Bull vs Bear debate on the trade.

        Two AI perspectives argue for/against, then reach consensus.
        OPTIMIZED: Single Ollama call for entire debate.
        """
        # Check cache
        cache_key = f"{symbol}_{action}_{entry_price:.2f}"
        if cache_key in self._debate_cache:
            result, cached_at = self._debate_cache[cache_key]
            if (datetime.now() - cached_at).total_seconds() < 300:  # 5 min cache
                return result

        # Build context for debate
        context = self._build_debate_context(
            symbol, action, entry_price,
            technical_data, analyst_data, news_sentiment, market_context
        )

        # Run debate via Ollama (OPTIMIZED: single call)
        result = await self._run_debate_ollama(symbol, action, context)

        # Cache result
        self._debate_cache[cache_key] = (result, datetime.now())

        self.logger.info(
            f"⚔️ Debate {symbol}: Bull {result.bull_score:.1f} vs Bear {result.bear_score:.1f} "
            f"→ {result.winner} | {result.consensus}"
        )

        return result

    def _build_debate_context(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        technical_data: Dict,
        analyst_data: Optional[Dict],
        news_sentiment: Optional[Dict],
        market_context: Optional[Dict],
    ) -> str:
        """Build compact context string for debate"""
        parts = [
            f"Stock: {symbol} | Action: {action} | Price: ${entry_price:.2f}"
        ]

        if technical_data:
            tech_str = ", ".join([
                f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}"
                for k, v in list(technical_data.items())[:5]
            ])
            parts.append(f"Technical: {tech_str}")

        if analyst_data:
            parts.append(
                f"Analysts: {analyst_data.get('signal', 'N/A')} "
                f"({analyst_data.get('bullish_percent', 0):.0f}% bullish)"
            )

        if news_sentiment:
            parts.append(
                f"News: {news_sentiment.get('overall_sentiment', 'N/A')} "
                f"(score: {news_sentiment.get('overall_score', 0):+.2f})"
            )

        if market_context:
            parts.append(f"Market: {market_context.get('regime', 'N/A')}")

        return " | ".join(parts)

    async def _run_debate_ollama(
        self,
        symbol: str,
        action: str,
        context: str
    ) -> DebateResult:
        """
        Run Bull vs Bear debate in a SINGLE Ollama call.

        Optimized prompt that gets both perspectives + verdict.
        """
        prompt = f"""You are analyzing a {action} trade for {symbol}.

Context: {context}

Provide a Bull vs Bear debate in JSON format:
{{
  "bull_argument": "2-3 sentences why this trade will succeed",
  "bull_score": 0-10,
  "bear_argument": "2-3 sentences why this trade could fail",
  "bear_score": 0-10,
  "key_risks": ["risk1", "risk2"],
  "key_opportunities": ["opp1", "opp2"],
  "consensus": "STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL",
  "recommendation": "Final 1-sentence recommendation"
}}

Be objective. Higher score = stronger argument."""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 400}
                    },
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response_text = data.get('response', '')
                        return self._parse_debate_response(symbol, response_text)

        except Exception as e:
            self.logger.debug(f"Debate Ollama call failed: {e}")

        # Fallback to rule-based debate
        return self._rule_based_debate(symbol, action, context)

    def _parse_debate_response(self, symbol: str, text: str) -> DebateResult:
        """Parse debate JSON from Ollama response"""
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)

                bull_score = float(data.get('bull_score', 5))
                bear_score = float(data.get('bear_score', 5))

                if bull_score > bear_score + 2:
                    winner = "BULL"
                elif bear_score > bull_score + 2:
                    winner = "BEAR"
                else:
                    winner = "TIE"

                return DebateResult(
                    symbol=symbol,
                    bull_argument=data.get('bull_argument', ''),
                    bear_argument=data.get('bear_argument', ''),
                    bull_score=bull_score,
                    bear_score=bear_score,
                    winner=winner,
                    consensus=data.get('consensus', 'HOLD'),
                    key_risks=data.get('key_risks', []),
                    key_opportunities=data.get('key_opportunities', []),
                    final_recommendation=data.get('recommendation', '')
                )

        except Exception as e:
            self.logger.debug(f"Error parsing debate response: {e}")

        return self._rule_based_debate(symbol, "BUY", "")

    def _rule_based_debate(
        self,
        symbol: str,
        action: str,
        context: str
    ) -> DebateResult:
        """Fallback rule-based debate when LLM unavailable"""
        return DebateResult(
            symbol=symbol,
            bull_argument="Technical setup looks promising based on momentum indicators",
            bear_argument="Market conditions present inherent risks",
            bull_score=6.0,
            bear_score=5.0,
            winner="TIE",
            consensus="HOLD",
            key_risks=["Market volatility", "Execution risk"],
            key_opportunities=["Momentum continuation", "Volume confirmation"],
            final_recommendation="Proceed with caution and strict risk management"
        )

    # ==================== COMBINED ANALYSIS ====================

    async def full_analysis(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        setup_type: str,
        technical_data: Dict,
        confidence: float,
        analyst_data: Optional[Dict] = None,
        news_sentiment: Optional[Dict] = None,
        market_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Run full intelligence analysis: reflection + debate.

        OPTIMIZED: Runs both in parallel when possible.
        """
        # Run reflection and debate concurrently
        reflection_task = self.reflect_on_trade(
            symbol, setup_type, technical_data, confidence
        )
        debate_task = self.debate_trade(
            symbol, action, entry_price,
            technical_data, analyst_data, news_sentiment, market_context
        )

        reflection, debate = await asyncio.gather(
            reflection_task, debate_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(reflection, Exception):
            self.logger.debug(f"Reflection failed: {reflection}")
            reflection = None
        if isinstance(debate, Exception):
            self.logger.debug(f"Debate failed: {debate}")
            debate = None

        # Calculate combined score adjustment
        score_adj = 0
        if reflection and reflection.recommendation == "avoid":
            score_adj -= 1.0
        elif reflection and reflection.recommendation == "proceed":
            score_adj += 0.5

        if debate:
            score_adj += debate.score_adjustment

        # Build combined recommendation
        if reflection and reflection.recommendation == "avoid":
            combined_rec = "AVOID - Poor historical performance"
        elif debate and debate.consensus in ["STRONG_SELL", "SELL"]:
            combined_rec = "CAUTION - Bear case is stronger"
        elif debate and debate.consensus in ["STRONG_BUY", "BUY"]:
            combined_rec = "PROCEED - Bull case is stronger"
        else:
            combined_rec = "NEUTRAL - Mixed signals"

        return {
            "symbol": symbol,
            "reflection": {
                "recommendation": reflection.recommendation if reflection else "unknown",
                "confidence": reflection.confidence if reflection else 0.5,
                "description": reflection.description if reflection else "",
            } if reflection else None,
            "debate": {
                "winner": debate.winner if debate else "TIE",
                "bull_score": debate.bull_score if debate else 5,
                "bear_score": debate.bear_score if debate else 5,
                "consensus": debate.consensus if debate else "HOLD",
                "key_risks": debate.key_risks if debate else [],
            } if debate else None,
            "score_adjustment": score_adj,
            "combined_recommendation": combined_rec,
        }
