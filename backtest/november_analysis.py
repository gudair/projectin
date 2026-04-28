"""
November 2025 Analysis

Why did we lose money? What was the optimal?
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
import numpy as np

from backtest.daily_data import DailyDataLoader
from backtest.optimal_hunter import OptimalTradeAnalyzer

logging.basicConfig(level=logging.WARNING)


async def analyze_november():
    """Deep dive into November 2025"""

    start = datetime(2025, 11, 1)
    end = datetime(2025, 11, 30)

    print(f"\n{'='*80}")
    print(f"NOVEMBER 2025 DEEP ANALYSIS")
    print(f"{'='*80}")

    # 1. What was the market doing?
    loader = DailyDataLoader()
    await loader.load(['SPY', 'QQQ', 'AMD', 'NVDA', 'COIN', 'TSLA', 'MU'], start - timedelta(days=10), end)

    spy_start = loader.get_price('SPY', start)
    spy_end = loader.get_price('SPY', end)
    spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

    qqq_start = loader.get_price('QQQ', start)
    qqq_end = loader.get_price('QQQ', end)
    qqq_return = (qqq_end - qqq_start) / qqq_start * 100 if qqq_start and qqq_end else 0

    print(f"\n📊 MARKET CONTEXT:")
    print(f"   SPY (S&P 500): {spy_return:+.2f}%")
    print(f"   QQQ (Nasdaq):  {qqq_return:+.2f}%")

    # 2. How did our symbols perform?
    print(f"\n📈 OUR HARDCODED SYMBOLS PERFORMANCE:")
    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
    for symbol in symbols:
        s = loader.get_price(symbol, start)
        e = loader.get_price(symbol, end)
        if s and e:
            ret = (e - s) / s * 100
            print(f"   {symbol}: {ret:+.2f}%")

    # 3. Find optimal trades for November
    print(f"\n🔍 OPTIMAL TRADES ANALYSIS (5%+ potential):")

    # Expand to more symbols to find where the opportunities were
    all_symbols = [
        'AMD', 'NVDA', 'MU', 'QCOM', 'MRVL', 'AVGO', 'INTC',
        'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
        'COIN', 'SQ', 'SHOP', 'PLTR', 'SNOW',
        'JPM', 'V', 'MA', 'GS',
        'XOM', 'CVX', 'OXY',
        'BA', 'CAT', 'DE',
    ]

    analyzer = OptimalTradeAnalyzer()
    optimal = await analyzer.find_optimal_trades(all_symbols, start, end, min_return_pct=0.05)

    print(f"   Found {len(optimal)} optimal trades")

    if optimal:
        # Analyze patterns
        patterns = analyzer.analyze_optimal_patterns(optimal)

        print(f"\n   📊 Optimal Trade Patterns:")
        print(f"      Great trades (10%+): {patterns['great_trades_10pct_plus']}")
        print(f"      Good trades (5-10%): {patterns['good_trades_5_to_10pct']}")
        print(f"      Avg return: {patterns['avg_return']:.1f}%")

        print(f"\n   🏆 Best Symbols in November:")
        for symbol, avg_ret in list(patterns['best_symbols'].items())[:10]:
            count = patterns['symbol_distribution'].get(symbol, 0)
            in_our_list = "✓" if symbol in symbols else ""
            print(f"      {symbol}: {avg_ret:.1f}% avg ({count} trades) {in_our_list}")

        print(f"\n   📋 Top 10 Optimal Trades:")
        sorted_trades = sorted(optimal, key=lambda t: t.pnl_pct, reverse=True)[:10]
        for i, t in enumerate(sorted_trades, 1):
            in_our_list = "✓" if t.symbol in symbols else ""
            print(
                f"      {i:2}. {t.symbol:5} | {t.entry_date.strftime('%m/%d')} | "
                f"+{t.pnl_pct*100:.1f}% in {t.hold_days}d {in_our_list}"
            )

        # Calculate what % of optimal was in our symbols
        our_optimal = [t for t in optimal if t.symbol in symbols]
        other_optimal = [t for t in optimal if t.symbol not in symbols]

        print(f"\n   📊 Optimal Distribution:")
        print(f"      In our symbols ({', '.join(symbols)}): {len(our_optimal)} trades")
        print(f"      In OTHER symbols: {len(other_optimal)} trades")

        if our_optimal:
            our_avg = np.mean([t.pnl_pct for t in our_optimal]) * 100
            print(f"      Our symbols avg return: {our_avg:.1f}%")
        if other_optimal:
            other_avg = np.mean([t.pnl_pct for t in other_optimal]) * 100
            print(f"      Other symbols avg return: {other_avg:.1f}%")

    # 4. What would a weekly scanner have found?
    print(f"\n\n{'='*80}")
    print(f"WEEKLY SCANNER SIMULATION")
    print(f"{'='*80}")

    # Simulate scanning at start of November based on October performance
    print(f"\n🔍 Scanning for best symbols at start of November...")
    print(f"   (Based on October volume, volatility, and momentum)")

    # Load October data for screening
    oct_start = datetime(2025, 10, 1)
    oct_end = datetime(2025, 10, 31)

    screen_symbols = all_symbols
    await loader.load(screen_symbols, oct_start, end)

    # Score each symbol based on October performance
    symbol_scores = []
    for symbol in screen_symbols:
        bars = loader.get_bars(symbol, oct_end, 20)
        if len(bars) < 15:
            continue

        # Calculate metrics
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        # Momentum (October return)
        oct_return = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0

        # Volatility (ATR%)
        true_ranges = []
        for i in range(1, len(bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        atr = np.mean(true_ranges[-14:]) if true_ranges else 0
        atr_pct = atr / closes[-1] if closes[-1] > 0 else 0

        # Volume
        avg_vol = np.mean(volumes)
        dollar_vol = avg_vol * closes[-1]

        symbol_scores.append({
            'symbol': symbol,
            'oct_return': oct_return * 100,
            'atr_pct': atr_pct * 100,
            'dollar_vol': dollar_vol,
        })

    # Sort by October return (momentum)
    symbol_scores.sort(key=lambda x: x['oct_return'], reverse=True)

    print(f"\n   Top 10 by October momentum:")
    for i, s in enumerate(symbol_scores[:10], 1):
        in_optimal = "🎯" if s['symbol'] in [t.symbol for t in optimal[:20]] else ""
        print(f"      {i:2}. {s['symbol']:5} | Oct: {s['oct_return']:+.1f}% | ATR: {s['atr_pct']:.1f}% {in_optimal}")

    # What if we used the top 5 momentum symbols for November?
    momentum_symbols = [s['symbol'] for s in symbol_scores[:5]]
    print(f"\n   Weekly scanner would select: {momentum_symbols}")

    # Check November optimal in those symbols
    momentum_optimal = [t for t in optimal if t.symbol in momentum_symbols]
    print(f"   Optimal trades in scanner symbols: {len(momentum_optimal)}")
    if momentum_optimal:
        momentum_avg = np.mean([t.pnl_pct for t in momentum_optimal]) * 100
        print(f"   Avg optimal return: {momentum_avg:.1f}%")


async def main():
    await analyze_november()


if __name__ == "__main__":
    asyncio.run(main())
