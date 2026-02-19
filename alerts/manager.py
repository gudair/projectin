"""
Alert Manager

Manages trading alerts queue and dispatch for CLI display.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
import threading
import uuid

from config.agent_config import AlertLevel


class AlertAction(Enum):
    """User response to alert"""
    CONFIRM = "confirm"
    REJECT = "reject"
    MORE_INFO = "more_info"
    MODIFY = "modify"
    SKIP = "skip"


@dataclass
class TradingOpportunity:
    """Trading opportunity details"""
    symbol: str
    action: str  # 'BUY' or 'SELL'
    current_price: float
    target_price: float
    stop_loss: float
    position_size: float  # Dollar amount
    shares: float
    confidence: float  # 0-1
    risk_reward_ratio: float
    reasoning: str
    similar_trades_win_rate: Optional[float] = None
    technical_signals: Dict[str, Any] = field(default_factory=dict)
    news_sentiment: Optional[str] = None
    market_context: Optional[str] = None


@dataclass
class Alert:
    """Trading alert"""
    id: str
    level: AlertLevel
    opportunity: TradingOpportunity
    created_at: datetime
    expires_at: Optional[datetime] = None
    user_response: Optional[AlertAction] = None
    response_timestamp: Optional[datetime] = None
    notes: str = ""

    @classmethod
    def create(
        cls,
        level: AlertLevel,
        opportunity: TradingOpportunity,
        expires_in_seconds: Optional[int] = None,
    ) -> 'Alert':
        """Factory method to create alert"""
        now = datetime.now()
        expires_at = None
        if expires_in_seconds:
            from datetime import timedelta
            expires_at = now + timedelta(seconds=expires_in_seconds)

        return cls(
            id=str(uuid.uuid4())[:8],
            level=level,
            opportunity=opportunity,
            created_at=now,
            expires_at=expires_at,
        )

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.user_response is None and not self.is_expired

    @property
    def time_until_expiry(self) -> Optional[int]:
        """Seconds until expiry"""
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now()
        return max(0, int(delta.total_seconds()))

    def respond(self, action: AlertAction, notes: str = ""):
        """Record user response"""
        self.user_response = action
        self.response_timestamp = datetime.now()
        self.notes = notes


class AlertQueue:
    """Thread-safe alert queue"""

    def __init__(self, max_size: int = 100):
        self._queue: Queue = Queue(maxsize=max_size)
        self._history: List[Alert] = []
        self._lock = threading.Lock()
        self._max_history = 1000

    def put(self, alert: Alert) -> bool:
        """Add alert to queue"""
        try:
            self._queue.put_nowait(alert)
            return True
        except Exception:
            return False

    def get(self, timeout: float = 0.1) -> Optional[Alert]:
        """Get next alert from queue"""
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def peek(self) -> Optional[Alert]:
        """Peek at next alert without removing"""
        with self._lock:
            if not self._queue.empty():
                # This is a bit hacky but Queue doesn't have peek
                alert = self._queue.get_nowait()
                # Put it back at front (not ideal but works for small queues)
                temp_queue = Queue()
                temp_queue.put(alert)
                while not self._queue.empty():
                    temp_queue.put(self._queue.get_nowait())
                while not temp_queue.empty():
                    self._queue.put(temp_queue.get_nowait())
                return alert
            return None

    def size(self) -> int:
        """Current queue size"""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self._queue.empty()

    def clear(self):
        """Clear all alerts from queue"""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Empty:
                    break

    def add_to_history(self, alert: Alert):
        """Add processed alert to history"""
        with self._lock:
            self._history.append(alert)
            # Trim history if needed
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def get_history(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        action: Optional[AlertAction] = None,
    ) -> List[Alert]:
        """Get alert history with optional filters"""
        with self._lock:
            filtered = self._history

            if symbol:
                filtered = [a for a in filtered if a.opportunity.symbol == symbol]

            if action:
                filtered = [a for a in filtered if a.user_response == action]

            return filtered[-limit:]


class AlertManager:
    """
    Manages the alert lifecycle:
    - Creates alerts from trading opportunities
    - Queues alerts for CLI display
    - Handles user responses
    - Tracks alert history
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.queue = AlertQueue()
        self._callbacks: Dict[str, List[Callable]] = {
            'on_alert': [],
            'on_response': [],
            'on_expire': [],
        }
        self._running = False
        self._process_thread: Optional[threading.Thread] = None

    def create_alert(
        self,
        level: AlertLevel,
        symbol: str,
        action: str,
        current_price: float,
        target_price: float,
        stop_loss: float,
        position_size: float,
        confidence: float,
        reasoning: str,
        expires_in_seconds: Optional[int] = 300,  # 5 minute default
        **kwargs
    ) -> Alert:
        """Create and queue a new alert"""
        # Calculate derived values
        shares = position_size / current_price if current_price > 0 else 0

        if action.upper() == 'BUY':
            risk = current_price - stop_loss
            reward = target_price - current_price
        else:
            risk = stop_loss - current_price
            reward = current_price - target_price

        risk_reward = reward / risk if risk > 0 else 0

        opportunity = TradingOpportunity(
            symbol=symbol,
            action=action.upper(),
            current_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
            position_size=position_size,
            shares=shares,
            confidence=confidence,
            risk_reward_ratio=risk_reward,
            reasoning=reasoning,
            similar_trades_win_rate=kwargs.get('win_rate'),
            technical_signals=kwargs.get('technical_signals', {}),
            news_sentiment=kwargs.get('news_sentiment'),
            market_context=kwargs.get('market_context'),
        )

        alert = Alert.create(
            level=level,
            opportunity=opportunity,
            expires_in_seconds=expires_in_seconds,
        )

        # Queue the alert
        if self.queue.put(alert):
            self.logger.info(f"Alert created: {alert.id} - {action} {symbol}")
            self._trigger_callbacks('on_alert', alert)
        else:
            self.logger.warning(f"Failed to queue alert: {alert.id}")

        return alert

    def respond_to_alert(self, alert: Alert, action: AlertAction, notes: str = ""):
        """Record user response to alert"""
        alert.respond(action, notes)
        self.queue.add_to_history(alert)
        self.logger.info(f"Alert {alert.id} responded: {action.value}")
        self._trigger_callbacks('on_response', alert, action)

    def get_pending_alert(self) -> Optional[Alert]:
        """Get next pending alert"""
        while True:
            alert = self.queue.get(timeout=0.1)
            if alert is None:
                return None

            # Skip expired alerts
            if alert.is_expired:
                self.logger.info(f"Alert {alert.id} expired")
                alert.respond(AlertAction.SKIP, "Expired")
                self.queue.add_to_history(alert)
                self._trigger_callbacks('on_expire', alert)
                continue

            return alert

    def has_pending_alerts(self) -> bool:
        """Check if there are pending alerts"""
        return not self.queue.is_empty()

    def pending_count(self) -> int:
        """Get count of pending alerts"""
        return self.queue.size()

    def register_callback(self, event: str, callback: Callable):
        """Register callback for alert events"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _trigger_callbacks(self, event: str, *args):
        """Trigger registered callbacks"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args)
            except Exception as e:
                self.logger.error(f"Callback error for {event}: {e}")

    def get_stats(self) -> Dict:
        """Get alert statistics"""
        history = self.queue.get_history(limit=500)

        total = len(history)
        confirmed = len([a for a in history if a.user_response == AlertAction.CONFIRM])
        rejected = len([a for a in history if a.user_response == AlertAction.REJECT])
        expired = len([a for a in history if a.user_response == AlertAction.SKIP])

        return {
            'total_alerts': total,
            'confirmed': confirmed,
            'rejected': rejected,
            'expired': expired,
            'pending': self.pending_count(),
            'confirmation_rate': confirmed / total if total > 0 else 0,
        }

    def clear_pending(self):
        """Clear all pending alerts"""
        self.queue.clear()
        self.logger.info("Cleared all pending alerts")
