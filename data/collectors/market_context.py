"""
Market Context Collector

Collects market-wide context including VIX, SPY, and sector data.
This is a data-layer wrapper around the agent's market context functionality.
"""
from typing import Dict, Optional
from datetime import datetime
import logging

from agent.core.context import MarketContext, MarketContextData, MarketRegime


class MarketContextCollector:
    """
    Data layer collector for market context.

    Provides market-wide context for trading decisions:
    - Index data (SPY, QQQ, IWM)
    - Volatility data (VIX)
    - Sector performance
    - Market regime classification
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._context = MarketContext()

    def get_context(self, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get current market context as dictionary.

        Returns:
            Dictionary with market context data
        """
        import asyncio

        async def _get():
            return await self._context.get_context(force_refresh=force_refresh)

        try:
            # Run async method
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _get())
                    context = future.result(timeout=30)
            else:
                context = asyncio.run(_get())

            return context.to_dict() if context else None

        except Exception as e:
            self.logger.error(f"Error getting market context: {e}")
            return None

    def get_regime(self) -> str:
        """Get current market regime"""
        context = self.get_context()
        if context:
            return context.get('regime', 'neutral')
        return 'neutral'

    def get_vix(self) -> Optional[float]:
        """Get current VIX value"""
        context = self.get_context()
        if context and 'vix' in context:
            return context['vix'].get('value')
        return None

    def get_spy_change(self) -> Optional[float]:
        """Get SPY daily change percentage"""
        context = self.get_context()
        if context and 'spy' in context:
            return context['spy'].get('change_pct')
        return None

    def is_risk_on(self) -> bool:
        """Check if market is in risk-on mode"""
        regime = self.get_regime()
        return regime == 'risk_on'

    def is_high_volatility(self) -> bool:
        """Check if market is in high volatility mode"""
        regime = self.get_regime()
        return regime == 'high_volatility'

    def get_position_size_multiplier(self) -> float:
        """Get recommended position size multiplier based on regime"""
        regime = self.get_regime()
        multipliers = {
            'risk_on': 1.0,
            'neutral': 0.8,
            'risk_off': 0.5,
            'high_volatility': 0.25,
        }
        return multipliers.get(regime, 0.8)

    def get_summary(self) -> str:
        """Get human-readable market summary"""
        context = self.get_context()
        if not context:
            return "Market context unavailable"

        spy = context.get('spy', {})
        vix = context.get('vix', {})
        regime = context.get('regime', 'unknown')

        return (
            f"SPY: {spy.get('change_pct', 0):+.2f}% | "
            f"VIX: {vix.get('value', 0):.1f} | "
            f"Regime: {regime.upper()}"
        )


# Singleton instance for convenience
_collector = None


def get_market_context() -> MarketContextCollector:
    """Get singleton market context collector"""
    global _collector
    if _collector is None:
        _collector = MarketContextCollector()
    return _collector
