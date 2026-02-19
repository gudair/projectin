"""
Position Intelligence - Advanced Position Management

Implements:
1. Kelly Criterion Position Sizing - Mathematical optimal sizing
2. Max Drawdown Protection - Real-time capital preservation
3. Market Session Awareness - Time-based strategy adjustment
4. Sector Correlation - Avoid concentrated exposure

Inspired by: FinCon, HedgeAgents, TradingAgents research
"""
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math


class MarketSession(Enum):
    """Market trading sessions with different characteristics"""
    PRE_MARKET = "pre_market"           # 4:00-9:30 AM ET
    OPENING_BELL = "opening_bell"       # 9:30-10:00 AM ET (volatile)
    MORNING = "morning"                 # 10:00-11:30 AM ET (momentum)
    MIDDAY = "midday"                   # 11:30-2:00 PM ET (choppy)
    AFTERNOON = "afternoon"             # 2:00-3:30 PM ET (trend)
    POWER_HOUR = "power_hour"           # 3:30-4:00 PM ET (volatile)
    AFTER_HOURS = "after_hours"         # 4:00-8:00 PM ET


@dataclass
class SessionConfig:
    """Configuration for each market session"""
    position_size_multiplier: float  # Adjust position size
    min_score_to_trade: float        # Higher bar for entry
    prefer_quick_trades: bool        # Exit faster
    avoid_new_entries: bool          # Don't open new positions
    max_hold_minutes: int            # Max time to hold


# Session-specific trading parameters
SESSION_CONFIGS = {
    MarketSession.PRE_MARKET: SessionConfig(
        position_size_multiplier=0.0,  # No trading pre-market
        min_score_to_trade=10.0,       # Impossible
        prefer_quick_trades=False,
        avoid_new_entries=True,
        max_hold_minutes=0,
    ),
    MarketSession.OPENING_BELL: SessionConfig(
        position_size_multiplier=0.5,  # Half size (high volatility)
        min_score_to_trade=7.0,        # Higher bar
        prefer_quick_trades=True,      # Quick scalps
        avoid_new_entries=False,
        max_hold_minutes=15,           # Very short holds
    ),
    MarketSession.MORNING: SessionConfig(
        position_size_multiplier=1.0,  # Full size (best momentum)
        min_score_to_trade=6.0,        # Standard
        prefer_quick_trades=False,
        avoid_new_entries=False,
        max_hold_minutes=60,
    ),
    MarketSession.MIDDAY: SessionConfig(
        position_size_multiplier=0.7,  # Reduced (choppy)
        min_score_to_trade=7.0,        # Higher bar
        prefer_quick_trades=True,
        avoid_new_entries=True,        # Avoid new entries
        max_hold_minutes=30,
    ),
    MarketSession.AFTERNOON: SessionConfig(
        position_size_multiplier=0.9,  # Near full
        min_score_to_trade=6.0,
        prefer_quick_trades=False,
        avoid_new_entries=False,
        max_hold_minutes=45,
    ),
    MarketSession.POWER_HOUR: SessionConfig(
        position_size_multiplier=0.6,  # Reduced (volatile)
        min_score_to_trade=7.5,        # Higher bar
        prefer_quick_trades=True,      # Quick exits
        avoid_new_entries=True,        # Close only
        max_hold_minutes=20,
    ),
    MarketSession.AFTER_HOURS: SessionConfig(
        position_size_multiplier=0.0,  # No trading
        min_score_to_trade=10.0,
        prefer_quick_trades=False,
        avoid_new_entries=True,
        max_hold_minutes=0,
    ),
}


@dataclass
class DrawdownState:
    """Tracks drawdown for capital preservation"""
    peak_equity: float
    current_equity: float
    max_drawdown_pct: float = 0.0
    daily_high: float = 0.0
    daily_low: float = float('inf')
    consecutive_losses: int = 0
    last_loss_time: Optional[datetime] = None

    @property
    def current_drawdown_pct(self) -> float:
        """Current drawdown from peak"""
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.current_equity) / self.peak_equity

    @property
    def daily_range_pct(self) -> float:
        """Daily equity range as percentage"""
        if self.daily_high <= 0:
            return 0.0
        return (self.daily_high - self.daily_low) / self.daily_high


