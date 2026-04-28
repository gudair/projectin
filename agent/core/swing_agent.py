"""
Swing Trading Agent

Uses mean reversion strategy (RSI + Bollinger Bands) for multi-day trades.
This agent is aligned with the backtested strategy in backtest/swing_engine.py.

Key differences from the day trading agent:
- Evaluates at end of day (not minute-by-minute)
- Uses daily indicators for entry decisions
- Monitors intraday only for stop loss / take profit
- Holds positions for 1-5 days
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from config.agent_config import AgentConfig, DEFAULT_CONFIG, AlertLevel
from agent.strategies.mean_reversion import MeanReversionStrategy, TechnicalIndicators, SwingSignal
from backtest.screener import DynamicScreener, ScreenerCriteria
from backtest.daily_data import DailyDataLoader
from alpaca.client import AlpacaClient
from alpaca.executor import OrderExecutor, OrderRequest, OrderSide, OrderType

logger = logging.getLogger(__name__)


@dataclass
class SwingPosition:
    """An open swing position"""
    symbol: str
    qty: float
    entry_price: float
    entry_date: datetime
    stop_loss: float
    take_profit: float
    signal: SwingSignal


@dataclass
class SwingAgentConfig:
    """Configuration for swing trading agent"""
    # Position sizing
    max_positions: int = 5
    position_size_pct: float = 0.05  # 5% of portfolio per trade

    # Strategy parameters
    stop_loss_pct: float = 0.03  # 3% stop loss
    take_profit_pct: float = 0.05  # 5% take profit
    max_hold_days: int = 5
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # Screener criteria
    min_price: float = 5.0
    min_volume: int = 500_000
    max_atr_pct: float = 0.025  # Max volatility (2.5%)
    max_symbols: int = 50

    # Timing
    entry_check_time: str = "15:45"  # Check for entries near close (3:45 PM ET)
    position_monitor_interval: int = 60  # Check positions every 60 seconds


class SwingTradingAgent:
    """
    Swing Trading Agent using Mean Reversion Strategy

    This agent:
    1. Screens for low-volatility, high-volume stocks dynamically
    2. Evaluates RSI + Bollinger Bands at end of day for entries
    3. Monitors positions intraday for stop loss / take profit
    4. Holds positions for 1-5 days until mean reversion completes
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        swing_config: Optional[SwingAgentConfig] = None,
    ):
        self.config = config or DEFAULT_CONFIG
        self.swing_config = swing_config or SwingAgentConfig()

        # Strategy
        self.strategy = MeanReversionStrategy(
            stop_loss_pct=self.swing_config.stop_loss_pct,
            take_profit_pct=self.swing_config.take_profit_pct,
            max_hold_days=self.swing_config.max_hold_days,
            rsi_oversold=self.swing_config.rsi_oversold,
            rsi_overbought=self.swing_config.rsi_overbought,
        )

        # Screener for dynamic symbol selection
        self.screener = DynamicScreener(ScreenerCriteria(
            min_price=self.swing_config.min_price,
            min_avg_volume=self.swing_config.min_volume,
            max_atr_pct=self.swing_config.max_atr_pct,
            max_symbols=self.swing_config.max_symbols,
        ))

        # Data loader for daily bars
        self.data_loader = DailyDataLoader()

        # Alpaca components
        self.alpaca_client = AlpacaClient(self.config.alpaca)
        self.executor = OrderExecutor(self.alpaca_client, self.config.risk)

        # State
        self.positions: Dict[str, SwingPosition] = {}
        self.symbols: List[str] = []
        self._running = False
        self._last_screen_date: Optional[datetime] = None

        # Statistics
        self.stats = {
            'signals_generated': 0,
            'trades_executed': 0,
            'stop_losses': 0,
            'take_profits': 0,
            'days_running': 0,
        }

    async def start(self):
        """Start the swing trading agent"""
        logger.info("=" * 60)
        logger.info("🚀 STARTING SWING TRADING AGENT")
        logger.info("=" * 60)
        logger.info(f"Strategy: Mean Reversion (RSI + Bollinger Bands)")
        logger.info(f"Max positions: {self.swing_config.max_positions}")
        logger.info(f"Position size: {self.swing_config.position_size_pct:.0%}")
        logger.info(f"Stop loss: {self.swing_config.stop_loss_pct:.0%}")
        logger.info(f"Take profit: {self.swing_config.take_profit_pct:.0%}")

        self._running = True

        # Get account info
        try:
            account = await self.alpaca_client.get_account()
            logger.info(f"💰 Account: ${account.equity:.2f} equity")
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return

        # Load existing positions from Alpaca
        await self._sync_positions()

        # Initial symbol screening
        await self._screen_symbols()

        # Start main loops
        try:
            await asyncio.gather(
                self._position_monitor_loop(),
                self._entry_check_loop(),
            )
        except asyncio.CancelledError:
            logger.info("Agent stopped")
        finally:
            self._running = False

    async def stop(self):
        """Stop the agent"""
        logger.info("🛑 Stopping Swing Trading Agent...")
        self._running = False
        await self.alpaca_client.close()

    async def _sync_positions(self):
        """Sync positions with Alpaca"""
        try:
            alpaca_positions = await self.alpaca_client.get_positions()

            for pos in alpaca_positions:
                if pos.symbol not in self.positions:
                    # Track position but without full signal info
                    # (will be managed for stop loss/take profit only)
                    entry_price = float(pos.avg_entry_price)
                    self.positions[pos.symbol] = SwingPosition(
                        symbol=pos.symbol,
                        qty=float(pos.qty),
                        entry_price=entry_price,
                        entry_date=datetime.now(),  # Unknown actual entry
                        stop_loss=entry_price * (1 - self.swing_config.stop_loss_pct),
                        take_profit=entry_price * (1 + self.swing_config.take_profit_pct),
                        signal=None,
                    )
                    logger.info(f"📊 Synced position: {pos.symbol} {pos.qty} @ ${entry_price:.2f}")

            logger.info(f"📊 Total positions: {len(self.positions)}")

        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")

    async def _screen_symbols(self):
        """Screen for tradeable symbols with volatility filter"""
        today = datetime.now().date()

        # Only re-screen once per day
        if self._last_screen_date == today and self.symbols:
            return

        logger.info("🔍 Screening for symbols...")

        try:
            # Get all tradeable symbols
            all_symbols = await self.screener.get_tradeable_symbols()
            logger.info(f"Found {len(all_symbols)} tradeable symbols")

            # Screen by volume, price, and volatility
            screened = await self.screener.screen_by_volume_and_price(
                all_symbols[:300],  # Limit for speed
                datetime.now(),
                lookback_days=20,
            )

            self.symbols = [s['symbol'] for s in screened]
            self._last_screen_date = today

            logger.info(f"✅ Screened to {len(self.symbols)} low-volatility symbols")

        except Exception as e:
            logger.error(f"Screening failed: {e}")
            # Fallback to hardcoded blue chips
            self.symbols = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'JPM', 'V', 'JNJ',
                'WMT', 'PG', 'HD', 'KO', 'PEP', 'MRK', 'COST',
            ]
            logger.info(f"Using fallback symbols: {len(self.symbols)}")

    async def _position_monitor_loop(self):
        """
        Monitor positions for stop loss / take profit.

        Runs frequently during market hours to catch intraday price movements.
        """
        logger.info("🛡️ Position monitor started")

        while self._running:
            try:
                # Check if market is open
                is_open = await self.alpaca_client.is_market_open()

                if not is_open:
                    await asyncio.sleep(60)
                    continue

                # Check each position
                for symbol in list(self.positions.keys()):
                    await self._check_position(symbol)

                await asyncio.sleep(self.swing_config.position_monitor_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in position monitor: {e}")
                await asyncio.sleep(10)

    async def _check_position(self, symbol: str):
        """Check a position for stop loss or take profit"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        try:
            # Get current quote
            quote = await self.alpaca_client.get_latest_quote(symbol)
            if not quote:
                return

            current_price = (quote.bid_price + quote.ask_price) / 2

            # Check STOP LOSS
            if current_price <= pos.stop_loss:
                logger.warning(f"🛑 STOP LOSS: {symbol} at ${current_price:.2f} (stop: ${pos.stop_loss:.2f})")
                await self._close_position(symbol, "stop_loss")
                self.stats['stop_losses'] += 1
                return

            # Check TAKE PROFIT
            if current_price >= pos.take_profit:
                logger.info(f"🎯 TAKE PROFIT: {symbol} at ${current_price:.2f} (target: ${pos.take_profit:.2f})")
                await self._close_position(symbol, "take_profit")
                self.stats['take_profits'] += 1
                return

            # Check MAX HOLD DAYS
            if pos.entry_date:
                hold_days = (datetime.now() - pos.entry_date).days
                if hold_days >= self.swing_config.max_hold_days:
                    logger.info(f"⏰ MAX HOLD: {symbol} held for {hold_days} days")
                    await self._close_position(symbol, "max_hold")
                    return

        except Exception as e:
            logger.error(f"Error checking position {symbol}: {e}")

    async def _entry_check_loop(self):
        """
        Check for new entry signals near market close.

        Only evaluates once per day near the configured entry time.
        """
        logger.info(f"📅 Entry check scheduled for {self.swing_config.entry_check_time} ET")

        last_check_date = None

        while self._running:
            try:
                now = datetime.now()
                today = now.date()

                # Only check once per day
                if last_check_date == today:
                    await asyncio.sleep(60)
                    continue

                # Check if it's time (near market close)
                current_time = now.strftime("%H:%M")
                if current_time < self.swing_config.entry_check_time:
                    await asyncio.sleep(60)
                    continue

                # Check if market is open
                is_open = await self.alpaca_client.is_market_open()
                if not is_open:
                    await asyncio.sleep(60)
                    continue

                logger.info("📊 Running end-of-day entry analysis...")
                last_check_date = today

                await self._check_entries()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in entry check: {e}")
                await asyncio.sleep(60)

    async def _check_entries(self):
        """Check for mean reversion entry signals"""

        # Refresh symbol screening (weekly)
        await self._screen_symbols()

        # Check position limits
        if len(self.positions) >= self.swing_config.max_positions:
            logger.info(f"📵 Max positions reached ({len(self.positions)})")
            return

        # Get account for position sizing
        try:
            account = await self.alpaca_client.get_account()
            buying_power = float(account.buying_power)
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return

        # Load daily data for analysis
        logger.info(f"Loading daily data for {len(self.symbols)} symbols...")
        start_date = datetime.now() - timedelta(days=60)
        await self.data_loader.load(self.symbols, start_date, datetime.now())

        # Find entry candidates
        candidates = []

        for symbol in self.symbols:
            if symbol in self.positions:
                continue  # Already have position

            bars = self.data_loader.get_bars(symbol, datetime.now(), 30)
            if len(bars) < 20:
                continue

            # Calculate indicators
            closes = [b.close for b in bars]
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]
            volumes = [b.volume for b in bars]

            indicators = self.strategy.calculate_indicators(closes, highs, lows, volumes)

            # Generate signal
            signal = self.strategy.generate_signal(
                symbol=symbol,
                current_price=closes[-1],
                indicators=indicators,
                has_position=False,
            )

            self.stats['signals_generated'] += 1

            if signal.action == 'BUY' and signal.confidence >= 0.7:
                candidates.append((symbol, signal, indicators))
                logger.info(
                    f"🎯 BUY SIGNAL: {symbol} | RSI={indicators.rsi:.0f} | "
                    f"BB%={indicators.bb_percent:.0%} | Conf={signal.confidence:.0%}"
                )

        # Execute top candidates
        slots_available = self.swing_config.max_positions - len(self.positions)
        for symbol, signal, indicators in candidates[:slots_available]:
            await self._open_position(symbol, signal, buying_power)

        if not candidates:
            logger.info("📭 No entry signals found today")

    async def _open_position(self, symbol: str, signal: SwingSignal, buying_power: float):
        """Open a new position"""
        try:
            # Calculate position size
            position_value = buying_power * self.swing_config.position_size_pct
            qty = position_value / signal.entry_price

            # Execute order
            order = OrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
            )

            result = await self.executor.execute_order(order)

            if result.is_success:
                # Track position
                self.positions[symbol] = SwingPosition(
                    symbol=symbol,
                    qty=result.order.filled_qty,
                    entry_price=result.order.filled_avg_price,
                    entry_date=datetime.now(),
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    signal=signal,
                )

                self.stats['trades_executed'] += 1

                logger.info(
                    f"✅ BOUGHT {symbol}: {qty:.2f} @ ${result.order.filled_avg_price:.2f} | "
                    f"Stop: ${signal.stop_loss:.2f} | Target: ${signal.take_profit:.2f}"
                )
            else:
                logger.error(f"❌ Order failed: {result.error_message}")

        except Exception as e:
            logger.error(f"Error opening position {symbol}: {e}")

    async def _close_position(self, symbol: str, reason: str):
        """Close a position"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        try:
            order = OrderRequest(
                symbol=symbol,
                qty=pos.qty,
                side=OrderSide.SELL,
                type=OrderType.MARKET,
            )

            result = await self.executor.execute_order(order)

            if result.is_success:
                pnl = (result.order.filled_avg_price - pos.entry_price) * pos.qty
                pnl_pct = (result.order.filled_avg_price - pos.entry_price) / pos.entry_price

                del self.positions[symbol]

                logger.info(
                    f"{'✅' if pnl > 0 else '❌'} SOLD {symbol}: {pos.qty:.2f} @ ${result.order.filled_avg_price:.2f} | "
                    f"P&L: ${pnl:+.2f} ({pnl_pct:+.1%}) | Reason: {reason}"
                )
            else:
                logger.error(f"❌ Close order failed: {result.error_message}")

        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            'running': self._running,
            'positions': len(self.positions),
            'symbols_tracked': len(self.symbols),
            'stats': self.stats,
            'positions_detail': {
                symbol: {
                    'qty': pos.qty,
                    'entry_price': pos.entry_price,
                    'stop_loss': pos.stop_loss,
                    'take_profit': pos.take_profit,
                }
                for symbol, pos in self.positions.items()
            }
        }


async def run_swing_agent():
    """Run the swing trading agent"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    agent = SwingTradingAgent()

    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(run_swing_agent())
