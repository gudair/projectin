"""
Trading Agent

Main orchestrator for the AI trading agent.
"""
import asyncio
import logging
import subprocess
import signal
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import uuid

from config.agent_config import (
    AgentConfig, DEFAULT_CONFIG, AlertLevel,
    MarketRegime, TradingMode, LLMProvider
)
from agent.core.reasoning import ReasoningEngine, AnalysisResult, DecisionResult
from agent.core.memory import TradingMemory, TradeRecord, PatternMatch
from agent.core.context import MarketContext, MarketContextData
from agent.core.discovery import StockDiscovery
from agent.core.momentum import MomentumScanner, MomentumConfig, PartialProfitManager, MomentumSetup
from agent.core.trade_logger import TradeLogger
from agent.core.analyst_ratings import AnalystRatingsProvider, AnalystRating
from agent.core.risk_manager import RiskManager, RiskConfig, RiskCheckResult
from agent.core.news_sentiment import NewsSentimentAnalyzer, NewsSentiment
from agent.core.trade_intelligence import TradeIntelligence, DebateResult, ReflectionInsight
from agent.core.atr_stops import ATRStopManager, ATRResult, DynamicStopLevels
from agent.core.periodic_reflection import PeriodicReflectionAgent, ReflectionReport
from agent.core.layered_memory import LayeredMemorySystem, MemoryItem
from agent.core.position_intelligence import PositionIntelligence, PositionRecommendation, MarketSession
from alerts.manager import AlertManager, Alert, TradingOpportunity, AlertAction
from alpaca.client import AlpacaClient
from alpaca.stream import AlpacaStreamer, StreamQuote, QuoteAggregator
from alpaca.executor import OrderExecutor, OrderRequest, ExecutionResult, OrderSide, OrderType
from data.collectors.news_collector import NewsCollector
from data.processors.sentiment_analyzer import SentimentAnalyzer


