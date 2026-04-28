"""
Universe Analysis - Find Best Dip-Buying Symbols

Analyze a broad universe of stocks to find which ones have
the best characteristics for dip-buying:
1. High volatility (2-4% daily range)
2. Strong mean-reversion after red days
3. High liquidity
4. Best risk-adjusted returns on dip entries
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

from alpaca.client import AlpacaClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# Broad universe of high-beta, liquid stocks
UNIVERSE = [
    # Current strategy symbols
    'AMD', 'NVDA', 'COIN', 'TSLA', 'MU',

    # Semiconductors
    'QCOM', 'MRVL', 'AVGO', 'INTC', 'AMAT', 'LRCX', 'KLAC', 'ASML', 'ON', 'SMCI',

    # Big Tech
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NFLX',

    # Fintech / Crypto-related
    'SQ', 'PYPL', 'MARA', 'RIOT', 'MSTR', 'HOOD', 'SOFI',

    # E-commerce / Growth
    'SHOP', 'ETSY', 'PINS', 'SNAP', 'UBER', 'LYFT', 'DASH', 'ABNB',

    # Software / Cloud
    'CRM', 'NOW', 'SNOW', 'PLTR', 'DDOG', 'NET', 'ZS', 'CRWD', 'MDB', 'PATH',

    # EV / Clean Energy
    'RIVN', 'LCID', 'NIO', 'XPEV', 'LI', 'ENPH', 'SEDG', 'FSLR',

    # Biotech (high volatility)
    'MRNA', 'BNTX', 'CRSP', 'EDIT', 'NTLA',

    # Industrial / Other High Beta
    'BA', 'CAT', 'DE', 'X', 'CLF', 'FCX', 'FREEPORT',

    # Meme / Retail favorites
    'GME', 'AMC', 'BBBY', 'SPCE', 'WKHS',

    # Index ETFs (for comparison)
    'SPY', 'QQQ', 'IWM', 'ARKK', 'SOXL', 'TQQQ',
]


@dataclass
class OptimalTrade:
    """A perfect hindsight trade"""
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    return_pct: float
    hold_days: int
    prev_day_return: float  # Previous day's return (looking for red days)


@dataclass
class SymbolStats:
    """Statistics for a symbol's dip-buying potential"""
    symbol: str
    total_optimal_trades: int
    avg_return: float
    win_rate: float
    avg_hold_days: float
    avg_daily_range: float  # Volatility
    avg_volume: float  # Liquidity
    dip_recovery_rate: float  # % of red days that recovered
    sharpe_like_ratio: float  # Return / volatility
    total_potential_return: float  # Sum of all optimal trade returns


