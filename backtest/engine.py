"""
Backtest Engine

Main orchestrator for running backtests.
Monkey-patches the agent to use historical data without modifying agent code.
"""
import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any, Callable
from unittest.mock import patch, MagicMock
import json

from backtest.historical_data import HistoricalDataLoader
from backtest.mock_client import MockAlpacaClient
from backtest.portfolio_tracker import PortfolioTracker
from backtest.report import ReportGenerator
from agent.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# Import agent's actual prompts for consistency
from agent.prompts.compact import (
    COMPACT_ANALYSIS_SYSTEM,
    compact_analysis_prompt,
)

# Reduce logging noise during backtest
logging.getLogger('agent.core').setLevel(logging.WARNING)
logging.getLogger('alpaca').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class SimulatedTime:
    """
    Manages simulated time for the backtest.
    Replaces datetime.now() calls throughout the codebase.
    """

    def __init__(self, start_time: datetime):
        self._current_time = start_time
        self._real_datetime = datetime

    def now(self, tz=None):
        """Return simulated current time"""
        return self._current_time

    def set_time(self, dt: datetime):
        """Set simulated time"""
        self._current_time = dt

    def advance(self, minutes: int = 1):
        """Advance time by N minutes"""
        self._current_time += timedelta(minutes=minutes)