class AgentState(Enum):
    """Agent operational state"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class AgentStatus:
    """Current agent status"""
    state: AgentState
    uptime_seconds: int
    signals_generated: int
    alerts_sent: int
    trades_executed: int
    last_signal_time: Optional[datetime]
    last_trade_time: Optional[datetime]
    market_open: bool
    current_regime: MarketRegime


class TradingAgent:
    """
    Main AI Trading Agent

    Orchestrates:
    - Real-time market data streaming
    - Signal generation and analysis
    - AI-powered decision making
    - Alert generation for user confirmation
    - Trade execution via Alpaca
    - Learning from past trades
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.logger = logging.getLogger(__name__)

        # Core components
        self.reasoning = ReasoningEngine(
            claude_config=self.config.claude,
            cost_config=self.config.cost,
            ollama_config=self.config.ollama,
            provider=self.config.llm_provider,
        )
        self.memory = TradingMemory(self.config.memory_file)
        self.market_context = MarketContext()
        self.alert_manager = AlertManager()
        self.discovery = StockDiscovery(self.config.discovery)

        # News & Sentiment (now active with Ollama - free analysis)
        self.news_collector = NewsCollector()
        self.sentiment_analyzer = SentimentAnalyzer()

        # Alpaca components
        self.alpaca_client = AlpacaClient(self.config.alpaca)
        self.streamer = AlpacaStreamer(self.config.alpaca)
        self.executor = OrderExecutor(self.alpaca_client, self.config.risk)
        self.quote_aggregator = QuoteAggregator()

        # Set base watchlist for discovery
        self.discovery.set_base_watchlist(self.config.watchlist)
        self.discovery.alpaca = self.alpaca_client

        # Momentum Scanner for high-probability setups (2% daily target)
        self.momentum_scanner = MomentumScanner(
            config=MomentumConfig(
                scan_interval_seconds=60,
                min_gap_pct=3.0,
                min_change_pct=2.0,
                min_volume_ratio=2.0,
                min_score_to_trade=6.0,
                stop_loss_pct=0.02,      # 2% stop
                target_1_pct=0.015,      # +1.5%
                target_2_pct=0.025,      # +2.5%
                target_3_pct=0.04,       # +4%
            ),
            alpaca_client=self.alpaca_client
        )

        # Partial Profit Manager for scaling out of winners
        self.profit_manager = PartialProfitManager()

        # Trade Logger - Saves detailed reasoning for each trade decision
        self.trade_logger = TradeLogger(log_dir="logs/trades")

        # Analyst Ratings - Yahoo Finance integration (free)
        self.analyst_ratings = AnalystRatingsProvider(cache_minutes=60)

        # Risk Manager - Independent trade validator
        self.risk_manager = RiskManager(RiskConfig(
            max_position_pct=0.20,
            max_daily_loss_pct=0.03,
            max_drawdown_pct=0.10,
            pdt_protection=True,
            min_confidence=0.5,
        ))

        # News Sentiment - Alpaca News API + Ollama analysis
        self.news_sentiment = NewsSentimentAnalyzer(
            cache_minutes=15,
            ollama_url=self.config.ollama.base_url if self.config.ollama else "http://localhost:11434",
        )

        # Trade Intelligence - Self-reflection + Bull/Bear debate
        self.trade_intelligence = TradeIntelligence(
            trade_log_dir="logs/trades",
            ollama_url=self.config.ollama.base_url if self.config.ollama else "http://localhost:11434",
        )

        # ATR Dynamic Stops - Volatility-based stop-loss management
        self.atr_manager = ATRStopManager(
            alpaca_client=self.alpaca_client,
            atr_period=14,
            cache_minutes=5,
            min_stop_pct=0.01,   # Minimum 1% stop
            max_stop_pct=0.05,   # Maximum 5% stop
        )

        # Periodic Reflection Agent - Learns from past trades every N executions
        self.periodic_reflection = PeriodicReflectionAgent(
            trade_log_dir="logs/trades",
            reflection_interval=10,  # Reflect every 10 trades
        )

        # Layered Memory System - Hierarchical memory (working/short-term/deep)
        self.layered_memory = LayeredMemorySystem(
            memory_dir="data/memory",
        )

        # Position Intelligence - Kelly Criterion, Drawdown Protection, Session Awareness
        self.position_intelligence = PositionIntelligence(
            initial_equity=1000.0,  # Will be updated on start
            max_drawdown_pct=0.10,
            max_sector_exposure_pct=0.40,
            use_half_kelly=True,  # Conservative approach
        )

        # State
        self._state = AgentState.STOPPED
        self._start_time: Optional[datetime] = None
        self._signals_generated = 0
        self._alerts_sent = 0
        self._trades_executed = 0
        self._last_signal_time: Optional[datetime] = None
        self._last_trade_time: Optional[datetime] = None

        # Tasks
        self._main_task: Optional[asyncio.Task] = None
        self._signal_task: Optional[asyncio.Task] = None
        self._context_task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._position_monitor_task: Optional[asyncio.Task] = None

        # Trading controls
        self._trading_halted: bool = False
        self._halt_reason: str = ""

        # Callbacks
        self._on_alert_callbacks: List[Callable] = []
        self._on_trade_callbacks: List[Callable] = []

        # Current context cache
        self._current_context: Optional[MarketContextData] = None

        # Market status cache (avoid multiple API calls per minute)
        self._market_open_cache: bool = False
        self._market_check_time: Optional[datetime] = None
        self._market_check_interval = 60  # seconds between market status checks

        # Ollama process management
        self._ollama_process: Optional[subprocess.Popen] = None

    def on_alert(self, callback: Callable):
        """Register callback for new alerts"""
        self._on_alert_callbacks.append(callback)

    def on_trade(self, callback: Callable):
        """Register callback for trade executions"""
        self._on_trade_callbacks.append(callback)

    async def _is_market_open(self) -> bool:
        """Check market status with caching to avoid excessive API calls"""
        now = datetime.now()

        # Use cached value if recent enough
        if self._market_check_time:
            elapsed = (now - self._market_check_time).total_seconds()
            if elapsed < self._market_check_interval:
                return self._market_open_cache

        # Fetch fresh status
        self._market_open_cache = await self.alpaca_client.is_market_open()
        self._market_check_time = now

        return self._market_open_cache


    def _start_ollama(self) -> bool:
        """Start Ollama server if not already running"""
        import urllib.request
        import urllib.error

        # Check if Ollama is already running
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    self.logger.info("✅ Ollama already running")
                    return True
        except (urllib.error.URLError, Exception):
            pass  # Not running, need to start

        # Start Ollama
        self.logger.info("🚀 Starting Ollama server...")
        try:
            # Start ollama serve in background
            self._ollama_process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if os.name != 'nt' else None,
            )

            # Wait for Ollama to be ready (max 30 seconds)
            import time
            for i in range(30):
                time.sleep(1)
                try:
                    req = urllib.request.Request("http://localhost:11434/api/tags")
                    with urllib.request.urlopen(req, timeout=2) as response:
                        if response.status == 200:
                            self.logger.info(f"✅ Ollama started successfully (took {i+1}s)")
                            return True
                except (urllib.error.URLError, Exception):
                    if i % 5 == 0:
                        self.logger.info(f"⏳ Waiting for Ollama... ({i}s)")

            self.logger.error("❌ Ollama failed to start within 30 seconds")
            return False

        except FileNotFoundError:
            self.logger.error("❌ Ollama not installed. Install from: https://ollama.ai")
            return False
        except Exception as e:
            self.logger.error(f"❌ Failed to start Ollama: {e}")
            return False

    def _stop_ollama(self):
        """Stop Ollama server if we started it"""
        if self._ollama_process:
            self.logger.info("🛑 Stopping Ollama server...")
            try:
                # Kill the process group
                if os.name != 'nt':
                    os.killpg(os.getpgid(self._ollama_process.pid), signal.SIGTERM)
                else:
                    self._ollama_process.terminate()

                # Wait for it to stop
                self._ollama_process.wait(timeout=5)
                self.logger.info("✅ Ollama stopped")
            except subprocess.TimeoutExpired:
                self.logger.warning("⚠️ Ollama didn't stop gracefully, killing...")
                if os.name != 'nt':
                    os.killpg(os.getpgid(self._ollama_process.pid), signal.SIGKILL)
                else:
                    self._ollama_process.kill()
            except Exception as e:
                self.logger.warning(f"⚠️ Error stopping Ollama: {e}")
            finally:
                self._ollama_process = None

    async def start(self):
        """Start the trading agent"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 STARTING TRADING AGENT")
        self.logger.info("=" * 60)
        self._state = AgentState.STARTING

        try:
            # Start Ollama if using Ollama provider
            if self.config.llm_provider == LLMProvider.OLLAMA:
                self.logger.info("📦 LLM Provider: Ollama (local)")
                if not self._start_ollama():
                    self.logger.error("❌ Cannot start without Ollama")
                    self._state = AgentState.ERROR
                    return False
            else:
                self.logger.info(f"📦 LLM Provider: {self.config.llm_provider.value}")

            # Validate configuration
            is_valid, errors = self.config.validate()
            if not is_valid:
                self.logger.error(f"❌ Configuration errors: {errors}")
                self._state = AgentState.ERROR
                return False
            self.logger.info("✅ Configuration validated")

            # Connect to Alpaca
            self.logger.info("🔌 Connecting to Alpaca...")
            await self.streamer.connect()
            self.logger.info("✅ Connected to Alpaca streaming")

            # Get account info
            try:
                account = await self.alpaca_client.get_account()
                self.logger.info(f"💰 Account: ${account.equity:.2f} equity, ${account.buying_power:.2f} buying power")
            except Exception as e:
                self.logger.warning(f"Could not get account info: {e}")

            # Subscribe to watchlist
            from alpaca.stream import StreamType
            self.logger.info(f"📋 Watchlist: {self.config.watchlist or 'Dynamic (discovery mode)'}")
            await self.streamer.subscribe(
                self.config.watchlist,
                stream_types=[StreamType.QUOTES, StreamType.TRADES]
            )

            # Register quote handler
            self.streamer.on_quote(self._handle_quote)

            # Auto-track existing positions with stop-losses (CRITICAL!)
            self.logger.info("🛡️ Setting up stop-losses for existing positions...")
            tracked = await self.executor.auto_track_existing_positions()
            if tracked > 0:
                self.logger.info(f"✅ {tracked} positions now protected with trailing stops")
            else:
                self.logger.info("📭 No existing positions to track")

            # Start background tasks
            self.logger.info("🔄 Starting background tasks...")
            self._main_task = asyncio.create_task(self.streamer.run())
            self._signal_task = asyncio.create_task(self._signal_loop())
            self._context_task = asyncio.create_task(self._context_loop())
            self._discovery_task = asyncio.create_task(self._discovery_loop())
            self._position_monitor_task = asyncio.create_task(self._position_monitor_loop())

            self._state = AgentState.RUNNING
            self._start_time = datetime.now()

            self.logger.info("=" * 60)
            self.logger.info("🤖 TRADING AGENT STARTED (AUTONOMOUS MODE)")
            self.logger.info("   - Position monitor: Every 30 seconds")
            self.logger.info("   - Signal generation: Every 60 seconds")
            self.logger.info("   - Emergency sell: Positions down >2%")
            self.logger.info("=" * 60)
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to start agent: {e}", exc_info=True)
            self._state = AgentState.ERROR
            return False

    async def stop(self):
        """Stop the trading agent"""
        self.logger.info("Stopping Trading Agent...")

        self._state = AgentState.STOPPED

        # Cancel tasks - including position monitor
        for task in [self._main_task, self._signal_task, self._context_task, self._discovery_task, self._position_monitor_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close connections
        await self.streamer.stop()
        await self.alpaca_client.close()

        # Stop Ollama if we started it
        self._stop_ollama()

        self.logger.info("Trading Agent stopped completely")

    def pause(self):
        """Pause signal generation (keeps streaming)"""
        self._state = AgentState.PAUSED
        self.logger.info("Agent paused")

    def resume(self):
        """Resume signal generation"""
        self._state = AgentState.RUNNING
        self.logger.info("Agent resumed")

    def _handle_quote(self, quote: StreamQuote):
        """Handle incoming quote from stream"""
        self.quote_aggregator.add_quote(quote)

    async def _signal_loop(self):
        """Main signal generation loop"""
        self.logger.info("📡 Signal loop started")
        signal_count = 0

        while self._state in [AgentState.RUNNING, AgentState.PAUSED]:
            try:
                if self._state == AgentState.PAUSED:
                    self.logger.debug("Signal loop: Agent paused")
                    await asyncio.sleep(1)
                    continue

                # Check if market is open (cached to reduce API calls)
                is_open = await self._is_market_open()
                if not is_open:
                    # Log waiting message (only once per hour to avoid spam)
                    if not hasattr(self, '_last_market_wait_log') or \
                       (datetime.now() - self._last_market_wait_log).seconds > 3600:
                        self._last_market_wait_log = datetime.now()
                        self.logger.info("💤 Mercado cerrado - esperando apertura (9:30 AM EST / 11:30 AM GMT-3)...")
                    await asyncio.sleep(60)  # Check every minute when closed
                    continue

                # Generate signals for watchlist
                signal_count += 1
                self.logger.debug(f"Signal loop iteration #{signal_count} - Generating signals...")
                await self._generate_signals()

                # Log every 5 iterations (5 minutes at 60s interval)
                if signal_count % 5 == 0:
                    self.logger.info(f"📡 Signal loop: {signal_count} iterations completed")

                # Wait for next interval
                await asyncio.sleep(self.config.signal_update_interval)

            except asyncio.CancelledError:
                self.logger.info("Signal loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in signal loop: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _context_loop(self):
        """Market context update loop"""
        self.logger.info("Context loop started")

        while self._state in [AgentState.RUNNING, AgentState.PAUSED, AgentState.STARTING]:
            try:
                self._current_context = await self.market_context.get_context(force_refresh=True)
                await asyncio.sleep(self.config.market_context_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in context loop: {e}")
                await asyncio.sleep(60)

    async def _discovery_loop(self):
        """Stock discovery loop - finds new interesting stocks"""
        self.logger.info("Discovery loop started")

        while self._state in [AgentState.RUNNING, AgentState.PAUSED, AgentState.STARTING]:
            try:
                if self._state == AgentState.PAUSED:
                    await asyncio.sleep(60)
                    continue

                # Only discover during market hours (cached to reduce API calls)
                is_open = await self._is_market_open()
                if not is_open:
                    await asyncio.sleep(300)  # Check every 5 min when closed
                    continue

                # Run discovery scan
                discovered = await self.discovery.discover()

                if discovered:
                    self.logger.info(f"Discovery found {len(discovered)} stocks:")
                    for stock in discovered[:5]:  # Log top 5
                        self.logger.info(
                            f"  {stock.symbol}: {stock.reason} "
                            f"(score: {stock.score:.1f}, change: {stock.change_pct:+.1f}%)"
                        )

                    # Subscribe to new symbols if any
                    from alpaca.stream import StreamType
                    already_subscribed = self.streamer._subscribed_symbols.get(StreamType.QUOTES, set())
                    new_symbols = [
                        s.symbol for s in discovered
                        if s.symbol not in already_subscribed
                    ]
                    if new_symbols:
                        await self.streamer.subscribe(
                            new_symbols,
                            stream_types=[StreamType.QUOTES, StreamType.TRADES]
                        )
                        self.logger.info(f"Subscribed to {len(new_symbols)} new symbols from discovery")

                # Wait for next discovery interval
                await asyncio.sleep(self.config.discovery.scan_interval_minutes * 60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(300)

    async def _log_trade_outcome(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        pnl_dollars: float,
        pnl_percent: float,
        entry_price: Optional[float] = None,
        entry_time: Optional[datetime] = None,
    ):
        """
        Log a trade outcome for learning.

        This is CRITICAL for the self-reflection system to work.
        Called when any position is closed (stop-loss, take-profit, emergency, manual).
        """
        try:
            # Calculate hold duration
            if entry_time:
                hold_duration = int((datetime.now() - entry_time).total_seconds() / 60)
            else:
                hold_duration = 0

            # Find the original order_id from recent decisions
            recent = self.trade_logger.get_recent_decisions(symbol=symbol, limit=5)
            order_id = None
            for decision in reversed(recent):
                if decision.executed and decision.symbol == symbol:
                    order_id = decision.order_id
                    if not entry_price:
                        entry_price = decision.execution_price or decision.entry_price
                    break

            if order_id:
                self.trade_logger.log_outcome(
                    symbol=symbol,
                    order_id=order_id,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    pnl_dollars=pnl_dollars,
                    pnl_percent=pnl_percent,
                    hold_duration_minutes=hold_duration,
                )
            else:
                # Log anyway for debugging even without order_id match
                self.logger.info(
                    f"📊 Trade outcome (no order_id): {symbol} | "
                    f"PnL: {pnl_percent:+.2f}% (${pnl_dollars:+.2f}) | "
                    f"Reason: {exit_reason}"
                )

            # Also update risk manager with result
            is_day_trade = hold_duration < 60 * 6.5  # Less than market day
            self.risk_manager.record_trade_result(pnl_dollars, is_day_trade)

            # Record trade for Position Intelligence (Kelly Criterion)
            self.position_intelligence.record_trade(symbol, pnl_dollars, pnl_percent)

            # === PERIODIC REFLECTION: Record trade and check if reflection needed ===
            try:
                # Increment trade counter - reflection system reads from trade_logger
                should_reflect = self.periodic_reflection.record_trade()

                # Check if it's time to run reflection
                if should_reflect:
                    reflection_report = await self.periodic_reflection.run_reflection()
                    if reflection_report:
                        self.logger.info(
                            f"🔄 Periodic Reflection Complete:\n"
                            f"   Win Rate: {reflection_report.win_rate*100:.1f}% "
                            f"({reflection_report.winners}/{reflection_report.total_trades})\n"
                            f"   Avg Win: ${reflection_report.avg_win:.2f} | "
                            f"Avg Loss: ${reflection_report.avg_loss:.2f}\n"
                            f"   Adjustments: {reflection_report.adjustments}"
                        )
            except Exception as reflection_error:
                self.logger.debug(f"Reflection recording failed: {reflection_error}")

            # === LAYERED MEMORY: Store trade outcome for pattern learning ===
            try:
                memory_type = 'trade_win' if pnl_dollars > 0 else 'trade_loss'
                self.layered_memory.add_memory(
                    memory_type=memory_type,
                    content={
                        'exit_reason': exit_reason,
                        'pnl_dollars': pnl_dollars,
                        'pnl_percent': pnl_percent,
                        'hold_duration': hold_duration,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'is_day_trade': is_day_trade,
                    },
                    symbol=symbol,
                    importance=min(1.0, abs(pnl_percent) / 5),  # Higher importance for bigger moves
                    tags=[exit_reason, 'day_trade' if is_day_trade else 'swing'],
                )
            except Exception as memory_error:
                self.logger.debug(f"Layered memory storage failed: {memory_error}")

        except Exception as e:
            self.logger.error(f"Error logging trade outcome: {e}")

    async def _position_monitor_loop(self):
        """
        Position monitoring loop - CRITICAL FOR LOSS PREVENTION!

        This loop:
        1. Checks all positions for stop-loss/take-profit triggers
        2. Executes sells when price hits stop-loss or take-profit
        3. EMERGENCY SELLS positions down >2% even without stop-loss
        4. Checks daily loss limit and halts trading if exceeded
        5. Logs extensively for debugging
        """
        self.logger.info("🛡️ Position monitor loop started")
        heartbeat_counter = 0
        last_position_log = datetime.now() - timedelta(minutes=5)  # Log positions immediately

        while self._state in [AgentState.RUNNING, AgentState.PAUSED, AgentState.STARTING]:
            try:
                heartbeat_counter += 1

                # HEARTBEAT: Log every 2 minutes that monitor is alive
                if heartbeat_counter % 4 == 0:  # Every 4 cycles (30s * 4 = 2min)
                    tracked = self.executor.get_tracked_positions()
                    self.logger.info(f"💓 Position monitor alive | Tracking {len(tracked)} positions")

                if self._state == AgentState.PAUSED:
                    self.logger.debug("Position monitor: Agent paused, waiting...")
                    await asyncio.sleep(30)
                    continue

                # Check market status but DON'T skip monitoring
                is_open = await self._is_market_open()
                if not is_open:
                    # Log every 5 minutes when market is closed
                    if heartbeat_counter % 10 == 0:
                        self.logger.info("💤 Market closed - position monitor idle (will resume when market opens)")
                    await asyncio.sleep(30)
                    continue

                # === MARKET IS OPEN - ACTIVE MONITORING ===

                # Log all positions every 5 minutes for debugging
                now = datetime.now()
                if (now - last_position_log).total_seconds() > 300:
                    await self._log_all_positions()
                    last_position_log = now

                # Check daily loss limit
                loss_exceeded, daily_pnl_pct = await self.executor.check_daily_loss_limit()
                self.logger.debug(f"Daily P&L: {daily_pnl_pct*100:+.2f}%")

                if loss_exceeded and not self._trading_halted:
                    self._trading_halted = True
                    self._halt_reason = f"Daily loss limit exceeded: {daily_pnl_pct*100:.2f}%"
                    self.logger.error(f"🚨 TRADING HALTED: {self._halt_reason}")

                    # Close all positions to prevent further losses
                    self.logger.warning("🔥 EMERGENCY: Closing ALL positions due to daily loss limit...")
                    results = await self.executor.close_all_positions()
                    for r in results:
                        if r.is_success:
                            self.logger.info(f"  ✅ Closed: {r.order.symbol}")
                        else:
                            self.logger.error(f"  ❌ Failed to close: {r.error_message}")
                    continue

                # Check stop-loss and take-profit triggers
                self.logger.debug("Checking stop-loss triggers...")
                triggers = await self.executor.check_stop_losses()

                if triggers:
                    self.logger.warning(f"🚨 {len(triggers)} STOP-LOSS/TAKE-PROFIT TRIGGERS!")

                for trigger in triggers:
                    symbol = trigger['symbol']
                    action = trigger['action']
                    reason = trigger['reason']

                    self.logger.warning(f"🔔 {action} triggered for {symbol}: {reason}")

                    # Execute the stop-loss or take-profit
                    result = await self.executor.execute_stop_loss(symbol, reason)

                    if result.is_success:
                        self.logger.info(f"✅ {action} executed for {symbol}")

                        # Record the trade
                        pnl = trigger.get('profit', trigger.get('loss', 0))
                        pnl_pct = trigger.get('pnl_pct', 0)
                        self.memory.record_trade(TradeRecord(
                            id=str(uuid.uuid4()),
                            symbol=symbol,
                            action='SELL',
                            entry_price=trigger.get('entry_price', 0),
                            exit_price=trigger['current_price'],
                            quantity=trigger['qty'],
                            entry_time=datetime.now(),
                            exit_time=datetime.now(),
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            reasoning=reason,
                            confidence=1.0,
                        ))

                        # LOG OUTCOME FOR LEARNING
                        await self._log_trade_outcome(
                            symbol=symbol,
                            exit_price=trigger['current_price'],
                            exit_reason=reason,
                            pnl_dollars=pnl,
                            pnl_percent=pnl_pct * 100 if abs(pnl_pct) < 1 else pnl_pct,
                            entry_price=trigger.get('entry_price'),
                        )
                    else:
                        self.logger.error(f"❌ Failed to execute {action} for {symbol}: {result.error_message}")

                # === PARTIAL PROFIT CHECK: Take profits at targets ===
                await self._check_partial_profits()

                # EMERGENCY CHECK: Sell any position down >2% that doesn't have a stop-loss
                await self._emergency_sell_losers()

                # Also check positions that might be in trouble but not at stop-loss yet
                await self._check_position_health()

                # Check every 30 seconds
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                self.logger.info("Position monitor loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in position monitor loop: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _log_all_positions(self):
        """Log all current positions with their status"""
        try:
            positions = await self.alpaca_client.get_positions()
            tracked = self.executor.get_tracked_positions()

            if not positions:
                self.logger.info("📭 No open positions")
                return

            self.logger.info(f"📊 POSITION STATUS ({len(positions)} positions):")
            total_pnl = 0
            for p in positions:
                pnl_pct = p.unrealized_plpc * 100
                total_pnl += p.unrealized_pl
                has_stop = "✅" if p.symbol in tracked else "❌"
                stop_price = tracked.get(p.symbol, {}).get('stop_loss', 0)

                self.logger.info(
                    f"  {p.symbol}: ${p.current_price:.2f} | "
                    f"P&L: ${p.unrealized_pl:+.2f} ({pnl_pct:+.1f}%) | "
                    f"Stop: {has_stop} ${stop_price:.2f}"
                )

            self.logger.info(f"  📈 TOTAL P&L: ${total_pnl:+.2f}")

        except Exception as e:
            self.logger.error(f"Error logging positions: {e}")

    async def _emergency_sell_losers(self):
        """
        EMERGENCY: Sell any position down >2% that we're not tracking.
        This is the LAST LINE OF DEFENSE against runaway losses.
        """
        try:
            positions = await self.alpaca_client.get_positions()
            tracked = self.executor.get_tracked_positions()

            for p in positions:
                pnl_pct = p.unrealized_plpc * 100  # Convert to percentage
                reason = None

                # If position is down more than 2% and NOT being tracked with a stop-loss
                if pnl_pct < -2.0 and p.symbol not in tracked:
                    reason = f"EMERGENCY: Down {pnl_pct:.1f}% with no stop-loss protection"
                    self.logger.error(f"🚨 EMERGENCY SELL: {p.symbol} down {pnl_pct:.1f}% with NO STOP-LOSS!")

                # Also emergency sell if down >3% even WITH a stop (stop might be too low)
                elif pnl_pct < -3.0:
                    reason = f"EMERGENCY: Down {pnl_pct:.1f}% exceeds 3% max loss"
                    self.logger.error(f"🚨 EMERGENCY SELL: {p.symbol} down {pnl_pct:.1f}% - exceeds max loss!")

                if reason:
                    result = await self.executor.close_position(p.symbol, reason)

                    if result.is_success:
                        self.logger.warning(f"🔥 Emergency sold {p.symbol} at ${p.current_price:.2f}")

                        # LOG OUTCOME FOR LEARNING
                        await self._log_trade_outcome(
                            symbol=p.symbol,
                            exit_price=p.current_price,
                            exit_reason=reason,
                            pnl_dollars=p.unrealized_pl,
                            pnl_percent=pnl_pct,
                            entry_price=p.avg_entry_price,
                        )
                    else:
                        self.logger.error(f"❌ FAILED to emergency sell {p.symbol}: {result.error_message}")

        except Exception as e:
            self.logger.error(f"Error in emergency sell check: {e}", exc_info=True)

    async def _check_partial_profits(self):
        """
        Check positions for partial profit taking at targets.

        This is KEY to locking in gains:
        - Target 1 (+1.5%): Sell 30%, stop to breakeven
        - Target 2 (+2.5%): Sell 30%, trail stop to +1%
        - Target 3 (+4%): Sell rest
        """
        try:
            positions = await self.alpaca_client.get_positions()

            for p in positions:
                symbol = p.symbol
                current_price = p.current_price
                entry_price = p.avg_entry_price

                # Check if we hit any profit targets
                action = self.profit_manager.check_targets(symbol, current_price)

                if action:
                    if action['action'] == 'PARTIAL_SELL':
                        # Execute partial sell
                        self.logger.info(
                            f"🎯 TAKING PARTIAL PROFIT: {symbol} - {action['reason']}"
                        )

                        request = OrderRequest(
                            symbol=symbol,
                            side=OrderSide.SELL,
                            quantity=action['qty'],
                            order_type=OrderType.MARKET,
                            reason=action['reason'],
                            current_price=current_price,
                        )

                        result = await self.executor.execute(request)

                        if result.is_success:
                            self.logger.info(
                                f"✅ Partial profit taken: Sold {action['qty']:.2f} {symbol} @ ${current_price:.2f}"
                            )

                            # Calculate partial PnL
                            partial_pnl = (current_price - entry_price) * action['qty']
                            partial_pnl_pct = ((current_price / entry_price) - 1) * 100

                            # LOG PARTIAL OUTCOME FOR LEARNING
                            await self._log_trade_outcome(
                                symbol=symbol,
                                exit_price=current_price,
                                exit_reason=action['reason'],
                                pnl_dollars=partial_pnl,
                                pnl_percent=partial_pnl_pct,
                                entry_price=entry_price,
                            )

                            # Update stop-loss to new level
                            if action.get('new_stop'):
                                self.executor._tracked_stops[symbol]['stop_loss'] = action['new_stop']
                                self.logger.info(f"📍 Stop moved to ${action['new_stop']:.2f}")
                        else:
                            self.logger.error(f"❌ Failed partial sell: {result.error_message}")

                    elif action['action'] == 'CLOSE_POSITION':
                        # Close remaining position
                        self.logger.info(
                            f"🎯 CLOSING POSITION AT TARGET 3: {symbol} - {action['reason']}"
                        )

                        result = await self.executor.close_position(symbol, action['reason'])

                        if result.is_success:
                            self.logger.info(f"✅ Position closed: {symbol} at target 3")

                            # Calculate final PnL
                            final_pnl = p.unrealized_pl
                            final_pnl_pct = p.unrealized_plpc * 100

                            # LOG FINAL OUTCOME FOR LEARNING
                            await self._log_trade_outcome(
                                symbol=symbol,
                                exit_price=current_price,
                                exit_reason=action['reason'],
                                pnl_dollars=final_pnl,
                                pnl_percent=final_pnl_pct,
                                entry_price=entry_price,
                            )

                            self.profit_manager.remove_position(symbol)
                        else:
                            self.logger.error(f"❌ Failed to close: {result.error_message}")

                # Update trailing stop for profitable positions
                self.profit_manager.update_trailing_stop(symbol, current_price)

        except Exception as e:
            self.logger.error(f"Error checking partial profits: {e}", exc_info=True)

    async def _check_position_health(self):
        """
        Check positions and use AI to generate proactive SELL alerts.
        This is THE KEY to not holding losers too long.
        """
        try:
            positions = await self.alpaca_client.get_positions()

            for position in positions:
                symbol = position.symbol
                pnl_pct = position.unrealized_plpc * 100
                current_price = position.current_price

                # Get tracked data
                tracked = self.executor.get_tracked_positions().get(symbol, {})
                entry_price = tracked.get('entry_price', position.avg_entry_price)
                highest_price = tracked.get('highest_price', current_price)

                # Calculate key metrics
                gain_from_entry = ((current_price / entry_price) - 1) * 100 if entry_price else 0
                drop_from_high = ((current_price / highest_price) - 1) * 100 if highest_price else 0

                # Conditions that should trigger AI SELL analysis
                should_analyze_exit = (
                    pnl_pct < -1.0 or           # Position is losing > 1%
                    drop_from_high < -2.0 or    # Dropped > 2% from high (giving back gains)
                    gain_from_entry > 3.0       # In profit > 3% (consider taking profits)
                )

                if should_analyze_exit:
                    self.logger.info(f"🤖 Analyzing {symbol} for potential exit (P&L: {pnl_pct:+.1f}%)")
                    
                    # Get market data for analysis
                    quote = await self.alpaca_client.get_quote(symbol)
                    technical_data = {
                        'current_price': current_price,
                        'entry_price': entry_price,
                        'highest_price': highest_price,
                        'pnl_percent': pnl_pct,
                        'gain_from_entry': gain_from_entry,
                        'drop_from_high': drop_from_high,
                        'position_qty': position.qty,
                        'position_value': position.market_value,
                    }

                    # Get news sentiment
                    news_sentiment = None
                    try:
                        news = self.news_collector.get_stock_news(symbol, hours_back=6)
                        if news:
                            analysis = self.sentiment_analyzer.analyze_news_batch(news)
                            news_sentiment = {
                                'sentiment': analysis['overall_sentiment'],
                                'score': analysis['overall_score'],
                                'article_count': analysis['article_count'],
                            }
                    except Exception:
                        pass

                    # Run AI analysis for exit decision
                    exit_analysis = await self._analyze_exit_opportunity(
                        symbol=symbol,
                        technical_data=technical_data,
                        news_sentiment=news_sentiment,
                        market_context=self._current_context,
                    )

                    if exit_analysis and exit_analysis.get('should_exit', False):
                        # AUTONOMOUS MODE: Execute SELL directly
                        self.logger.warning(
                            f"🤖 AUTO-SELLING {symbol}: {exit_analysis.get('reason', 'No reason provided')}"
                        )

                        # Create trading opportunity for exit
                        opportunity = TradingOpportunity(
                            symbol=symbol,
                            action='SELL',
                            current_price=current_price,
                            target_price=current_price,  # Sell at market
                            stop_loss=current_price * 0.99,  # 1% below current
                            position_size=position.market_value,
                            shares=float(position.qty),
                            confidence=exit_analysis.get('confidence', 0.7),
                            risk_reward_ratio=1.0,  # Exit trade
                            reasoning=exit_analysis.get('reasoning', ''),
                            news_sentiment=news_sentiment.get('sentiment') if news_sentiment else None,
                        )

                        # AUTO-EXECUTE the sell
                        result = await self._auto_execute_opportunity(opportunity)
                        if result and result.is_success:
                            self._trades_executed += 1
                            # Remove from tracking since we sold
                            if symbol in self.executor._tracked_stops:
                                del self.executor._tracked_stops[symbol]
                            self.logger.info(
                                f"✅ SOLD {symbol} @ ${result.order.filled_avg_price:.2f} "
                                f"(AI decision, P&L: {pnl_pct:+.1f}%)"
                            )
                        elif result:
                            self.logger.error(f"❌ Failed to sell {symbol}: {result.error_message}")

        except Exception as e:
            self.logger.error(f"Error checking position health: {e}")

    async def _analyze_exit_opportunity(
        self,
        symbol: str,
        technical_data: Dict[str, Any],
        news_sentiment: Optional[Dict],
        market_context: Optional[MarketContextData],
    ) -> Optional[Dict]:
        """
        Use AI to analyze if we should exit a position.
        This is the PROACTIVE SELL analysis.
        """
        try:
            # Build exit analysis prompt
            prompt = f"""## EXIT ANALYSIS REQUEST: {symbol}

