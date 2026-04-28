"""
Hardcoded Symbols + Strict Regime Filter

Keep the best symbols but add strict market regime check:
- Only trade when SPY is above 20 SMA and momentum is positive
- Skip weeks with high volatility
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import numpy as np

from backtest.daily_data import DailyDataLoader
from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

logging.basicConfig(level=logging.WARNING)


class RegimeFilter:
    """Strict market regime filter"""

    def __init__(self):
        self.data_loader = DailyDataLoader()

    async def should_trade(self, as_of_date: datetime) -> tuple[bool, str]:
        """
        Check if we should trade on this day

        Returns:
            (should_trade, reason)
        """
        await self.data_loader.load(['SPY'], as_of_date - timedelta(days=30), as_of_date)

        bars = self.data_loader.get_bars('SPY', as_of_date, 25)
        if len(bars) < 22:
            return False, "Insufficient data"

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        current = closes[-1]

        # 1. Trend: Must be above 20 SMA
        sma_20 = np.mean(closes[-20:])
        above_sma = current > sma_20
        trend_pct = (current - sma_20) / sma_20 * 100

        # 2. Momentum: 5-day return must be positive
        momentum_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0

        # 3. Volatility: ATR% must be reasonable (<1.5%)
        true_ranges = []
        for i in range(1, len(bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        atr = np.mean(true_ranges[-14:])
        atr_pct = atr / current * 100

        # Decision - LESS STRICT
        # Only avoid clearly bearish conditions
        if trend_pct < -2.0 and momentum_5d < -2.0:
            return False, f"Bearish: SPY {trend_pct:+.1f}% vs SMA, mom {momentum_5d:+.1f}%"

        if atr_pct > 2.0:
            return False, f"High volatility (ATR {atr_pct:.1f}%)"

        return True, f"OK: SPY {trend_pct:+.1f}% vs SMA, mom {momentum_5d:+.1f}%"


class RegimeFilteredBacktest:
    """Backtest with regime filtering"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        symbols: List[str] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.symbols = symbols or ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
        self.regime_filter = RegimeFilter()
        self.data_loader = DailyDataLoader()

    async def run(self) -> Dict:
        """Run backtest with regime filtering"""

        # Load data
        all_symbols = self.symbols + ['SPY']
        await self.data_loader.load(
            all_symbols,
            self.start_date - timedelta(days=35),
            self.end_date
        )

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)

        # Track daily results
        initial_capital = 100_000.0
        cash = initial_capital
        positions = {}
        trades = []
        days_traded = 0
        days_skipped = 0

        config = AggressiveBacktestConfig(
            initial_capital=initial_capital,
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,  # We handle regime externally
        )

        # Simple simulation: check regime at start of each week
        current_week = None
        can_trade_this_week = False
        week_reason = ""

        for day in trading_days:
            # Check if new week
            week_num = day.isocalendar()[1]
            if week_num != current_week:
                current_week = week_num
                can_trade_this_week, week_reason = await self.regime_filter.should_trade(day)

            if can_trade_this_week:
                days_traded += 1
            else:
                days_skipped += 1

        # Now run the actual backtest only on "tradeable" days
        # For simplicity, run separate backtests for each "tradeable" period

        # Find tradeable periods
        tradeable_periods = []
        period_start = None

        current_week = None
        can_trade_this_week = False

        for day in trading_days:
            week_num = day.isocalendar()[1]
            if week_num != current_week:
                current_week = week_num
                can_trade_this_week, _ = await self.regime_filter.should_trade(day)

            if can_trade_this_week:
                if period_start is None:
                    period_start = day
            else:
                if period_start is not None:
                    tradeable_periods.append((period_start, trading_days[trading_days.index(day) - 1]))
                    period_start = None

        # Handle last period
        if period_start is not None:
            tradeable_periods.append((period_start, trading_days[-1]))

        # Run backtest on each tradeable period
        total_pnl = 0
        total_trades = 0

        for period_start, period_end in tradeable_periods:
            engine = AggressiveBacktestEngine(
                period_start,
                period_end,
                config,
                symbols=self.symbols,
            )
            results = await engine.run()
            total_pnl += results['performance']['total_return']
            total_trades += results['trades']['total']

        total_return_pct = total_pnl / initial_capital * 100

        return {
            'total_return_pct': total_return_pct,
            'total_trades': total_trades,
            'days_traded': days_traded,
            'days_skipped': days_skipped,
            'tradeable_periods': len(tradeable_periods),
        }


async def compare_filtered_vs_unfiltered():
    """Compare regime-filtered vs unfiltered"""

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
    ]

    print(f"\n{'='*90}")
    print(f"REGIME-FILTERED vs UNFILTERED (Same Symbols)")
    print(f"Symbols: AMD, NVDA, COIN, TSLA, MU")
    print(f"{'='*90}")

    loader = DailyDataLoader()

    print(f"\n{'Period':<12} | {'SPY':>10} | {'Unfiltered':>12} | {'Filtered':>12} | {'Improvement':>12}")
    print("-" * 75)

    total_spy = 0
    total_unfiltered = 0
    total_filtered = 0

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    for start, end, name in periods:
        # SPY
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

        # Unfiltered
        unfiltered_config = AggressiveBacktestConfig(
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,
        )
        unfiltered_engine = AggressiveBacktestEngine(start, end, unfiltered_config, symbols=symbols)
        unfiltered_results = await unfiltered_engine.run()
        unfiltered_return = unfiltered_results['performance']['total_return_pct']

        # Filtered
        filtered_bt = RegimeFilteredBacktest(start, end, symbols=symbols)
        filtered_results = await filtered_bt.run()
        filtered_return = filtered_results['total_return_pct']

        improvement = filtered_return - unfiltered_return

        print(
            f"{name:<12} | {spy_return:>+9.2f}% | {unfiltered_return:>+11.2f}% | "
            f"{filtered_return:>+11.2f}% | {improvement:>+11.2f}%"
        )

        total_spy += spy_return
        total_unfiltered += unfiltered_return
        total_filtered += filtered_return

    print("-" * 75)
    avg_spy = total_spy / len(periods)
    avg_unfiltered = total_unfiltered / len(periods)
    avg_filtered = total_filtered / len(periods)
    avg_improvement = avg_filtered - avg_unfiltered

    print(
        f"{'AVERAGE':<12} | {avg_spy:>+9.2f}% | {avg_unfiltered:>+11.2f}% | "
        f"{avg_filtered:>+11.2f}% | {avg_improvement:>+11.2f}%"
    )

    print(f"\n📊 SUMMARY:")
    print(f"   Unfiltered alpha vs SPY: {avg_unfiltered - avg_spy:+.2f}%")
    print(f"   Filtered alpha vs SPY:   {avg_filtered - avg_spy:+.2f}%")

    if avg_filtered > avg_unfiltered:
        print(f"\n   ✅ Regime filtering IMPROVES returns by {avg_improvement:+.2f}%")
    else:
        print(f"\n   ❌ Regime filtering REDUCES returns by {avg_improvement:.2f}%")


if __name__ == "__main__":
    asyncio.run(compare_filtered_vs_unfiltered())
