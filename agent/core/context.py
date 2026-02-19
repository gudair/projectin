"""
Market Context Aggregator

Provides market-wide context including VIX, SPY, sector performance.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import yfinance as yf

from config.agent_config import MarketRegime, VIX_THRESHOLDS, DEFAULT_CONFIG


@dataclass
class IndexData:
    """Data for market index"""
    symbol: str
    price: float
    change_pct: float
    volume: int
    avg_volume: int
    timestamp: datetime

    @property
    def volume_ratio(self) -> float:
        return self.volume / self.avg_volume if self.avg_volume > 0 else 1.0


@dataclass
class VIXData:
    """VIX volatility data"""
    value: float
    change_pct: float
    percentile_30d: float
    timestamp: datetime

    @property
    def regime(self) -> MarketRegime:
        if self.value < VIX_THRESHOLDS['low']:
            return MarketRegime.RISK_ON
        elif self.value < VIX_THRESHOLDS['medium']:
            return MarketRegime.NEUTRAL
        elif self.value < VIX_THRESHOLDS['high']:
            return MarketRegime.RISK_OFF
        else:
            return MarketRegime.HIGH_VOLATILITY


@dataclass
class SectorPerformance:
    """Sector performance data"""
    sector: str
    etf_symbol: str
    change_pct: float
    relative_strength: float  # vs SPY


@dataclass
class MarketContextData:
    """Complete market context"""
    spy: IndexData
    vix: VIXData
    qqq: Optional[IndexData] = None
    iwm: Optional[IndexData] = None
    sectors: List[SectorPerformance] = field(default_factory=list)
    regime: MarketRegime = MarketRegime.NEUTRAL
    is_market_open: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'spy': {
                'price': self.spy.price,
                'change_pct': self.spy.change_pct,
                'volume_ratio': self.spy.volume_ratio,
            },
            'vix': {
                'value': self.vix.value,
                'change_pct': self.vix.change_pct,
                'percentile': self.vix.percentile_30d,
            },
            'regime': self.regime.value,
            'is_market_open': self.is_market_open,
            'timestamp': self.timestamp.isoformat(),
            'sectors': [
                {
                    'sector': s.sector,
                    'change_pct': s.change_pct,
                    'relative_strength': s.relative_strength,
                }
                for s in self.sectors
            ],
        }

    def get_summary(self) -> str:
        """Get human-readable summary"""
        regime_emoji = {
            MarketRegime.RISK_ON: "🟢",
            MarketRegime.NEUTRAL: "🟡",
            MarketRegime.RISK_OFF: "🟠",
            MarketRegime.HIGH_VOLATILITY: "🔴",
        }

        lines = [
            f"Market: {'OPEN' if self.is_market_open else 'CLOSED'}",
            f"SPY: ${self.spy.price:.2f} ({self.spy.change_pct:+.2f}%)",
            f"VIX: {self.vix.value:.1f} ({self.vix.change_pct:+.2f}%)",
            f"Regime: {regime_emoji.get(self.regime, '')} {self.regime.value.upper()}",
        ]

        if self.sectors:
            top_sector = max(self.sectors, key=lambda s: s.change_pct)
            bottom_sector = min(self.sectors, key=lambda s: s.change_pct)
            lines.append(f"Top: {top_sector.sector} ({top_sector.change_pct:+.2f}%)")
            lines.append(f"Bottom: {bottom_sector.sector} ({bottom_sector.change_pct:+.2f}%)")

        return " | ".join(lines)


# Standard sector ETFs
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financials': 'XLF',
    'Consumer Discretionary': 'XLY',
    'Consumer Staples': 'XLP',
    'Energy': 'XLE',
    'Industrials': 'XLI',
    'Materials': 'XLB',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Communications': 'XLC',
}


class MarketContext:
    """
    Aggregates market-wide context for trading decisions.

    Provides:
    - SPY/QQQ/IWM index data
    - VIX volatility data
    - Sector performance
    - Market regime classification
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._cache: Optional[MarketContextData] = None
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)

    async def get_context(self, force_refresh: bool = False) -> MarketContextData:
        """Get current market context"""
        now = datetime.now()

        # Return cached if valid
        if not force_refresh and self._cache and self._cache_time:
            if now - self._cache_time < self._cache_duration:
                return self._cache

        # Fetch fresh data
        context = await self._fetch_context()
        self._cache = context
        self._cache_time = now

        return context

    async def _fetch_context(self) -> MarketContextData:
        """Fetch all market context data"""
        loop = asyncio.get_event_loop()

        # Run blocking yfinance calls in executor
        spy_data, vix_data, qqq_data, iwm_data, sectors = await asyncio.gather(
            loop.run_in_executor(None, self._fetch_index, 'SPY'),
            loop.run_in_executor(None, self._fetch_vix),
            loop.run_in_executor(None, self._fetch_index, 'QQQ'),
            loop.run_in_executor(None, self._fetch_index, 'IWM'),
            loop.run_in_executor(None, self._fetch_sectors),
            return_exceptions=True,
        )

        # Handle any errors
        if isinstance(spy_data, Exception):
            self.logger.error(f"Error fetching SPY: {spy_data}")
            spy_data = self._default_index('SPY')

        if isinstance(vix_data, Exception):
            self.logger.error(f"Error fetching VIX: {vix_data}")
            vix_data = self._default_vix()

        if isinstance(qqq_data, Exception):
            qqq_data = None

        if isinstance(iwm_data, Exception):
            iwm_data = None

        if isinstance(sectors, Exception):
            sectors = []

        # Determine regime
        regime = vix_data.regime if vix_data else MarketRegime.NEUTRAL

        # Adjust regime based on SPY trend
        if spy_data and spy_data.change_pct < -2.0:
            regime = MarketRegime.RISK_OFF
        elif spy_data and spy_data.change_pct > 1.5 and regime == MarketRegime.RISK_ON:
            regime = MarketRegime.RISK_ON

        return MarketContextData(
            spy=spy_data,
            vix=vix_data,
            qqq=qqq_data,
            iwm=iwm_data,
            sectors=sectors or [],
            regime=regime,
            is_market_open=self._is_market_open(),
            timestamp=datetime.now(),
        )

    def _fetch_index(self, symbol: str) -> IndexData:
        """Fetch index data (blocking)"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='5d')

            if hist.empty:
                return self._default_index(symbol)

            current_price = float(hist['Close'].iloc[-1])
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
            change_pct = ((current_price - prev_close) / prev_close) * 100

            volume = int(hist['Volume'].iloc[-1])
            avg_volume = int(hist['Volume'].mean())

            return IndexData(
                symbol=symbol,
                price=current_price,
                change_pct=change_pct,
                volume=volume,
                avg_volume=avg_volume,
                timestamp=datetime.now(),
            )

        except Exception as e:
            self.logger.error(f"Error fetching {symbol}: {e}")
            return self._default_index(symbol)

    def _fetch_vix(self) -> VIXData:
        """Fetch VIX data (blocking)"""
        try:
            ticker = yf.Ticker('^VIX')
            hist = ticker.history(period='30d')

            if hist.empty:
                return self._default_vix()

            current_value = float(hist['Close'].iloc[-1])
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_value
            change_pct = ((current_value - prev_close) / prev_close) * 100

            # Calculate percentile
            values = hist['Close'].values
            percentile = (values < current_value).sum() / len(values) * 100

            return VIXData(
                value=current_value,
                change_pct=change_pct,
                percentile_30d=percentile,
                timestamp=datetime.now(),
            )

        except Exception as e:
            self.logger.error(f"Error fetching VIX: {e}")
            return self._default_vix()

    def _fetch_sectors(self) -> List[SectorPerformance]:
        """Fetch sector performance (blocking)"""
        sectors = []

        try:
            # Get SPY as benchmark
            spy = yf.Ticker('SPY')
            spy_hist = spy.history(period='5d')
            spy_change = 0.0

            if not spy_hist.empty:
                spy_current = float(spy_hist['Close'].iloc[-1])
                spy_prev = float(spy_hist['Close'].iloc[-2]) if len(spy_hist) > 1 else spy_current
                spy_change = ((spy_current - spy_prev) / spy_prev) * 100

            # Fetch sector ETFs
            for sector_name, etf_symbol in SECTOR_ETFS.items():
                try:
                    ticker = yf.Ticker(etf_symbol)
                    hist = ticker.history(period='5d')

                    if hist.empty:
                        continue

                    current = float(hist['Close'].iloc[-1])
                    prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
                    change_pct = ((current - prev) / prev) * 100
                    relative_strength = change_pct - spy_change

                    sectors.append(SectorPerformance(
                        sector=sector_name,
                        etf_symbol=etf_symbol,
                        change_pct=change_pct,
                        relative_strength=relative_strength,
                    ))

                except Exception as e:
                    self.logger.debug(f"Error fetching {etf_symbol}: {e}")

        except Exception as e:
            self.logger.error(f"Error fetching sectors: {e}")

        return sectors

    def _default_index(self, symbol: str) -> IndexData:
        """Return default index data"""
        return IndexData(
            symbol=symbol,
            price=0.0,
            change_pct=0.0,
            volume=0,
            avg_volume=1,
            timestamp=datetime.now(),
        )

    def _default_vix(self) -> VIXData:
        """Return default VIX data"""
        return VIXData(
            value=20.0,
            change_pct=0.0,
            percentile_30d=50.0,
            timestamp=datetime.now(),
        )

    def _is_market_open(self) -> bool:
        """Check if US market is open"""
        now = datetime.now()

        # Simple check - weekday and between 9:30 AM and 4:00 PM EST
        # Note: This is simplified, doesn't account for holidays
        if now.weekday() >= 5:  # Weekend
            return False

        # Convert to EST (simplified - assumes system is in a US timezone)
        hour = now.hour
        minute = now.minute
        time_minutes = hour * 60 + minute

        market_open = 9 * 60 + 30   # 9:30 AM
        market_close = 16 * 60       # 4:00 PM

        return market_open <= time_minutes < market_close

    def get_regime_description(self, regime: MarketRegime) -> str:
        """Get detailed description of market regime"""
        descriptions = {
            MarketRegime.RISK_ON: (
                "Risk-On Environment: Low volatility, bullish sentiment. "
                "Favor growth stocks, momentum plays, larger position sizes."
            ),
            MarketRegime.NEUTRAL: (
                "Neutral Environment: Mixed signals. "
                "Use standard position sizing, focus on high-conviction setups."
            ),
            MarketRegime.RISK_OFF: (
                "Risk-Off Environment: Elevated volatility, cautious sentiment. "
                "Reduce position sizes, favor defensive names, tighter stops."
            ),
            MarketRegime.HIGH_VOLATILITY: (
                "High Volatility Environment: Extreme uncertainty. "
                "Minimize new positions, protect capital, consider hedges."
            ),
        }
        return descriptions.get(regime, "Unknown regime")

    def get_position_size_multiplier(self, regime: MarketRegime) -> float:
        """Get position size multiplier based on regime"""
        multipliers = {
            MarketRegime.RISK_ON: 1.0,
            MarketRegime.NEUTRAL: 0.8,
            MarketRegime.RISK_OFF: 0.5,
            MarketRegime.HIGH_VOLATILITY: 0.25,
        }
        return multipliers.get(regime, 0.5)