### Current Position Status
- Entry Price: ${technical_data.get('entry_price', 0):.2f}
- Current Price: ${technical_data.get('current_price', 0):.2f}
- P&L: {technical_data.get('pnl_percent', 0):+.1f}%
- Gain from Entry: {technical_data.get('gain_from_entry', 0):+.1f}%
- Drop from High: {technical_data.get('drop_from_high', 0):.1f}%
- Position Value: ${technical_data.get('position_value', 0):.2f}
"""

            if news_sentiment:
                prompt += f"""
### News Sentiment
- Overall: {news_sentiment.get('sentiment', 'neutral')}
- Score: {news_sentiment.get('score', 0):.2f}
- Articles: {news_sentiment.get('article_count', 0)}
"""

            if market_context:
                prompt += f"""
### Market Context
- SPY Change: {market_context.spy.change_pct:+.1f}%
- VIX Level: {market_context.vix.value:.1f}
- Market Regime: {market_context.regime.value}
"""

            prompt += """
### Your Task
Analyze whether to EXIT this position now. Consider:
1. Is the trend reversing?
2. Is news sentiment turning negative?
3. Has the original trade thesis been invalidated?
4. Are we giving back too much profit?
5. Is the broader market turning against us?

Respond ONLY in JSON:
{
  "should_exit": true/false,
  "confidence": 0.0-1.0,
  "reason": "Brief reason for exit/hold recommendation",
  "reasoning": "Detailed analysis",
  "urgency": "immediate|soon|no_rush"
}
"""

            system_prompt = """You are an expert day trader managing existing positions.