@dataclass
class KellyResult:
    """Kelly Criterion calculation result"""
    optimal_fraction: float     # Optimal bet fraction
    half_kelly: float          # Conservative half-kelly
    quarter_kelly: float       # Very conservative
    recommended: float         # What we actually recommend
    win_rate: float
    win_loss_ratio: float
    edge: float                # Expected edge
    reasoning: str


@dataclass
class PositionRecommendation:
    """Final position sizing recommendation"""
    symbol: str
    base_size_pct: float           # Base position size
    adjusted_size_pct: float       # After all adjustments
    kelly_adjustment: float        # Kelly factor
    session_adjustment: float      # Session factor
    drawdown_adjustment: float     # Drawdown factor
    correlation_adjustment: float  # Correlation factor
    final_size_dollars: float
    final_shares: float
    reasoning: List[str]
    warnings: List[str]


class PositionIntelligence:
    """
    Advanced position management combining multiple factors:
    - Kelly Criterion for mathematically optimal sizing
    - Drawdown protection for capital preservation
    - Session awareness for time-based adjustments
    - Sector correlation to avoid concentrated risk
    """

    # Sector mappings for major stocks
    SECTOR_MAP = {
        # Technology
        'AAPL': 'technology', 'MSFT': 'technology', 'GOOGL': 'technology',
        'GOOG': 'technology', 'META': 'technology', 'NVDA': 'technology',
        'AMD': 'technology', 'INTC': 'technology', 'CRM': 'technology',
        'ADBE': 'technology', 'ORCL': 'technology', 'CSCO': 'technology',
        # Finance
        'JPM': 'finance', 'BAC': 'finance', 'WFC': 'finance',
        'GS': 'finance', 'MS': 'finance', 'C': 'finance',
        'V': 'finance', 'MA': 'finance', 'AXP': 'finance',
        # Healthcare
        'JNJ': 'healthcare', 'PFE': 'healthcare', 'UNH': 'healthcare',
        'ABBV': 'healthcare', 'MRK': 'healthcare', 'LLY': 'healthcare',
        # Consumer
        'AMZN': 'consumer', 'WMT': 'consumer', 'HD': 'consumer',
        'NKE': 'consumer', 'MCD': 'consumer', 'SBUX': 'consumer',
        'COST': 'consumer', 'TGT': 'consumer',
        # Energy
        'XOM': 'energy', 'CVX': 'energy', 'COP': 'energy',
        'SLB': 'energy', 'EOG': 'energy',
        # Industrial
        'CAT': 'industrial', 'BA': 'industrial', 'GE': 'industrial',
        'HON': 'industrial', 'UPS': 'industrial',
        # Communication
        'DIS': 'communication', 'NFLX': 'communication', 'CMCSA': 'communication',
        'T': 'communication', 'VZ': 'communication',
    }

    # Drawdown thresholds
    DRAWDOWN_THRESHOLDS = {
        'normal': 0.02,      # < 2% drawdown = normal trading
        'caution': 0.03,     # 2-3% = reduce size
        'defensive': 0.05,   # 3-5% = defensive mode
        'critical': 0.08,    # 5-8% = minimal trading
        'halt': 0.10,        # > 10% = halt trading
    }

    def __init__(
        self,
        initial_equity: float = 1000.0,
        max_drawdown_pct: float = 0.10,
        max_sector_exposure_pct: float = 0.40,
        use_half_kelly: bool = True,
    ):
        self.logger = logging.getLogger(__name__)
        self.max_drawdown_pct = max_drawdown_pct
        self.max_sector_exposure_pct = max_sector_exposure_pct
        self.use_half_kelly = use_half_kelly

        # Initialize drawdown tracking
        self.drawdown = DrawdownState(
            peak_equity=initial_equity,
            current_equity=initial_equity,
            daily_high=initial_equity,
            daily_low=initial_equity,
        )

        # Trade history for Kelly calculation
        self._trade_history: List[Dict] = []
        self._sector_exposure: Dict[str, float] = {}

    def get_current_session(self, now: Optional[datetime] = None) -> MarketSession:
        """Determine current market session based on time (ET)"""
        if now is None:
            now = datetime.now()

        # Convert to ET (simplified - assumes local is close to ET)
        current_time = now.time()

        # Session boundaries (ET)
        if current_time < time(9, 30):
            return MarketSession.PRE_MARKET
        elif current_time < time(10, 0):
            return MarketSession.OPENING_BELL
        elif current_time < time(11, 30):
            return MarketSession.MORNING
        elif current_time < time(14, 0):
            return MarketSession.MIDDAY
        elif current_time < time(15, 30):
            return MarketSession.AFTERNOON
        elif current_time < time(16, 0):
            return MarketSession.POWER_HOUR
        else:
            return MarketSession.AFTER_HOURS

    def get_session_config(self, session: Optional[MarketSession] = None) -> SessionConfig:
        """Get configuration for a session"""
        if session is None:
            session = self.get_current_session()
        return SESSION_CONFIGS.get(session, SESSION_CONFIGS[MarketSession.MORNING])

    def calculate_kelly(
        self,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
    ) -> KellyResult:
        """
        Calculate Kelly Criterion optimal position size.

        Kelly Formula: f* = (bp - q) / b
        Where:
            f* = fraction of capital to bet
            b = win/loss ratio
            p = probability of winning
            q = probability of losing (1 - p)
        """
        # Use historical data if not provided
        if win_rate is None or avg_win is None or avg_loss is None:
            stats = self._calculate_historical_stats()
            win_rate = stats.get('win_rate', 0.5)
            avg_win = stats.get('avg_win', 100)
            avg_loss = stats.get('avg_loss', 100)

        # Ensure valid values
        win_rate = max(0.01, min(0.99, win_rate))
        avg_loss = max(1, abs(avg_loss))
        avg_win = max(1, avg_win)

        # Calculate components
        p = win_rate
        q = 1 - p
        b = avg_win / avg_loss  # Win/loss ratio

        # Kelly formula
        edge = (b * p) - q
        kelly = edge / b if b > 0 else 0

        # Constrain Kelly to reasonable range
        kelly = max(0, min(0.25, kelly))  # Max 25% even with edge

        # Conservative versions
        half_kelly = kelly / 2
        quarter_kelly = kelly / 4

        # Determine recommendation based on confidence
        if len(self._trade_history) < 10:
            # Not enough data - be very conservative
            recommended = min(0.05, quarter_kelly)
            reasoning = "Insufficient trade history - using quarter Kelly"
        elif edge <= 0:
            recommended = 0.02  # Minimum bet size
            reasoning = "No edge detected - using minimum position size"
        elif self.use_half_kelly:
            recommended = half_kelly
            reasoning = f"Using half Kelly (edge: {edge:.2%})"
        else:
            recommended = kelly
            reasoning = f"Using full Kelly (edge: {edge:.2%})"

        return KellyResult(
            optimal_fraction=kelly,
            half_kelly=half_kelly,
            quarter_kelly=quarter_kelly,
            recommended=recommended,
            win_rate=win_rate,
            win_loss_ratio=b,
            edge=edge,
            reasoning=reasoning,
        )

    def _calculate_historical_stats(self) -> Dict:
        """Calculate stats from trade history"""
        if not self._trade_history:
            return {'win_rate': 0.5, 'avg_win': 100, 'avg_loss': 100}

        wins = [t for t in self._trade_history if t.get('pnl', 0) > 0]
        losses = [t for t in self._trade_history if t.get('pnl', 0) < 0]

        win_rate = len(wins) / len(self._trade_history) if self._trade_history else 0.5
        avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 100
        avg_loss = abs(sum(t['pnl'] for t in losses) / len(losses)) if losses else 100

        return {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_trades': len(self._trade_history),
        }

    def update_equity(self, new_equity: float):
        """Update equity for drawdown tracking"""
        self.drawdown.current_equity = new_equity

        # Update peak
        if new_equity > self.drawdown.peak_equity:
            self.drawdown.peak_equity = new_equity

        # Update daily tracking
        if new_equity > self.drawdown.daily_high:
            self.drawdown.daily_high = new_equity
        if new_equity < self.drawdown.daily_low:
            self.drawdown.daily_low = new_equity

        # Update max drawdown
        current_dd = self.drawdown.current_drawdown_pct
        if current_dd > self.drawdown.max_drawdown_pct:
            self.drawdown.max_drawdown_pct = current_dd

    def record_trade(self, symbol: str, pnl: float, pnl_pct: float):
        """Record a trade for Kelly calculation and drawdown tracking"""
        self._trade_history.append({
            'symbol': symbol,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'time': datetime.now(),
        })

        # Keep last 100 trades
        if len(self._trade_history) > 100:
            self._trade_history = self._trade_history[-100:]

        # Update consecutive losses
        if pnl < 0:
            self.drawdown.consecutive_losses += 1
            self.drawdown.last_loss_time = datetime.now()
        else:
            self.drawdown.consecutive_losses = 0

    def get_drawdown_multiplier(self) -> Tuple[float, str]:
        """
        Get position size multiplier based on current drawdown.

        Returns:
            (multiplier, reason) - e.g., (0.5, "Defensive mode: 4% drawdown")
        """
        dd = self.drawdown.current_drawdown_pct

        if dd < self.DRAWDOWN_THRESHOLDS['normal']:
            return 1.0, "Normal trading"
        elif dd < self.DRAWDOWN_THRESHOLDS['caution']:
            return 0.75, f"Caution: {dd*100:.1f}% drawdown"
        elif dd < self.DRAWDOWN_THRESHOLDS['defensive']:
            return 0.5, f"Defensive: {dd*100:.1f}% drawdown"
        elif dd < self.DRAWDOWN_THRESHOLDS['critical']:
            return 0.25, f"Critical: {dd*100:.1f}% drawdown"
        else:
            return 0.0, f"HALT: {dd*100:.1f}% drawdown exceeds {self.max_drawdown_pct*100}%"

    def get_consecutive_loss_multiplier(self) -> Tuple[float, str]:
        """Reduce size after consecutive losses"""
        losses = self.drawdown.consecutive_losses

        if losses <= 1:
            return 1.0, "Normal"
        elif losses == 2:
            return 0.8, "2 consecutive losses"
        elif losses == 3:
            return 0.6, "3 consecutive losses"
        elif losses == 4:
            return 0.4, "4 consecutive losses"
        else:
            return 0.2, f"{losses} consecutive losses - minimal size"

    def get_sector(self, symbol: str) -> str:
        """Get sector for a symbol"""
        return self.SECTOR_MAP.get(symbol, 'unknown')

    def update_sector_exposure(self, positions: List[Dict]):
        """Update sector exposure from current positions"""
        self._sector_exposure = {}
        total_value = sum(p.get('market_value', 0) for p in positions)

        if total_value <= 0:
            return

        for p in positions:
            symbol = p.get('symbol', '')
            value = p.get('market_value', 0)
            sector = self.get_sector(symbol)

            if sector not in self._sector_exposure:
                self._sector_exposure[sector] = 0
            self._sector_exposure[sector] += value / total_value

    def get_sector_multiplier(self, symbol: str) -> Tuple[float, str]:
        """Reduce size if sector already has high exposure"""
        sector = self.get_sector(symbol)
        exposure = self._sector_exposure.get(sector, 0)

        if exposure < self.max_sector_exposure_pct * 0.5:
            return 1.0, f"{sector}: {exposure*100:.0f}% exposure"
        elif exposure < self.max_sector_exposure_pct * 0.75:
            return 0.7, f"{sector}: {exposure*100:.0f}% exposure (reducing)"
        elif exposure < self.max_sector_exposure_pct:
            return 0.4, f"{sector}: {exposure*100:.0f}% exposure (high)"
        else:
            return 0.0, f"{sector}: {exposure*100:.0f}% exceeds {self.max_sector_exposure_pct*100}% limit"

    def calculate_position(
        self,
        symbol: str,
        entry_price: float,
        confidence: float,
        account_equity: float,
        base_position_pct: float = 0.20,
        positions: Optional[List[Dict]] = None,
    ) -> PositionRecommendation:
        """
        Calculate optimal position size considering all factors.

        Args:
            symbol: Stock ticker
            entry_price: Planned entry price
            confidence: Trade confidence (0-1)
            account_equity: Current account equity
            base_position_pct: Base position size (default 20%)
            positions: Current positions for correlation check

        Returns:
            PositionRecommendation with all adjustments
        """
        reasoning = []
        warnings = []

        # Update sector exposure
        if positions:
            self.update_sector_exposure(positions)

        # 1. Kelly Criterion
        kelly = self.calculate_kelly()
        kelly_adj = min(kelly.recommended / base_position_pct, 1.5)  # Max 1.5x boost
        kelly_adj = max(kelly_adj, 0.5)  # Min 0.5x
        reasoning.append(f"Kelly: {kelly.reasoning} → {kelly_adj:.2f}x")

        # 2. Session adjustment
        session = self.get_current_session()
        session_config = self.get_session_config(session)
        session_adj = session_config.position_size_multiplier
        reasoning.append(f"Session: {session.value} → {session_adj:.2f}x")

        if session_config.avoid_new_entries:
            warnings.append(f"⚠️ {session.value}: Avoid new entries")

        # 3. Drawdown adjustment
        dd_adj, dd_reason = self.get_drawdown_multiplier()
        reasoning.append(f"Drawdown: {dd_reason} → {dd_adj:.2f}x")

        if dd_adj == 0:
            warnings.append(f"🚨 Trading HALTED: {dd_reason}")

        # 4. Consecutive loss adjustment
        loss_adj, loss_reason = self.get_consecutive_loss_multiplier()
        if loss_adj < 1.0:
            reasoning.append(f"Losses: {loss_reason} → {loss_adj:.2f}x")

        # 5. Sector correlation
        sector_adj, sector_reason = self.get_sector_multiplier(symbol)
        if sector_adj < 1.0:
            reasoning.append(f"Sector: {sector_reason} → {sector_adj:.2f}x")

        if sector_adj == 0:
            warnings.append(f"🚨 Sector limit reached: {sector_reason}")

        # 6. Confidence scaling
        conf_adj = 0.5 + (confidence * 0.5)  # 50% to 100% based on confidence
        reasoning.append(f"Confidence: {confidence*100:.0f}% → {conf_adj:.2f}x")

        # Calculate final size
        adjusted_pct = base_position_pct * kelly_adj * session_adj * dd_adj * loss_adj * sector_adj * conf_adj
        adjusted_pct = max(0, min(0.25, adjusted_pct))  # Cap at 25%

        final_dollars = account_equity * adjusted_pct
        final_shares = final_dollars / entry_price if entry_price > 0 else 0

        return PositionRecommendation(
            symbol=symbol,
            base_size_pct=base_position_pct,
            adjusted_size_pct=adjusted_pct,
            kelly_adjustment=kelly_adj,
            session_adjustment=session_adj,
            drawdown_adjustment=dd_adj,
            correlation_adjustment=sector_adj,
            final_size_dollars=final_dollars,
            final_shares=final_shares,
            reasoning=reasoning,
            warnings=warnings,
        )

    def should_trade(self, symbol: str, score: float) -> Tuple[bool, str]:
        """
        Check if we should trade based on session and conditions.

        Returns:
            (should_trade, reason)
        """
        session = self.get_current_session()
        config = self.get_session_config(session)

        # Check session allows trading
        if config.position_size_multiplier == 0:
            return False, f"No trading during {session.value}"

        if config.avoid_new_entries:
            return False, f"Avoiding new entries during {session.value}"

        # Check minimum score
        if score < config.min_score_to_trade:
            return False, f"Score {score:.1f} below {session.value} minimum {config.min_score_to_trade}"

        # Check drawdown
        dd_mult, dd_reason = self.get_drawdown_multiplier()
        if dd_mult == 0:
            return False, dd_reason

        # Check consecutive losses
        if self.drawdown.consecutive_losses >= 5:
            return False, f"Too many consecutive losses ({self.drawdown.consecutive_losses})"

        return True, f"OK for {session.value}"

    def reset_daily(self):
        """Reset daily tracking (call at start of each trading day)"""
        self.drawdown.daily_high = self.drawdown.current_equity
        self.drawdown.daily_low = self.drawdown.current_equity

    def get_status(self) -> Dict:
        """Get current position intelligence status"""
        session = self.get_current_session()
        config = self.get_session_config(session)
        dd_mult, dd_reason = self.get_drawdown_multiplier()

        return {
            'session': session.value,
            'session_multiplier': config.position_size_multiplier,
            'avoid_new_entries': config.avoid_new_entries,
            'current_drawdown_pct': self.drawdown.current_drawdown_pct * 100,
            'max_drawdown_pct': self.drawdown.max_drawdown_pct * 100,
            'drawdown_multiplier': dd_mult,
            'drawdown_status': dd_reason,
            'consecutive_losses': self.drawdown.consecutive_losses,
            'peak_equity': self.drawdown.peak_equity,
            'current_equity': self.drawdown.current_equity,
            'sector_exposure': self._sector_exposure,
            'trade_count': len(self._trade_history),
        }
