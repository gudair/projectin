"""
Backtest with Weekly Scanner

Tests the aggressive strategy WITH the weekly scanner:
- Scanner runs once per week
- Only trades when market regime is favorable
- Dynamically selects symbols based on momentum/volatility
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np

from backtest.daily_data import DailyDataLoader
from backtest.weekly_scanner import WeeklyScanner, MarketRegime
from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

logging.basicConfig(level=logging.WARNING)


@dataclass
class ScannerBacktestConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 2
    position_size_pct: float = 0.50
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.10
    trailing_stop_pct: float = 0.02
    max_hold_days: int = 4
    # Scanner settings
    scan_top_n: int = 5
    min_momentum: float = 0.0  # Minimum 10-day return to trade a symbol


class ScannerBacktest:
    """Backtest with weekly symbol scanning and market regime awareness"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: ScannerBacktestConfig = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or ScannerBacktestConfig()
        self.scanner = WeeklyScanner()
        self.data_loader = DailyDataLoader()

    async def run(self) -> Dict:
        """Run backtest with weekly scanning"""

        # Get all Mondays in the period (scan dates)
        current = self.start_date
        results_by_week = []
        total_return_pct = 0
        weeks_traded = 0
        weeks_skipped = 0

        while current <= self.end_date:
            # Find the Monday of this week
            week_start = current - timedelta(days=current.weekday())
            week_end = min(week_start + timedelta(days=6), self.end_date)

            if week_start < self.start_date:
                week_start = self.start_date

            # Run scanner for this week
            symbols, regime = await self.scanner.scan_symbols(week_start, self.config.scan_top_n)

            week_result = {
                'week_start': week_start,
                'week_end': week_end,
                'regime': regime.regime,
                'should_trade': regime.should_trade,
                'symbols': [s.symbol for s in symbols],
                'return_pct': 0,
                'trades': 0,
                'reason': regime.reason,
            }

            if regime.should_trade and symbols:
                # Filter symbols by minimum momentum
                filtered_symbols = [
                    s.symbol for s in symbols
                    if s.recent_return >= self.config.min_momentum
                ]

                if filtered_symbols:
                    # Run aggressive backtest for this week
                    engine_config = AggressiveBacktestConfig(
                        initial_capital=self.config.initial_capital,
                        max_positions=self.config.max_positions,
                        position_size_pct=self.config.position_size_pct,
                        stop_loss_pct=self.config.stop_loss_pct,
                        take_profit_pct=self.config.take_profit_pct,
                        trailing_stop_pct=self.config.trailing_stop_pct,
                        max_hold_days=self.config.max_hold_days,
                        require_bullish_market=False,
                    )

                    engine = AggressiveBacktestEngine(
                        week_start,
                        week_end,
                        engine_config,
                        symbols=filtered_symbols,
                    )

                    week_results = await engine.run()

                    week_result['return_pct'] = week_results['performance']['total_return_pct']
                    week_result['trades'] = week_results['trades']['total']
                    total_return_pct += week_result['return_pct']
                    weeks_traded += 1
                else:
                    week_result['should_trade'] = False
                    week_result['reason'] = 'No symbols with positive momentum'
                    weeks_skipped += 1
            else:
                weeks_skipped += 1

            results_by_week.append(week_result)

            # Move to next week
            current = week_end + timedelta(days=1)

        return {
            'total_return_pct': total_return_pct,
            'weeks_traded': weeks_traded,
            'weeks_skipped': weeks_skipped,
            'results_by_week': results_by_week,
        }


async def compare_scanner_vs_hardcoded():
    """Compare scanner-based vs hardcoded symbols"""

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
    ]

    print(f"\n{'='*90}")
    print(f"SCANNER-BASED vs HARDCODED COMPARISON")
    print(f"{'='*90}")

    loader = DailyDataLoader()

    print(f"\n{'Period':<12} | {'SPY':>10} | {'Hardcoded':>10} | {'Scanner':>10} | {'Best':>10}")
    print("-" * 65)

    total_spy = 0
    total_hardcoded = 0
    total_scanner = 0

    for start, end, name in periods:
        # SPY return
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

        # Hardcoded approach
        hardcoded_config = AggressiveBacktestConfig(
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,
        )
        hardcoded_engine = AggressiveBacktestEngine(
            start, end, hardcoded_config,
            symbols=['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
        )
        hardcoded_results = await hardcoded_engine.run()
        hardcoded_return = hardcoded_results['performance']['total_return_pct']

        # Scanner approach
        scanner_bt = ScannerBacktest(start, end)
        scanner_results = await scanner_bt.run()
        scanner_return = scanner_results['total_return_pct']

        best = "SCANNER" if scanner_return > hardcoded_return else "HARDCODED"
        if spy_return > max(scanner_return, hardcoded_return):
            best = "SPY"

        print(
            f"{name:<12} | {spy_return:>+9.2f}% | {hardcoded_return:>+9.2f}% | "
            f"{scanner_return:>+9.2f}% | {best:>10}"
        )

        total_spy += spy_return
        total_hardcoded += hardcoded_return
        total_scanner += scanner_return

    print("-" * 65)
    avg_spy = total_spy / len(periods)
    avg_hardcoded = total_hardcoded / len(periods)
    avg_scanner = total_scanner / len(periods)

    best_overall = "SCANNER" if avg_scanner > avg_hardcoded else "HARDCODED"
    if avg_spy > max(avg_scanner, avg_hardcoded):
        best_overall = "SPY"

    print(
        f"{'AVERAGE':<12} | {avg_spy:>+9.2f}% | {avg_hardcoded:>+9.2f}% | "
        f"{avg_scanner:>+9.2f}% | {best_overall:>10}"
    )

    print(f"\n📊 ANALYSIS:")
    print(f"   Hardcoded alpha vs SPY: {avg_hardcoded - avg_spy:+.2f}%")
    print(f"   Scanner alpha vs SPY:   {avg_scanner - avg_spy:+.2f}%")
    print(f"   Scanner vs Hardcoded:   {avg_scanner - avg_hardcoded:+.2f}%")

    # Show November detail
    print(f"\n📅 NOVEMBER DETAIL (Scanner):")
    nov_scanner = ScannerBacktest(datetime(2025, 11, 1), datetime(2025, 11, 30))
    nov_results = await nov_scanner.run()

    for week in nov_results['results_by_week']:
        trade_str = "✅" if week['should_trade'] else "❌"
        print(
            f"   {week['week_start'].strftime('%m/%d')} | {trade_str} {week['regime']:<10} | "
            f"Symbols: {', '.join(week['symbols'][:3]) if week['symbols'] else 'NONE'} | "
            f"Return: {week['return_pct']:+.2f}%"
        )


if __name__ == "__main__":
    asyncio.run(compare_scanner_vs_hardcoded())
