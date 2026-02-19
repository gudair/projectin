"""
Alpaca WebSocket Streaming

Real-time market data streaming via Alpaca WebSocket.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed

from config.agent_config import AlpacaConfig, DEFAULT_CONFIG


class StreamType(Enum):
    TRADES = "trades"
    QUOTES = "quotes"
    BARS = "bars"


@dataclass
class StreamQuote:
    """Real-time quote from stream"""
    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: datetime
    conditions: List[str]

    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price


@dataclass
class StreamTrade:
    """Real-time trade from stream"""
    symbol: str
    price: float
    size: int
    timestamp: datetime
    exchange: str
    conditions: List[str]
    tape: str


@dataclass
class StreamBar:
    """Real-time bar from stream"""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    vwap: float
    trade_count: int


class AlpacaStreamer:
    """
    Real-time market data streaming via Alpaca WebSocket.

    Supports:
    - Quotes (bid/ask)
    - Trades (executions)
    - Bars (OHLCV aggregates)
    """

    def __init__(self, config: Optional[AlpacaConfig] = None):
        self.config = config or DEFAULT_CONFIG.alpaca
        self.logger = logging.getLogger(__name__)

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._authenticated = False
        self._subscribed_symbols: Dict[StreamType, Set[str]] = {
            StreamType.TRADES: set(),
            StreamType.QUOTES: set(),
            StreamType.BARS: set(),
        }

        # Callbacks
        self._quote_callbacks: List[Callable[[StreamQuote], Any]] = []
        self._trade_callbacks: List[Callable[[StreamTrade], Any]] = []
        self._bar_callbacks: List[Callable[[StreamBar], Any]] = []
        self._error_callbacks: List[Callable[[Exception], Any]] = []

        # Connection settings
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    def on_quote(self, callback: Callable[[StreamQuote], Any]):
        """Register quote callback"""
        self._quote_callbacks.append(callback)

    def on_trade(self, callback: Callable[[StreamTrade], Any]):
        """Register trade callback"""
        self._trade_callbacks.append(callback)

    def on_bar(self, callback: Callable[[StreamBar], Any]):
        """Register bar callback"""
        self._bar_callbacks.append(callback)

    def on_error(self, callback: Callable[[Exception], Any]):
        """Register error callback"""
        self._error_callbacks.append(callback)

    async def connect(self):
        """Connect to WebSocket stream"""
        self.logger.info("Connecting to Alpaca stream...")

        try:
            self._ws = await websockets.connect(
                self.config.stream_url,
                ping_interval=20,
                ping_timeout=10,
            )

            # Wait for welcome message
            welcome = await self._ws.recv()
            welcome_data = json.loads(welcome)
            self.logger.debug(f"Received welcome: {welcome_data}")

            # Authenticate
            await self._authenticate()

            self._running = True
            self._reconnect_attempts = 0
            self.logger.info("Connected to Alpaca stream")

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            raise

    async def _authenticate(self):
        """Authenticate with API keys"""
        auth_msg = {
            "action": "auth",
            "key": self.config.api_key,
            "secret": self.config.secret_key,
        }

        await self._ws.send(json.dumps(auth_msg))
        response = await self._ws.recv()
        response_data = json.loads(response)

        if isinstance(response_data, list):
            for msg in response_data:
                if msg.get("T") == "error":
                    raise Exception(f"Authentication error: {msg.get('msg')}")
                if msg.get("T") == "success" and msg.get("msg") == "authenticated":
                    self._authenticated = True
                    self.logger.info("Authenticated successfully")
                    return

        raise Exception("Authentication failed - unexpected response")

    async def subscribe(
        self,
        symbols: List[str],
        stream_types: List[StreamType] = None
    ):
        """Subscribe to symbols"""
        if not self._ws or not self._authenticated:
            raise Exception("Not connected or authenticated")

        # Skip if no symbols to subscribe (dynamic mode starts empty)
        if not symbols:
            self.logger.debug("No symbols to subscribe, skipping")
            return

        if stream_types is None:
            stream_types = [StreamType.QUOTES, StreamType.TRADES]

        subscribe_msg = {"action": "subscribe"}

        for stream_type in stream_types:
            self._subscribed_symbols[stream_type].update(symbols)

            if stream_type == StreamType.QUOTES:
                subscribe_msg["quotes"] = list(self._subscribed_symbols[StreamType.QUOTES])
            elif stream_type == StreamType.TRADES:
                subscribe_msg["trades"] = list(self._subscribed_symbols[StreamType.TRADES])
            elif stream_type == StreamType.BARS:
                subscribe_msg["bars"] = list(self._subscribed_symbols[StreamType.BARS])

        await self._ws.send(json.dumps(subscribe_msg))
        self.logger.info(f"Subscribed to {len(symbols)} symbols")

    async def unsubscribe(
        self,
        symbols: List[str],
        stream_types: List[StreamType] = None
    ):
        """Unsubscribe from symbols"""
        if not self._ws or not self._authenticated:
            return

        if stream_types is None:
            stream_types = [StreamType.QUOTES, StreamType.TRADES, StreamType.BARS]

        unsubscribe_msg = {"action": "unsubscribe"}

        for stream_type in stream_types:
            self._subscribed_symbols[stream_type].difference_update(symbols)

            if stream_type == StreamType.QUOTES:
                unsubscribe_msg["quotes"] = symbols
            elif stream_type == StreamType.TRADES:
                unsubscribe_msg["trades"] = symbols
            elif stream_type == StreamType.BARS:
                unsubscribe_msg["bars"] = symbols

        await self._ws.send(json.dumps(unsubscribe_msg))
        self.logger.info(f"Unsubscribed from {len(symbols)} symbols")

    async def run(self):
        """Main message processing loop"""
        while self._running:
            try:
                if not self._ws:
                    await self.connect()

                    # Resubscribe after reconnection
                    all_symbols = set()
                    for symbols in self._subscribed_symbols.values():
                        all_symbols.update(symbols)

                    if all_symbols:
                        await self.subscribe(list(all_symbols))

                message = await self._ws.recv()
                await self._process_message(message)

            except ConnectionClosed:
                self.logger.warning("WebSocket connection closed")
                await self._handle_reconnect()

            except Exception as e:
                self.logger.error(f"Stream error: {e}")
                self._trigger_error_callbacks(e)
                await self._handle_reconnect()

    async def _process_message(self, message: str):
        """Process incoming message"""
        try:
            data = json.loads(message)

            if not isinstance(data, list):
                data = [data]

            for msg in data:
                msg_type = msg.get("T")

                if msg_type == "q":  # Quote
                    quote = self._parse_quote(msg)
                    for callback in self._quote_callbacks:
                        try:
                            result = callback(quote)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            self.logger.error(f"Quote callback error: {e}")

                elif msg_type == "t":  # Trade
                    trade = self._parse_trade(msg)
                    for callback in self._trade_callbacks:
                        try:
                            result = callback(trade)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            self.logger.error(f"Trade callback error: {e}")

                elif msg_type == "b":  # Bar
                    bar = self._parse_bar(msg)
                    for callback in self._bar_callbacks:
                        try:
                            result = callback(bar)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            self.logger.error(f"Bar callback error: {e}")

                elif msg_type == "error":
                    self.logger.error(f"Stream error message: {msg.get('msg')}")

                elif msg_type == "subscription":
                    self.logger.debug(f"Subscription update: {msg}")

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")

    def _parse_quote(self, data: Dict) -> StreamQuote:
        """Parse quote message"""
        timestamp = data.get("t", "")
        if timestamp:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now()

        return StreamQuote(
            symbol=data.get("S", ""),
            bid_price=float(data.get("bp", 0)),
            bid_size=int(data.get("bs", 0)),
            ask_price=float(data.get("ap", 0)),
            ask_size=int(data.get("as", 0)),
            timestamp=timestamp,
            conditions=data.get("c", []),
        )

    def _parse_trade(self, data: Dict) -> StreamTrade:
        """Parse trade message"""
        timestamp = data.get("t", "")
        if timestamp:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now()

        return StreamTrade(
            symbol=data.get("S", ""),
            price=float(data.get("p", 0)),
            size=int(data.get("s", 0)),
            timestamp=timestamp,
            exchange=data.get("x", ""),
            conditions=data.get("c", []),
            tape=data.get("z", ""),
        )

    def _parse_bar(self, data: Dict) -> StreamBar:
        """Parse bar message"""
        timestamp = data.get("t", "")
        if timestamp:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now()

        return StreamBar(
            symbol=data.get("S", ""),
            open=float(data.get("o", 0)),
            high=float(data.get("h", 0)),
            low=float(data.get("l", 0)),
            close=float(data.get("c", 0)),
            volume=int(data.get("v", 0)),
            timestamp=timestamp,
            vwap=float(data.get("vw", 0)),
            trade_count=int(data.get("n", 0)),
        )

    async def _handle_reconnect(self):
        """Handle reconnection with exponential backoff"""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._authenticated = False
        self._reconnect_attempts += 1

        if self._reconnect_attempts > self._max_reconnect_attempts:
            self.logger.error("Max reconnect attempts reached")
            self._running = False
            return

        delay = min(
            self._reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            self._max_reconnect_delay
        )

        self.logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})")
        await asyncio.sleep(delay)

    def _trigger_error_callbacks(self, error: Exception):
        """Trigger error callbacks"""
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception as e:
                self.logger.error(f"Error callback failed: {e}")

    async def stop(self):
        """Stop the stream"""
        self._running = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self.logger.info("Stream stopped")

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._ws is not None and self._authenticated

    @property
    def subscribed_symbols(self) -> Dict[StreamType, Set[str]]:
        """Get subscribed symbols by type"""
        return self._subscribed_symbols.copy()


class QuoteAggregator:
    """
    Aggregates streaming quotes into actionable data.
    Provides last quote, VWAP, and trend detection.
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._quotes: Dict[str, List[StreamQuote]] = {}
        self._last_quotes: Dict[str, StreamQuote] = {}

    def add_quote(self, quote: StreamQuote):
        """Add quote to aggregator"""
        symbol = quote.symbol

        if symbol not in self._quotes:
            self._quotes[symbol] = []

        self._quotes[symbol].append(quote)
        self._last_quotes[symbol] = quote

        # Trim to window size
        if len(self._quotes[symbol]) > self.window_size:
            self._quotes[symbol] = self._quotes[symbol][-self.window_size:]

    def get_last_quote(self, symbol: str) -> Optional[StreamQuote]:
        """Get last quote for symbol"""
        return self._last_quotes.get(symbol)

    def get_mid_price(self, symbol: str) -> Optional[float]:
        """Get current mid price"""
        quote = self._last_quotes.get(symbol)
        return quote.mid_price if quote else None

    def get_spread_pct(self, symbol: str) -> Optional[float]:
        """Get current spread percentage"""
        quote = self._last_quotes.get(symbol)
        if quote and quote.mid_price > 0:
            return (quote.spread / quote.mid_price) * 100
        return None

    def get_vwap(self, symbol: str) -> Optional[float]:
        """Calculate VWAP from recent quotes"""
        quotes = self._quotes.get(symbol, [])
        if not quotes:
            return None

        total_value = sum(q.mid_price * (q.bid_size + q.ask_size) for q in quotes)
        total_volume = sum(q.bid_size + q.ask_size for q in quotes)

        return total_value / total_volume if total_volume > 0 else None

    def get_price_trend(self, symbol: str, periods: int = 10) -> Optional[str]:
        """Detect price trend from recent quotes"""
        quotes = self._quotes.get(symbol, [])
        if len(quotes) < periods:
            return None

        recent = quotes[-periods:]
        first_mid = recent[0].mid_price
        last_mid = recent[-1].mid_price

        change_pct = (last_mid - first_mid) / first_mid if first_mid > 0 else 0

        if change_pct > 0.001:
            return "UP"
        elif change_pct < -0.001:
            return "DOWN"
        return "FLAT"

    def get_symbols(self) -> List[str]:
        """Get all tracked symbols"""
        return list(self._quotes.keys())

    def clear(self, symbol: Optional[str] = None):
        """Clear quote history"""
        if symbol:
            self._quotes.pop(symbol, None)
            self._last_quotes.pop(symbol, None)
        else:
            self._quotes.clear()
            self._last_quotes.clear()
