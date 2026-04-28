"""
Order Executor

Handles order execution via Alpaca with risk management.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import uuid

from alpaca.client import (
    AlpacaClient, Order, Position, Account,
    OrderSide, OrderType, TimeInForce, OrderStatus
)
from config.agent_config import RiskConfig, DEFAULT_CONFIG


class ExecutionStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass
class OrderRequest:
    """Order request with risk parameters"""
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    client_order_id: Optional[str] = None
    reason: str = ""
    current_price: Optional[float] = None  # For buying power estimation

    def __post_init__(self):
        if not self.client_order_id:
            self.client_order_id = f"agent_{uuid.uuid4().hex[:8]}"


@dataclass
class ExecutionResult:
    """Result of order execution"""
    status: ExecutionStatus
    order: Optional[Order] = None
    stop_loss_order: Optional[Order] = None
    take_profit_order: Optional[Order] = None
    error_message: str = ""
    execution_time: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS


class OrderExecutor:
    """
    Handles order execution with risk management:
    - Position sizing validation
    - Stop loss placement
    - Take profit orders
    - PDT rule tracking
    """

    def __init__(
        self,
        client: Optional[AlpacaClient] = None,
        risk_config: Optional[RiskConfig] = None
    ):
        self.client = client or AlpacaClient()
        self.risk = risk_config or DEFAULT_CONFIG.risk
        self.logger = logging.getLogger(__name__)

        # PDT tracking
        self._day_trades: List[Dict] = []
        self._last_pdt_check: Optional[datetime] = None

        # Software-based stop-loss/take-profit tracking for fractional shares
        # Now includes trailing stop support
        self._tracked_stops: Dict[str, Dict] = {}
        # Structure: symbol -> {
        #   stop_loss: float,       # Current stop-loss price
        #   take_profit: float,     # Take-profit price (optional)
        #   qty: float,             # Position quantity
        #   entry_price: float,     # Original entry price
        #   highest_price: float,   # Highest price since entry (for trailing)
        #   trailing_pct: float,    # Trailing stop percentage (e.g., 0.03 = 3%)
        #   is_trailing: bool,      # Whether trailing is active
        # }

        self._daily_pnl: float = 0.0
        self._daily_pnl_start: Optional[datetime] = None

    async def execute(self, request: OrderRequest) -> ExecutionResult:
        """
        Execute order with risk management.

        Returns ExecutionResult with main order and optional bracket orders.
        """
        start_time = datetime.now()

        try:
            # Validate request
            is_valid, error = await self._validate_request(request)
            if not is_valid:
                return ExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    error_message=error,
                )

            # For SELL orders: cancel any pending orders first to free up shares
            if request.side == OrderSide.SELL:
                await self._cancel_pending_orders_for_symbol(request.symbol)

            # For BUY orders: cancel any pending SELL/STOP orders to avoid wash trade error
            if request.side == OrderSide.BUY:
                cancelled = await self._cancel_opposite_side_orders(request.symbol)
                if cancelled > 0:
                    self.logger.info(f"🗑️ Cancelled {cancelled} opposite-side order(s) for {request.symbol} to avoid wash trade")

            # Submit main order
            main_order = await self.client.submit_order(
                symbol=request.symbol,
                qty=request.quantity,
                side=request.side,
                order_type=request.order_type,
                time_in_force=request.time_in_force,
                limit_price=request.limit_price,
                client_order_id=request.client_order_id,
            )

            self.logger.info(f"Order submitted: {main_order.id}")

            # Wait for fill (with timeout)
            filled_order = await self._wait_for_fill(main_order.id, timeout=30)

            if not filled_order or filled_order.status not in [
                OrderStatus.FILLED.value,
                OrderStatus.PARTIALLY_FILLED.value
            ]:
                return ExecutionResult(
                    status=ExecutionStatus.PENDING,
                    order=filled_order or main_order,
                    error_message="Order not filled within timeout",
                )

            # Record day trade if applicable
            if request.side == OrderSide.SELL:
                await self._record_day_trade(request.symbol)

            # NOTE: No bracket orders placed here.
            # The aggressive agent handles all stop loss / take profit / trailing stop
            # in software via its position monitor loop. This avoids:
            # 1. Dual stop tracking (Alpaca orders vs agent software) that caused conflicts
            # 2. Bracket orders blocking full position close (shares locked by pending orders)
            # 3. Wash trade rejections from Alpaca
            stop_order = None
            tp_order = None

            execution_time = (datetime.now() - start_time).total_seconds()

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                order=filled_order,
                stop_loss_order=stop_order,
                take_profit_order=tp_order,
                execution_time=execution_time,
            )

        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
            )

    async def _validate_request(self, request: OrderRequest) -> Tuple[bool, str]:
        """Validate order request against risk rules"""

        # Get account info
        try:
            account = await self.client.get_account()
        except Exception as e:
            return False, f"Failed to get account info: {e}"

        # Check if trading is allowed
        if account.trading_blocked:
            return False, "Trading is blocked on this account"

        # Check PDT rule
        if self.risk.pdt_enabled:
            pdt_ok, pdt_msg = await self._check_pdt_rule(account, request)
            if not pdt_ok:
                return False, pdt_msg

        # Check buying power (use daytrading_buying_power for PDT accounts)
        if request.side == OrderSide.BUY:
            # Use limit_price, current_price, or stop_loss as price estimate
            price_estimate = request.limit_price or request.current_price or request.stop_loss or 0
            if price_estimate > 0:
                estimated_cost = request.quantity * price_estimate * 1.02  # Add 2% buffer for slippage
                available_bp = min(account.buying_power, account.daytrading_buying_power) if account.daytrading_buying_power > 0 else account.buying_power
                if estimated_cost > available_bp:
                    return False, f"Insufficient buying power. Need ~${estimated_cost:.2f}, Available: ${available_bp:.2f} (DT BP: ${account.daytrading_buying_power:.2f})"

        # Check position size (1% tolerance to avoid floating-point edge cases)
        position_pct = await self._calculate_position_pct(request, account)
        if position_pct > self.risk.max_position_pct * 1.01:
            return False, f"Position too large ({position_pct*100:.1f}% > {self.risk.max_position_pct*100:.0f}% limit)"

        # Check max positions
        if request.side == OrderSide.BUY:
            positions = await self.client.get_positions()
            existing = [p for p in positions if p.symbol == request.symbol]

            if not existing and len(positions) >= self.risk.max_positions:
                return False, f"Max positions reached ({self.risk.max_positions})"

        # Check risk/reward if stop loss provided
        if request.side == OrderSide.BUY and request.stop_loss and request.take_profit:
            entry_est = request.limit_price or 0

            if entry_est > 0:
                risk = entry_est - request.stop_loss
                reward = request.take_profit - entry_est

                if risk > 0:
                    rr_ratio = reward / risk
                    if rr_ratio < self.risk.min_risk_reward:
                        return False, f"Risk/Reward ratio too low ({rr_ratio:.2f} < {self.risk.min_risk_reward})"

        return True, ""

    async def _check_pdt_rule(self, account: Account, request: OrderRequest) -> Tuple[bool, str]:
        """Check Pattern Day Trader rule"""

        # If not a sell, PDT doesn't apply
        if request.side != OrderSide.SELL:
            return True, ""

        # PDT only applies if account < $25,000
        if account.equity >= 25000:
            return True, ""

        # Check if this would be a day trade
        positions = await self.client.get_positions()
        position = next((p for p in positions if p.symbol == request.symbol), None)

        if not position:
            return True, ""  # Selling something we don't own (short) - different rules

        # Count day trades in last 5 business days
        await self._refresh_day_trades()
        day_trade_count = len(self._day_trades)

        if day_trade_count >= self.risk.pdt_limit:
            return False, f"PDT limit reached ({day_trade_count}/{self.risk.pdt_limit} day trades)"

        return True, ""

    async def _refresh_day_trades(self):
        """Refresh day trade count from Alpaca"""
        now = datetime.now()

        # Only refresh once per hour
        if self._last_pdt_check and (now - self._last_pdt_check).seconds < 3600:
            return

        try:
            account = await self.client.get_account()
            # Alpaca tracks this for us
            self._day_trades = [{}] * account.daytrade_count
            self._last_pdt_check = now
        except Exception as e:
            self.logger.error(f"Failed to refresh PDT count: {e}")

    async def _record_day_trade(self, symbol: str):
        """Record a day trade"""
        self._day_trades.append({
            "symbol": symbol,
            "timestamp": datetime.now(),
        })

        # Clean up old trades (> 5 business days)
        cutoff = datetime.now() - timedelta(days=7)  # Approximate
        self._day_trades = [t for t in self._day_trades if t.get("timestamp", datetime.now()) > cutoff]

    async def _calculate_position_pct(self, request: OrderRequest, account: Account) -> float:
        """Calculate position as percentage of portfolio"""

        # Get current position
        position = await self.client.get_position(request.symbol)
        current_value = position.market_value if position else 0

        # Estimate new position value - use current_price for market orders
        estimated_price = request.limit_price or request.current_price or request.stop_loss or 100
        additional_value = request.quantity * estimated_price

        if request.side == OrderSide.SELL:
            new_value = max(0, current_value - additional_value)
        else:
            new_value = current_value + additional_value

        return new_value / account.equity if account.equity > 0 else 0

    async def _wait_for_fill(self, order_id: str, timeout: int = 30) -> Optional[Order]:
        """Wait for order to fill with timeout"""
        start = datetime.now()

        while (datetime.now() - start).seconds < timeout:
            try:
                order = await self.client.get_order(order_id)

                if order.status in [
                    OrderStatus.FILLED.value,
                    OrderStatus.PARTIALLY_FILLED.value,
                    OrderStatus.CANCELED.value,
                    OrderStatus.EXPIRED.value,
                    OrderStatus.REJECTED.value,
                ]:
                    return order

                await asyncio.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error checking order status: {e}")
                await asyncio.sleep(1)

        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        return await self.client.cancel_order(order_id)

    async def _cancel_pending_orders_for_symbol(self, symbol: str) -> int:
        """Cancel all pending orders for a symbol to free up shares for selling"""
        try:
            orders = await self.client.get_orders(status='open')
            symbol_orders = [o for o in orders if o.symbol == symbol]

            if not symbol_orders:
                return 0

            cancelled = 0
            for order in symbol_orders:
                try:
                    await self.client.cancel_order(order.id)
                    cancelled += 1
                    self.logger.info(f"🗑️ Cancelled pending {order.type} order for {symbol} (qty: {order.qty})")
                except Exception as e:
                    self.logger.warning(f"Failed to cancel order {order.id}: {e}")

            # Wait briefly for cancellations to process
            if cancelled > 0:
                await asyncio.sleep(0.5)

            return cancelled

        except Exception as e:
            self.logger.error(f"Error cancelling orders for {symbol}: {e}")
            return 0

    async def _cancel_opposite_side_orders(self, symbol: str) -> int:
        """
        Cancel opposite-side (sell/stop) orders for a symbol to avoid wash trade errors.
        This is called before placing a BUY order to ensure no conflicting sell orders exist.
        """
        try:
            orders = await self.client.get_orders(status='open')
            # Find sell-side orders for this symbol (sell, stop, stop_limit)
            opposite_orders = [
                o for o in orders
                if o.symbol == symbol and o.side == 'sell'
            ]

            if not opposite_orders:
                return 0

            cancelled = 0
            for order in opposite_orders:
                try:
                    await self.client.cancel_order(order.id)
                    cancelled += 1
                    self.logger.info(
                        f"🗑️ Cancelled {order.side} {order.type} order for {symbol} "
                        f"(qty: {order.qty}, id: {order.id[:8]}...) to avoid wash trade"
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to cancel order {order.id}: {e}")

            # Wait briefly for cancellations to process
            if cancelled > 0:
                await asyncio.sleep(0.5)

            return cancelled

        except Exception as e:
            self.logger.error(f"Error cancelling opposite-side orders for {symbol}: {e}")
            return 0

    async def close_position(
        self,
        symbol: str,
        reason: str = "Manual close"
    ) -> ExecutionResult:
        """Close entire position using Alpaca's atomic DELETE endpoint.

        This is more reliable than submit sell + wait for fill:
        - No qty mismatch possible (Alpaca closes everything)
        - No timeout issues (Alpaca handles the liquidation)
        - Cancels pending orders automatically
        """
        try:
            # Cancel pending orders first to free shares
            await self._cancel_pending_orders_for_symbol(symbol)

            # Use atomic DELETE - Alpaca closes the entire position
            order = await self.client.close_position_atomic(symbol)

            if not order:
                return ExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    error_message=f"No position found for {symbol}",
                )

            # Wait for the liquidation order to fill
            filled_order = await self._wait_for_fill(order.id, timeout=60)

            if filled_order and filled_order.status == OrderStatus.FILLED.value:
                self.logger.info(
                    f"✅ Closed {symbol}: {filled_order.filled_qty:.2f} shares "
                    f"@ ${filled_order.filled_avg_price:.2f} | Reason: {reason}"
                )
                return ExecutionResult(
                    status=ExecutionStatus.FILLED,
                    order=filled_order,
                )

            # Even if we didn't confirm the fill in time, return what we have
            # The position may still be closing in Alpaca
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                order=filled_order or order,
                error_message=f"Liquidation order submitted but not confirmed filled within timeout",
            )

        except Exception as e:
            self.logger.error(f"Error closing position {symbol}: {e}")
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                error_message=str(e),
            )

    async def close_all_positions(self) -> List[ExecutionResult]:
        """Close all positions"""
        positions = await self.client.get_positions()
        results = []

        for position in positions:
            result = await self.close_position(position.symbol, "Close all positions")
            results.append(result)

        return results

    async def get_position_summary(self) -> Dict:
        """Get summary of all positions"""
        positions = await self.client.get_positions()
        account = await self.client.get_account()

        return {
            "total_positions": len(positions),
            "total_market_value": sum(p.market_value for p in positions),
            "total_unrealized_pl": sum(p.unrealized_pl for p in positions),
            "buying_power": account.buying_power,
            "equity": account.equity,
            "day_trades": len(self._day_trades),
            # Dict keyed by symbol for format_portfolio_state compatibility
            "positions": {
                p.symbol: {
                    "symbol": p.symbol,
                    "shares": p.qty,
                    "qty": p.qty,
                    "market_value": p.market_value,
                    "unrealized_pnl": p.unrealized_pl,
                    "unrealized_pl": p.unrealized_pl,
                    "unrealized_pnl_percent": p.unrealized_plpc * 100,
                    "unrealized_plpc": p.unrealized_plpc,
                }
                for p in positions
            },
        }

    def _track_stop_loss(self, symbol: str, stop_price: float, qty: float, entry_price: float = None, trailing_pct: float = 0.03):
        """
        Track stop loss for software-based monitoring with trailing stop support.
        
        Args:
            symbol: Stock symbol
            stop_price: Initial stop-loss price
            qty: Position quantity
            entry_price: Entry price (for trailing calculation)
            trailing_pct: Trailing stop percentage (default 3%)
        """
        self._tracked_stops[symbol] = {
            'stop_loss': stop_price,
            'qty': qty,
            'entry_price': entry_price or stop_price * 1.02,  # Estimate if not provided
            'highest_price': entry_price or stop_price * 1.02,
            'trailing_pct': trailing_pct,
            'is_trailing': True,  # Enable trailing by default
        }
        self.logger.info(f"📍 Tracking trailing stop for {symbol}: ${stop_price:.2f} ({trailing_pct*100:.0f}% trail)")
    def _track_take_profit(self, symbol: str, tp_price: float, qty: float):
        """Track take profit for software-based monitoring"""
        if symbol not in self._tracked_stops:
            self._tracked_stops[symbol] = {}
        self._tracked_stops[symbol]['take_profit'] = tp_price
        self._tracked_stops[symbol]['qty'] = qty
        self.logger.info(f"📍 Tracking take profit for {symbol}: ${tp_price:.2f}")

    def get_tracked_positions(self) -> Dict[str, Dict]:
        """Get all positions with software-tracked SL/TP"""
        return self._tracked_stops.copy()

    async def check_stop_losses(self) -> List[Dict]:
        """
        Check all tracked positions for stop-loss/take-profit triggers.
        Also updates trailing stops when price moves up.
        Returns list of positions that need to be closed.
        """
        triggers = []

        if not self._tracked_stops:
            self.logger.debug("No positions being tracked for stop-losses")
            return triggers

        self.logger.debug(f"Checking stop-losses for {len(self._tracked_stops)} tracked positions")

        positions = await self.client.get_positions()
        position_map = {p.symbol: p for p in positions}

        for symbol, tracking in list(self._tracked_stops.items()):
            if symbol not in position_map:
                # Position no longer exists, remove tracking
                del self._tracked_stops[symbol]
                continue

            position = position_map[symbol]
            current_price = position.current_price

            # Update trailing stop if price has moved up
            if tracking.get('is_trailing', False):
                highest_price = tracking.get('highest_price', current_price)
                
                if current_price > highest_price:
                    # Price made new high - update highest and potentially stop
                    old_highest = highest_price
                    tracking['highest_price'] = current_price
                    
                    # Calculate new trailing stop
                    trailing_pct = tracking.get('trailing_pct', 0.03)
                    new_stop = current_price * (1 - trailing_pct)
                    
                    # Only move stop up, never down
                    old_stop = tracking['stop_loss']
                    if new_stop > old_stop:
                        tracking['stop_loss'] = new_stop
                        gain_from_entry = ((current_price / tracking.get('entry_price', current_price)) - 1) * 100
                        self.logger.info(
                            f"📈 {symbol} trailing stop raised: ${old_stop:.2f} → ${new_stop:.2f} "
                            f"(price ${old_highest:.2f} → ${current_price:.2f}, +{gain_from_entry:.1f}%)"
                        )

            # Check stop loss trigger
            stop_loss = tracking.get('stop_loss')
            if stop_loss and current_price <= stop_loss:
                entry_price = tracking.get('entry_price', stop_loss)
                pnl_pct = ((current_price / entry_price) - 1) * 100
                
                triggers.append({
                    'symbol': symbol,
                    'action': 'STOP_LOSS',
                    'trigger_price': stop_loss,
                    'current_price': current_price,
                    'qty': position.qty,
                    'loss': position.unrealized_pl,
                    'pnl_pct': pnl_pct,
                    'reason': f"Stop loss triggered: ${current_price:.2f} <= ${stop_loss:.2f} ({pnl_pct:+.1f}%)"
                })
                self.logger.warning(
                    f"🛑 STOP LOSS TRIGGERED: {symbol} at ${current_price:.2f} "
                    f"(stop was ${stop_loss:.2f})"
                )

            # Check take profit (if set)
            take_profit = tracking.get('take_profit')
            if take_profit and current_price >= take_profit:
                entry_price = tracking.get('entry_price', take_profit)
                pnl_pct = ((current_price / entry_price) - 1) * 100
                
                triggers.append({
                    'symbol': symbol,
                    'action': 'TAKE_PROFIT',
                    'trigger_price': take_profit,
                    'current_price': current_price,
                    'qty': position.qty,
                    'profit': position.unrealized_pl,
                    'pnl_pct': pnl_pct,
                    'reason': f"Take profit triggered: ${current_price:.2f} >= ${take_profit:.2f} ({pnl_pct:+.1f}%)"
                })
                self.logger.info(
                    f"🎯 TAKE PROFIT TRIGGERED: {symbol} at ${current_price:.2f} "
                    f"(target was ${take_profit:.2f})"
                )

        return triggers

    async def execute_stop_loss(self, symbol: str, reason: str = "Stop loss triggered") -> ExecutionResult:
        """Execute stop loss - close entire position"""
        result = await self.close_position(symbol, reason)

        # Remove from tracking
        if symbol in self._tracked_stops:
            del self._tracked_stops[symbol]

        return result

    async def check_daily_loss_limit(self) -> Tuple[bool, float]:
        """
        Check if daily loss limit has been exceeded.
        Returns (is_exceeded, current_loss_pct)
        """
        # Reset daily tracking at start of new day
        now = datetime.now()
        if self._daily_pnl_start is None or self._daily_pnl_start.date() != now.date():
            self._daily_pnl_start = now
            self._daily_pnl = 0.0

        try:
            account = await self.client.get_account()
            # Calculate today's P&L
            daily_pnl = account.equity - account.last_equity
            daily_pnl_pct = daily_pnl / account.last_equity if account.last_equity > 0 else 0

            self._daily_pnl = daily_pnl

            # Check against limit
            if daily_pnl_pct < -self.risk.max_daily_loss_pct:
                self.logger.error(
                    f"🚨 DAILY LOSS LIMIT EXCEEDED: {daily_pnl_pct*100:.2f}% "
                    f"(limit: -{self.risk.max_daily_loss_pct*100:.0f}%)"
                )
                return True, daily_pnl_pct

            return False, daily_pnl_pct

        except Exception as e:
            self.logger.error(f"Failed to check daily loss: {e}")
            return False, 0.0

    def get_daily_pnl(self) -> float:
        """Get current daily P&L"""
        return self._daily_pnl

    async def auto_track_existing_positions(self, default_stop_pct: float = 0.03) -> int:
        """
        Auto-track all existing positions with trailing stops.
        Called on startup to ensure all positions have protection.

        Args:
            default_stop_pct: Default stop-loss percentage below entry (e.g., 0.03 = 3%)

        Returns:
            Number of positions now being tracked
        """
        try:
            positions = await self.client.get_positions()
            tracked_count = 0

            if not positions:
                self.logger.info("📭 No existing positions to track")
                return 0

            self.logger.info(f"🔄 Auto-tracking {len(positions)} existing positions...")

            for position in positions:
                symbol = position.symbol

                # Skip if already tracked
                if symbol in self._tracked_stops:
                    self.logger.debug(f"  {symbol}: already tracked")
                    continue

                # Use entry price from position
                entry_price = position.avg_entry_price
                current_price = position.current_price
                qty = position.qty

                # Calculate stop-loss based on entry price (not current!)
                # If position is already down, use a tighter stop from current price
                pnl_pct = position.unrealized_plpc  # Already a decimal

                if pnl_pct < -0.02:  # Already down >2%
                    # Use tighter stop from current price to limit further losses
                    stop_price = current_price * (1 - 0.02)  # 2% below current
                    trailing_pct = 0.02
                    self.logger.warning(
                        f"  ⚠️ {symbol}: DOWN {pnl_pct*100:.1f}%, setting tight stop at ${stop_price:.2f} (2% below current)"
                    )
                elif pnl_pct > 0.02:  # Up >2%
                    # Lock in some gains with trailing stop from current price
                    stop_price = current_price * (1 - default_stop_pct)
                    trailing_pct = default_stop_pct
                    self.logger.info(
                        f"  ✅ {symbol}: UP {pnl_pct*100:.1f}%, trailing stop at ${stop_price:.2f} (3% below current)"
                    )
                else:
                    # Near breakeven - use standard stop from entry
                    stop_price = entry_price * (1 - default_stop_pct)
                    trailing_pct = default_stop_pct
                    self.logger.info(
                        f"  📍 {symbol}: {pnl_pct*100:+.1f}%, stop at ${stop_price:.2f} (3% below entry ${entry_price:.2f})"
                    )

                # Track with trailing stop
                self._tracked_stops[symbol] = {
                    'stop_loss': stop_price,
                    'qty': qty,
                    'entry_price': entry_price,
                    'highest_price': max(entry_price, current_price),
                    'trailing_pct': trailing_pct,
                    'is_trailing': True,
                }
                tracked_count += 1

            self.logger.info(f"✅ Now tracking {tracked_count} positions with trailing stops")
            return tracked_count

        except Exception as e:
            self.logger.error(f"Failed to auto-track positions: {e}")
            return 0

    # ==================== TIME-BASED STOPS ====================

    def add_time_stop(
        self,
        symbol: str,
        entry_time: datetime,
        max_hold_minutes: int,
        min_profit_pct: float = 0.005,
    ):
        """
        Add time-based stop to a position.

        If position hasn't reached min_profit_pct within max_hold_minutes,
        it will be flagged for exit.

        Args:
            symbol: Stock symbol
            entry_time: When the position was opened
            max_hold_minutes: Maximum time to hold without profit
            min_profit_pct: Minimum profit to avoid time stop (default 0.5%)
        """
        if symbol not in self._tracked_stops:
            self._tracked_stops[symbol] = {}

        self._tracked_stops[symbol]['entry_time'] = entry_time
        self._tracked_stops[symbol]['max_hold_minutes'] = max_hold_minutes
        self._tracked_stops[symbol]['min_profit_pct'] = min_profit_pct
        self._tracked_stops[symbol]['time_stop_enabled'] = True

        self.logger.info(
            f"⏱️ Time stop added for {symbol}: "
            f"{max_hold_minutes}min max hold, "
            f"need >{min_profit_pct*100:.1f}% profit to avoid exit"
        )

    async def check_time_stops(self) -> List[Dict]:
        """
        Check all positions for time-based stop triggers.

        Returns list of positions that should be exited due to time.
        """
        triggers = []
        now = datetime.now()

        if not self._tracked_stops:
            return triggers

        positions = await self.client.get_positions()
        position_map = {p.symbol: p for p in positions}

        for symbol, tracking in list(self._tracked_stops.items()):
            # Skip if time stop not enabled
            if not tracking.get('time_stop_enabled', False):
                continue

            # Skip if position no longer exists
            if symbol not in position_map:
                continue

            position = position_map[symbol]
            entry_time = tracking.get('entry_time')
            max_hold = tracking.get('max_hold_minutes', 60)
            min_profit = tracking.get('min_profit_pct', 0.005)

            if not entry_time:
                continue

            # Calculate time held
            time_held = (now - entry_time).total_seconds() / 60  # minutes

            # Check if time exceeded
            if time_held >= max_hold:
                # Check if profitable enough to keep
                pnl_pct = position.unrealized_plpc

                if pnl_pct < min_profit:
                    triggers.append({
                        'symbol': symbol,
                        'action': 'TIME_STOP',
                        'time_held_minutes': time_held,
                        'max_hold_minutes': max_hold,
                        'current_pnl_pct': pnl_pct,
                        'min_profit_pct': min_profit,
                        'current_price': position.current_price,
                        'qty': position.qty,
                        'pnl': position.unrealized_pl,
                        'reason': (
                            f"Time stop: held {time_held:.0f}min (max {max_hold}min) "
                            f"with only {pnl_pct*100:+.2f}% gain (need >{min_profit*100:.1f}%)"
                        )
                    })
                    self.logger.warning(
                        f"⏱️ TIME STOP: {symbol} held {time_held:.0f}min "
                        f"with only {pnl_pct*100:+.2f}% - exiting"
                    )
                else:
                    # Profitable enough - disable time stop, let trailing handle it
                    tracking['time_stop_enabled'] = False
                    self.logger.info(
                        f"✅ {symbol} profitable ({pnl_pct*100:+.2f}%) after {time_held:.0f}min - "
                        f"time stop disabled, trailing stop active"
                    )

        return triggers

    async def check_all_stops(self) -> List[Dict]:
        """
        Check all stop types: price-based, trailing, and time-based.

        Returns combined list of all triggers.
        """
        triggers = []

        # Price-based stops (including trailing)
        price_triggers = await self.check_stop_losses()
        triggers.extend(price_triggers)

        # Time-based stops
        time_triggers = await self.check_time_stops()
        triggers.extend(time_triggers)

        return triggers

    def get_stop_summary(self) -> Dict:
        """Get summary of all stop tracking"""
        summary = {
            'total_tracked': len(self._tracked_stops),
            'positions': {}
        }

        for symbol, tracking in self._tracked_stops.items():
            summary['positions'][symbol] = {
                'stop_loss': tracking.get('stop_loss'),
                'take_profit': tracking.get('take_profit'),
                'is_trailing': tracking.get('is_trailing', False),
                'trailing_pct': tracking.get('trailing_pct'),
                'highest_price': tracking.get('highest_price'),
                'time_stop_enabled': tracking.get('time_stop_enabled', False),
                'max_hold_minutes': tracking.get('max_hold_minutes'),
                'entry_time': tracking.get('entry_time').isoformat() if tracking.get('entry_time') else None,
            }

        return summary
