"""
November Trade Analysis - When did we lose?
"""

import asyncio
import logging
from datetime import datetime, timedelta

from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

logging.basicConfig(level=logging.WARNING)


async def analyze_november_trades():
    """Show all November trades"""

    config = AggressiveBacktestConfig(
        initial_capital=100_000,
        max_positions=2,
        position_size_pct=0.50,
        min_prev_day_drop=-0.01,
        min_day_range=0.02,
        max_rsi=45.0,
        stop_loss_pct=0.02,
        take_profit_pct=0.10,
        trailing_stop_pct=0.02,
        max_hold_days=4,
        require_bullish_market=False,
    )

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    start = datetime(2025, 11, 1)
    end = datetime(2025, 11, 30)

    engine = AggressiveBacktestEngine(start, end, config, symbols=symbols)
    results = await engine.run()

    print(f"\n{'='*80}")
    print(f"NOVEMBER 2025 - ALL TRADES DETAIL")
    print(f"{'='*80}")

    print(f"\nTotal Return: {results['performance']['total_return_pct']:+.2f}%")
    print(f"Trades: {results['trades']['total']} (Win: {results['trades']['winning']}, Loss: {results['trades']['losing']})")
    print(f"Win Rate: {results['trades']['win_rate']:.0f}%")

    # Group by week
    trades = results['trade_list']

    print(f"\n📅 TRADES BY WEEK:")
    print("-" * 80)

    weeks = {
        'Week 1 (Nov 1-7)': [],
        'Week 2 (Nov 8-14)': [],
        'Week 3 (Nov 15-21)': [],
        'Week 4 (Nov 22-30)': [],
    }

    for t in trades:
        entry = datetime.fromisoformat(t['entry_date'])
        if entry.day <= 7:
            weeks['Week 1 (Nov 1-7)'].append(t)
        elif entry.day <= 14:
            weeks['Week 2 (Nov 8-14)'].append(t)
        elif entry.day <= 21:
            weeks['Week 3 (Nov 15-21)'].append(t)
        else:
            weeks['Week 4 (Nov 22-30)'].append(t)

    for week, week_trades in weeks.items():
        if not week_trades:
            print(f"\n{week}: No trades")
            continue

        week_pnl = sum(t['pnl'] for t in week_trades)
        week_wins = len([t for t in week_trades if t['pnl_pct'] > 0])
        week_losses = len([t for t in week_trades if t['pnl_pct'] <= 0])

        print(f"\n{week}: {len(week_trades)} trades | P&L: ${week_pnl:+,.0f} | W:{week_wins} L:{week_losses}")

        for t in week_trades:
            emoji = "✅" if t['pnl_pct'] > 0 else "❌"
            print(
                f"   {emoji} {t['symbol']:5} | {t['entry_date'][:10]} → {t['exit_date'][:10]} | "
                f"{t['pnl_pct']*100:+5.1f}% | {t['exit_reason']}"
            )

    # Summary
    print(f"\n{'='*80}")
    print(f"PROBLEM ANALYSIS")
    print(f"{'='*80}")

    # Count stop loss vs other exits
    stop_losses = [t for t in trades if 'Stop loss' in t['exit_reason']]
    trailing_stops = [t for t in trades if 'Trailing' in t['exit_reason']]

    print(f"\nExit breakdown:")
    print(f"   Stop losses: {len(stop_losses)} ({sum(t['pnl'] for t in stop_losses):+,.0f})")
    print(f"   Trailing stops: {len(trailing_stops)} ({sum(t['pnl'] for t in trailing_stops):+,.0f})")

    # The issue: November optimal trades started Nov 20, but we traded all month
    print(f"\n💡 KEY INSIGHT:")
    print(f"   Optimal trades in November started around Nov 20")
    print(f"   Our strategy traded all month, hitting stop losses early")
    print(f"   Solution: Need market regime filter or momentum confirmation")


async def main():
    await analyze_november_trades()


if __name__ == "__main__":
    asyncio.run(main())
