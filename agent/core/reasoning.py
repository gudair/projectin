"""
Reasoning Engine

Uses LLM (Ollama local or Claude API) for intelligent trading analysis.
Cost-optimized with caching, batching, and rate limiting.
Supports: Ollama (free, local) and Claude (paid, cloud).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
import json
import httpx

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from config.agent_config import (
    ClaudeConfig, OllamaConfig, CostOptimizationConfig,
    LLMProvider, DEFAULT_CONFIG
)
from agent.prompts.analysis import ANALYSIS_SYSTEM_PROMPT, create_analysis_prompt
from agent.prompts.decision import DECISION_SYSTEM_PROMPT, create_decision_prompt
from agent.prompts.compact import (
    COMPACT_ANALYSIS_SYSTEM, COMPACT_DECISION_SYSTEM, COMPACT_EXIT_SYSTEM,
    compact_analysis_prompt, compact_decision_prompt, compact_exit_prompt
)


# Cost-optimized batch analysis prompt (compact version)
BATCH_ANALYSIS_SYSTEM_PROMPT = """Stock analyst. JSON array only.
Per stock: {sym,rec:BUY|SELL|HOLD,conf:0-1,reason:str<20}"""


@dataclass
class CachedAnalysis:
    """Cached analysis result with metadata"""
    result: 'AnalysisResult'
    timestamp: datetime
    price_at_analysis: float

    def is_valid(self, current_price: float, cache_minutes: int, min_price_change_pct: float) -> bool:
        """Check if cache is still valid"""
        # Check time validity
        age = (datetime.now() - self.timestamp).total_seconds() / 60
        if age > cache_minutes:
            return False

        # Check price change
        if self.price_at_analysis > 0:
            price_change_pct = abs(current_price - self.price_at_analysis) / self.price_at_analysis * 100
            if price_change_pct > min_price_change_pct:
                return False

        return True


@dataclass
class AnalysisResult:
    """Result of LLM analysis"""
    symbol: str
    recommendation: str  # BUY, SELL, HOLD
    confidence: float
    reasoning: str
    key_factors: List[str]
    risks: List[str]
    suggested_entry: Optional[float]
    suggested_stop_loss: Optional[float]
    suggested_take_profit: Optional[float]
    position_size_suggestion: str  # FULL, HALF, QUARTER
    time_horizon: str
    raw_response: str


@dataclass
class DecisionResult:
    """Final trading decision from LLM"""
    should_trade: bool
    action: str  # BUY, SELL, PASS
    symbol: str
    confidence: float
    reasoning: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    position_size_pct: float
    urgency: str  # IMMEDIATE, STANDARD, LOW


class ReasoningEngine:
    """
    AI reasoning engine supporting multiple LLM backends.
    Cost-optimized with caching, batching, and rate limiting.

    Supports:
    - Ollama (local, free) - DEFAULT
    - Claude API (cloud, paid)

    Provides:
    - Multi-factor analysis synthesis
    - Pattern recognition
    - Risk assessment
    - Decision justification
    - Analysis caching (avoid redundant API calls)
    - Rate limiting (max calls per hour)
    - Batch analysis (multiple stocks per call)
    """

    def __init__(
        self,
        claude_config: Optional[ClaudeConfig] = None,
        cost_config: Optional[CostOptimizationConfig] = None,
        ollama_config: Optional[OllamaConfig] = None,
        provider: LLMProvider = LLMProvider.OLLAMA,
    ):
        self.claude_config = claude_config or DEFAULT_CONFIG.claude
        self.ollama_config = ollama_config or DEFAULT_CONFIG.ollama
        self.cost_config = cost_config or DEFAULT_CONFIG.cost
        self.provider = provider
        self.logger = logging.getLogger(__name__)

        # Initialize Claude client if needed
        self._claude_client = None
        if provider == LLMProvider.CLAUDE:
            if ANTHROPIC_AVAILABLE and self.claude_config.api_key:
                self._claude_client = anthropic.Anthropic(api_key=self.claude_config.api_key)
            else:
                self.logger.warning("Claude selected but not available, falling back to Ollama")
                self.provider = LLMProvider.OLLAMA

        # Initialize Ollama HTTP client
        self._ollama_client = httpx.AsyncClient(
            base_url=self.ollama_config.base_url,
            timeout=60.0  # Longer timeout for local inference
        )

        # Check Ollama availability (silently - agent will start it if needed)
        self._ollama_available = False
        if self.provider == LLMProvider.OLLAMA:
            self._check_ollama_sync()

        # Cost optimization: caching
        self._analysis_cache: Dict[str, CachedAnalysis] = {}

        # Cost optimization: rate limiting
        self._api_calls: deque = deque()  # timestamps of API calls
        self._api_calls_this_hour = 0

        # Stats tracking
        self._cache_hits = 0
        self._cache_misses = 0
        self._api_calls_total = 0
        self._api_calls_saved = 0

    def _check_ollama_sync(self, silent: bool = True):
        """Check if Ollama is available (sync version for init)"""
        import httpx as httpx_sync
        try:
            with httpx_sync.Client(timeout=2.0) as client:
                response = client.get(f"{self.ollama_config.base_url}/api/tags")
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    model_names = [m.get('name', '') for m in models]

                    # More flexible model matching
                    wanted_model = self.ollama_config.model.lower()
                    for name in model_names:
                        name_lower = name.lower()
                        if wanted_model == name_lower or wanted_model.split(':')[0] == name_lower.split(':')[0]:
                            self._ollama_available = True
                            return

                    # Model not found
                    if not silent:
                        self.logger.warning(f"⚠️ Model '{self.ollama_config.model}' not found. Install: ollama pull {self.ollama_config.model}")
                    self._ollama_available = True  # Let it fail at runtime
        except Exception:
            # Ollama not running - agent will start it
            pass

    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Call Ollama API with detailed logging"""
        import time
        start_time = time.time()

        try:
            self.logger.debug(f"🔄 Ollama request starting with model: {self.ollama_config.model}")

            # Use /api/chat endpoint (more reliable than /api/generate)
            response = await self._ollama_client.post(
                "/api/chat",
                json={
                    "model": self.ollama_config.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": self.ollama_config.temperature,
                        "num_predict": self.ollama_config.max_tokens,
                    }
                }
            )
            response.raise_for_status()
            data = response.json()

            elapsed = time.time() - start_time
            tokens = data.get('eval_count', 0)
            eval_duration = data.get('eval_duration', 0) / 1e9  # Convert to seconds

            # Calculate tokens per second
            tokens_per_sec = tokens / eval_duration if eval_duration > 0 else 0

            self.logger.info(
                f"✅ Ollama response: {elapsed:.2f}s | "
                f"{tokens} tokens | {tokens_per_sec:.1f} tok/s"
            )

            # Track Ollama-specific stats
            if not hasattr(self, '_ollama_stats'):
                self._ollama_stats = {'requests': 0, 'tokens': 0, 'total_time': 0}
            self._ollama_stats['requests'] += 1
            self._ollama_stats['tokens'] += tokens
            self._ollama_stats['total_time'] += elapsed

            # /api/chat returns response in message.content
            return data.get("message", {}).get("content", "")

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"❌ Ollama error after {elapsed:.2f}s: {e}")
            raise

    async def _call_claude(self, system_prompt: str, user_prompt: str) -> str:
        """Call Claude API"""
        if not self._claude_client:
            raise RuntimeError("Claude client not initialized")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._claude_client.messages.create(
                model=self.claude_config.model,
                max_tokens=self.claude_config.max_tokens,
                temperature=self.claude_config.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
        )
        return response.content[0].text

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the configured LLM provider"""
        if self.provider == LLMProvider.OLLAMA:
            if not self._ollama_available:
                self.logger.warning("Ollama not available, using fallback")
                return ""
            return await self._call_ollama(system_prompt, user_prompt)
        else:
            return await self._call_claude(system_prompt, user_prompt)

    def _check_rate_limit(self) -> bool:
        """Check if we're under the rate limit"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        # Remove old entries
        while self._api_calls and self._api_calls[0] < hour_ago:
            self._api_calls.popleft()

        return len(self._api_calls) < self.cost_config.max_analyses_per_hour

    def _record_api_call(self):
        """Record an API call for rate limiting"""
        self._api_calls.append(datetime.now())
        self._api_calls_total += 1

    def get_cached_analysis(self, symbol: str, current_price: float) -> Optional[AnalysisResult]:
        """Get cached analysis if valid"""
        if symbol not in self._analysis_cache:
            return None

        cached = self._analysis_cache[symbol]
        if cached.is_valid(
            current_price,
            self.cost_config.cache_analysis_minutes,
            self.cost_config.min_price_change_pct
        ):
            self._cache_hits += 1
            self.logger.debug(f"Cache hit for {symbol} (saved API call)")
            return cached.result

        self._cache_misses += 1
        return None

    def cache_analysis(self, symbol: str, result: AnalysisResult, price: float):
        """Cache an analysis result"""
        self._analysis_cache[symbol] = CachedAnalysis(
            result=result,
            timestamp=datetime.now(),
            price_at_analysis=price
        )

    def should_skip_analysis(self, symbol: str, current_price: float, market_open: bool) -> Tuple[bool, str]:
        """Determine if we should skip analysis to save costs"""
        # Check if market is closed and config says skip
        if not market_open and self.cost_config.skip_outside_market_hours:
            self._api_calls_saved += 1
            return True, "market closed"

        # Check rate limit
        if not self._check_rate_limit():
            self._api_calls_saved += 1
            return True, f"rate limit ({self.cost_config.max_analyses_per_hour}/hr)"

        # Check cache
        cached = self.get_cached_analysis(symbol, current_price)
        if cached is not None:
            self._api_calls_saved += 1
            return True, "cached"

        return False, ""

    def get_cost_stats(self) -> Dict[str, Any]:
        """Get cost optimization statistics"""
        total_potential = self._api_calls_total + self._api_calls_saved
        savings_pct = (self._api_calls_saved / total_potential * 100) if total_potential > 0 else 0

        stats = {
            "api_calls_made": self._api_calls_total,
            "api_calls_saved": self._api_calls_saved,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "savings_percentage": round(savings_pct, 1),
            "calls_last_hour": len(self._api_calls),
            "rate_limit": self.cost_config.max_analyses_per_hour,
            "provider": self.provider.value,
        }

        # Add Ollama-specific stats if available
        if hasattr(self, '_ollama_stats') and self._ollama_stats['requests'] > 0:
            stats["ollama_requests"] = self._ollama_stats['requests']
            stats["ollama_tokens"] = self._ollama_stats['tokens']
            stats["ollama_total_time"] = round(self._ollama_stats['total_time'], 2)
            avg_time = self._ollama_stats['total_time'] / self._ollama_stats['requests']
            stats["ollama_avg_response_time"] = round(avg_time, 2)

        return stats

    async def analyze_setup(
        self,
        symbol: str,
        technical_data: Dict[str, Any],
        news_sentiment: Optional[Dict] = None,
        market_context: Optional[Dict] = None,
        memory_context: Optional[str] = None,
        market_open: bool = True,
    ) -> AnalysisResult:
        """
        Analyze a trading setup using LLM (Ollama or Claude).
        Uses caching and rate limiting to minimize costs.

        Returns comprehensive analysis with recommendation.
        """
        current_price = technical_data.get('current_price', 0)

        # Check if we should skip analysis
        should_skip, reason = self.should_skip_analysis(symbol, current_price, market_open)
        if should_skip:
            # Return cached result if available
            cached = self.get_cached_analysis(symbol, current_price)
            if cached:
                self.logger.debug(f"Using cached analysis for {symbol} ({reason})")
                return cached

            # Otherwise return fallback
            self.logger.debug(f"Skipping analysis for {symbol}: {reason}")
            return self._fallback_analysis(symbol, technical_data)

        # Check if LLM is available
        if self.provider == LLMProvider.OLLAMA and not self._ollama_available:
            return self._fallback_analysis(symbol, technical_data)
        if self.provider == LLMProvider.CLAUDE and not self._claude_client:
            return self._fallback_analysis(symbol, technical_data)

        # Build the prompt - use compact for Ollama (faster), verbose for Claude
        if self.provider == LLMProvider.OLLAMA:
            # Compact prompt: ~200 tokens vs ~800
            prompt = compact_analysis_prompt(
                symbol=symbol,
                technical=technical_data,
                market=market_context,
                news=news_sentiment,
            )
            system_prompt = COMPACT_ANALYSIS_SYSTEM
        else:
            # Full prompt for Claude (more capable)
            prompt = create_analysis_prompt(
                symbol=symbol,
                technical_data=technical_data,
                news_sentiment=news_sentiment,
                market_context=market_context,
                memory_context=memory_context,
            )
            system_prompt = ANALYSIS_SYSTEM_PROMPT

        try:
            # Record API call for rate limiting
            self._record_api_call()

            # Call LLM (Ollama or Claude)
            response_text = await self._call_llm(system_prompt, prompt)

            if not response_text:
                return self._fallback_analysis(symbol, technical_data)

            result = self._parse_analysis_text(symbol, response_text)

            # Cache the result
            self.cache_analysis(symbol, result, current_price)

            return result

        except Exception as e:
            self.logger.error(f"LLM API error: {e}")
            return self._fallback_analysis(symbol, technical_data)

    async def batch_analyze(
        self,
        stocks: List[Dict[str, Any]],
        market_context: Optional[Dict] = None,
        market_open: bool = True,
    ) -> List[AnalysisResult]:
        """
        Analyze multiple stocks in a single API call to reduce costs.

        Args:
            stocks: List of dicts with 'symbol' and 'technical_data' keys
            market_context: Market context data
            market_open: Whether market is open

        Returns:
            List of AnalysisResult for each stock
        """
        if not stocks:
            return []

        # Check market open
        if not market_open and self.cost_config.skip_outside_market_hours:
            self.logger.info("Skipping batch analysis: market closed")
            return [self._fallback_analysis(s['symbol'], s.get('technical_data', {})) for s in stocks]

        # Check rate limit
        if not self._check_rate_limit():
            self.logger.warning("Rate limit reached, using fallback for batch")
            return [self._fallback_analysis(s['symbol'], s.get('technical_data', {})) for s in stocks]

        # Filter out stocks with valid cache
        stocks_to_analyze = []
        cached_results = []

        for stock in stocks:
            symbol = stock['symbol']
            tech_data = stock.get('technical_data', {})
            current_price = tech_data.get('current_price', 0)

            cached = self.get_cached_analysis(symbol, current_price)
            if cached:
                cached_results.append((symbol, cached))
            else:
                stocks_to_analyze.append(stock)

        # If all cached, return cached results
        if not stocks_to_analyze:
            self.logger.info(f"All {len(stocks)} stocks served from cache")
            return [r for _, r in cached_results]

        # Limit batch size
        batch_size = min(len(stocks_to_analyze), self.cost_config.max_stocks_per_batch)
        stocks_to_analyze = stocks_to_analyze[:batch_size]

        # Check if LLM is available
        if self.provider == LLMProvider.OLLAMA and not self._ollama_available:
            results = [self._fallback_analysis(s['symbol'], s.get('technical_data', {})) for s in stocks_to_analyze]
            results.extend([r for _, r in cached_results])
            return results
        if self.provider == LLMProvider.CLAUDE and not self._claude_client:
            results = [self._fallback_analysis(s['symbol'], s.get('technical_data', {})) for s in stocks_to_analyze]
            results.extend([r for _, r in cached_results])
            return results

        # Build batch prompt
        prompt = self._create_batch_prompt(stocks_to_analyze, market_context)

        try:
            self._record_api_call()
            self.logger.info(f"Batch analyzing {len(stocks_to_analyze)} stocks in 1 API call")

            # Call LLM (Ollama or Claude)
            response_text = await self._call_llm(BATCH_ANALYSIS_SYSTEM_PROMPT, prompt)

            if not response_text:
                results = [self._fallback_analysis(s['symbol'], s.get('technical_data', {})) for s in stocks_to_analyze]
                results.extend([r for _, r in cached_results])
                return results

            # Parse batch response
            results = self._parse_batch_response_text(stocks_to_analyze, response_text)

            # Cache results
            for stock, result in zip(stocks_to_analyze, results):
                price = stock.get('technical_data', {}).get('current_price', 0)
                self.cache_analysis(stock['symbol'], result, price)

            # Add cached results
            results.extend([r for _, r in cached_results])
            return results

        except Exception as e:
            self.logger.error(f"Batch analysis error: {e}")
            results = [self._fallback_analysis(s['symbol'], s.get('technical_data', {})) for s in stocks_to_analyze]
            results.extend([r for _, r in cached_results])
            return results

    def _create_batch_prompt(self, stocks: List[Dict], market_context: Optional[Dict]) -> str:
        """Create a prompt for batch analysis"""
        prompt_parts = ["Analyze these stocks briefly. For each, provide: recommendation (BUY/SELL/HOLD), confidence (0-1), and key reason.\n"]

        if market_context:
            prompt_parts.append(f"Market: SPY {market_context.get('spy_change', 0):+.1f}%, VIX {market_context.get('vix', 20):.1f}\n")

        prompt_parts.append("\nStocks:\n")
        for stock in stocks:
            symbol = stock['symbol']
            tech = stock.get('technical_data', {})
            prompt_parts.append(
                f"- {symbol}: ${tech.get('current_price', 0):.2f}, "
                f"chg {tech.get('change_pct', 0):+.1f}%, "
                f"RSI {tech.get('rsi', 50):.0f}, "
                f"vol {tech.get('volume_ratio', 1):.1f}x\n"
            )

        prompt_parts.append("\nRespond in JSON: [{\"symbol\": \"X\", \"recommendation\": \"BUY\", \"confidence\": 0.7, \"reason\": \"...\"}]")
        return "".join(prompt_parts)

    def _parse_batch_response_text(self, stocks: List[Dict], content: str) -> List[AnalysisResult]:
        """Parse batch analysis response text (works with both Ollama and Claude)"""
        results = []
        try:
            # Extract JSON
            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                json_str = content[json_start:json_end].strip()
            elif '[' in content:
                json_start = content.find('[')
                json_end = content.rfind(']') + 1
                json_str = content[json_start:json_end]
            else:
                json_str = content

            data = json.loads(json_str)

            # Map results to stocks
            symbol_to_data = {d.get('symbol', ''): d for d in data}

            for stock in stocks:
                symbol = stock['symbol']
                tech = stock.get('technical_data', {})

                if symbol in symbol_to_data:
                    d = symbol_to_data[symbol]
                    results.append(AnalysisResult(
                        symbol=symbol,
                        recommendation=d.get('recommendation', 'HOLD'),
                        confidence=float(d.get('confidence', 0.5)),
                        reasoning=d.get('reason', ''),
                        key_factors=[d.get('reason', '')] if d.get('reason') else [],
                        risks=[],
                        suggested_entry=tech.get('current_price'),
                        suggested_stop_loss=None,
                        suggested_take_profit=None,
                        position_size_suggestion='QUARTER',
                        time_horizon='intraday',
                        raw_response=content,
                    ))
                else:
                    results.append(self._fallback_analysis(symbol, tech))

        except Exception as e:
            self.logger.error(f"Error parsing batch response: {e}")
            for stock in stocks:
                results.append(self._fallback_analysis(stock['symbol'], stock.get('technical_data', {})))

        return results

    async def make_decision(
        self,
        analyses: List[AnalysisResult],
        portfolio_state: Dict[str, Any],
        risk_constraints: Dict[str, Any],
        market_context: Optional[Dict] = None,
    ) -> DecisionResult:
        """
        Synthesize analyses into a final trading decision.

        Considers:
        - Multiple analysis results
        - Current portfolio state
        - Risk constraints
        - Market conditions
        """
        # Check if LLM is available
        if self.provider == LLMProvider.OLLAMA and not self._ollama_available:
            return self._fallback_decision(analyses)
        if self.provider == LLMProvider.CLAUDE and not self._claude_client:
            return self._fallback_decision(analyses)

        # Build decision prompt - compact for Ollama, verbose for Claude
        if self.provider == LLMProvider.OLLAMA:
            prompt = compact_decision_prompt(
                analyses=analyses,
                portfolio=portfolio_state,
                risk=risk_constraints,
                market=market_context,
            )
            system_prompt = COMPACT_DECISION_SYSTEM
        else:
            prompt = create_decision_prompt(
                analyses=analyses,
                portfolio_state=portfolio_state,
                risk_constraints=risk_constraints,
                market_context=market_context,
            )
            system_prompt = DECISION_SYSTEM_PROMPT

        try:
            # Call LLM (Ollama or Claude)
            response_text = await self._call_llm(system_prompt, prompt)

            if not response_text:
                return self._fallback_decision(analyses)

            return self._parse_decision_text(analyses, response_text)

        except Exception as e:
            self.logger.error(f"LLM API error in decision: {e}")
            return self._fallback_decision(analyses)

    def _parse_analysis_text(self, symbol: str, text: str) -> AnalysisResult:
        """Parse LLM analysis response text (works with both Ollama and Claude)"""
        try:
            # Try to extract JSON if present
            try:
                # Look for JSON block
                if '```json' in text:
                    json_start = text.find('```json') + 7
                    json_end = text.find('```', json_start)
                    json_str = text[json_start:json_end].strip()
                    data = json.loads(json_str)
                elif '{' in text:
                    # Try to find JSON object
                    json_start = text.find('{')
                    json_end = text.rfind('}') + 1
                    json_str = text[json_start:json_end]
                    data = json.loads(json_str)
                else:
                    # Try parsing entire response as JSON
                    data = json.loads(text)

                # Debug: Log parsed analysis
                self.logger.info(
                    f"🔍 {symbol} Analysis: {data.get('recommendation', 'HOLD')} "
                    f"@ {data.get('confidence', 0):.0%} conf"
                )

                return AnalysisResult(
                    symbol=symbol,
                    recommendation=data.get('recommendation', 'HOLD'),
                    confidence=float(data.get('confidence', 0.5)),
                    reasoning=data.get('reasoning', text),
                    key_factors=data.get('key_factors', []),
                    risks=data.get('risks', []),
                    suggested_entry=data.get('entry_price'),
                    suggested_stop_loss=data.get('stop_loss'),
                    suggested_take_profit=data.get('take_profit'),
                    position_size_suggestion=data.get('position_size', 'QUARTER'),
                    time_horizon=data.get('time_horizon', 'intraday'),
                    raw_response=text,
                )

            except json.JSONDecodeError:
                # Parse free-form text response
                return self._parse_freeform_analysis(symbol, text)

        except Exception as e:
            self.logger.error(f"Error parsing analysis response: {e}")
            return self._fallback_analysis(symbol, {})

    def _parse_analysis_response(self, symbol: str, response) -> AnalysisResult:
        """Parse Claude's analysis response (legacy - delegates to _parse_analysis_text)"""
        try:
            content = response.content[0].text

            # Try to extract JSON if present
            try:
                # Look for JSON block
                if '```json' in content:
                    json_start = content.find('```json') + 7
                    json_end = content.find('```', json_start)
                    json_str = content[json_start:json_end].strip()
                    data = json.loads(json_str)
                else:
                    # Try parsing entire response as JSON
                    data = json.loads(content)

                return AnalysisResult(
                    symbol=symbol,
                    recommendation=data.get('recommendation', 'HOLD'),
                    confidence=float(data.get('confidence', 0.5)),
                    reasoning=data.get('reasoning', content),
                    key_factors=data.get('key_factors', []),
                    risks=data.get('risks', []),
                    suggested_entry=data.get('entry_price'),
                    suggested_stop_loss=data.get('stop_loss'),
                    suggested_take_profit=data.get('take_profit'),
                    position_size_suggestion=data.get('position_size', 'QUARTER'),
                    time_horizon=data.get('time_horizon', 'intraday'),
                    raw_response=content,
                )

            except json.JSONDecodeError:
                # Parse free-form text response
                return self._parse_freeform_analysis(symbol, content)

        except Exception as e:
            self.logger.error(f"Error parsing analysis response: {e}")
            return self._fallback_analysis(symbol, {})

    def _parse_freeform_analysis(self, symbol: str, content: str) -> AnalysisResult:
        """Parse free-form text analysis"""
        # Extract recommendation
        content_lower = content.lower()
        if 'strong buy' in content_lower or 'strongly recommend buying' in content_lower:
            recommendation = 'BUY'
            confidence = 0.8
        elif 'buy' in content_lower and 'don\'t buy' not in content_lower:
            recommendation = 'BUY'
            confidence = 0.65
        elif 'sell' in content_lower or 'exit' in content_lower:
            recommendation = 'SELL'
            confidence = 0.65
        else:
            recommendation = 'HOLD'
            confidence = 0.5

        return AnalysisResult(
            symbol=symbol,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=content,
            key_factors=[],
            risks=[],
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
            position_size_suggestion='QUARTER',
            time_horizon='intraday',
            raw_response=content,
        )

    def _parse_decision_text(self, analyses: List[AnalysisResult], content: str) -> DecisionResult:
        """Parse LLM decision response text (works with both Ollama and Claude)"""
        try:
            # Try JSON parsing first
            try:
                if '```json' in content:
                    json_start = content.find('```json') + 7
                    json_end = content.find('```', json_start)
                    json_str = content[json_start:json_end].strip()
                    data = json.loads(json_str)
                elif '{' in content:
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    json_str = content[json_start:json_end]
                    data = json.loads(json_str)
                else:
                    data = json.loads(content)

                # Handle should_trade as string or bool
                should_trade = data.get('should_trade', False)
                if isinstance(should_trade, str):
                    should_trade = should_trade.lower() == 'true'

                # Debug: Log parsed decision
                symbol = data.get('symbol', analyses[0].symbol if analyses else '?')
                self.logger.info(
                    f"🎯 Decision for {symbol}: trade={should_trade}, "
                    f"action={data.get('action', 'PASS')}, conf={data.get('confidence', 0):.0%}"
                )

                return DecisionResult(
                    should_trade=should_trade,
                    action=data.get('action', 'PASS'),
                    symbol=data.get('symbol', analyses[0].symbol if analyses else ''),
                    confidence=float(data.get('confidence', 0.5)),
                    reasoning=data.get('reasoning', content),
                    entry_price=data.get('entry_price'),
                    stop_loss=data.get('stop_loss'),
                    take_profit=data.get('take_profit'),
                    position_size_pct=float(data.get('position_size_pct', 0.1)),
                    urgency=data.get('urgency', 'STANDARD'),
                )

            except json.JSONDecodeError:
                # Parse free-form
                return self._parse_freeform_decision(analyses, content)

        except Exception as e:
            self.logger.error(f"Error parsing decision response: {e}")
            return self._fallback_decision(analyses)

    def _parse_decision_response(self, analyses: List[AnalysisResult], response) -> DecisionResult:
        """Parse Claude's decision response (legacy - delegates to _parse_decision_text)"""
        try:
            content = response.content[0].text
            return self._parse_decision_text(analyses, content)
        except Exception as e:
            self.logger.error(f"Error parsing decision response: {e}")
            return self._fallback_decision(analyses)

    def _parse_freeform_decision(self, analyses: List[AnalysisResult], content: str) -> DecisionResult:
        """Parse free-form decision text"""
        content_lower = content.lower()

        should_trade = 'recommend' in content_lower and 'pass' not in content_lower
        action = 'PASS'
        confidence = 0.5

        if 'buy' in content_lower and 'don\'t buy' not in content_lower:
            action = 'BUY'
            confidence = 0.6
            should_trade = True
        elif 'sell' in content_lower:
            action = 'SELL'
            confidence = 0.6
            should_trade = True

        return DecisionResult(
            should_trade=should_trade,
            action=action,
            symbol=analyses[0].symbol if analyses else '',
            confidence=confidence,
            reasoning=content,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            position_size_pct=0.1,
            urgency='STANDARD',
        )

    def _fallback_analysis(self, symbol: str, technical_data: Dict) -> AnalysisResult:
        """Fallback analysis when Claude is unavailable"""
        # Simple rule-based analysis
        rsi = technical_data.get('rsi', 50)
        macd_bullish = technical_data.get('macd', 0) > technical_data.get('macd_signal', 0)

        if rsi < 30 and macd_bullish:
            recommendation = 'BUY'
            confidence = 0.6
            reasoning = f"Oversold RSI ({rsi:.1f}) with bullish MACD crossover"
        elif rsi > 70 and not macd_bullish:
            recommendation = 'SELL'
            confidence = 0.6
            reasoning = f"Overbought RSI ({rsi:.1f}) with bearish MACD"
        else:
            recommendation = 'HOLD'
            confidence = 0.5
            reasoning = f"No clear signal. RSI: {rsi:.1f}"

        return AnalysisResult(
            symbol=symbol,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            key_factors=['Technical indicators only (Claude unavailable)'],
            risks=['Limited analysis due to API unavailability'],
            suggested_entry=technical_data.get('current_price'),
            suggested_stop_loss=None,
            suggested_take_profit=None,
            position_size_suggestion='QUARTER',
            time_horizon='intraday',
            raw_response='[Fallback analysis - Claude API not available]',
        )

    def _fallback_decision(self, analyses: List[AnalysisResult]) -> DecisionResult:
        """Fallback decision when Claude is unavailable"""
        if not analyses:
            return DecisionResult(
                should_trade=False,
                action='PASS',
                symbol='',
                confidence=0,
                reasoning='No analyses available',
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                position_size_pct=0,
                urgency='LOW',
            )

        # Use simple majority voting
        buy_votes = sum(1 for a in analyses if a.recommendation == 'BUY')
        sell_votes = sum(1 for a in analyses if a.recommendation == 'SELL')

        best_analysis = max(analyses, key=lambda a: a.confidence)

        if buy_votes > sell_votes and buy_votes > len(analyses) / 2:
            return DecisionResult(
                should_trade=True,
                action='BUY',
                symbol=best_analysis.symbol,
                confidence=best_analysis.confidence * 0.8,  # Reduce confidence for fallback
                reasoning=f"Fallback decision: {buy_votes}/{len(analyses)} analyses recommend BUY",
                entry_price=best_analysis.suggested_entry,
                stop_loss=best_analysis.suggested_stop_loss,
                take_profit=best_analysis.suggested_take_profit,
                position_size_pct=0.1,
                urgency='STANDARD',
            )

        return DecisionResult(
            should_trade=False,
            action='PASS',
            symbol=best_analysis.symbol,
            confidence=0.5,
            reasoning='No clear consensus from analyses',
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            position_size_pct=0,
            urgency='LOW',
        )

    def test_connection(self) -> Tuple[bool, str]:
        """Test LLM connection (Ollama or Claude)"""
        if self.provider == LLMProvider.OLLAMA:
            if self._ollama_available:
                return True, f"Ollama connected ({self.ollama_config.model})"
            else:
                return False, "Ollama not available - run 'ollama serve'"
        else:
            if not self._claude_client:
                return False, "Claude API key not configured"
            try:
                self._claude_client.messages.create(
                    model=self.claude_config.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hello"}]
                )
                return True, f"Claude connected ({self.claude_config.model})"
            except Exception as e:
                self.logger.error(f"Claude connection test failed: {e}")
                return False, f"Claude connection failed: {e}"

    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current LLM provider"""
        if self.provider == LLMProvider.OLLAMA:
            # Fresh check for Ollama availability (agent may have started it)
            ollama_running = self._check_ollama_status()
            if ollama_running:
                self._ollama_available = True
            return {
                "provider": "Ollama (Local)",
                "model": self.ollama_config.model,
                "available": ollama_running,
                "cost": "Free",
                "base_url": self.ollama_config.base_url,
            }
        else:
            return {
                "provider": "Claude (Cloud)",
                "model": self.claude_config.model,
                "available": self._claude_client is not None,
                "cost": "Paid (API)",
            }

    def _check_ollama_status(self) -> bool:
        """Quick check if Ollama is running"""
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(f"{self.ollama_config.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, Exception):
            return False