Your job is to decide when to EXIT positions to protect profits or cut losses.
Be decisive - don't hold losers hoping they'll recover.
If a position is giving back profits, consider exiting to lock in gains.
If news turns negative or market conditions change, exit quickly."""

            # Call LLM for exit analysis
            response = await self.reasoning._call_llm(system_prompt, prompt)
            
            if not response:
                return None

            # Parse response
            import json
            try:
                # Find JSON in response
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(response[json_start:json_end])
                    return result
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse exit analysis for {symbol}")
                return None

        except Exception as e:
            self.logger.error(f"Error in exit analysis for {symbol}: {e}")
            return None

    def is_trading_halted(self) -> Tuple[bool, str]:
        """Check if trading is halted"""
        return self._trading_halted, self._halt_reason

    def resume_trading(self):
        """Resume trading after halt (manual override)"""
        if self._trading_halted:
            self.logger.warning("Trading resumed by manual override")
            self._trading_halted = False
            self._halt_reason = ""

    def get_dynamic_watchlist(self) -> List[str]:
        """Get combined watchlist (base + discovered)"""
        return self.discovery.get_dynamic_watchlist()

    def get_discovery_summary(self) -> Dict:
        """Get summary of discovered stocks"""
        return self.discovery.get_discovery_summary()

    async def _generate_signals(self):
        """
        Generate trading signals using MOMENTUM-FIRST approach.

        Strategy (MODERADO):
        1. Buscar setups de alta calidad (score >= 6)
        2. Si no hay, buscar setups decentes (score >= 4) como fallback
        3. Ejecutar las mejores oportunidades
        """
        self.logger.debug("Generating signals with momentum scanner...")

        # === POSITION INTELLIGENCE: Check if trading allowed ===
        session = self.position_intelligence.get_current_session()
        session_config = self.position_intelligence.get_session_config(session)

        if session_config.avoid_new_entries:
            self.logger.debug(f"📵 {session.value}: Avoiding new entries")
            return

        dd_mult, dd_reason = self.position_intelligence.get_drawdown_multiplier()
        if dd_mult == 0:
            self.logger.warning(f"🚨 {dd_reason}")
            return

        # Use dynamic watchlist (base + discovered stocks)
        watchlist = self.get_dynamic_watchlist()

        # === MOMENTUM SCAN: Find setups ===
        all_setups = await self.momentum_scanner.scan(watchlist, force=True)

        # Separate high-quality (score >= 6) from decent (score >= 4)
        high_quality_setups = [s for s in all_setups if s.score >= 6.0]
        decent_setups = [s for s in all_setups if 4.0 <= s.score < 6.0]

        # Use high-quality if available, otherwise fallback to decent
        if high_quality_setups:
            momentum_setups = high_quality_setups
            self.logger.info(f"🚀 Found {len(momentum_setups)} HIGH-QUALITY setups (score ≥6)")
        elif decent_setups:
            momentum_setups = decent_setups
            self.logger.info(f"📊 No premium setups - using {len(decent_setups)} DECENT setups (score 4-6)")
        else:
            momentum_setups = []
            self.logger.info("📭 No tradeable setups found (all scores < 4)")

        if momentum_setups:
            self.logger.info(f"🚀 Found {len(momentum_setups)} momentum setups")

            # Process top setups (limit to avoid overtrading)
            for setup in momentum_setups[:3]:  # Max 3 per scan cycle
                try:
                    # Convert momentum setup to trading opportunity
                    opportunity = await self._momentum_setup_to_opportunity(setup)

                    if opportunity:
                        self._signals_generated += 1
                        self._last_signal_time = datetime.now()

                        # AUTONOMOUS MODE: Execute trade directly
                        self.logger.info(
                            f"🎯 MOMENTUM TRADE: {setup.setup_type.value} {opportunity.symbol} | "
                            f"Score: {setup.score:.1f} | Target: +{setup.potential_gain_pct:.1f}%"
                        )

                        result = await self._auto_execute_opportunity(opportunity)

                        if result and result.is_success:
                            self._trades_executed += 1
                            self._last_trade_time = datetime.now()

                            # Register with profit manager for partial exits
                            self.profit_manager.register_position(
                                symbol=setup.symbol,
                                qty=result.order.filled_qty,
                                entry_price=result.order.filled_avg_price,
                                targets=(setup.target_1, setup.target_2, setup.target_3)
                            )

                            self.logger.info(
                                f"✅ Momentum trade executed: {opportunity.action} {result.order.filled_qty:.4f} "
                                f"{opportunity.symbol} @ ${result.order.filled_avg_price:.2f} | "
                                f"Targets: ${setup.target_1:.2f} → ${setup.target_2:.2f} → ${setup.target_3:.2f}"
                            )
                        elif result:
                            self.logger.warning(f"⚠️ Trade failed: {result.error_message}")

                except Exception as e:
                    self.logger.error(f"Error processing momentum setup {setup.symbol}: {e}")

        # NOTE: Fallback analysis removed - momentum-only strategy
        # The old fallback (analyze_opportunity) didn't pass through:
        # - RiskManager validation
        # - News sentiment (Alpaca)
        # - Trade intelligence (reflection/debate)
        # - Analyst ratings
        # All trades now go through _momentum_setup_to_opportunity which has full protection

    async def _momentum_setup_to_opportunity(self, setup: MomentumSetup) -> Optional[TradingOpportunity]:
        """
        Convert a momentum setup to a trading opportunity.

        Enhanced with:
        - Analyst ratings (Yahoo Finance)
        - News sentiment (Alpaca News API)
        - Self-reflection (learn from past)
        - Bull/Bear debate
        - Risk manager validation
        """
        try:
            # Skip if we already have a position
            try:
                position = await self.alpaca_client.get_position(setup.symbol)
                if position:
                    account = await self.alpaca_client.get_account()
                    position_pct = position.market_value / account.equity if account.equity > 0 else 0
                    if position_pct >= 0.15:
                        self.logger.debug(f"{setup.symbol}: Already have {position_pct*100:.1f}% position")
                        return None
            except Exception:
                pass  # No position

            # === PARALLEL DATA FETCHING (optimized) ===
            analyst_task = self.analyst_ratings.get_rating(setup.symbol)
            news_task = self.news_sentiment.get_sentiment(setup.symbol, hours_back=24)
            atr_task = self.atr_manager.calculate_dynamic_levels(
                symbol=setup.symbol,
                entry_price=setup.entry_price,
                direction='LONG'
            )

            analyst_rating, news_sentiment, atr_levels = await asyncio.gather(
                analyst_task, news_task, atr_task,
                return_exceptions=True
            )

            # Handle exceptions gracefully
            if isinstance(analyst_rating, Exception):
                self.logger.debug(f"Analyst rating failed: {analyst_rating}")
                analyst_rating = None
            if isinstance(news_sentiment, Exception):
                self.logger.debug(f"News sentiment failed: {news_sentiment}")
                news_sentiment = None
            if isinstance(atr_levels, Exception):
                self.logger.debug(f"ATR calculation failed: {atr_levels}")
                atr_levels = None

            # === APPLY ATR DYNAMIC STOPS ===
            # Override fixed percentage stops with volatility-based ATR stops
            if atr_levels:
                old_stop = setup.stop_loss
                setup.stop_loss = atr_levels.stop_loss
                setup.target_1 = atr_levels.target_1
                setup.target_2 = atr_levels.target_2
                setup.target_3 = atr_levels.target_3
                self.logger.info(
                    f"📊 {setup.symbol} ATR Stops: "
                    f"Regime={atr_levels.multiplier_used:.1f}x | "
                    f"Stop ${old_stop:.2f}→${atr_levels.stop_loss:.2f} | "
                    f"Targets ${atr_levels.target_1:.2f}/${atr_levels.target_2:.2f}/${atr_levels.target_3:.2f}"
                )

            # === QUERY LAYERED MEMORY for past patterns ===
            memory_context = {}
            try:
                memory_query = await self.layered_memory.query(setup.symbol)
                if memory_query:
                    memory_context = {
                        'recent_win_rate': memory_query.shortterm_win_rate or 0.5,
                        'patterns': memory_query.shortterm_patterns,
                        'score_adjustment': memory_query.memory_score_adjustment,
                        'confidence_factor': memory_query.memory_confidence_factor,
                    }
                    # Apply memory-based score adjustment
                    if memory_query.memory_score_adjustment != 0:
                        setup.score += memory_query.memory_score_adjustment
                        win_rate_display = (memory_query.shortterm_win_rate or 0.5) * 100
                        self.logger.debug(
                            f"🧠 {setup.symbol} Memory: Win rate {win_rate_display:.0f}% | "
                            f"Score adj: {memory_query.memory_score_adjustment:+.1f}"
                        )
            except Exception as mem_error:
                self.logger.debug(f"Memory query failed: {mem_error}")

            # === APPLY REFLECTION ADJUSTMENTS to confidence ===
            base_confidence = setup.score / 10.0
            adjusted_confidence = self.periodic_reflection.apply_adjustments_to_confidence(base_confidence)
            if adjusted_confidence != base_confidence:
                self.logger.info(
                    f"🔄 {setup.symbol} Confidence adjusted: "
                    f"{base_confidence*100:.0f}% → {adjusted_confidence*100:.0f}%"
                )

            # === PROCESS ANALYST RATINGS ===
            analyst_data = {}
            if analyst_rating and analyst_rating.total_analysts > 0:
                analyst_data = analyst_rating.to_dict()
                self.logger.info(
                    f"📊 {setup.symbol} Analyst: {analyst_rating.signal} "
                    f"({analyst_rating.bullish_percent:.0f}% bullish)"
                )
                # Adjust score
                setup.score += analyst_rating.score_adjustment

            # === PROCESS NEWS SENTIMENT ===
            news_data = {}
            if news_sentiment and news_sentiment.article_count > 0:
                news_data = news_sentiment.to_dict()
                self.logger.info(
                    f"📰 {setup.symbol} News: {news_sentiment.overall_sentiment} "
                    f"(score: {news_sentiment.overall_score:+.2f}, {news_sentiment.article_count} articles)"
                )
                # Adjust score
                setup.score += news_sentiment.score_adjustment

            # === TRADE INTELLIGENCE (reflection + debate) ===
            technical_data = {
                'change_pct': setup.change_pct,
                'volume_ratio': setup.volume_ratio,
                'setup_type': setup.setup_type.value,
            }

            intelligence = await self.trade_intelligence.full_analysis(
                symbol=setup.symbol,
                action='BUY',
                entry_price=setup.entry_price,
                setup_type=setup.setup_type.value,
                technical_data=technical_data,
                confidence=setup.score / 10.0,
                analyst_data=analyst_data,
                news_sentiment=news_data,
                market_context={'regime': self._current_context.regime.value if self._current_context else 'unknown'},
            )

            # Log intelligence results
            if intelligence.get('reflection'):
                ref = intelligence['reflection']
                self.logger.info(
                    f"🔍 {setup.symbol} Reflection: {ref['recommendation']} "
                    f"({ref['confidence']*100:.0f}% confidence)"
                )

            if intelligence.get('debate'):
                deb = intelligence['debate']
                self.logger.info(
                    f"⚔️ {setup.symbol} Debate: Bull {deb['bull_score']:.1f} vs Bear {deb['bear_score']:.1f} "
                    f"→ {deb['winner']} ({deb['consensus']})"
                )

            # Apply intelligence score adjustment
            setup.score += intelligence.get('score_adjustment', 0)

            # Check if intelligence recommends avoiding
            if intelligence.get('combined_recommendation', '').startswith('AVOID'):
                self.logger.warning(f"⛔ {setup.symbol}: Intelligence recommends AVOID - skipping")
                return None

            # === GET CURRENT POSITIONS (needed for both Position Intelligence and Risk Manager) ===
            account = await self.alpaca_client.get_account()
            positions = await self.alpaca_client.get_positions()
            positions_dict = [
                {'symbol': p.symbol, 'market_value': p.market_value}
                for p in positions
            ] if positions else []

            # Update equity for drawdown tracking
            self.position_intelligence.update_equity(account.equity)

            # === CALCULATE POSITION SIZE with Position Intelligence ===
            pos_rec = self.position_intelligence.calculate_position(
                symbol=setup.symbol,
                entry_price=setup.entry_price,
                confidence=adjusted_confidence,
                account_equity=account.equity,
                base_position_pct=0.20,
                positions=positions_dict,
            )

            shares = pos_rec.final_shares

            # Log position intelligence reasoning
            if pos_rec.adjusted_size_pct != 0.20:
                self.logger.info(
                    f"📐 {setup.symbol} Position: {pos_rec.adjusted_size_pct*100:.1f}% "
                    f"(${pos_rec.final_size_dollars:.0f}, {shares:.2f} shares)"
                )
                for r in pos_rec.reasoning[:3]:  # Show top 3 adjustments
                    self.logger.debug(f"   └─ {r}")

            # Check for warnings
            for w in pos_rec.warnings:
                self.logger.warning(w)
                if "HALTED" in w or "limit reached" in w:
                    return None

            # === RISK MANAGER CHECK ===

            risk_check = await self.risk_manager.validate_trade(
                symbol=setup.symbol,
                action='BUY',
                shares=shares,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                confidence=setup.score / 10.0,
                account_equity=account.equity,
                buying_power=account.buying_power,
                current_positions=positions_dict,
                analyst_rating=analyst_data,
            )

            if not risk_check.approved:
                self.logger.warning(
                    f"🛡️ {setup.symbol}: Risk Manager REJECTED - "
                    f"{', '.join(v.value for v in risk_check.violations)}"
                )
                # Check if we can use adjusted size
                if 'suggested_shares' in risk_check.adjustments:
                    shares = risk_check.adjustments['suggested_shares']
                    self.logger.info(f"  └─ Using adjusted size: {shares:.2f} shares")
                else:
                    return None

            # === BUILD REASONING ===
            reasoning_parts = [f"MOMENTUM {setup.setup_type.value}: {setup.reasoning}"]

            if analyst_data:
                reasoning_parts.append(
                    f"Analyst: {analyst_data.get('signal', 'N/A')} "
                    f"({analyst_data.get('bullish_percent', 0):.0f}% bullish)"
                )

            if news_data:
                reasoning_parts.append(
                    f"News: {news_data.get('overall_sentiment', 'N/A')} "
                    f"({news_data.get('overall_score', 0):+.2f})"
                )

            if intelligence.get('debate'):
                reasoning_parts.append(f"Debate: {intelligence['debate']['consensus']}")

            # === STORE TRADE OPPORTUNITY IN LAYERED MEMORY ===
            try:
                self.layered_memory.record_trade(
                    symbol=setup.symbol,
                    action='BUY',
                    entry_price=setup.entry_price,
                    outcome=None,  # Will be updated when trade closes
                    setup_type=setup.setup_type.value,
                    technical_data={
                        'score': setup.score,
                        'adjusted_confidence': adjusted_confidence,
                        'stop_loss': setup.stop_loss,
                        'targets': [setup.target_1, setup.target_2, setup.target_3],
                        'analyst_signal': analyst_data.get('signal'),
                        'news_sentiment': news_data.get('overall_sentiment'),
                    },
                    market_regime=self._current_context.regime.value if self._current_context else 'unknown',
                )
            except Exception:
                pass  # Non-critical, continue

            return TradingOpportunity(
                symbol=setup.symbol,
                action='BUY',
                current_price=setup.current_price,
                target_price=setup.target_1,
                stop_loss=setup.stop_loss,
                confidence=adjusted_confidence,  # Use reflection-adjusted confidence
                reasoning=" | ".join(reasoning_parts),
                shares=shares,
                position_size_pct=0.20,
                technical_signals={
                    'change_pct': setup.change_pct,
                    'volume_ratio': setup.volume_ratio,
                    'setup_type': setup.setup_type.value,
                    'score': setup.score,
                    'adjusted_confidence': adjusted_confidence,
                    'analyst_signal': analyst_data.get('signal', 'N/A'),
                    'news_sentiment': news_data.get('overall_sentiment', 'N/A'),
                    'debate_winner': intelligence.get('debate', {}).get('winner', 'N/A'),
                    'memory_win_rate': memory_context.get('recent_win_rate', 'N/A'),
                    'atr_regime': atr_levels.multiplier_used if atr_levels else 'N/A',
                },
                market_context=self._current_context.regime.value if self._current_context else 'unknown',
            )

        except Exception as e:
            self.logger.error(f"Error converting momentum setup: {e}")
            return None

    async def analyze_opportunity(self, symbol: str) -> Optional[TradingOpportunity]:
        """Analyze a symbol for trading opportunity"""

        # Skip if we already have a large position in this symbol (saves Ollama calls)
        try:
            position = await self.alpaca_client.get_position(symbol)
            if position:
                account = await self.alpaca_client.get_account()
                position_pct = position.market_value / account.equity if account.equity > 0 else 0
                # If position is already >= 15% of portfolio, don't try to buy more
                if position_pct >= 0.15:
                    return None  # Silent skip - we already own enough of this stock
        except Exception:
            pass  # No position, continue with analysis

        # Get current quote
        quote = self.quote_aggregator.get_last_quote(symbol)
        if not quote:
            return None

        # Get technical data (from existing signal generator or Alpaca)
        technical_data = await self._get_technical_data(symbol, quote)

        # Get market context
        context = self._current_context
        context_dict = context.to_dict() if context else None

        # Get memory context
        memory_context = self.memory.generate_reflection_prompt(symbol)

        # Find similar historical setups
        similar_setups = self.memory.find_similar_setups(
            symbol=symbol,
            technical_signals=technical_data,
            market_regime=context.regime.value if context else 'neutral',
        )

        win_rate = None
        if similar_setups:
            # Use average win rate of similar setups
            win_rate = sum(s.historical_win_rate for s in similar_setups) / len(similar_setups)

        # Fetch and analyze news sentiment (now active with Ollama - free!)
        news_sentiment = None
        try:
            news_articles = self.news_collector.get_stock_news(symbol, hours_back=24)
            if news_articles:
                news_analysis = self.sentiment_analyzer.analyze_news_batch(news_articles)
                news_sentiment = {
                    'sentiment': news_analysis['overall_sentiment'],
                    'score': news_analysis['overall_score'],
                    'confidence': news_analysis['confidence'],
                    'article_count': news_analysis['article_count'],
                    'positive_ratio': news_analysis['sentiment_distribution']['positive_ratio'],
                    'negative_ratio': news_analysis['sentiment_distribution']['negative_ratio'],
                    'high_impact_count': news_analysis['high_impact_count'],
                }
                self.logger.debug(f"📰 {symbol} news: {news_sentiment['sentiment']} ({news_sentiment['article_count']} articles)")
        except Exception as e:
            self.logger.warning(f"Failed to fetch news for {symbol}: {e}")

        # Run AI analysis (cost-optimized with caching)
        market_open = context.is_market_open if context else True
        analysis = await self.reasoning.analyze_setup(
            symbol=symbol,
            technical_data=technical_data,
            news_sentiment=news_sentiment,
            market_context=context_dict,
            memory_context=memory_context,
            market_open=market_open,
        )

        # Check if actionable
        if analysis.recommendation == 'HOLD':
            return None

        if analysis.confidence < self.config.risk.min_confidence_buy:
            return None

        # Get portfolio state for decision
        portfolio = await self.executor.get_position_summary()

        # Make final decision
        decision = await self.reasoning.make_decision(
            analyses=[analysis],
            portfolio_state=portfolio,
            risk_constraints={
                'max_position_pct': self.config.risk.max_position_pct,
                'max_daily_loss_pct': self.config.risk.max_daily_loss_pct,
                'max_positions': self.config.risk.max_positions,
                'min_risk_reward': self.config.risk.min_risk_reward,
                'min_confidence': self.config.risk.min_confidence_buy,
            },
            market_context=context_dict,
        )

        if not decision.should_trade:
            self.logger.info(f"📊 {symbol}: PASS - {decision.action} @ {decision.confidence:.0%} conf")
            return None

        self.logger.info(f"📈 {symbol}: SIGNAL - {decision.action} @ {decision.confidence:.0%} conf")

        # Calculate position size
        current_price = quote.mid_price
        account = await self.alpaca_client.get_account()

        # Apply regime multiplier
        regime_multiplier = self.market_context.get_position_size_multiplier(
            context.regime if context else MarketRegime.NEUTRAL
        )

        position_size = min(
            account.buying_power * decision.position_size_pct * regime_multiplier,
            account.equity * self.config.risk.max_position_pct,
        )

        # Create opportunity
        return TradingOpportunity(
            symbol=symbol,
            action=decision.action,
            current_price=current_price,
            target_price=decision.take_profit or (current_price * 1.03),
            stop_loss=decision.stop_loss or (current_price * 0.98),
            position_size=position_size,
            shares=position_size / current_price,
            confidence=decision.confidence,
            risk_reward_ratio=self._calculate_rr(
                current_price,
                decision.stop_loss or current_price * 0.98,
                decision.take_profit or current_price * 1.03,
                decision.action
            ),
            reasoning=decision.reasoning,
            similar_trades_win_rate=win_rate,
            technical_signals=technical_data,
            market_context=context.regime.value if context else None,
        )

    async def generate_alert(self, opportunity: TradingOpportunity) -> Optional[Alert]:
        """Generate alert from opportunity"""

        # Determine alert level
        if opportunity.confidence >= 0.8 and opportunity.risk_reward_ratio >= 2.5:
            level = AlertLevel.IMMEDIATE
        else:
            level = AlertLevel.STANDARD

        alert = self.alert_manager.create_alert(
            level=level,
            symbol=opportunity.symbol,
            action=opportunity.action,
            current_price=opportunity.current_price,
            target_price=opportunity.target_price,
            stop_loss=opportunity.stop_loss,
            position_size=opportunity.position_size,
            confidence=opportunity.confidence,
            reasoning=opportunity.reasoning,
            win_rate=opportunity.similar_trades_win_rate,
            technical_signals=opportunity.technical_signals,
            market_context=opportunity.market_context,
        )

        return alert

    async def _auto_execute_opportunity(self, opportunity: TradingOpportunity) -> Optional[ExecutionResult]:
        """
        AUTONOMOUS EXECUTION - No user confirmation required.
        Execute trade automatically when AI identifies opportunity.
        Includes detailed logging of reasoning for each decision.
        """
        # Check if trading is halted
        if self._trading_halted:
            self.logger.warning(f"⛔ Trading halted, skipping: {self._halt_reason}")
            return None

        try:
            # LOG DECISION BEFORE EXECUTING
            # This captures the full reasoning for later analysis
            decision_log = self.trade_logger.log_decision(
                symbol=opportunity.symbol,
                action=opportunity.action,
                confidence=opportunity.confidence,
                entry_price=opportunity.current_price,
                reasoning=opportunity.reasoning,
                technical_data=opportunity.technical_signals,
                market_context={
                    'regime': opportunity.market_context or 'unknown',
                    'context': self._current_context.__dict__ if self._current_context else {},
                },
                stop_loss=opportunity.stop_loss,
                targets=(opportunity.target_price, None, None),  # First target only
                position_size=opportunity.shares * opportunity.current_price if opportunity.shares else None,
            )

            # Create order request
            if opportunity.action == 'BUY':
                order_request = OrderRequest(
                    symbol=opportunity.symbol,
                    quantity=opportunity.shares,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,  # Market order for speed
                    stop_loss=opportunity.stop_loss,
                    take_profit=None,  # No fixed take-profit, use trailing stop
                    current_price=opportunity.current_price,  # For buying power check
                )
            else:  # SELL
                order_request = OrderRequest(
                    symbol=opportunity.symbol,
                    quantity=opportunity.shares,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                )

            # Execute the order
            result = await self.executor.execute(order_request)

            # LOG EXECUTION RESULT
            if result:
                order_id = result.order.client_order_id if result.order else str(uuid.uuid4())
                exec_price = result.order.filled_avg_price if result.order else opportunity.current_price

                self.trade_logger.log_execution(
                    symbol=opportunity.symbol,
                    order_id=order_id,
                    execution_price=exec_price or 0,
                    success=result.is_success,
                    error_message=result.error_message if not result.is_success else None,
                )

            # Record in memory
            if result.is_success:
                trade_record = TradeRecord(
                    id=str(uuid.uuid4()),
                    symbol=opportunity.symbol,
                    action=opportunity.action,
                    entry_price=result.order.filled_avg_price or opportunity.current_price,
                    exit_price=None,
                    quantity=opportunity.shares,
                    entry_time=datetime.now(),
                    exit_time=None,
                    stop_loss=opportunity.stop_loss,
                    take_profit=opportunity.target_price,
                    confidence=opportunity.confidence,
                    reasoning=opportunity.reasoning,
                    technical_signals=opportunity.technical_signals or {},
                    market_regime=opportunity.market_context or 'unknown',
                    pnl=0,
                    pnl_pct=0,
                )
                self.memory.record_trade(trade_record)

            return result

        except Exception as e:
            self.logger.error(f"Auto-execution error for {opportunity.symbol}: {e}")
            return None

    async def execute_trade(self, alert: Alert) -> ExecutionResult:
        """Execute trade from confirmed alert"""
        opp = alert.opportunity

        # Create order request
        request = OrderRequest(
            symbol=opp.symbol,
            side=OrderSide.BUY if opp.action == 'BUY' else OrderSide.SELL,
            quantity=opp.shares,
            order_type=OrderType.MARKET,
            stop_loss=opp.stop_loss,
            take_profit=opp.target_price,
            reason=opp.reasoning,
            current_price=opp.current_price,  # For buying power check
        )

        # Execute
        result = await self.executor.execute(request)

        if result.is_success:
            self._trades_executed += 1
            self._last_trade_time = datetime.now()

            # Record to memory
            trade_record = TradeRecord(
                id=str(uuid.uuid4())[:8],
                symbol=opp.symbol,
                action=opp.action,
                entry_price=result.order.filled_avg_price or opp.current_price,
                exit_price=None,
                quantity=opp.shares,
                entry_time=datetime.now(),
                exit_time=None,
                stop_loss=opp.stop_loss,
                take_profit=opp.target_price,
                confidence=opp.confidence,
                reasoning=opp.reasoning,
                technical_signals=opp.technical_signals,
                market_regime=opp.market_context or 'unknown',
            )
            self.memory.record_trade(trade_record)

            # Trigger callbacks
            self._trigger_trade_callbacks(result)

        return result

    async def handle_alert_response(self, alert: Alert, action: AlertAction) -> Optional[ExecutionResult]:
        """Handle user response to alert"""
        self.alert_manager.respond_to_alert(alert, action)

        if action == AlertAction.CONFIRM:
            return await self.execute_trade(alert)

        return None

    async def _get_technical_data(self, symbol: str, quote: StreamQuote) -> Dict[str, Any]:
        """Get technical indicators for symbol"""
        # Use existing market data collector for technical indicators
        from data.collectors.market_data import MarketDataCollector

        collector = MarketDataCollector()
        indicators = collector.get_technical_indicators(symbol)

        # Add current price from live quote
        indicators['current_price'] = quote.mid_price
        indicators['bid'] = quote.bid_price
        indicators['ask'] = quote.ask_price
        indicators['spread'] = quote.spread

        return indicators

    def _calculate_rr(
        self,
        entry: float,
        stop: float,
        target: float,
        action: str
    ) -> float:
        """Calculate risk/reward ratio"""
        if action == 'BUY':
            risk = entry - stop
            reward = target - entry
        else:
            risk = stop - entry
            reward = entry - target

        return reward / risk if risk > 0 else 0

    def _trigger_alert_callbacks(self, alert: Alert):
        """Trigger alert callbacks"""
        for callback in self._on_alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Alert callback error: {e}")

    def _trigger_trade_callbacks(self, result: ExecutionResult):
        """Trigger trade callbacks"""
        for callback in self._on_trade_callbacks:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"Trade callback error: {e}")

    def get_status(self) -> AgentStatus:
        """Get current agent status"""
        uptime = 0
        if self._start_time:
            uptime = int((datetime.now() - self._start_time).total_seconds())

        return AgentStatus(
            state=self._state,
            uptime_seconds=uptime,
            signals_generated=self._signals_generated,
            alerts_sent=self._alerts_sent,
            trades_executed=self._trades_executed,
            last_signal_time=self._last_signal_time,
            last_trade_time=self._last_trade_time,
            market_open=self._current_context.is_market_open if self._current_context else False,
            current_regime=self._current_context.regime if self._current_context else MarketRegime.NEUTRAL,
        )

    def get_portfolio_summary(self) -> Dict:
        """Get synchronous portfolio summary (for CLI)"""
        import asyncio
        import concurrent.futures

        async def _get():
            return await self.executor.get_position_summary()

        try:
            # Try to get the running loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We're inside an async context - use thread-safe approach
                future = asyncio.run_coroutine_threadsafe(_get(), loop)
                try:
                    return future.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    self.logger.warning("Portfolio fetch timed out")
                    return self._get_cached_portfolio()
            else:
                # No running loop - create new one
                return asyncio.run(_get())
        except Exception as e:
            self.logger.error(f"Error getting portfolio: {e}")
            return self._get_cached_portfolio()

    def _get_cached_portfolio(self) -> Dict:
        """Return last known portfolio state as fallback"""
        # Return minimal valid structure
        return {
            "total_positions": 0,
            "total_market_value": 0,
            "total_unrealized_pl": 0,
            "buying_power": 0,
            "equity": 0,
            "day_trades": 0,
            "positions": {},
        }

    def get_market_context_summary(self) -> Optional[str]:
        """Get market context summary"""
        if self._current_context:
            return self._current_context.get_summary()
        return None
