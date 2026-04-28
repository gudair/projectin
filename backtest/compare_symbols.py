"""
Symbol Comparison Backtest

Compare OLD symbols (AMD, NVDA, COIN, TSLA, MU) vs
NEW symbols (SOXL, SMCI, MARA, COIN, MU) selected via universe analysis.

Uses OPTIMAL parameters confirmed in previous backtests:
- 50% position size, max 2 positions
- 2% stop loss, 2% trailing stop, 10% take profit
- Entry after red day + volatility
- NO market regime filter
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass

from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig
from backtest.daily_data import DailyDataLoader

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# OPTIMAL PARAMETERS (confirmed via extensive backtesting)
OPTIMAL_CONFIG = AggressiveBacktestConfig(
    initial_capital=100_000.0,
    max_positions=2,           # Concentrated
    position_size_pct=0.50,    # 50% per position
    min_prev_day_drop=-0.01,   # Previous day red
    min_day_range=0.02,        # 2% daily range
    max_rsi=45.0,              # RSI below 45
    stop_loss_pct=0.02,        # 2% stop loss
    take_profit_pct=0.10,      # 10% take profit
    trailing_stop_pct=0.02,    # 2% trailing stop
    max_hold_days=4,
    require_bullish_market=False,  # NO regime filter
)

# Symbol lists to compare
OLD_SYMBOLS = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
NEW_SYMBOLS = ['SOXL', 'SMCI', 'MARA', 'COIN', 'MU']


async def run_backtest_for_symbols(
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    label: str,
) -> Dict[str, Any]:
    """Run backtest for a specific symbol list"""

    engine = AggressiveBacktestEngine(
        start_date=start_date,
        end_date=end_date,
        config=OPTIMAL_CONFIG,
        symbols=symbols,
    )

    results = await engine.run()
    results['label'] = label
    results['symbols'] = symbols

    return results


async def compare_symbols():
    """Compare old vs new symbols over multiple periods"""

    print("=" * 80)
    print("SYMBOL COMPARISON BACKTEST")
    print("=" * 80)
    print(f"OLD: {OLD_SYMBOLS}")
    print(f"NEW: {NEW_SYMBOLS}")
    print("-" * 80)
    print("Config: 50% positions, 2 max, 2% SL, 2% trail, 10% TP, no regime filter")
    print("=" * 80)

    # Define test periods (monthly)
    periods = [
        (datetime(2025, 3, 1), datetime(2025, 3, 31), "Mar 2025"),
        (datetime(2025, 4, 1), datetime(2025, 4, 30), "Apr 2025"),
        (datetime(2025, 5, 1), datetime(2025, 5, 31), "May 2025"),
        (datetime(2025, 6, 1), datetime(2025, 6, 30), "Jun 2025"),
        (datetime(2025, 7, 1), datetime(2025, 7, 31), "Jul 2025"),
        (datetime(2025, 8, 1), datetime(2025, 8, 31), "Aug 2025"),
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
        (datetime(2026, 1, 1), datetime(2026, 1, 31), "Jan 2026"),
        (datetime(2026, 2, 1), datetime(2026, 2, 24), "Feb 2026"),
    ]

    # Get SPY returns for each period
    loader = DailyDataLoader()
    all_symbols = list(set(OLD_SYMBOLS + NEW_SYMBOLS + ['SPY']))
    await loader.load(all_symbols, datetime(2025, 2, 1), datetime(2026, 2, 25))

    results_table = []

    for start, end, label in periods:
        print(f"\n📅 Testing {label}...")

        try:
            # Run both backtests
            old_results = await run_backtest_for_symbols(OLD_SYMBOLS, start, end, f"OLD-{label}")
            new_results = await run_backtest_for_symbols(NEW_SYMBOLS, start, end, f"NEW-{label}")

            # Get SPY return
            spy_start = loader.get_price('SPY', start)
            spy_end = loader.get_price('SPY', end)
            spy_return = ((spy_end - spy_start) / spy_start * 100) if spy_start and spy_end else 0

            old_return = old_results['performance']['total_return_pct']
            new_return = new_results['performance']['total_return_pct']

            results_table.append({
                'period': label,
                'spy': spy_return,
                'old': old_return,
                'new': new_return,
                'old_trades': old_results['trades']['total'],
                'new_trades': new_results['trades']['total'],
                'old_winrate': old_results['trades']['win_rate'],
                'new_winrate': new_results['trades']['win_rate'],
            })

        except Exception as e:
            print(f"   Error: {e}")
            results_table.append({
                'period': label,
                'spy': 0,
                'old': 0,
                'new': 0,
                'old_trades': 0,
                'new_trades': 0,
                'old_winrate': 0,
                'new_winrate': 0,
            })

    # Print results table
    print("\n")
    print("=" * 100)
    print("RESULTS COMPARISON")
    print("=" * 100)
    print(f"\n{'Period':<12} | {'SPY':>8} | {'OLD':>10} | {'NEW':>10} | {'Winner':<8} | {'OLD Trades':>10} | {'NEW Trades':>10}")
    print("-" * 100)

    old_total = 0
    new_total = 0
    spy_total = 0
    old_wins = 0
    new_wins = 0

    for r in results_table:
        winner = "OLD" if r['old'] > r['new'] else "NEW" if r['new'] > r['old'] else "TIE"
        if r['old'] > r['new']:
            old_wins += 1
        elif r['new'] > r['old']:
            new_wins += 1

        old_total += r['old']
        new_total += r['new']
        spy_total += r['spy']

        print(f"{r['period']:<12} | {r['spy']:>+7.1f}% | {r['old']:>+9.1f}% | {r['new']:>+9.1f}% | {winner:<8} | {r['old_trades']:>10} | {r['new_trades']:>10}")

    print("-" * 100)

    n_periods = len(results_table)
    print(f"{'AVERAGE':<12} | {spy_total/n_periods:>+7.1f}% | {old_total/n_periods:>+9.1f}% | {new_total/n_periods:>+9.1f}% |")
    print(f"{'TOTAL':<12} | {spy_total:>+7.1f}% | {old_total:>+9.1f}% | {new_total:>+9.1f}% |")

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    print(f"\nOLD Symbols: {OLD_SYMBOLS}")
    print(f"  - Average Monthly Return: {old_total/n_periods:+.2f}%")
    print(f"  - Total Return: {old_total:+.2f}%")
    print(f"  - Months Won: {old_wins}/{n_periods}")

    print(f"\nNEW Symbols: {NEW_SYMBOLS}")
    print(f"  - Average Monthly Return: {new_total/n_periods:+.2f}%")
    print(f"  - Total Return: {new_total:+.2f}%")
    print(f"  - Months Won: {new_wins}/{n_periods}")

    print(f"\nSPY Benchmark:")
    print(f"  - Average Monthly Return: {spy_total/n_periods:+.2f}%")
    print(f"  - Total Return: {spy_total:+.2f}%")

    improvement = new_total - old_total
    print(f"\n🎯 IMPROVEMENT: NEW vs OLD = {improvement:+.2f}%")

    if new_total > old_total:
        print("✅ NEW SYMBOLS ARE BETTER!")
    else:
        print("❌ OLD SYMBOLS WERE BETTER - Keep original list")

    return results_table


if __name__ == "__main__":
    asyncio.run(compare_symbols())
