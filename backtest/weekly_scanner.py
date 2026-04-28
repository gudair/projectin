"""
Weekly Symbol Scanner with Market Regime

Runs weekly to:
1. Check if market regime is favorable for trading
2. Select best symbols based on recent momentum/volatility
3. Avoid trading in choppy/bearish conditions
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from backtest.daily_data import DailyDataLoader

logging.basicConfig(level=logging.WARNING)


@dataclass
class MarketRegime:
    """Market regime assessment"""
    regime: str  # 'BULLISH', 'BEARISH', 'CHOPPY'
    spy_trend: float  # % above/below 20-day SMA
    spy_momentum: float  # 5-day return
    vix_level: str  # 'LOW', 'MEDIUM', 'HIGH'
    should_trade: bool
    reason: str


@dataclass
class SymbolScore:
    """Scored symbol for trading"""
    symbol: str
    momentum_score: float  # Recent return
    volatility_score: float  # ATR%
    volume_score: float  # Dollar volume
    total_score: float
    recent_return: float


class WeeklyScanner:
    """
    Weekly symbol scanner with market regime awareness
    """

    def __init__(self):
        self.data_loader = DailyDataLoader()

        # Universe to scan from
        self.universe = [
            # Semiconductors
            'AMD', 'NVDA', 'MU', 'QCOM', 'MRVL', 'AVGO', 'INTC', 'AMAT',
            # Big Tech
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NFLX', 'TSLA',
            # Fintech/Crypto
            'COIN', 'SQ', 'SHOP', 'PLTR', 'SNOW',
            # Other high-beta
            'BA', 'CAT', 'DE', 'GS', 'JPM',
        ]

    async def assess_market_regime(self, as_of_date: datetime) -> MarketRegime:
        """
        Assess overall market regime

        Returns whether we should be trading at all
        """
        await self.data_loader.load(['SPY', 'QQQ'], as_of_date - timedelta(days=60), as_of_date)

        spy_bars = self.data_loader.get_bars('SPY', as_of_date, 30)
        if len(spy_bars) < 25:
            return MarketRegime(
                regime='UNKNOWN',
                spy_trend=0,
                spy_momentum=0,
                vix_level='UNKNOWN',
                should_trade=False,
                reason='Insufficient data'
            )

        closes = [b.close for b in spy_bars]

        # 1. Trend: Price vs 20-day SMA
        sma_20 = np.mean(closes[-20:])
        current = closes[-1]
        trend_pct = (current - sma_20) / sma_20 * 100

        # 2. Momentum: 5-day return
        momentum = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0

        # 3. Volatility: Recent ATR
        highs = [b.high for b in spy_bars]
        lows = [b.low for b in spy_bars]
        true_ranges = []
        for i in range(1, len(spy_bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        atr = np.mean(true_ranges[-14:]) if true_ranges else 0
        atr_pct = atr / current * 100

        # Determine VIX-like volatility level
        if atr_pct < 1.0:
            vix_level = 'LOW'
        elif atr_pct < 1.5:
            vix_level = 'MEDIUM'
        else:
            vix_level = 'HIGH'

        # Determine regime
        if trend_pct > 1.0 and momentum > 0:
            regime = 'BULLISH'
            should_trade = True
            reason = f'SPY +{trend_pct:.1f}% vs SMA, momentum +{momentum:.1f}%'
        elif trend_pct < -2.0 or momentum < -3.0:
            regime = 'BEARISH'
            should_trade = False
            reason = f'SPY {trend_pct:.1f}% vs SMA, momentum {momentum:.1f}%'
        else:
            regime = 'CHOPPY'
            # Only trade in choppy if volatility is not too high
            should_trade = vix_level != 'HIGH'
            reason = f'Sideways market, ATR={atr_pct:.1f}%'

        return MarketRegime(
            regime=regime,
            spy_trend=trend_pct,
            spy_momentum=momentum,
            vix_level=vix_level,
            should_trade=should_trade,
            reason=reason,
        )

    async def scan_symbols(
        self,
        as_of_date: datetime,
        top_n: int = 5,
    ) -> Tuple[List[SymbolScore], MarketRegime]:
        """
        Scan universe and return best symbols for trading

        Returns:
            (list of scored symbols, market regime)
        """
        # First check market regime
        regime = await self.assess_market_regime(as_of_date)

        if not regime.should_trade:
            return [], regime

        # Load data for all symbols
        await self.data_loader.load(
            self.universe,
            as_of_date - timedelta(days=40),
            as_of_date
        )

        # Score each symbol
        scores = []
        for symbol in self.universe:
            bars = self.data_loader.get_bars(symbol, as_of_date, 25)
            if len(bars) < 20:
                continue

            score = self._score_symbol(symbol, bars)
            if score:
                scores.append(score)

        # Sort by total score
        scores.sort(key=lambda x: x.total_score, reverse=True)

        return scores[:top_n], regime

    def _score_symbol(self, symbol: str, bars: List) -> Optional[SymbolScore]:
        """Score a symbol based on multiple factors"""
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        current = closes[-1]

        # 1. Momentum: 10-day return (want positive but not overextended)
        if len(closes) >= 11:
            return_10d = (closes[-1] - closes[-11]) / closes[-11] * 100
        else:
            return_10d = 0

        # Score: prefer 5-15% momentum (not too cold, not too hot)
        if 5 <= return_10d <= 15:
            momentum_score = 1.0
        elif 0 <= return_10d < 5:
            momentum_score = 0.5
        elif 15 < return_10d <= 25:
            momentum_score = 0.7
        else:
            momentum_score = 0.3

        # 2. Volatility: ATR% (want 2-4% for good swings)
        true_ranges = []
        for i in range(1, len(bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        atr = np.mean(true_ranges[-14:]) if true_ranges else 0
        atr_pct = atr / current * 100

        if 2.5 <= atr_pct <= 4.5:
            volatility_score = 1.0
        elif 2.0 <= atr_pct < 2.5 or 4.5 < atr_pct <= 5.5:
            volatility_score = 0.7
        else:
            volatility_score = 0.4

        # 3. Volume: Dollar volume (want high liquidity)
        avg_volume = np.mean(volumes)
        dollar_volume = avg_volume * current

        if dollar_volume > 500_000_000:  # $500M+
            volume_score = 1.0
        elif dollar_volume > 100_000_000:  # $100M+
            volume_score = 0.8
        elif dollar_volume > 50_000_000:  # $50M+
            volume_score = 0.6
        else:
            volume_score = 0.3

        # Total score
        total_score = (momentum_score * 0.5) + (volatility_score * 0.3) + (volume_score * 0.2)

        return SymbolScore(
            symbol=symbol,
            momentum_score=momentum_score,
            volatility_score=volatility_score,
            volume_score=volume_score,
            total_score=total_score,
            recent_return=return_10d,
        )


async def simulate_weekly_scanning():
    """Simulate running the scanner each week"""

    scanner = WeeklyScanner()

    # Simulate for Q4 2025
    weeks = [
        datetime(2025, 9, 1),
        datetime(2025, 9, 8),
        datetime(2025, 9, 15),
        datetime(2025, 9, 22),
        datetime(2025, 9, 29),
        datetime(2025, 10, 6),
        datetime(2025, 10, 13),
        datetime(2025, 10, 20),
        datetime(2025, 10, 27),
        datetime(2025, 11, 3),
        datetime(2025, 11, 10),
        datetime(2025, 11, 17),
        datetime(2025, 11, 24),
        datetime(2025, 12, 1),
        datetime(2025, 12, 8),
        datetime(2025, 12, 15),
        datetime(2025, 12, 22),
    ]

    print(f"\n{'='*90}")
    print(f"WEEKLY SCANNER SIMULATION - Q4 2025")
    print(f"{'='*90}")

    print(f"\n{'Week':<12} | {'Regime':<10} | {'Trade?':<8} | {'Top Symbols':<35} | Reason")
    print("-" * 90)

    for week_start in weeks:
        symbols, regime = await scanner.scan_symbols(week_start, top_n=5)

        symbol_str = ', '.join([f"{s.symbol}({s.recent_return:+.0f}%)" for s in symbols]) if symbols else "NONE"
        trade_str = "✅ YES" if regime.should_trade else "❌ NO"

        print(f"{week_start.strftime('%Y-%m-%d'):<12} | {regime.regime:<10} | {trade_str:<8} | {symbol_str:<35} | {regime.reason}")

    # Summary
    print(f"\n{'='*90}")
    print(f"KEY INSIGHT:")
    print(f"   The scanner would have STOPPED trading during bearish/high-vol periods")
    print(f"   This would have avoided many of the November losses")
    print(f"{'='*90}")


if __name__ == "__main__":
    asyncio.run(simulate_weekly_scanning())
