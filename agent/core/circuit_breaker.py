"""
Circuit Breaker System

Protects the trading agent from catastrophic losses by:
1. Limiting daily losses (stops trading if loss exceeds threshold)
2. Monitoring intraday win rate (stops if win rate drops below threshold)
3. Blacklisting stocks that consistently lose
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    # Daily loss limit
    max_daily_loss_pct: float = 0.02  # Stop trading if daily loss exceeds 2%

    # Win rate circuit breaker
    min_trades_for_winrate_check: int = 5  # Need at least 5 trades to check win rate
    min_win_rate_pct: float = 35.0  # Stop if win rate drops below 35%

    # Stock blacklist
    max_losses_per_stock: int = 2  # Blacklist stock after 2 losses in a day
    blacklist_duration_hours: int = 24  # How long to blacklist (hours)

    # Recovery thresholds
    consecutive_wins_to_resume: int = 3  # Resume normal trading after 3 consecutive wins

    # Partial shutdown
    reduce_size_after_losses: int = 3  # Reduce position size after 3 consecutive losses
    size_reduction_factor: float = 0.5  # Reduce to 50% of normal size


@dataclass
class DailyStats:
    """Track daily trading statistics"""
    date: date
    starting_equity: float
    current_equity: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0

    @property
    def win_rate(self) -> float:
        """Calculate current win rate"""
        if self.winning_trades + self.losing_trades == 0:
            return 100.0  # No completed trades = assume OK
        return (self.winning_trades / (self.winning_trades + self.losing_trades)) * 100

    @property
    def return_pct(self) -> float:
        """Calculate daily return percentage"""
        if self.starting_equity == 0:
            return 0.0
        return ((self.current_equity - self.starting_equity) / self.starting_equity) * 100


@dataclass
class StockStats:
    """Track per-stock statistics for the day"""
    symbol: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    last_trade_time: Optional[datetime] = None
    blacklisted_until: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit Breaker System

    Prevents catastrophic losses by monitoring and halting trading when:
    - Daily loss limit is exceeded
    - Win rate drops too low
    - Individual stocks are consistently losing
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.logger = logging.getLogger(__name__)

        # Daily tracking
        self._daily_stats: Optional[DailyStats] = None
        self._stock_stats: Dict[str, StockStats] = {}

        # Circuit breaker state
        self._circuit_open: bool = False  # True = trading halted
        self._circuit_open_reason: str = ""
        self._reduced_size_mode: bool = False

        # History for learning
        self._blacklist_history: List[Dict] = []

    def initialize_day(self, starting_equity: float):
        """Initialize tracking for a new trading day"""
        today = date.today()

        # Check if we need to reset for new day
        if self._daily_stats is None or self._daily_stats.date != today:
            self._daily_stats = DailyStats(
                date=today,
                starting_equity=starting_equity,
                current_equity=starting_equity,
                peak_equity=starting_equity,
            )
            self._stock_stats = {}
            self._circuit_open = False
            self._circuit_open_reason = ""
            self._reduced_size_mode = False

            self.logger.info(f"📊 Circuit Breaker initialized for {today}")
            self.logger.info(f"   Starting equity: ${starting_equity:,.2f}")
            self.logger.info(f"   Max daily loss: {self.config.max_daily_loss_pct * 100:.1f}%")
            self.logger.info(f"   Min win rate: {self.config.min_win_rate_pct:.0f}%")

    def record_trade(self, symbol: str, pnl: float, equity_after: float):
        """Record a completed trade and check circuit breakers"""
        if self._daily_stats is None:
            self.initialize_day(equity_after)

        # Update daily stats
        self._daily_stats.total_trades += 1
        self._daily_stats.total_pnl += pnl
        self._daily_stats.current_equity = equity_after

        # Track peak equity for drawdown
        if equity_after > self._daily_stats.peak_equity:
            self._daily_stats.peak_equity = equity_after

        # Calculate current drawdown
        if self._daily_stats.peak_equity > 0:
            current_dd = (self._daily_stats.peak_equity - equity_after) / self._daily_stats.peak_equity * 100
            self._daily_stats.max_drawdown_pct = max(self._daily_stats.max_drawdown_pct, current_dd)

        # Track wins/losses
        if pnl > 0:
            self._daily_stats.winning_trades += 1
            self._daily_stats.consecutive_wins += 1
            self._daily_stats.consecutive_losses = 0
        elif pnl < 0:
            self._daily_stats.losing_trades += 1
            self._daily_stats.consecutive_losses += 1
            self._daily_stats.consecutive_wins = 0

        # Update per-stock stats
        if symbol not in self._stock_stats:
            self._stock_stats[symbol] = StockStats(symbol=symbol)

        stock = self._stock_stats[symbol]
        stock.trades += 1
        stock.total_pnl += pnl
        stock.last_trade_time = datetime.now()

        if pnl > 0:
            stock.wins += 1
        elif pnl < 0:
            stock.losses += 1
            # Check if should blacklist
            if stock.losses >= self.config.max_losses_per_stock:
                self._blacklist_stock(symbol, f"Lost {stock.losses} times today")

        # Log the trade
        status = "✅" if pnl > 0 else "❌"
        self.logger.info(
            f"{status} {symbol}: ${pnl:+.2f} | "
            f"Daily: {self._daily_stats.return_pct:+.2f}% | "
            f"WR: {self._daily_stats.win_rate:.0f}% | "
            f"Trades: {self._daily_stats.total_trades}"
        )

        # Check circuit breakers
        self._check_circuit_breakers()

    def _blacklist_stock(self, symbol: str, reason: str):
        """Add stock to blacklist"""
        until = datetime.now().replace(hour=23, minute=59, second=59)  # End of day

        if symbol in self._stock_stats:
            self._stock_stats[symbol].blacklisted_until = until
        else:
            self._stock_stats[symbol] = StockStats(
                symbol=symbol,
                blacklisted_until=until,
            )

        self.logger.warning(f"🚫 BLACKLISTED {symbol}: {reason} (until {until.strftime('%H:%M')})")

        # Record in history
        self._blacklist_history.append({
            'symbol': symbol,
            'reason': reason,
            'time': datetime.now().isoformat(),
            'until': until.isoformat(),
        })

    def _check_circuit_breakers(self):
        """Check all circuit breaker conditions"""
        if self._daily_stats is None:
            return

        # 1. Check daily loss limit
        daily_return = self._daily_stats.return_pct
        if daily_return < -self.config.max_daily_loss_pct * 100:
            self._trip_circuit(
                f"Daily loss limit exceeded: {daily_return:.2f}% < -{self.config.max_daily_loss_pct * 100:.1f}%"
            )
            return

        # 2. Check win rate (only after minimum trades)
        if self._daily_stats.total_trades >= self.config.min_trades_for_winrate_check:
            if self._daily_stats.win_rate < self.config.min_win_rate_pct:
                self._trip_circuit(
                    f"Win rate too low: {self._daily_stats.win_rate:.1f}% < {self.config.min_win_rate_pct:.0f}%"
                )
                return

        # 3. Check consecutive losses for reduced size mode
        if self._daily_stats.consecutive_losses >= self.config.reduce_size_after_losses:
            if not self._reduced_size_mode:
                self._reduced_size_mode = True
                self.logger.warning(
                    f"⚠️ REDUCED SIZE MODE: {self._daily_stats.consecutive_losses} consecutive losses. "
                    f"Position sizes reduced to {self.config.size_reduction_factor * 100:.0f}%"
                )

        # 4. Check for recovery from reduced size mode
        if self._reduced_size_mode:
            if self._daily_stats.consecutive_wins >= self.config.consecutive_wins_to_resume:
                self._reduced_size_mode = False
                self.logger.info(
                    f"✅ NORMAL MODE RESTORED: {self._daily_stats.consecutive_wins} consecutive wins"
                )

    def _trip_circuit(self, reason: str):
        """Trip the circuit breaker - halt all trading"""
        self._circuit_open = True
        self._circuit_open_reason = reason

        self.logger.critical(f"🛑 CIRCUIT BREAKER TRIPPED: {reason}")
        self.logger.critical(f"   Trading halted for remainder of day")
        self.logger.critical(f"   Daily stats: {self._daily_stats}")

    def can_trade(self, symbol: str = "") -> Tuple[bool, str]:
        """
        Check if trading is allowed

        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        # Check global circuit breaker
        if self._circuit_open:
            return False, f"Circuit breaker open: {self._circuit_open_reason}"

        # Check if specific stock is blacklisted
        if symbol and symbol in self._stock_stats:
            stock = self._stock_stats[symbol]
            if stock.blacklisted_until:
                if datetime.now() < stock.blacklisted_until:
                    return False, f"Stock {symbol} blacklisted until {stock.blacklisted_until.strftime('%H:%M')}"
                else:
                    # Blacklist expired
                    stock.blacklisted_until = None

        return True, "OK"

    def get_position_size_multiplier(self) -> float:
        """
        Get position size multiplier based on circuit breaker state

        Returns:
            Multiplier to apply to position size (0.0 to 1.0)
        """
        if self._circuit_open:
            return 0.0

        if self._reduced_size_mode:
            return self.config.size_reduction_factor

        return 1.0

    def get_status(self) -> Dict:
        """Get current circuit breaker status"""
        if self._daily_stats is None:
            return {
                'initialized': False,
                'can_trade': True,
                'message': 'Not initialized',
            }

        return {
            'initialized': True,
            'date': self._daily_stats.date.isoformat(),
            'starting_equity': self._daily_stats.starting_equity,
            'current_equity': self._daily_stats.current_equity,
            'return_pct': self._daily_stats.return_pct,
            'total_trades': self._daily_stats.total_trades,
            'winning_trades': self._daily_stats.winning_trades,
            'losing_trades': self._daily_stats.losing_trades,
            'win_rate': self._daily_stats.win_rate,
            'max_drawdown_pct': self._daily_stats.max_drawdown_pct,
            'consecutive_losses': self._daily_stats.consecutive_losses,
            'consecutive_wins': self._daily_stats.consecutive_wins,
            'circuit_open': self._circuit_open,
            'circuit_open_reason': self._circuit_open_reason,
            'reduced_size_mode': self._reduced_size_mode,
            'blacklisted_stocks': [
                s for s, stats in self._stock_stats.items()
                if stats.blacklisted_until and datetime.now() < stats.blacklisted_until
            ],
            'can_trade': not self._circuit_open,
            'size_multiplier': self.get_position_size_multiplier(),
        }

    def get_daily_report(self) -> str:
        """Generate daily circuit breaker report"""
        if self._daily_stats is None:
            return "Circuit Breaker: Not initialized"

        stats = self._daily_stats

        lines = [
            "=" * 50,
            "CIRCUIT BREAKER DAILY REPORT",
            "=" * 50,
            f"Date: {stats.date}",
            f"",
            f"PERFORMANCE:",
            f"  Starting Equity: ${stats.starting_equity:,.2f}",
            f"  Current Equity:  ${stats.current_equity:,.2f}",
            f"  Daily Return:    {stats.return_pct:+.2f}%",
            f"  Max Drawdown:    {stats.max_drawdown_pct:.2f}%",
            f"",
            f"TRADES:",
            f"  Total: {stats.total_trades}",
            f"  Wins:  {stats.winning_trades}",
            f"  Losses: {stats.losing_trades}",
            f"  Win Rate: {stats.win_rate:.1f}%",
            f"",
            f"CIRCUIT BREAKER STATE:",
            f"  Circuit Open: {self._circuit_open}",
            f"  Reason: {self._circuit_open_reason or 'N/A'}",
            f"  Reduced Size Mode: {self._reduced_size_mode}",
            f"  Size Multiplier: {self.get_position_size_multiplier():.1%}",
            f"",
            f"BLACKLISTED STOCKS:",
        ]

        blacklisted = [
            s for s, stats in self._stock_stats.items()
            if stats.blacklisted_until and datetime.now() < stats.blacklisted_until
        ]
        if blacklisted:
            for sym in blacklisted:
                stock = self._stock_stats[sym]
                lines.append(f"  {sym}: {stock.losses} losses, until {stock.blacklisted_until.strftime('%H:%M')}")
        else:
            lines.append("  None")

        lines.extend([
            "",
            "=" * 50,
        ])

        return "\n".join(lines)
