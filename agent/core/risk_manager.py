"""
Risk Manager - Independent Trade Validator

Validates every trade before execution against risk rules.
Acts as a "guardian" that can reject trades that violate risk parameters.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class RiskViolation(Enum):
    """Types of risk violations"""
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    PDT_LIMIT = "pdt_limit"
    CORRELATION_RISK = "correlation_risk"
    VOLATILITY_TOO_HIGH = "volatility_too_high"
    INSUFFICIENT_BUYING_POWER = "insufficient_buying_power"
    MAX_POSITIONS_REACHED = "max_positions_reached"
    SECTOR_CONCENTRATION = "sector_concentration"
    DRAWDOWN_LIMIT = "drawdown_limit"
    LOW_CONFIDENCE = "low_confidence"
    ADVERSE_ANALYST_RATING = "adverse_analyst_rating"


@dataclass
class RiskCheckResult:
    """Result of a risk check"""
    approved: bool
    violations: List[RiskViolation]
    warnings: List[str]
    adjustments: Dict[str, any]  # Suggested adjustments (e.g., reduced size)
    reasoning: str

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class RiskConfig:
    """Risk management configuration"""
    # Position limits
    max_position_pct: float = 0.20          # Max 20% of portfolio per position
    max_total_exposure_pct: float = 0.80    # Max 80% of portfolio in positions
    max_positions: int = 5                   # Max concurrent positions

    # Loss limits
    max_daily_loss_pct: float = 0.03        # Max 3% daily loss
    max_drawdown_pct: float = 0.10          # Max 10% drawdown from peak
    stop_loss_required: bool = True          # Every trade must have stop loss

    # PDT protection (Pattern Day Trader)
    pdt_protection: bool = True
    max_day_trades_per_week: int = 3        # PDT limit for < $25k accounts

    # Quality thresholds
    min_confidence: float = 0.5              # Minimum confidence to trade
    min_risk_reward: float = 1.5             # Minimum risk/reward ratio

    # Sector limits
    max_sector_concentration_pct: float = 0.40  # Max 40% in same sector

    # Correlation
    max_correlated_positions: int = 2        # Max positions in correlated assets


class RiskManager:
    """
    Independent risk validator for all trades.

    Acts as a final checkpoint before any trade is executed.
    Can reject trades, suggest adjustments, or approve with warnings.
    """

    # Sector mappings for concentration checks
    SECTOR_MAP = {
        # Tech
        'AAPL': 'tech', 'MSFT': 'tech', 'GOOGL': 'tech', 'META': 'tech',
        'NVDA': 'tech', 'AMD': 'tech', 'INTC': 'tech', 'QCOM': 'tech',
        'AVGO': 'tech', 'MU': 'tech', 'NFLX': 'tech', 'AMZN': 'tech',
        # EV/Auto
        'TSLA': 'ev', 'RIVN': 'ev', 'LCID': 'ev', 'NIO': 'ev',
        'LI': 'ev', 'XPEV': 'ev', 'F': 'ev', 'GM': 'ev',
        # Crypto-related
        'COIN': 'crypto', 'MARA': 'crypto', 'RIOT': 'crypto', 'HOOD': 'crypto',
        # Fintech
        'SQ': 'fintech', 'PYPL': 'fintech', 'SOFI': 'fintech', 'AFRM': 'fintech',
        # China tech
        'BABA': 'china', 'JD': 'china', 'PDD': 'china', 'BIDU': 'china',
        # Energy
        'XOM': 'energy', 'CVX': 'energy', 'OXY': 'energy', 'DVN': 'energy',
        # Financials
        'JPM': 'financial', 'BAC': 'financial', 'WFC': 'financial', 'GS': 'financial',
    }

    # Correlation groups (assets that move together)
    CORRELATION_GROUPS = [
        {'NVDA', 'AMD', 'INTC', 'MU', 'AVGO'},  # Semiconductors
        {'TSLA', 'RIVN', 'LCID', 'NIO'},         # EV
        {'COIN', 'MARA', 'RIOT'},                 # Crypto
        {'AAPL', 'MSFT', 'GOOGL', 'META'},        # Big tech
        {'BABA', 'JD', 'PDD', 'BIDU'},            # China
        {'XOM', 'CVX', 'OXY'},                    # Oil
    ]

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self.logger = logging.getLogger(__name__)

        # Track daily stats
        self._daily_pnl: float = 0
        self._daily_trades: int = 0
        self._day_trades_this_week: int = 0
        self._last_reset: datetime = datetime.now()
        self._peak_equity: float = 0

    async def validate_trade(
        self,
        symbol: str,
        action: str,
        shares: float,
        entry_price: float,
        stop_loss: Optional[float],
        confidence: float,
        account_equity: float,
        buying_power: float,
        current_positions: List[Dict],
        analyst_rating: Optional[Dict] = None,
    ) -> RiskCheckResult:
        """
        Validate a proposed trade against all risk rules.

        Args:
            symbol: Stock ticker
            action: BUY or SELL
            shares: Number of shares
            entry_price: Proposed entry price
            stop_loss: Stop loss price
            confidence: AI confidence (0-1)
            account_equity: Total account equity
            buying_power: Available buying power
            current_positions: List of current positions
            analyst_rating: Optional analyst rating data

        Returns:
            RiskCheckResult with approval status and any violations
        """
        violations = []
        warnings = []
        adjustments = {}

        position_value = shares * entry_price

        # Reset daily stats if new day
        self._check_daily_reset()

        # Update peak equity tracking
        if account_equity > self._peak_equity:
            self._peak_equity = account_equity

        # === HARD CHECKS (will reject) ===

        # 1. Position size limit
        position_pct = position_value / account_equity if account_equity > 0 else 1
        if position_pct > self.config.max_position_pct:
            violations.append(RiskViolation.POSITION_SIZE_EXCEEDED)
            # Suggest reduced size
            max_value = account_equity * self.config.max_position_pct
            adjustments['suggested_shares'] = max_value / entry_price
            adjustments['suggested_value'] = max_value

        # 2. Buying power check
        if position_value > buying_power:
            violations.append(RiskViolation.INSUFFICIENT_BUYING_POWER)
            adjustments['max_affordable_shares'] = buying_power / entry_price

        # 3. Max positions
        if len(current_positions) >= self.config.max_positions and action == 'BUY':
            violations.append(RiskViolation.MAX_POSITIONS_REACHED)

        # 4. Daily loss limit
        if self._daily_pnl < -(account_equity * self.config.max_daily_loss_pct):
            violations.append(RiskViolation.DAILY_LOSS_LIMIT)

        # 5. Drawdown limit
        drawdown = (self._peak_equity - account_equity) / self._peak_equity if self._peak_equity > 0 else 0
        if drawdown > self.config.max_drawdown_pct:
            violations.append(RiskViolation.DRAWDOWN_LIMIT)

        # 6. PDT protection
        if self.config.pdt_protection and account_equity < 25000:
            if self._day_trades_this_week >= self.config.max_day_trades_per_week:
                violations.append(RiskViolation.PDT_LIMIT)

        # 7. Stop loss required
        if self.config.stop_loss_required and stop_loss is None and action == 'BUY':
            violations.append(RiskViolation.POSITION_SIZE_EXCEEDED)  # Using as proxy
            warnings.append("Stop loss is required for all trades")

        # 8. Minimum confidence
        if confidence < self.config.min_confidence:
            violations.append(RiskViolation.LOW_CONFIDENCE)

        # === SOFT CHECKS (warnings) ===

        # 9. Sector concentration
        sector = self.SECTOR_MAP.get(symbol, 'other')
        sector_exposure = self._calculate_sector_exposure(current_positions, sector)
        if sector_exposure + position_pct > self.config.max_sector_concentration_pct:
            warnings.append(f"High {sector} sector concentration: {(sector_exposure + position_pct)*100:.0f}%")

        # 10. Correlation risk
        correlated_count = self._count_correlated_positions(symbol, current_positions)
        if correlated_count >= self.config.max_correlated_positions:
            warnings.append(f"Already have {correlated_count} correlated positions")

        # 11. Total exposure
        total_exposure = sum(p.get('market_value', 0) for p in current_positions) / account_equity if account_equity > 0 else 0
        if total_exposure + position_pct > self.config.max_total_exposure_pct:
            warnings.append(f"High total exposure: {(total_exposure + position_pct)*100:.0f}%")

        # 12. Risk/Reward check
        if stop_loss and entry_price:
            risk = entry_price - stop_loss
            if risk > 0:
                # Assume first target is 1.5% above entry
                reward = entry_price * 0.015
                rr_ratio = reward / risk
                if rr_ratio < self.config.min_risk_reward:
                    warnings.append(f"Low risk/reward ratio: {rr_ratio:.2f}")

        # 13. Adverse analyst rating
        if analyst_rating:
            bearish_pct = analyst_rating.get('bearish_percent', 0)
            if bearish_pct > 50:
                warnings.append(f"Analyst consensus is bearish: {bearish_pct:.0f}% sell ratings")
                if bearish_pct > 70:
                    violations.append(RiskViolation.ADVERSE_ANALYST_RATING)

        # Build reasoning
        approved = len(violations) == 0
        reasoning = self._build_reasoning(approved, violations, warnings, adjustments)

        self.logger.info(
            f"🛡️ Risk Check {symbol}: {'✅ APPROVED' if approved else '❌ REJECTED'} | "
            f"Violations: {len(violations)} | Warnings: {len(warnings)}"
        )

        if violations:
            for v in violations:
                self.logger.warning(f"  ❌ {v.value}")
        if warnings:
            for w in warnings:
                self.logger.info(f"  ⚠️ {w}")

        return RiskCheckResult(
            approved=approved,
            violations=violations,
            warnings=warnings,
            adjustments=adjustments,
            reasoning=reasoning,
        )

    def record_trade_result(self, pnl: float, is_day_trade: bool = False):
        """Record trade result for daily tracking"""
        self._daily_pnl += pnl
        self._daily_trades += 1
        if is_day_trade:
            self._day_trades_this_week += 1

    def _check_daily_reset(self):
        """Reset daily stats at market open"""
        now = datetime.now()
        if now.date() > self._last_reset.date():
            self._daily_pnl = 0
            self._daily_trades = 0
            self._last_reset = now

            # Reset weekly day trades on Monday
            if now.weekday() == 0:  # Monday
                self._day_trades_this_week = 0

    def _calculate_sector_exposure(self, positions: List[Dict], sector: str) -> float:
        """Calculate current exposure to a sector"""
        sector_value = 0
        total_value = 0

        for pos in positions:
            symbol = pos.get('symbol', '')
            value = pos.get('market_value', 0)
            total_value += value

            if self.SECTOR_MAP.get(symbol, 'other') == sector:
                sector_value += value

        return sector_value / total_value if total_value > 0 else 0

    def _count_correlated_positions(self, symbol: str, positions: List[Dict]) -> int:
        """Count how many current positions are correlated with the new symbol"""
        # Find which correlation group the symbol belongs to
        symbol_group = None
        for group in self.CORRELATION_GROUPS:
            if symbol in group:
                symbol_group = group
                break

        if not symbol_group:
            return 0

        # Count positions in the same group
        count = 0
        for pos in positions:
            if pos.get('symbol', '') in symbol_group:
                count += 1

        return count

    def _build_reasoning(
        self,
        approved: bool,
        violations: List[RiskViolation],
        warnings: List[str],
        adjustments: Dict
    ) -> str:
        """Build human-readable reasoning"""
        parts = []

        if approved:
            parts.append("Trade approved by Risk Manager.")
            if warnings:
                parts.append(f"Warnings: {', '.join(warnings)}")
        else:
            parts.append("Trade REJECTED by Risk Manager.")
            parts.append(f"Violations: {', '.join(v.value for v in violations)}")

            if adjustments:
                if 'suggested_shares' in adjustments:
                    parts.append(
                        f"Suggested: Reduce to {adjustments['suggested_shares']:.2f} shares "
                        f"(${adjustments.get('suggested_value', 0):.2f})"
                    )

        return " | ".join(parts)

    def get_risk_status(self, account_equity: float) -> Dict:
        """Get current risk status summary"""
        drawdown = (self._peak_equity - account_equity) / self._peak_equity if self._peak_equity > 0 else 0

        return {
            "daily_pnl": self._daily_pnl,
            "daily_pnl_pct": self._daily_pnl / account_equity if account_equity > 0 else 0,
            "daily_trades": self._daily_trades,
            "day_trades_this_week": self._day_trades_this_week,
            "pdt_remaining": max(0, self.config.max_day_trades_per_week - self._day_trades_this_week),
            "current_drawdown_pct": drawdown,
            "max_drawdown_pct": self.config.max_drawdown_pct,
            "daily_loss_limit_remaining": (account_equity * self.config.max_daily_loss_pct) + self._daily_pnl,
        }
