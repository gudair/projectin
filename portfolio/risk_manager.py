"""
Risk Manager

Dynamic risk management for the trading agent.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from config.agent_config import RiskConfig, DEFAULT_CONFIG, MarketRegime


@dataclass
class RiskAssessment:
    """Risk assessment result"""
    can_trade: bool
    max_position_size: float
    risk_score: float  # 0-1, higher = more risky
    warnings: List[str]
    blockers: List[str]
    recommended_stop_pct: float
    recommended_size_pct: float


@dataclass
class PortfolioRisk:
    """Current portfolio risk metrics"""
    total_exposure: float
    concentration_risk: float  # Highest single position %
    sector_exposure: Dict[str, float]
    correlation_risk: float
    daily_var: float  # Value at Risk
    max_drawdown: float


class RiskManager:
    """
    Dynamic risk management for trading decisions.

    Features:
    - Position sizing based on volatility
    - Portfolio-level risk monitoring
    - Regime-adjusted risk limits
    - PDT rule compliance
    - Correlation-aware position limits
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or DEFAULT_CONFIG.risk
        self.logger = logging.getLogger(__name__)

        # Tracking
        self._daily_trades: List[Dict] = []
        self._daily_pnl: float = 0.0
        self._day_trade_count: int = 0
        self._last_day_reset: datetime = datetime.now().date()

    def assess_trade(
        self,
        symbol: str,
        action: str,
        current_price: float,
        proposed_size: float,
        stop_loss: Optional[float],
        portfolio_value: float,
        current_positions: Dict[str, Dict],
        market_regime: MarketRegime = MarketRegime.NEUTRAL,
    ) -> RiskAssessment:
        """
        Assess risk of a proposed trade.

        Returns comprehensive risk assessment with recommendations.
        """
        warnings = []
        blockers = []

        # Reset daily tracking if new day
        self._check_daily_reset()

        # Calculate position percentage
        position_pct = proposed_size / portfolio_value if portfolio_value > 0 else 1.0

        # 1. Check position size limit
        max_position_pct = self._get_regime_adjusted_limit(
            self.config.max_position_pct,
            market_regime,
        )

        if position_pct > max_position_pct:
            blockers.append(f"Position size {position_pct*100:.1f}% exceeds limit {max_position_pct*100:.0f}%")

        # 2. Check max positions
        existing_position = symbol in current_positions
        if not existing_position and len(current_positions) >= self.config.max_positions:
            blockers.append(f"Max positions limit reached ({self.config.max_positions})")

        # 3. Check daily loss limit
        daily_loss_pct = abs(self._daily_pnl) / portfolio_value if portfolio_value > 0 else 0
        remaining_risk = self.config.max_daily_loss_pct - daily_loss_pct

        if remaining_risk <= 0:
            blockers.append(f"Daily loss limit reached ({self.config.max_daily_loss_pct*100:.0f}%)")
        elif remaining_risk < 0.01:
            warnings.append(f"Near daily loss limit ({daily_loss_pct*100:.1f}%/{self.config.max_daily_loss_pct*100:.0f}%)")

        # 4. Check PDT rule
        if self.config.pdt_enabled:
            pdt_ok, pdt_msg = self._check_pdt(action, existing_position, portfolio_value)
            if not pdt_ok:
                blockers.append(pdt_msg)
            elif "warning" in pdt_msg.lower():
                warnings.append(pdt_msg)

        # 5. Check risk/reward
        if stop_loss:
            risk_per_share = abs(current_price - stop_loss)
            risk_pct = risk_per_share / current_price

            if risk_pct > self.config.default_stop_loss_pct * 2:
                warnings.append(f"Wide stop loss ({risk_pct*100:.1f}%)")

        # 6. Concentration check
        concentration = self._check_concentration(symbol, proposed_size, current_positions, portfolio_value)
        if concentration > 0.4:
            warnings.append(f"High concentration in {symbol} ({concentration*100:.0f}%)")
        if concentration > 0.5:
            blockers.append(f"Excessive concentration ({concentration*100:.0f}%)")

        # 7. Regime warnings
        if market_regime == MarketRegime.HIGH_VOLATILITY:
            warnings.append("High volatility regime - reduced sizing recommended")
        elif market_regime == MarketRegime.RISK_OFF:
            warnings.append("Risk-off regime - defensive positioning recommended")

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            position_pct=position_pct,
            daily_loss_pct=daily_loss_pct,
            concentration=concentration,
            regime=market_regime,
            has_stop=stop_loss is not None,
        )

        # Determine if can trade
        can_trade = len(blockers) == 0

        # Recommended sizing
        recommended_size_pct = self._recommend_position_size(
            position_pct,
            market_regime,
            risk_score,
        )

        # Recommended stop
        recommended_stop_pct = self._recommend_stop_loss(
            market_regime,
            current_price,
        )

        return RiskAssessment(
            can_trade=can_trade,
            max_position_size=portfolio_value * max_position_pct,
            risk_score=risk_score,
            warnings=warnings,
            blockers=blockers,
            recommended_stop_pct=recommended_stop_pct,
            recommended_size_pct=recommended_size_pct,
        )

    def record_trade(self, symbol: str, pnl: float, is_day_trade: bool = False):
        """Record a completed trade"""
        self._daily_pnl += pnl
        self._daily_trades.append({
            'symbol': symbol,
            'pnl': pnl,
            'timestamp': datetime.now(),
            'is_day_trade': is_day_trade,
        })

        if is_day_trade:
            self._day_trade_count += 1

    def get_portfolio_risk(
        self,
        positions: Dict[str, Dict],
        portfolio_value: float,
    ) -> PortfolioRisk:
        """Calculate current portfolio risk metrics"""
        if not positions or portfolio_value <= 0:
            return PortfolioRisk(
                total_exposure=0,
                concentration_risk=0,
                sector_exposure={},
                correlation_risk=0,
                daily_var=0,
                max_drawdown=0,
            )

        # Calculate exposures
        position_values = {
            sym: pos.get('market_value', 0)
            for sym, pos in positions.items()
        }

        total_exposure = sum(position_values.values())
        exposure_pct = total_exposure / portfolio_value

        # Concentration (largest position)
        if position_values:
            max_position = max(position_values.values())
            concentration = max_position / portfolio_value
        else:
            concentration = 0

        # Simple VaR estimate (2% of exposure)
        daily_var = total_exposure * 0.02

        return PortfolioRisk(
            total_exposure=exposure_pct,
            concentration_risk=concentration,
            sector_exposure={},  # Would need sector data
            correlation_risk=0,  # Would need correlation matrix
            daily_var=daily_var,
            max_drawdown=abs(self._daily_pnl),
        )

    def _get_regime_adjusted_limit(self, base_limit: float, regime: MarketRegime) -> float:
        """Adjust limit based on market regime"""
        adjustments = {
            MarketRegime.RISK_ON: 1.0,
            MarketRegime.NEUTRAL: 0.8,
            MarketRegime.RISK_OFF: 0.5,
            MarketRegime.HIGH_VOLATILITY: 0.25,
        }
        return base_limit * adjustments.get(regime, 0.8)

    def _check_pdt(
        self,
        action: str,
        existing_position: bool,
        portfolio_value: float,
    ) -> Tuple[bool, str]:
        """Check PDT rule compliance"""
        # PDT only applies to accounts < $25,000
        if portfolio_value >= 25000:
            return True, ""

        # Selling an existing position same day = day trade
        if action == 'SELL' and existing_position:
            remaining = self.config.pdt_limit - self._day_trade_count

            if remaining <= 0:
                return False, f"PDT limit reached ({self._day_trade_count}/{self.config.pdt_limit})"
            elif remaining == 1:
                return True, f"Warning: Last day trade available ({self._day_trade_count}/{self.config.pdt_limit})"

        return True, ""

    def _check_concentration(
        self,
        symbol: str,
        proposed_size: float,
        current_positions: Dict[str, Dict],
        portfolio_value: float,
    ) -> float:
        """Calculate concentration after proposed trade"""
        current_value = current_positions.get(symbol, {}).get('market_value', 0)
        new_value = current_value + proposed_size

        return new_value / portfolio_value if portfolio_value > 0 else 1.0

    def _calculate_risk_score(
        self,
        position_pct: float,
        daily_loss_pct: float,
        concentration: float,
        regime: MarketRegime,
        has_stop: bool,
    ) -> float:
        """Calculate overall risk score 0-1"""
        score = 0.0

        # Position size component (0-0.3)
        score += min(0.3, position_pct / self.config.max_position_pct * 0.3)

        # Daily loss component (0-0.2)
        score += min(0.2, daily_loss_pct / self.config.max_daily_loss_pct * 0.2)

        # Concentration component (0-0.2)
        score += min(0.2, concentration * 0.4)

        # Regime component (0-0.2)
        regime_risk = {
            MarketRegime.RISK_ON: 0.0,
            MarketRegime.NEUTRAL: 0.05,
            MarketRegime.RISK_OFF: 0.15,
            MarketRegime.HIGH_VOLATILITY: 0.2,
        }
        score += regime_risk.get(regime, 0.1)

        # No stop loss penalty (0-0.1)
        if not has_stop:
            score += 0.1

        return min(1.0, score)

    def _recommend_position_size(
        self,
        proposed_pct: float,
        regime: MarketRegime,
        risk_score: float,
    ) -> float:
        """Recommend position size based on conditions"""
        # Start with proposed
        recommended = proposed_pct

        # Regime adjustment
        regime_factor = {
            MarketRegime.RISK_ON: 1.0,
            MarketRegime.NEUTRAL: 0.8,
            MarketRegime.RISK_OFF: 0.5,
            MarketRegime.HIGH_VOLATILITY: 0.25,
        }.get(regime, 0.8)

        recommended *= regime_factor

        # Risk score adjustment
        if risk_score > 0.7:
            recommended *= 0.5
        elif risk_score > 0.5:
            recommended *= 0.75

        # Apply limits
        max_limit = self._get_regime_adjusted_limit(self.config.max_position_pct, regime)
        recommended = min(recommended, max_limit)

        return recommended

    def _recommend_stop_loss(self, regime: MarketRegime, current_price: float) -> float:
        """Recommend stop loss percentage"""
        base_stop = self.config.default_stop_loss_pct

        # Widen in volatile regimes
        if regime == MarketRegime.HIGH_VOLATILITY:
            return base_stop * 1.5
        elif regime == MarketRegime.RISK_OFF:
            return base_stop * 1.25

        return base_stop

    def _check_daily_reset(self):
        """Reset daily tracking if new day"""
        today = datetime.now().date()
        if today > self._last_day_reset:
            self._daily_pnl = 0.0
            self._daily_trades = []
            self._day_trade_count = 0
            self._last_day_reset = today

    def get_daily_summary(self) -> Dict:
        """Get daily risk summary"""
        return {
            'daily_pnl': self._daily_pnl,
            'trade_count': len(self._daily_trades),
            'day_trades': self._day_trade_count,
            'pdt_remaining': self.config.pdt_limit - self._day_trade_count,
        }
