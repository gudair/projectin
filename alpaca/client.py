"""
Alpaca API Client

Provides REST API access to Alpaca for account info, positions, and orders.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import httpx

from config.agent_config import AlpacaConfig, DEFAULT_CONFIG


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(Enum):
    DAY = "day"
    GTC = "gtc"  # Good til cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class OrderStatus(Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    PENDING_NEW = "pending_new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    REJECTED = "rejected"


@dataclass
class Account:
    """Alpaca account information"""
    id: str
    account_number: str
    status: str
    currency: str
    cash: float
    portfolio_value: float
    buying_power: float
    daytrading_buying_power: float
    pattern_day_trader: bool
    trade_suspended_by_user: bool
    trading_blocked: bool
    equity: float
    last_equity: float
    daytrade_count: int

    @classmethod
    def from_dict(cls, data: Dict) -> 'Account':
        return cls(
            id=data.get('id', ''),
            account_number=data.get('account_number', ''),
            status=data.get('status', ''),
            currency=data.get('currency', 'USD'),
            cash=float(data.get('cash', 0)),
            portfolio_value=float(data.get('portfolio_value', 0)),
            buying_power=float(data.get('buying_power', 0)),
            daytrading_buying_power=float(data.get('daytrading_buying_power', 0)),
            pattern_day_trader=data.get('pattern_day_trader', False),
            trade_suspended_by_user=data.get('trade_suspended_by_user', False),
            trading_blocked=data.get('trading_blocked', False),
            equity=float(data.get('equity', 0)),
            last_equity=float(data.get('last_equity', 0)),
            daytrade_count=int(data.get('daytrade_count', 0)),
        )


@dataclass
class Position:
    """Alpaca position"""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_plpc: float
    side: str

    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        return cls(
            symbol=data.get('symbol', ''),
            qty=float(data.get('qty', 0)),
            avg_entry_price=float(data.get('avg_entry_price', 0)),
            current_price=float(data.get('current_price', 0)),
            market_value=float(data.get('market_value', 0)),
            cost_basis=float(data.get('cost_basis', 0)),
            unrealized_pl=float(data.get('unrealized_pl', 0)),
            unrealized_plpc=float(data.get('unrealized_plpc', 0)),
            side=data.get('side', 'long'),
        )


@dataclass
class Order:
    """Alpaca order"""
    id: str
    client_order_id: str
    symbol: str
    qty: float
    filled_qty: float
    side: str
    type: str
    time_in_force: str
    limit_price: Optional[float]
    stop_price: Optional[float]
    filled_avg_price: Optional[float]
    status: str
    created_at: datetime
    filled_at: Optional[datetime]

    @classmethod
    def from_dict(cls, data: Dict) -> 'Order':
        created_at = data.get('created_at', '')
        filled_at = data.get('filled_at')

        return cls(
            id=data.get('id', ''),
            client_order_id=data.get('client_order_id', ''),
            symbol=data.get('symbol', ''),
            qty=float(data.get('qty', 0)),
            filled_qty=float(data.get('filled_qty', 0)),
            side=data.get('side', ''),
            type=data.get('type', ''),
            time_in_force=data.get('time_in_force', ''),
            limit_price=float(data['limit_price']) if data.get('limit_price') else None,
            stop_price=float(data['stop_price']) if data.get('stop_price') else None,
            filled_avg_price=float(data['filled_avg_price']) if data.get('filled_avg_price') else None,
            status=data.get('status', ''),
            created_at=datetime.fromisoformat(created_at.replace('Z', '+00:00')) if created_at else datetime.now(),
            filled_at=datetime.fromisoformat(filled_at.replace('Z', '+00:00')) if filled_at else None,
        )


@dataclass
class Quote:
    """Market quote"""
    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    last_price: float
    last_size: int
    timestamp: datetime

    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price

    @property
    def spread_pct(self) -> float:
        if self.mid_price == 0:
            return 0
        return (self.spread / self.mid_price) * 100


@dataclass
class Bar:
    """OHLCV bar"""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    vwap: Optional[float] = None
    trade_count: Optional[int] = None


class AlpacaClient:
    """Alpaca REST API Client"""

    def __init__(self, config: Optional[AlpacaConfig] = None):
        self.config = config or DEFAULT_CONFIG.alpaca
        self.logger = logging.getLogger(__name__)

        self._headers = {
            'APCA-API-KEY-ID': self.config.api_key,
            'APCA-API-SECRET-KEY': self.config.secret_key,
        }

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        silent_errors: list = None,
        max_retries: int = 3,
        **kwargs
    ) -> Dict:
        """Make API request with retry and exponential backoff

        Args:
            silent_errors: List of HTTP status codes that are expected and shouldn't be logged as errors
            max_retries: Maximum number of retries for network errors (default: 3)
        """
        client = await self._get_client()
        silent_errors = silent_errors or []

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                # Handle empty responses (e.g., 204 No Content from DELETE)
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()

            except httpx.HTTPStatusError as e:
                # HTTP errors (4xx, 5xx) - don't retry, these are API responses
                if e.response.status_code not in silent_errors:
                    self.logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
                raise

            except (httpx.ConnectError, httpx.TimeoutException, OSError) as e:
                # Network errors - retry with backoff
                last_exception = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    self.logger.warning(
                        f"Network error (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Network error after {max_retries + 1} attempts: {e}")

            except Exception as e:
                # Other unexpected errors - don't retry
                self.logger.error(f"Request error: {e}")
                raise

        # If we get here, all retries failed
        raise last_exception

    # Account endpoints
    async def get_account(self) -> Account:
        """Get account information"""
        url = f"{self.config.base_url}/v2/account"
        data = await self._request('GET', url)
        return Account.from_dict(data)

    async def get_positions(self) -> List[Position]:
        """Get all open positions"""
        url = f"{self.config.base_url}/v2/positions"
        data = await self._request('GET', url)
        return [Position.from_dict(p) for p in data]

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol. Returns None if no position exists."""
        try:
            url = f"{self.config.base_url}/v2/positions/{symbol}"
            data = await self._request('GET', url, silent_errors=[404])
            return Position.from_dict(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None  # No position - expected behavior
            raise

    async def close_position_atomic(self, symbol: str) -> Optional[Order]:
        """Close entire position atomically using DELETE /v2/positions/{symbol}.

        This is Alpaca's recommended way to liquidate a position.
        Returns the liquidation order, or None if no position exists.
        """
        try:
            url = f"{self.config.base_url}/v2/positions/{symbol}"
            data = await self._request('DELETE', url, silent_errors=[404])
            if not data:
                return None
            return Order.from_dict(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def close_all_positions_atomic(self) -> List[Order]:
        """Close all positions atomically using DELETE /v2/positions."""
        url = f"{self.config.base_url}/v2/positions"
        data = await self._request('DELETE', url)
        if not data:
            return []
        return [Order.from_dict(o) for o in data]

    # Order endpoints
    async def get_orders(
        self,
        status: str = 'open',
        limit: int = 100,
        direction: str = 'desc'
    ) -> List[Order]:
        """Get orders"""
        url = f"{self.config.base_url}/v2/orders"
        params = {
            'status': status,
            'limit': limit,
            'direction': direction,
        }
        data = await self._request('GET', url, params=params)
        return [Order.from_dict(o) for o in data]

    async def get_order(self, order_id: str) -> Order:
        """Get specific order by ID"""
        url = f"{self.config.base_url}/v2/orders/{order_id}"
        data = await self._request('GET', url)
        return Order.from_dict(data)

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Submit a new order"""
        url = f"{self.config.base_url}/v2/orders"

        order_data = {
            'symbol': symbol,
            'qty': str(qty),
            'side': side.value,
            'type': order_type.value,
            'time_in_force': time_in_force.value,
        }

        if limit_price is not None:
            order_data['limit_price'] = str(limit_price)

        if stop_price is not None:
            order_data['stop_price'] = str(stop_price)

        if client_order_id:
            order_data['client_order_id'] = client_order_id

        self.logger.info(f"Submitting order: {order_data}")
        data = await self._request('POST', url, json=order_data)
        return Order.from_dict(data)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        url = f"{self.config.base_url}/v2/orders/{order_id}"
        try:
            await self._request('DELETE', url)
            return True
        except Exception as e:
            self.logger.error(f"Error canceling order {order_id}: {e}")
            return False

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders"""
        url = f"{self.config.base_url}/v2/orders"
        try:
            data = await self._request('DELETE', url)
            return len(data) if isinstance(data, list) else 0
        except Exception as e:
            self.logger.error(f"Error canceling all orders: {e}")
            return 0

    # Market data endpoints
    async def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest quote for symbol"""
        url = f"{self.config.data_url}/v2/stocks/{symbol}/quotes/latest"
        # Use IEX feed (free) instead of SIP (paid)
        params = {'feed': 'iex'}
        try:
            data = await self._request('GET', url, params=params)
            quote_data = data.get('quote', {})

            return Quote(
                symbol=symbol,
                bid_price=float(quote_data.get('bp', 0)),
                bid_size=int(quote_data.get('bs', 0)),
                ask_price=float(quote_data.get('ap', 0)),
                ask_size=int(quote_data.get('as', 0)),
                last_price=float(quote_data.get('bp', 0)),  # Use bid as proxy
                last_size=0,
                timestamp=datetime.now(),
            )
        except Exception as e:
            self.logger.error(f"Error getting quote for {symbol}: {e}")
            return None

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get latest quotes for multiple symbols"""
        url = f"{self.config.data_url}/v2/stocks/quotes/latest"
        # Use IEX feed (free) instead of SIP (paid)
        params = {'symbols': ','.join(symbols), 'feed': 'iex'}

        try:
            data = await self._request('GET', url, params=params)
            quotes = {}

            for symbol, quote_data in data.get('quotes', {}).items():
                quotes[symbol] = Quote(
                    symbol=symbol,
                    bid_price=float(quote_data.get('bp', 0)),
                    bid_size=int(quote_data.get('bs', 0)),
                    ask_price=float(quote_data.get('ap', 0)),
                    ask_size=int(quote_data.get('as', 0)),
                    last_price=float(quote_data.get('bp', 0)),
                    last_size=0,
                    timestamp=datetime.now(),
                )

            return quotes
        except Exception as e:
            self.logger.error(f"Error getting quotes: {e}")
            return {}

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = '1D',
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Bar]:
        """Get historical bars"""
        url = f"{self.config.data_url}/v2/stocks/{symbol}/bars"

        params = {
            'timeframe': timeframe,
            'limit': limit,
            'feed': 'iex',  # Use IEX feed (free) instead of SIP (paid)
        }

        if start:
            # Alpaca wants RFC3339 (with Z) or just date (YYYY-MM-DD)
            params['start'] = start.strftime('%Y-%m-%d')
        if end:
            params['end'] = end.strftime('%Y-%m-%d')

        try:
            data = await self._request('GET', url, params=params)
            bars = []

            # Handle None or missing 'bars' key
            bars_data = data.get('bars') if data else None
            if not bars_data:
                return []

            for bar_data in bars_data:
                bars.append(Bar(
                    symbol=symbol,
                    open=float(bar_data.get('o', 0)),
                    high=float(bar_data.get('h', 0)),
                    low=float(bar_data.get('l', 0)),
                    close=float(bar_data.get('c', 0)),
                    volume=int(bar_data.get('v', 0)),
                    timestamp=datetime.fromisoformat(bar_data.get('t', '').replace('Z', '+00:00')),
                    vwap=float(bar_data.get('vw', 0)) if bar_data.get('vw') else None,
                    trade_count=int(bar_data.get('n', 0)) if bar_data.get('n') else None,
                ))

            return bars
        except Exception as e:
            self.logger.error(f"Error getting bars for {symbol}: {e}")
            return []

    async def get_assets(
        self,
        status: str = 'active',
        asset_class: str = 'us_equity',
    ) -> List:
        """
        Get all tradeable assets from Alpaca.

        Args:
            status: 'active' or 'inactive'
            asset_class: 'us_equity', 'crypto', etc.

        Returns:
            List of asset objects with symbol, exchange, tradable, etc.
        """
        url = f"{self.config.base_url}/v2/assets"

        params = {
            'status': status,
            'asset_class': asset_class,
        }

        try:
            data = await self._request('GET', url, params=params)

            if not data:
                return []

            # Convert to simple objects
            from dataclasses import dataclass

            @dataclass
            class Asset:
                symbol: str
                name: str
                exchange: str
                asset_class: str
                tradable: bool
                status: str
                fractionable: bool = False
                marginable: bool = False

            assets = []
            for item in data:
                assets.append(Asset(
                    symbol=item.get('symbol', ''),
                    name=item.get('name', ''),
                    exchange=item.get('exchange', ''),
                    asset_class=item.get('class', ''),
                    tradable=item.get('tradable', False),
                    status=item.get('status', ''),
                    fractionable=item.get('fractionable', False),
                    marginable=item.get('marginable', False),
                ))

            self.logger.info(f"Fetched {len(assets)} assets from Alpaca")
            return assets

        except Exception as e:
            self.logger.error(f"Error getting assets: {e}")
            return []

    # Market status
    async def get_clock(self) -> Dict:
        """Get market clock"""
        url = f"{self.config.base_url}/v2/clock"
        return await self._request('GET', url)

    async def is_market_open(self) -> bool:
        """Check if market is currently open"""
        clock = await self.get_clock()
        return clock.get('is_open', False)

    # Utility methods
    def test_connection(self) -> bool:
        """Test API connection synchronously"""
        import asyncio

        async def _test():
            try:
                await self.get_account()
                return True
            except Exception as e:
                self.logger.error(f"Connection test failed: {e}")
                return False
            finally:
                await self.close()

        return asyncio.run(_test())


# Convenience function for quick tests
def test_alpaca_connection() -> bool:
    """Quick test of Alpaca connection"""
    client = AlpacaClient()
    return client.test_connection()
