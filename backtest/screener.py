"""
Dynamic Symbol Screener

Selects symbols dynamically based on criteria instead of hardcoded lists.
Avoids survivorship bias by screening based on current/historical conditions.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScreenerCriteria:
    """Criteria for symbol screening"""
    min_price: float = 5.0           # Minimum stock price (avoid penny stocks)
    max_price: float = 10000.0       # Maximum stock price
    min_avg_volume: int = 500_000    # Minimum average daily volume
    min_market_cap: float = 1e9      # Minimum market cap ($1B) - if available
    exclude_etfs: bool = False       # Whether to exclude ETFs
    exclude_otc: bool = True         # Exclude OTC stocks
    only_us: bool = True             # Only US exchanges
    max_symbols: int = 100           # Maximum symbols to return
    # Volatility filter - exclude stocks too volatile for our stop loss
    max_atr_pct: float = 0.025       # Max ATR as % of price (2.5% for 3% stop loss)


class DynamicScreener:
    """
    Screens for tradeable symbols based on dynamic criteria.

    Uses Alpaca API to get current market data and filter symbols.
    """

    def __init__(self, criteria: ScreenerCriteria = None):
        self.criteria = criteria or ScreenerCriteria()
        self._asset_cache: Dict = {}

    async def get_tradeable_symbols(self) -> List[str]:
        """
        Get all tradeable symbols from Alpaca that meet basic criteria.

        Returns list of symbols sorted by average volume (most liquid first).
        """
        from alpaca.client import AlpacaClient

        client = AlpacaClient()

        try:
            # Get all assets from Alpaca
            assets = await client.get_assets()

            if not assets:
                logger.warning("No assets returned from Alpaca")
                return self._get_fallback_symbols()

            # Filter assets
            valid_symbols = []
            for asset in assets:
                # Basic filters
                if not asset.tradable:
                    continue
                if asset.status != 'active':
                    continue
                if self.criteria.exclude_otc and asset.exchange == 'OTC':
                    continue
                if self.criteria.only_us and asset.exchange not in ['NYSE', 'NASDAQ', 'ARCA', 'AMEX', 'BATS']:
                    continue
                if self.criteria.exclude_etfs and getattr(asset, 'asset_class', '') == 'etf':
                    continue

                valid_symbols.append(asset.symbol)

            logger.info(f"Found {len(valid_symbols)} tradeable symbols from Alpaca")

            await client.close()
            return valid_symbols

        except Exception as e:
            logger.error(f"Error fetching assets: {e}")
            await client.close()
            return self._get_fallback_symbols()

    async def screen_by_volume_and_price(
        self,
        symbols: List[str],
        as_of_date: datetime,
        lookback_days: int = 20,
    ) -> List[Dict]:
        """
        Screen symbols by volume and price criteria.

        Args:
            symbols: List of symbols to screen
            as_of_date: Date to evaluate (for backtesting)
            lookback_days: Days to calculate average volume

        Returns:
            List of dicts with symbol info, sorted by volume
        """
        from backtest.daily_data import DailyDataLoader

        loader = DailyDataLoader()

        # Load data for all symbols
        start_date = as_of_date - timedelta(days=lookback_days + 10)
        await loader.load(symbols, start_date, as_of_date)

        # Screen each symbol
        screened = []
        filtered_volatility = 0

        for symbol in symbols:
            bars = loader.get_bars(symbol, as_of_date, lookback_days)

            if len(bars) < 14:  # Need enough data for ATR
                continue

            # Calculate metrics
            current_price = bars[-1].close
            avg_volume = sum(b.volume for b in bars) / len(bars)

            # Calculate ATR (Average True Range) for volatility filter
            true_ranges = []
            for i in range(1, len(bars)):
                high_low = bars[i].high - bars[i].low
                high_close = abs(bars[i].high - bars[i-1].close)
                low_close = abs(bars[i].low - bars[i-1].close)
                true_ranges.append(max(high_low, high_close, low_close))

            atr = sum(true_ranges[-14:]) / min(14, len(true_ranges))
            atr_pct = atr / current_price  # ATR as percentage of price

            # Apply filters
            if current_price < self.criteria.min_price:
                continue
            if current_price > self.criteria.max_price:
                continue
            if avg_volume < self.criteria.min_avg_volume:
                continue

            # VOLATILITY FILTER: Exclude stocks too volatile for our stop loss
            if atr_pct > self.criteria.max_atr_pct:
                filtered_volatility += 1
                continue

            screened.append({
                'symbol': symbol,
                'price': current_price,
                'avg_volume': avg_volume,
                'volume_dollars': current_price * avg_volume,
                'atr_pct': atr_pct,
            })

        if filtered_volatility > 0:
            logger.info(f"Filtered {filtered_volatility} symbols for high volatility (ATR% > {self.criteria.max_atr_pct:.1%})")

        # Sort by dollar volume (most liquid first)
        screened.sort(key=lambda x: x['volume_dollars'], reverse=True)

        # Limit to max symbols
        screened = screened[:self.criteria.max_symbols]

        logger.info(f"Screened to {len(screened)} symbols meeting criteria")

        return screened

    async def screen_for_mean_reversion(
        self,
        symbols: List[str],
        as_of_date: datetime,
        rsi_threshold: float = 35.0,
        bb_threshold: float = 0.2,
    ) -> List[Dict]:
        """
        Screen for mean reversion candidates (oversold stocks).

        Finds stocks with:
        - RSI below threshold (oversold)
        - Price near lower Bollinger Band

        Args:
            symbols: Symbols to screen
            as_of_date: Date to evaluate
            rsi_threshold: RSI level to consider oversold
            bb_threshold: Bollinger Band %B threshold (0.2 = near lower band)

        Returns:
            List of mean reversion candidates
        """
        from backtest.daily_data import DailyDataLoader
        from agent.strategies.mean_reversion import MeanReversionStrategy

        loader = DailyDataLoader()
        strategy = MeanReversionStrategy()

        # Load data
        start_date = as_of_date - timedelta(days=60)
        await loader.load(symbols, start_date, as_of_date)

        candidates = []

        for symbol in symbols:
            bars = loader.get_bars(symbol, as_of_date, 30)

            if len(bars) < 20:
                continue

            # Calculate indicators
            closes = [b.close for b in bars]
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]
            volumes = [b.volume for b in bars]

            indicators = strategy.calculate_indicators(closes, highs, lows, volumes)

            # Check if oversold
            is_oversold = (
                indicators.rsi <= rsi_threshold or
                indicators.bb_percent <= bb_threshold
            )

            if is_oversold:
                candidates.append({
                    'symbol': symbol,
                    'price': closes[-1],
                    'rsi': indicators.rsi,
                    'bb_percent': indicators.bb_percent,
                    'volume_ratio': indicators.volume_ratio,
                })

        # Sort by RSI (most oversold first)
        candidates.sort(key=lambda x: x['rsi'])

        logger.info(f"Found {len(candidates)} mean reversion candidates")

        return candidates

    def _get_fallback_symbols(self) -> List[str]:
        """
        Fallback list if API fails.
        Uses S&P 500 components as a reasonable universe.
        """
        # Top 100 S&P 500 by market cap (as of 2025)
        # This is still a fallback, not the primary method
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'BRK.B', 'TSLA',
            'UNH', 'XOM', 'JNJ', 'JPM', 'V', 'PG', 'MA', 'HD', 'CVX', 'MRK',
            'ABBV', 'LLY', 'PEP', 'KO', 'COST', 'AVGO', 'WMT', 'MCD', 'CSCO',
            'TMO', 'ABT', 'ACN', 'CRM', 'DHR', 'NKE', 'TXN', 'NEE', 'WFC',
            'PM', 'UPS', 'MS', 'UNP', 'RTX', 'ORCL', 'BMY', 'QCOM', 'HON',
            'INTC', 'IBM', 'AMGN', 'LOW', 'CAT', 'GE', 'BA', 'SBUX', 'GS',
            'BLK', 'INTU', 'AMD', 'GILD', 'PLD', 'MDLZ', 'ADI', 'AXP', 'ISRG',
            'BKNG', 'VRTX', 'DE', 'TMUS', 'SYK', 'CB', 'LMT', 'NOW', 'MMC',
            'MO', 'SO', 'DUK', 'CI', 'REGN', 'PGR', 'AON', 'ZTS', 'BDX',
            'CME', 'ITW', 'CSX', 'SCHW', 'NOC', 'CL', 'EOG', 'SLB', 'USB',
            'FDX', 'MU', 'NFLX', 'ATVI', 'PNC', 'TGT', 'F', 'GM', 'DIS',
        ]


async def get_screened_symbols(
    as_of_date: datetime = None,
    criteria: ScreenerCriteria = None,
    include_mean_reversion_filter: bool = False,
) -> List[str]:
    """
    Convenience function to get screened symbols.

    Args:
        as_of_date: Date to screen as of (default: today)
        criteria: Screening criteria
        include_mean_reversion_filter: If True, only return oversold stocks

    Returns:
        List of symbols meeting criteria
    """
    as_of_date = as_of_date or datetime.now()

    screener = DynamicScreener(criteria)

    # Get tradeable symbols
    all_symbols = await screener.get_tradeable_symbols()

    # Screen by volume and price
    screened = await screener.screen_by_volume_and_price(
        all_symbols[:500],  # Limit initial fetch for speed
        as_of_date,
    )

    symbols = [s['symbol'] for s in screened]

    # Optionally filter for mean reversion candidates
    if include_mean_reversion_filter:
        candidates = await screener.screen_for_mean_reversion(symbols, as_of_date)
        symbols = [c['symbol'] for c in candidates]

    return symbols


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    async def main():
        print("Dynamic Symbol Screener")
        print("=" * 50)

        # Screen as of a specific date for backtesting
        test_date = datetime(2025, 10, 1)

        criteria = ScreenerCriteria(
            min_price=10.0,
            min_avg_volume=1_000_000,
            max_symbols=50,
        )

        screener = DynamicScreener(criteria)

        # Get tradeable symbols
        print(f"\nFetching tradeable symbols...")
        all_symbols = await screener.get_tradeable_symbols()
        print(f"Found {len(all_symbols)} tradeable symbols")

        # Screen by volume/price
        print(f"\nScreening by volume and price as of {test_date.date()}...")
        screened = await screener.screen_by_volume_and_price(
            all_symbols[:200],  # Test with subset
            test_date,
        )

        print(f"\nTop 20 by liquidity:")
        for i, s in enumerate(screened[:20], 1):
            print(f"  {i:2}. {s['symbol']:5} - ${s['price']:8.2f} - Vol: {s['avg_volume']/1e6:.1f}M")

        # Screen for mean reversion
        print(f"\nScreening for mean reversion candidates...")
        symbols = [s['symbol'] for s in screened[:50]]
        candidates = await screener.screen_for_mean_reversion(symbols, test_date)

        print(f"\nMean reversion candidates (oversold):")
        for c in candidates[:10]:
            print(f"  {c['symbol']:5} - RSI: {c['rsi']:.0f} - BB%: {c['bb_percent']:.1%}")

    asyncio.run(main())