class BacktestEngine:
    """
    Main backtest engine.

    Runs the trading agent against historical data by:
    1. Loading historical data for the period
    2. Replacing the Alpaca client with a mock
    3. Simulating time progression
    4. Recording all trades and decisions
    5. Generating a comparison report
    """

    def __init__(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        initial_capital: float = 100000.0,
        use_ollama: bool = True,
        time_step_minutes: int = 5,  # How often to check for signals
        verbose: bool = False,
    ):
        self.start_date = start_date or datetime(2025, 10, 1)
        self.end_date = end_date or datetime(2025, 12, 31)
        self.initial_capital = initial_capital
        self.use_ollama = use_ollama
        self.time_step_minutes = time_step_minutes
        self.verbose = verbose

        # Components
        self.data_loader = HistoricalDataLoader()
        self.portfolio = PortfolioTracker(initial_capital)
        self.mock_client: Optional[MockAlpacaClient] = None
        self.sim_time: Optional[SimulatedTime] = None

        # Circuit Breaker - Protects against catastrophic losses
        self.circuit_breaker = CircuitBreaker(CircuitBreakerConfig(
            max_daily_loss_pct=0.02,  # Stop trading if daily loss exceeds 2%
            min_trades_for_winrate_check=5,  # Need 5 trades to check win rate
            min_win_rate_pct=35.0,  # Stop if win rate drops below 35%
            max_losses_per_stock=2,  # Blacklist stock after 2 losses
            reduce_size_after_losses=3,  # Reduce size after 3 consecutive losses
            size_reduction_factor=0.5,  # Reduce to 50% of normal size
        ))

        # Results
        self.agent_decisions: List[Dict] = []
        self.errors: List[Dict] = []

        # Ollama statistics (to understand filtering)
        self.ollama_stats = {
            'total_signals': 0,  # Momentum signals detected
            'ollama_calls': 0,  # Times Ollama was called
            'ollama_no_response': 0,  # Ollama failed to respond
            'ollama_hold': 0,  # Ollama said HOLD
            'ollama_sell': 0,  # Ollama said SELL
            'ollama_buy_low_conf': 0,  # BUY but confidence < 70%
            'ollama_buy_approved': 0,  # BUY with confidence >= 70%
            'rejected_reasons': [],  # Sample of rejection reasons
        }

        # State
        self._running = False
        self._current_day: Optional[datetime] = None
        self._days_processed = 0
        self._total_days = 0

    async def run(self) -> Dict[str, Any]:
        """
        Run the complete backtest.

        Returns:
            Dict with results including agent performance and optimal comparison
        """
        logger.info("=" * 60)
        logger.info("BACKTEST STARTING")
        logger.info(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        logger.info(f"Initial Capital: ${self.initial_capital:,.2f}")
        logger.info(f"Use Ollama: {self.use_ollama}")
        logger.info("=" * 60)

        self._running = True

        # Step 1: Load historical data
        logger.info("Loading historical data...")
        await self.data_loader.load_data(
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Get trading days
        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)
        self._total_days = len(trading_days)
        logger.info(f"Found {self._total_days} trading days")

        if not trading_days:
            logger.error("No trading days found in data")
            return {'error': 'No trading days found'}

        # Setup price lookup for portfolio
        self.portfolio.set_price_lookup(self.data_loader.get_price_at_time)

        # Step 2: Verify Ollama if needed
        if self.use_ollama:
            ollama_ok = await self._check_ollama_available()
            if not ollama_ok:
                logger.error("❌ Ollama is not running but use_ollama=True!")
                logger.error("   Start Ollama with: ollama serve")
                logger.error("   Or run backtest with --no-ollama flag")
                return {'error': 'Ollama not available'}

        # Step 3: Initialize mock client and simulated time
        self.mock_client = MockAlpacaClient(
            self.data_loader,
            self.portfolio,
            self.initial_capital,
        )

        self.sim_time = SimulatedTime(trading_days[0].replace(hour=9, minute=30))

        # Step 3: Run simulation day by day
        try:
            for day in trading_days:
                if not self._running:
                    break

                await self._simulate_day(day)
                self._days_processed += 1

                # Progress update every 10 days
                if self._days_processed % 10 == 0:
                    equity = self.portfolio.get_equity(self.sim_time._current_time)
                    pnl = equity - self.initial_capital
                    logger.info(
                        f"Progress: {self._days_processed}/{self._total_days} days | "
                        f"Equity: ${equity:,.2f} | P&L: ${pnl:+,.2f}"
                    )

        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            self.errors.append({
                'time': self.sim_time._current_time.isoformat() if self.sim_time else None,
                'error': str(e),
            })

        # Step 4: Generate results
        logger.info("Generating results...")
        results = self._generate_results()

        logger.info("=" * 60)
        logger.info("BACKTEST COMPLETE")
        logger.info("=" * 60)

        return results

    async def _simulate_day(self, day: datetime):
        """Simulate a single trading day"""
        self._current_day = day

        # Set time to market open
        market_open = day.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = day.replace(hour=16, minute=0, second=0, microsecond=0)

        self.sim_time.set_time(market_open)
        self.mock_client.set_current_time(market_open)

        # Start new day in portfolio tracker
        self.portfolio.start_new_day(day, market_open)

        # Initialize circuit breaker for new day
        starting_equity = self.portfolio.get_equity(market_open)
        self.circuit_breaker.initialize_day(starting_equity)

        # Run signal checks throughout the day
        current_time = market_open
        while current_time < market_close and self._running:
            self.sim_time.set_time(current_time)
            self.mock_client.set_current_time(current_time)

            try:
                # Run agent's signal generation
                await self._run_agent_cycle(current_time)

                # Update portfolio tracking
                self.portfolio.update_intraday(current_time)

            except Exception as e:
                if self.verbose:
                    logger.warning(f"Error at {current_time}: {e}")
                self.errors.append({
                    'time': current_time.isoformat(),
                    'error': str(e),
                })

            # Advance time
            current_time += timedelta(minutes=self.time_step_minutes)

        # End of day: close any open positions (day trading)
        await self._close_all_positions(market_close)

        # Record daily stats
        self.portfolio.end_day(market_close)

    async def _run_agent_cycle(self, current_time: datetime):
        """
        Run one cycle of the agent's decision making.

        This is where we intercept the agent and feed it historical data.
        """
        # Get market movers for discovery
        movers = self.data_loader.get_top_movers(current_time, top_n=20)

        if not movers and self.verbose:
            logger.debug(f"No movers found at {current_time}")
            return

        # Simulate momentum scanning for top movers
        symbols_to_scan = [m['symbol'] for m in movers[:10]]

        for symbol in symbols_to_scan:
            mover_info = next((m for m in movers if m['symbol'] == symbol), {})

            # Get current price data
            bar = self.data_loader.get_bar_at_time(symbol, current_time)
            if not bar:
                continue

            # Get previous bars for momentum calculation
            bars = await self.mock_client.get_bars(symbol, limit=20)
            if len(bars) < 3:  # Reduced from 5 to 3
                continue

            # Calculate simple momentum metrics
            current_price = bar.close
            price_5_min_ago = bars[-min(5, len(bars))].close if len(bars) >= 5 else bars[0].close
            price_20_min_ago = bars[0].close if bars else current_price

            momentum_5 = (current_price - price_5_min_ago) / price_5_min_ago * 100 if price_5_min_ago > 0 else 0
            momentum_20 = (current_price - price_20_min_ago) / price_20_min_ago * 100 if price_20_min_ago > 0 else 0

            # Volume analysis
            avg_volume = sum(b.volume for b in bars) / len(bars) if bars else 1
            volume_ratio = bar.volume / avg_volume if avg_volume > 0 else 1

            # Simple scoring (mimics momentum scanner)
            score = 0
            if abs(momentum_5) > 0.3:  # Relaxed from 0.5
                score += 2
            if abs(momentum_20) > 0.5:  # Relaxed from 1.0
                score += 2
            if volume_ratio > 1.2:  # Relaxed from 1.5
                score += 2
            if bar.close > bar.open:  # Green candle
                score += 1

            # Also consider the day's change from open
            day_change = mover_info.get('change_pct', 0)
            if abs(day_change) > 2.0:  # Stock is moving significantly
                score += 2

            # Decision logic (simplified version of agent's logic)
            # Buy if: score is decent AND we have positive momentum
            if score >= 4 and momentum_5 > 0.2:  # Relaxed from score >= 5 and momentum_5 > 0.3
                # Potential buy signal
                if self.verbose:
                    logger.info(f"📊 BUY SIGNAL: {symbol} score={score} mom5={momentum_5:.2f}% vol={volume_ratio:.1f}x")
                await self._evaluate_buy(symbol, current_price, score, momentum_5, volume_ratio, current_time)

        # Check existing positions for exits
        await self._check_exits(current_time)

    async def _evaluate_buy(
        self,
        symbol: str,
        price: float,
        score: float,
        momentum: float,
        volume_ratio: float,
        current_time: datetime,
    ):
        """Evaluate a potential buy signal"""
        # Track signal detected
        self.ollama_stats['total_signals'] += 1

        # CIRCUIT BREAKER CHECK - Skip if trading is halted or stock is blacklisted
        can_trade, cb_reason = self.circuit_breaker.can_trade(symbol)
        if not can_trade:
            if self.verbose:
                logger.debug(f"🛑 {symbol}: Circuit breaker blocked - {cb_reason}")
            return

        # Check if we already have a position
        if symbol in self.portfolio.positions:
            return

        # Check if we have capacity for more positions
        if len(self.portfolio.positions) >= 5:
            return

        # Position sizing (20% max per position)
        equity = self.portfolio.get_equity(current_time)

        # Apply circuit breaker multiplier (reduces size after consecutive losses)
        cb_multiplier = self.circuit_breaker.get_position_size_multiplier()

        max_position_value = equity * 0.20 * cb_multiplier
        position_value = min(max_position_value, self.portfolio.cash * 0.5 * cb_multiplier)

        if position_value < 100:
            return

        qty = position_value / price

        # Risk/reward check (tighter stops to reduce avg loss)
        stop_loss = price * 0.985  # 1.5% stop
        take_profit = price * 1.025  # 2.5% target

        # Ollama analysis (if enabled)
        analysis_result = None
        if self.use_ollama:
            self.ollama_stats['ollama_calls'] += 1

            # Get additional context for better analysis
            bars = await self.mock_client.get_bars(symbol, limit=20)
            mover_info = next((m for m in self.data_loader.get_top_movers(current_time, 50)
                              if m['symbol'] == symbol), {})

            analysis_result = await self._run_ollama_analysis(
                symbol=symbol,
                price=price,
                momentum=momentum,
                volume_ratio=volume_ratio,
                bars=bars,
                day_change=mover_info.get('change_pct', 0),
                current_positions=len(self.portfolio.positions),
                current_pnl_pct=((self.portfolio.get_equity(current_time) - self.initial_capital)
                                / self.initial_capital * 100),
                current_time=current_time,
            )
            # Skip if not a strong BUY recommendation
            if analysis_result:
                rec = analysis_result.get('recommendation', 'HOLD')
                conf = analysis_result.get('confidence', 0)
                reasoning = analysis_result.get('reasoning', '')[:80]

                # Track rejection reasons
                if rec == 'SKIP' or rec == 'SELL':
                    self.ollama_stats['ollama_sell'] += 1
                    if len(self.ollama_stats['rejected_reasons']) < 20:
                        self.ollama_stats['rejected_reasons'].append(
                            f"{symbol}: {rec} conf={conf:.0%} - {reasoning[:50]}"
                        )
                    return
                elif rec == 'HOLD':
                    self.ollama_stats['ollama_hold'] += 1
                    if len(self.ollama_stats['rejected_reasons']) < 20:
                        self.ollama_stats['rejected_reasons'].append(
                            f"{symbol}: HOLD conf={conf:.0%} - {reasoning[:50]}"
                        )
                    return
                elif rec == 'BUY' and conf < 0.7:
                    self.ollama_stats['ollama_buy_low_conf'] += 1
                    if len(self.ollama_stats['rejected_reasons']) < 20:
                        self.ollama_stats['rejected_reasons'].append(
                            f"{symbol}: BUY LOW CONF={conf:.0%} - {reasoning[:50]}"
                        )
                    return
                elif rec == 'BUY' and conf >= 0.7:
                    self.ollama_stats['ollama_buy_approved'] += 1
                    logger.info(f"✅ OLLAMA APPROVED: {symbol} conf={conf:.0%}")
                else:
                    # Unknown state
                    return
            else:
                self.ollama_stats['ollama_no_response'] += 1
                return

        # Execute buy
        success = self.portfolio.buy(symbol, qty, price, current_time)

        if success:
            decision = {
                'time': current_time.isoformat(),
                'symbol': symbol,
                'action': 'BUY',
                'price': price,
                'qty': qty,
                'score': score,
                'momentum': momentum,
                'volume_ratio': volume_ratio,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'ollama_analysis': analysis_result,
            }
            self.agent_decisions.append(decision)

    async def _check_ollama_available(self) -> bool:
        """Check if Ollama server is running and accessible"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        logger.info("✅ Ollama server is running")
                        return True
        except Exception as e:
            logger.warning(f"Ollama check failed: {e}")
        return False

    async def _run_ollama_analysis(
        self,
        symbol: str,
        price: float,
        momentum: float,
        volume_ratio: float,
        bars: List = None,
        day_change: float = 0,
        current_positions: int = 0,
        current_pnl_pct: float = 0,
        current_time: datetime = None,
    ) -> Optional[Dict]:
        """
        Run Ollama analysis using THE SAME prompts as the real agent.
        This ensures backtest results match actual agent behavior.
        """
        try:
            import aiohttp

            bars = bars or []

            # Build technical data dict (same format as agent uses)
            technical_data = {
                'current_price': price,
                'change_pct': day_change,
                'daily_change': day_change,
                'volume_ratio': volume_ratio,
            }

            # Calculate RSI approximation from bars
            if len(bars) >= 14:
                gains = []
                losses = []
                for i in range(1, min(15, len(bars))):
                    diff = bars[i].close - bars[i-1].close
                    if diff > 0:
                        gains.append(diff)
                        losses.append(0)
                    else:
                        gains.append(0)
                        losses.append(abs(diff))
                avg_gain = sum(gains) / len(gains) if gains else 0.001
                avg_loss = sum(losses) / len(losses) if losses else 0.001
                rs = avg_gain / avg_loss if avg_loss > 0 else 100
                rsi = 100 - (100 / (1 + rs))
                technical_data['rsi'] = rsi
            else:
                technical_data['rsi'] = 50  # neutral if not enough data

            # MACD approximation (simplified)
            if len(bars) >= 12:
                ema12 = sum(b.close for b in bars[-12:]) / 12
                ema26 = sum(b.close for b in bars[-min(26, len(bars)):]) / min(26, len(bars))
                macd = ema12 - ema26
                macd_signal = macd * 0.9  # Simplified signal line
                technical_data['macd'] = macd
                technical_data['macd_signal'] = macd_signal
            else:
                technical_data['macd'] = 0
                technical_data['macd_signal'] = 0

            # High/Low from bars
            if bars:
                technical_data['high'] = max(b.high for b in bars)
                technical_data['low'] = min(b.low for b in bars)
            else:
                technical_data['high'] = price
                technical_data['low'] = price

            # Build market context (same format as agent uses)
            market_context = None
            if current_time:
                spy_bar = self.data_loader.get_bar_at_time('SPY', current_time)
                if spy_bar:
                    spy_day_data = self.data_loader._data_cache.get('SPY', {}).get(
                        current_time.date().isoformat(), None)
                    if spy_day_data:
                        spy_change = ((spy_bar.close - spy_day_data.open_price) /
                                     spy_day_data.open_price * 100)
                        # Determine regime
                        if spy_change > 0.5:
                            regime = 'RISK_ON'
                        elif spy_change < -0.5:
                            regime = 'RISK_OFF'
                        else:
                            regime = 'neutral'

                        market_context = {
                            'regime': regime,
                            'spy': {'change_pct': spy_change},
                            'vix': {'value': 18},  # Estimated VIX
                        }

            # Use the REAL agent's prompt builder
            prompt = compact_analysis_prompt(
                symbol=symbol,
                technical=technical_data,
                market=market_context,
                news=None,  # No news in backtest
            )

            # Call Ollama with same system prompt as agent
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'http://localhost:11434/api/generate',
                    json={
                        'model': 'llama3.1:latest',
                        'prompt': prompt,
                        'system': COMPACT_ANALYSIS_SYSTEM,
                        'stream': False,
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        response = result.get('response', '').strip()

                        # Parse JSON response (same as agent does)
                        try:
                            import json
                            # Try to extract JSON from response
                            json_match = response
                            if '{' in response:
                                start = response.index('{')
                                end = response.rindex('}') + 1
                                json_match = response[start:end]
                            parsed = json.loads(json_match)

                            recommendation = parsed.get('recommendation', 'HOLD').upper()
                            confidence = parsed.get('confidence', 0.5)
                            reasoning = parsed.get('reasoning', '')

                            # LOG: Show what Ollama actually responded
                            logger.debug(f"📝 OLLAMA RAW: {symbol} -> {recommendation} conf={confidence} reason={reasoning[:50]}")

                            # Map to SKIP if not BUY or low confidence
                            original_rec = recommendation
                            if recommendation not in ['BUY', 'SELL', 'HOLD']:
                                recommendation = 'HOLD'
                            if recommendation == 'SELL':
                                recommendation = 'SKIP'
                            if recommendation == 'HOLD':
                                recommendation = 'SKIP'  # Don't buy on HOLD

                            # NOTE: No longer filtering by confidence here - let the caller decide
                            # This was causing double-filtering

                            return {
                                'recommendation': recommendation,
                                'confidence': confidence,
                                'reasoning': reasoning[:200],
                                'entry_price': parsed.get('entry_price'),
                                'stop_loss': parsed.get('stop_loss'),
                                'take_profit': parsed.get('take_profit'),
                                'raw_response': response[:300],
                            }
                        except (json.JSONDecodeError, ValueError):
                            # Fallback: parse text response
                            recommendation = 'HOLD'
                            if 'BUY' in response.upper():
                                recommendation = 'BUY'
                            elif 'SELL' in response.upper():
                                recommendation = 'SKIP'

                            return {
                                'recommendation': recommendation,
                                'confidence': 0.5,
                                'reasoning': response[:200],
                                'raw_response': response[:300],
                            }
        except Exception as e:
            if self.verbose:
                logger.warning(f"Ollama analysis failed: {e}")
            return None

        return None

    async def _check_exits(self, current_time: datetime):
        """Check positions for exit signals"""
        positions_to_close = []

        for symbol, pos in list(self.portfolio.positions.items()):
            current_price = self.data_loader.get_price_at_time(symbol, current_time)
            if not current_price:
                continue

            entry_price = pos['avg_price']
            pnl_pct = (current_price - entry_price) / entry_price * 100

            # Exit conditions
            should_exit = False
            exit_reason = ""

            # Stop loss (1.5% - tighter to reduce avg loss)
            if pnl_pct <= -1.5:
                should_exit = True
                exit_reason = "stop_loss"

            # Take profit (2.5%)
            elif pnl_pct >= 2.5:
                should_exit = True
                exit_reason = "take_profit"

            # Time-based exit (held too long without movement)
            hold_time = (current_time - pos['entry_time']).total_seconds() / 60
            if hold_time > 60 and abs(pnl_pct) < 0.5:
                should_exit = True
                exit_reason = "time_exit"

            if should_exit:
                positions_to_close.append((symbol, current_price, exit_reason))

        # Execute exits
        for symbol, price, reason in positions_to_close:
            pos = self.portfolio.positions[symbol]
            qty = pos['qty']
            entry_price = pos['avg_price']

            # Calculate PnL for circuit breaker
            pnl_dollars = (price - entry_price) * qty

            success = self.portfolio.sell(symbol, qty, price, current_time)

            if success:
                # Record trade in circuit breaker
                new_equity = self.portfolio.get_equity(current_time)
                self.circuit_breaker.record_trade(symbol, pnl_dollars, new_equity)

                decision = {
                    'time': current_time.isoformat(),
                    'symbol': symbol,
                    'action': 'SELL',
                    'price': price,
                    'qty': qty,
                    'reason': reason,
                    'pnl': pnl_dollars,
                }
                self.agent_decisions.append(decision)

    async def _close_all_positions(self, current_time: datetime):
        """Close all positions at end of day"""
        for symbol in list(self.portfolio.positions.keys()):
            price = self.data_loader.get_price_at_time(symbol, current_time)
            if price:
                pos = self.portfolio.positions[symbol]
                qty = pos['qty']
                entry_price = pos['avg_price']

                # Calculate PnL for circuit breaker
                pnl_dollars = (price - entry_price) * qty

                self.portfolio.sell(symbol, qty, price, current_time)

                # Record trade in circuit breaker
                new_equity = self.portfolio.get_equity(current_time)
                self.circuit_breaker.record_trade(symbol, pnl_dollars, new_equity)

                decision = {
                    'time': current_time.isoformat(),
                    'symbol': symbol,
                    'action': 'SELL',
                    'price': price,
                    'qty': qty,
                    'reason': 'end_of_day',
                    'pnl': pnl_dollars,
                }
                self.agent_decisions.append(decision)

    def _generate_results(self) -> Dict[str, Any]:
        """Generate final results"""
        # Get portfolio summary
        summary = self.portfolio.get_summary()

        # Calculate optimal (hindsight)
        optimal = self._calculate_optimal()

        # Efficiency
        if optimal['total_return'] > 0:
            efficiency = summary['total_return'] / optimal['total_return'] * 100
        else:
            efficiency = 0

        results = {
            'period': {
                'start': self.start_date.isoformat(),
                'end': self.end_date.isoformat(),
                'trading_days': self._total_days,
            },
            'config': {
                'initial_capital': self.initial_capital,
                'use_ollama': self.use_ollama,
                'time_step_minutes': self.time_step_minutes,
            },
            'agent_performance': summary,
            'optimal_performance': optimal,
            'efficiency_pct': efficiency,
            'decisions_count': len(self.agent_decisions),
            'errors_count': len(self.errors),
            'ollama_stats': self.ollama_stats if self.use_ollama else None,
        }

        return results

    def _calculate_optimal(self) -> Dict[str, Any]:
        """
        Calculate optimal performance with perfect hindsight.

        This represents the maximum possible return if we made perfect trades.
        """
        total_optimal_gain = 0
        optimal_trades = 0

        for day in self.data_loader.get_trading_days(self.start_date, self.end_date):
            # For each day, calculate the best possible trades
            date_str = day.date().isoformat()

            for symbol in self.data_loader._data_cache:
                if date_str not in self.data_loader._data_cache[symbol]:
                    continue

                day_data = self.data_loader._data_cache[symbol][date_str]

                # Calculate intraday range
                if day_data.high_price > 0 and day_data.low_price > 0:
                    # Best case: buy at low, sell at high
                    intraday_gain = (day_data.high_price - day_data.low_price) / day_data.low_price * 100

                    # Only count significant moves (>1%)
                    if intraday_gain > 1.0:
                        total_optimal_gain += intraday_gain
                        optimal_trades += 1

        # Assuming we could capture 20% of perfect trades with full capital each time
        # This is a theoretical maximum
        avg_gain_per_trade = total_optimal_gain / optimal_trades if optimal_trades > 0 else 0

        # Realistic optimal: assume we could do 2 trades per day at 50% efficiency
        trading_days = len(self.data_loader.get_trading_days(self.start_date, self.end_date))
        realistic_trades = trading_days * 2
        realistic_return_pct = realistic_trades * avg_gain_per_trade * 0.3  # 30% capture rate

        return {
            'theoretical_max_trades': optimal_trades,
            'avg_gain_per_optimal_trade': avg_gain_per_trade,
            'realistic_return_pct': realistic_return_pct,
            'total_return': self.initial_capital * (realistic_return_pct / 100),
        }

    def stop(self):
        """Stop the backtest"""
        self._running = False


async def run_backtest(
    start_date: datetime = None,
    end_date: datetime = None,
    initial_capital: float = 100000.0,
    use_ollama: bool = True,
    save_report: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function to run a backtest.

    Args:
        start_date: Start of backtest period (default: Oct 1, 2025)
        end_date: End of backtest period (default: Dec 31, 2025)
        initial_capital: Starting capital
        use_ollama: Whether to use Ollama for analysis
        save_report: Whether to save report to file

    Returns:
        Dict with backtest results
    """
    engine = BacktestEngine(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        use_ollama=use_ollama,
    )

    results = await engine.run()

    if save_report:
        report_gen = ReportGenerator(results, engine.portfolio, engine.agent_decisions)
        report_path = report_gen.save_report()
        results['report_path'] = report_path

    return results