class UniverseAnalyzer:
    """Analyze entire universe for optimal dip-buying candidates"""

    def __init__(self):
        self.client = AlpacaClient()
        self.data: Dict[str, List] = {}

    async def load_data(self, symbols: List[str], days: int = 365):
        """Load historical data for all symbols"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)  # Extra for lookback

        print(f"Loading data for {len(symbols)} symbols...")

        loaded = 0
        for i, symbol in enumerate(symbols):
            if i > 0 and i % 20 == 0:
                print(f"  Progress: {i}/{len(symbols)} symbols loaded")
                await asyncio.sleep(0.3)  # Rate limit

            try:
                bars = await self.client.get_bars(
                    symbol=symbol,
                    timeframe='1Day',
                    start=start_date,
                    end=end_date,
                    limit=500,
                )

                if bars and len(bars) >= 50:  # Need at least 50 days
                    self.data[symbol] = bars
                    loaded += 1

            except Exception as e:
                logger.debug(f"Failed to load {symbol}: {e}")

        print(f"Loaded {loaded} symbols with sufficient data")
        await self.client.close()

    def find_optimal_trades(
        self,
        symbol: str,
        min_return: float = 0.03,  # Minimum 3% return
        max_hold_days: int = 5,
        require_prev_red: bool = True,
    ) -> List[OptimalTrade]:
        """Find optimal dip-buying trades for a symbol"""

        if symbol not in self.data:
            return []

        bars = self.data[symbol]
        if len(bars) < 10:
            return []

        trades = []

        for i in range(2, len(bars) - max_hold_days):
            entry_bar = bars[i]
            prev_bar = bars[i - 1]

            # Check if previous day was red (if required)
            prev_return = (prev_bar.close - prev_bar.open) / prev_bar.open

            if require_prev_red and prev_return >= 0:
                continue

            entry_price = entry_bar.close

            # Find best exit within max_hold_days
            best_exit_price = entry_price
            best_exit_idx = i

            for j in range(i + 1, min(i + max_hold_days + 1, len(bars))):
                if bars[j].high > best_exit_price:
                    best_exit_price = bars[j].high
                    best_exit_idx = j

            return_pct = (best_exit_price - entry_price) / entry_price

            if return_pct >= min_return:
                trades.append(OptimalTrade(
                    symbol=symbol,
                    entry_date=entry_bar.timestamp,
                    exit_date=bars[best_exit_idx].timestamp,
                    entry_price=entry_price,
                    exit_price=best_exit_price,
                    return_pct=return_pct,
                    hold_days=best_exit_idx - i,
                    prev_day_return=prev_return,
                ))

        return trades

    def calculate_symbol_stats(self, symbol: str) -> SymbolStats:
        """Calculate dip-buying statistics for a symbol"""

        if symbol not in self.data:
            return None

        bars = self.data[symbol]

        # Find optimal trades
        trades = self.find_optimal_trades(symbol, min_return=0.03)

        # Calculate daily ranges (volatility)
        ranges = [(b.high - b.low) / b.close for b in bars]
        avg_range = np.mean(ranges) * 100

        # Calculate average volume
        avg_volume = np.mean([b.volume for b in bars])

        # Calculate dip recovery rate
        red_days = 0
        recovered_days = 0

        for i in range(1, len(bars) - 1):
            if bars[i].close < bars[i].open:  # Red day
                red_days += 1
                # Check if next day recovered
                if bars[i + 1].close > bars[i].close:
                    recovered_days += 1

        dip_recovery = recovered_days / red_days if red_days > 0 else 0

        # Calculate stats
        if trades:
            avg_return = np.mean([t.return_pct for t in trades]) * 100
            win_rate = 100.0  # All trades are winners by definition (min 3%)
            avg_hold = np.mean([t.hold_days for t in trades])
            total_potential = sum(t.return_pct for t in trades) * 100
        else:
            avg_return = 0
            win_rate = 0
            avg_hold = 0
            total_potential = 0

        # Sharpe-like ratio (return per unit volatility)
        sharpe = avg_return / avg_range if avg_range > 0 else 0

        return SymbolStats(
            symbol=symbol,
            total_optimal_trades=len(trades),
            avg_return=avg_return,
            win_rate=win_rate,
            avg_hold_days=avg_hold,
            avg_daily_range=avg_range,
            avg_volume=avg_volume,
            dip_recovery_rate=dip_recovery * 100,
            sharpe_like_ratio=sharpe,
            total_potential_return=total_potential,
        )


async def analyze_universe():
    """Main analysis function"""

    analyzer = UniverseAnalyzer()

    # Load data for entire universe
    await analyzer.load_data(UNIVERSE, days=365)

    print(f"\n{'='*100}")
    print(f"UNIVERSE ANALYSIS - Best Dip-Buying Symbols (Last 12 Months)")
    print(f"{'='*100}")

    # Calculate stats for all symbols
    all_stats = []

    for symbol in analyzer.data.keys():
        stats = analyzer.calculate_symbol_stats(symbol)
        if stats and stats.total_optimal_trades >= 5:  # At least 5 trades
            all_stats.append(stats)

    # Sort by total potential return
    all_stats.sort(key=lambda x: x.total_potential_return, reverse=True)

    # Current strategy symbols
    current_symbols = {'AMD', 'NVDA', 'COIN', 'TSLA', 'MU'}

    print(f"\n📊 TOP 30 SYMBOLS BY DIP-BUYING POTENTIAL:")
    print(f"\n{'Rank':<5} | {'Symbol':<6} | {'Trades':>7} | {'Avg Ret':>8} | {'Tot Pot':>9} | {'Range%':>7} | {'Recovery':>8} | {'In List?':<8}")
    print("-" * 90)

    for i, stats in enumerate(all_stats[:30], 1):
        in_list = "✅ YES" if stats.symbol in current_symbols else ""
        print(
            f"{i:<5} | {stats.symbol:<6} | {stats.total_optimal_trades:>7} | "
            f"{stats.avg_return:>+7.1f}% | {stats.total_potential_return:>+8.0f}% | "
            f"{stats.avg_daily_range:>6.1f}% | {stats.dip_recovery_rate:>7.0f}% | {in_list:<8}"
        )

    # Find symbols NOT in current list that should be
    print(f"\n{'='*100}")
    print(f"🔍 SYMBOLS TO CONSIDER ADDING (Not in current list, top performers):")
    print(f"{'='*100}")

    candidates = [s for s in all_stats if s.symbol not in current_symbols][:15]

    print(f"\n{'Symbol':<6} | {'Trades':>7} | {'Avg Ret':>8} | {'Tot Pot':>9} | {'Range%':>7} | {'Recovery':>8} | {'Vol (M)':>10}")
    print("-" * 85)

    for stats in candidates:
        vol_millions = stats.avg_volume / 1_000_000
        print(
            f"{stats.symbol:<6} | {stats.total_optimal_trades:>7} | "
            f"{stats.avg_return:>+7.1f}% | {stats.total_potential_return:>+8.0f}% | "
            f"{stats.avg_daily_range:>6.1f}% | {stats.dip_recovery_rate:>7.0f}% | {vol_millions:>9.1f}M"
        )

    # Compare current list vs optimal
    print(f"\n{'='*100}")
    print(f"📈 CURRENT STRATEGY SYMBOLS RANKING:")
    print(f"{'='*100}")

    current_stats = [s for s in all_stats if s.symbol in current_symbols]
    current_stats.sort(key=lambda x: x.total_potential_return, reverse=True)

    for stats in current_stats:
        rank = all_stats.index(stats) + 1
        print(f"   {stats.symbol}: Rank #{rank} | {stats.total_optimal_trades} trades | {stats.total_potential_return:+.0f}% potential")

    # Recommendation
    print(f"\n{'='*100}")
    print(f"💡 RECOMMENDATION:")
    print(f"{'='*100}")

    # Find the best not-in-list symbols
    best_new = [s for s in all_stats[:10] if s.symbol not in current_symbols]

    if best_new:
        print(f"\nConsider ADDING these symbols to the strategy:")
        for s in best_new[:5]:
            print(f"   + {s.symbol}: {s.total_optimal_trades} trades, {s.total_potential_return:+.0f}% potential, {s.avg_daily_range:.1f}% daily range")

    # Find current symbols that underperform
    weak_current = [s for s in all_stats if s.symbol in current_symbols and all_stats.index(s) > 20]
    if weak_current:
        print(f"\nConsider REMOVING these symbols (underperforming):")
        for s in weak_current:
            rank = all_stats.index(s) + 1
            print(f"   - {s.symbol}: Rank #{rank}")

    # Optimal symbol list
    print(f"\n🎯 SUGGESTED OPTIMAL SYMBOL LIST:")

    # Take top performers that have good liquidity and volatility
    optimal = []
    for s in all_stats:
        if s.avg_volume >= 5_000_000:  # At least 5M avg volume
            if 2.0 <= s.avg_daily_range <= 6.0:  # Good volatility range
                optimal.append(s.symbol)
                if len(optimal) >= 8:
                    break

    print(f"   {optimal}")

    return all_stats


if __name__ == "__main__":
    asyncio.run(analyze_universe())
