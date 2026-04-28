"""
Mock Alpaca Client for Backtesting

Replaces the real AlpacaClient with one that returns historical data.
The agent doesn't know it's being fed historical data.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from decimal import Decimal

from backtest.historical_data import HistoricalDataLoader, BarData
from backtest.portfolio_tracker import PortfolioTracker

logger = logging.getLogger(__name__)


@dataclass
class MockQuote:
    """Simulates an Alpaca quote"""
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: int
    ask_size: int
    timestamp: datetime

    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2


@dataclass
class MockBar:
    """Simulates an Alpaca bar"""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    vwap: float = 0.0
    trade_count: int = 0


@dataclass
class MockPosition:
    """Simulates an Alpaca position"""
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float
    current_price: float
    side: str = "long"

    @property
    def quantity(self):
        return self.qty


@dataclass
class MockOrder:
    """Simulates an Alpaca order"""
    id: str
    symbol: str
    side: str
    qty: float
    filled_qty: float
    filled_avg_price: float
    status: str
    order_type: str
    time_in_force: str
    limit_price: Optional[float]
    stop_price: Optional[float]
    created_at: datetime
    filled_at: Optional[datetime]


@dataclass
class MockAccount:
    """Simulates an Alpaca account"""
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    status: str = "ACTIVE"
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    account_blocked: bool = False


class MockAlpacaClient:
    """
    Mock Alpaca client that returns historical data.

    This class has the same interface as the real AlpacaClient,
    allowing the agent to run without modification.
    """

    def __init__(
        self,
        data_loader: HistoricalDataLoader,
        portfolio_tracker: PortfolioTracker,
        initial_cash: float = 100000.0,
    ):
        self.data_loader = data_loader
        self.portfolio = portfolio_tracker
        self.initial_cash = initial_cash

        # Simulated time (controlled by BacktestEngine)
        self._current_time: datetime = datetime(2025, 10, 1, 9, 30)

        # Order tracking
        self._orders: Dict[str, MockOrder] = {}
        self._order_counter = 0

        # Market state
        self._market_open = False

    def set_current_time(self, dt: datetime):
        """Set the simulated current time"""
        self._current_time = dt
        # Update market open status based on time
        hour = dt.hour
        minute = dt.minute
        weekday = dt.weekday()

        # Market is open Mon-Fri 9:30 AM - 4:00 PM ET
        if weekday < 5:  # Monday = 0, Friday = 4
            if (hour == 9 and minute >= 30) or (10 <= hour < 16):
                self._market_open = True
            else:
                self._market_open = False
        else:
            self._market_open = False

    def get_current_time(self) -> datetime:
        """Get the simulated current time"""
        return self._current_time

    async def get_account(self) -> MockAccount:
        """Get simulated account info"""
        positions_value = self.portfolio.get_total_position_value(self._current_time)
        cash = self.portfolio.cash
        equity = cash + positions_value

        return MockAccount(
            equity=equity,
            cash=cash,
            buying_power=cash * 4,  # 4x margin for day trading
            portfolio_value=equity,
        )

    async def get_positions(self) -> List[MockPosition]:
        """Get current positions"""
        positions = []
        for symbol, pos in self.portfolio.positions.items():
            if pos['qty'] > 0:
                current_price = self.data_loader.get_price_at_time(symbol, self._current_time)
                if current_price is None:
                    current_price = pos['avg_price']

                market_value = pos['qty'] * current_price
                cost_basis = pos['qty'] * pos['avg_price']
                unrealized_pl = market_value - cost_basis
                unrealized_plpc = (unrealized_pl / cost_basis) if cost_basis > 0 else 0

                positions.append(MockPosition(
                    symbol=symbol,
                    qty=pos['qty'],
                    avg_entry_price=pos['avg_price'],
                    market_value=market_value,
                    unrealized_pl=unrealized_pl,
                    unrealized_plpc=unrealized_plpc,
                    current_price=current_price,
                ))

        return positions

    async def get_position(self, symbol: str) -> Optional[MockPosition]:
        """Get position for a specific symbol"""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None

    async def get_quote(self, symbol: str) -> Optional[MockQuote]:
        """Get current quote for a symbol"""
        bar = self.data_loader.get_bar_at_time(symbol, self._current_time)
        if bar is None:
            return None

        # Simulate bid/ask spread (0.02% spread)
        spread = bar.close * 0.0002
        return MockQuote(
            symbol=symbol,
            bid_price=bar.close - spread / 2,
            ask_price=bar.close + spread / 2,
            bid_size=100,
            ask_size=100,
            timestamp=self._current_time,
        )

    async def get_quotes(self, symbols: List[str]) -> Dict[str, MockQuote]:
        """Get quotes for multiple symbols"""
        quotes = {}
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                quotes[symbol] = quote
        return quotes

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Min",
        limit: int = 100,
    ) -> List[MockBar]:
        """Get historical bars for a symbol"""
        date_str = self._current_time.date().isoformat()

        if symbol not in self.data_loader._data_cache:
            return []

        if date_str not in self.data_loader._data_cache[symbol]:
            return []

        day_data = self.data_loader._data_cache[symbol][date_str]

        # Convert simulation time (ET) to UTC for comparison
        # ET is UTC-4 (EDT) during October
        current_time_utc = self._current_time + timedelta(hours=4)

        # Filter bars up to current time
        bars = []
        for bar in day_data.bars:
            # Remove timezone info for comparison
            bar_time = bar.timestamp.replace(tzinfo=None)
            if bar_time <= current_time_utc:
                bars.append(MockBar(
                    symbol=symbol,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    timestamp=bar.timestamp,
                    vwap=bar.vwap,
                    trade_count=bar.trade_count,
                ))

        # Return last N bars
        return bars[-limit:] if len(bars) > limit else bars

    async def get_latest_bar(self, symbol: str) -> Optional[MockBar]:
        """Get the latest bar for a symbol"""
        bars = await self.get_bars(symbol, limit=1)
        return bars[-1] if bars else None

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        **kwargs
    ) -> MockOrder:
        """Submit an order"""
        self._order_counter += 1
        order_id = f"backtest-{self._order_counter}"

        # Get current price
        current_price = self.data_loader.get_price_at_time(symbol, self._current_time)
        if current_price is None:
            raise ValueError(f"No price data for {symbol} at {self._current_time}")

        # Determine fill price
        if order_type == "market":
            fill_price = current_price
        elif order_type == "limit":
            if side == "buy" and limit_price >= current_price:
                fill_price = current_price
            elif side == "sell" and limit_price <= current_price:
                fill_price = current_price
            else:
                # Limit not met - order pending (simplified: just fill at limit)
                fill_price = limit_price
        else:
            fill_price = current_price

        # Execute the trade in portfolio tracker
        if side == "buy":
            success = self.portfolio.buy(symbol, qty, fill_price, self._current_time)
        else:
            success = self.portfolio.sell(symbol, qty, fill_price, self._current_time)

        status = "filled" if success else "rejected"

        order = MockOrder(
            id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            filled_qty=qty if success else 0,
            filled_avg_price=fill_price if success else 0,
            status=status,
            order_type=order_type,
            time_in_force=time_in_force,
            limit_price=limit_price,
            stop_price=stop_price,
            created_at=self._current_time,
            filled_at=self._current_time if success else None,
        )

        self._orders[order_id] = order
        return order

    async def get_order(self, order_id: str) -> Optional[MockOrder]:
        """Get order by ID"""
        return self._orders.get(order_id)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == "pending":
                order.status = "cancelled"
                return True
        return False

    async def is_market_open(self) -> bool:
        """Check if market is open"""
        return self._market_open

    async def get_clock(self) -> Dict[str, Any]:
        """Get market clock"""
        return {
            'is_open': self._market_open,
            'timestamp': self._current_time,
            'next_open': self._current_time.replace(hour=9, minute=30),
            'next_close': self._current_time.replace(hour=16, minute=0),
        }

    # Methods for discovery/scanning simulation

    async def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """Get top gaining stocks"""
        movers = self.data_loader.get_top_movers(self._current_time, top_n=limit * 2)
        gainers = [m for m in movers if m['change_pct'] > 0]
        return gainers[:limit]

    async def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """Get top losing stocks"""
        movers = self.data_loader.get_top_movers(self._current_time, top_n=limit * 2)
        losers = [m for m in movers if m['change_pct'] < 0]
        losers.sort(key=lambda x: x['change_pct'])  # Most negative first
        return losers[:limit]

    async def get_most_active(self, limit: int = 10) -> List[Dict]:
        """Get most active stocks by volume"""
        movers = self.data_loader.get_top_movers(self._current_time, top_n=100)
        movers.sort(key=lambda x: x['volume'], reverse=True)
        return movers[:limit]
