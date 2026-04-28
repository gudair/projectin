"""
Timing Analysis - Find signals that predict bad trading conditions

Analyze November Week 2 (when ALL 7 trades lost) to find warning signals
that could have prevented those losses.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import numpy as np

from backtest.daily_data import DailyDataLoader
from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

logging.basicConfig(level=logging.WARNING)


class TimingAnalyzer:
    """Analyze market conditions to find timing signals"""

    def __init__(self):
        self.data_loader = DailyDataLoader()

    async def analyze_day(self, date: datetime) -> Dict:
        """Get detailed market conditions for a specific day"""
        await self.data_loader.load(
            ['SPY', 'QQQ', 'AMD', 'NVDA', 'COIN', 'TSLA', 'MU'],
            date - timedelta(days=30),
            date
        )

        spy_bars = self.data_loader.get_bars('SPY', date, 25)
        if len(spy_bars) < 20:
            return {'error': 'Insufficient data'}

        closes = [b.close for b in spy_bars]
        highs = [b.high for b in spy_bars]
        lows = [b.low for b in spy_bars]

        current = closes[-1]
        prev_close = closes[-2] if len(closes) > 1 else current

        # Daily return
        daily_return = (current - prev_close) / prev_close * 100

        # Trend: vs 20 SMA
        sma_20 = np.mean(closes[-20:])
        trend_pct = (current - sma_20) / sma_20 * 100

        # Short-term momentum: 3-day and 5-day returns
        mom_3d = (closes[-1] - closes[-4]) / closes[-4] * 100 if len(closes) >= 4 else 0
        mom_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0

        # Volatility: ATR%
        true_ranges = []
        for i in range(1, len(spy_bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        atr_14 = np.mean(true_ranges[-14:]) if len(true_ranges) >= 14 else 0
        atr_5 = np.mean(true_ranges[-5:]) if len(true_ranges) >= 5 else 0
        atr_pct = atr_14 / current * 100

        # Volatility expansion: Is recent vol higher than normal?
        vol_expansion = atr_5 / atr_14 if atr_14 > 0 else 1

        # Count red days in last 5
        red_days_5 = sum(1 for i in range(-5, 0) if closes[i] < closes[i-1])

        # Average daily range last 5 days
        avg_range_5 = np.mean([highs[i] - lows[i] for i in range(-5, 0)]) / current * 100

        # Consecutive red/green days
        consecutive_red = 0
        consecutive_green = 0
        for i in range(-1, -len(closes), -1):
            if closes[i] < closes[i-1]:
                if consecutive_green == 0:
                    consecutive_red += 1
                else:
                    break
            else:
                if consecutive_red == 0:
                    consecutive_green += 1
                else:
                    break

        return {
            'date': date,
            'spy_close': current,
            'daily_return': daily_return,
            'trend_vs_sma': trend_pct,
            'momentum_3d': mom_3d,
            'momentum_5d': mom_5d,
            'atr_pct': atr_pct,
            'vol_expansion': vol_expansion,
            'red_days_5': red_days_5,
            'avg_range_5': avg_range_5,
            'consecutive_red': consecutive_red,
            'consecutive_green': consecutive_green,
        }


async def analyze_november_week2():
    """Deep dive into November Week 2"""

    analyzer = TimingAnalyzer()

    print(f"\n{'='*90}")
    print(f"NOVEMBER WEEK 2 ANALYSIS (Nov 8-14, 2025)")
    print(f"All 7 trades were stopped out - what signals could have warned us?")
    print(f"{'='*90}")

    # Analyze each day of Week 2
    dates = [
        datetime(2025, 11, 7),   # Friday before
        datetime(2025, 11, 10),  # Monday
        datetime(2025, 11, 11),  # Tuesday
        datetime(2025, 11, 12),  # Wednesday
        datetime(2025, 11, 13),  # Thursday
        datetime(2025, 11, 14),  # Friday
    ]

    print(f"\n{'Date':<12} | {'SPY':>7} | {'Daily':>7} | {'Trend':>7} | {'Mom3d':>7} | {'Mom5d':>7} | {'ATR%':>6} | {'VolExp':>6} | {'Red5':>5}")
    print("-" * 90)

    for date in dates:
        conditions = await analyzer.analyze_day(date)
        if 'error' in conditions:
            continue

        print(
            f"{date.strftime('%Y-%m-%d'):<12} | "
            f"${conditions['spy_close']:>6.0f} | "
            f"{conditions['daily_return']:>+6.2f}% | "
            f"{conditions['trend_vs_sma']:>+6.2f}% | "
            f"{conditions['momentum_3d']:>+6.2f}% | "
            f"{conditions['momentum_5d']:>+6.2f}% | "
            f"{conditions['atr_pct']:>5.2f}% | "
            f"{conditions['vol_expansion']:>5.2f}x | "
            f"{conditions['red_days_5']:>5}"
        )

    # Compare to good weeks
    print(f"\n{'='*90}")
    print(f"COMPARISON: GOOD WEEKS vs BAD WEEKS")
    print(f"{'='*90}")

    good_weeks = [
        (datetime(2025, 10, 14), "Oct 14 - Good week"),
        (datetime(2025, 10, 21), "Oct 21 - Good week"),
        (datetime(2025, 12, 2), "Dec 2 - Good week"),
    ]

    bad_weeks = [
        (datetime(2025, 11, 10), "Nov 10 - Bad week"),
        (datetime(2025, 11, 17), "Nov 17 - Mixed"),
    ]

    print(f"\n📈 GOOD WEEKS:")
    for date, label in good_weeks:
        conditions = await analyzer.analyze_day(date)
        if 'error' not in conditions:
            print(
                f"  {label}: Trend {conditions['trend_vs_sma']:+.2f}%, "
                f"Mom5d {conditions['momentum_5d']:+.2f}%, "
                f"ATR {conditions['atr_pct']:.2f}%, "
                f"VolExp {conditions['vol_expansion']:.2f}x"
            )

    print(f"\n📉 BAD WEEKS:")
    for date, label in bad_weeks:
        conditions = await analyzer.analyze_day(date)
        if 'error' not in conditions:
            print(
                f"  {label}: Trend {conditions['trend_vs_sma']:+.2f}%, "
                f"Mom5d {conditions['momentum_5d']:+.2f}%, "
                f"ATR {conditions['atr_pct']:.2f}%, "
                f"VolExp {conditions['vol_expansion']:.2f}x"
            )


async def find_timing_signals():
    """Find which signals best predict bad trading conditions"""

    analyzer = TimingAnalyzer()
    loader = DailyDataLoader()

    # Get all trading days Sep-Dec 2025
    start = datetime(2025, 9, 1)
    end = datetime(2025, 12, 31)

    await loader.load(['SPY'], start, end)
    trading_days = loader.get_trading_days(start, end)

    print(f"\n{'='*90}")
    print(f"SIGNAL ANALYSIS: What predicts bad trading days?")
    print(f"{'='*90}")

    # For each day, get conditions and run a mini backtest
    results = []

    config = AggressiveBacktestConfig(
        max_positions=2,
        position_size_pct=0.50,
        stop_loss_pct=0.02,
        take_profit_pct=0.10,
        trailing_stop_pct=0.02,
        max_hold_days=4,
        require_bullish_market=False,
    )
    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    # Run weekly backtests and correlate with conditions
    week_results = []
    current_week = None

    for day in trading_days:
        week_num = day.isocalendar()[1]

        if week_num != current_week:
            current_week = week_num
            week_start = day
            week_end = day + timedelta(days=6)
            if week_end > end:
                week_end = end

            # Get conditions at start of week
            conditions = await analyzer.analyze_day(day)
            if 'error' in conditions:
                continue

            # Run backtest for this week
            engine = AggressiveBacktestEngine(
                week_start, week_end, config, symbols=symbols
            )
            bt_results = await engine.run()

            week_results.append({
                'week_start': week_start,
                'conditions': conditions,
                'return_pct': bt_results['performance']['total_return_pct'],
                'trades': bt_results['trades']['total'],
                'win_rate': bt_results['trades']['win_rate'],
            })

    # Analyze correlations
    print(f"\n{'Week Start':<12} | {'Return':>8} | {'Trend':>7} | {'Mom5d':>7} | {'ATR%':>6} | {'VolExp':>6} | {'Signal':>10}")
    print("-" * 80)

    for wr in week_results:
        c = wr['conditions']
        ret = wr['return_pct']

        # Determine signal based on conditions
        signals = []
        if c['momentum_5d'] < -1.5:
            signals.append('NEG_MOM')
        if c['vol_expansion'] > 1.3:
            signals.append('HIGH_VOL')
        if c['trend_vs_sma'] < -1.0 and c['momentum_5d'] < 0:
            signals.append('BEARISH')

        signal_str = ','.join(signals) if signals else 'CLEAR'

        marker = "📈" if ret > 0 else "📉"

        print(
            f"{c['date'].strftime('%Y-%m-%d'):<12} | "
            f"{ret:>+7.2f}% | "
            f"{c['trend_vs_sma']:>+6.2f}% | "
            f"{c['momentum_5d']:>+6.2f}% | "
            f"{c['atr_pct']:>5.2f}% | "
            f"{c['vol_expansion']:>5.2f}x | "
            f"{signal_str:<10} {marker}"
        )

    # Calculate signal effectiveness
    print(f"\n{'='*90}")
    print(f"SIGNAL EFFECTIVENESS")
    print(f"{'='*90}")

    # Group by signal presence
    clear_weeks = [w for w in week_results if
                   w['conditions']['momentum_5d'] >= -1.5 and
                   w['conditions']['vol_expansion'] <= 1.3]
    warning_weeks = [w for w in week_results if
                    w['conditions']['momentum_5d'] < -1.5 or
                    w['conditions']['vol_expansion'] > 1.3]

    if clear_weeks:
        clear_avg = np.mean([w['return_pct'] for w in clear_weeks])
        print(f"\n✅ CLEAR signal weeks ({len(clear_weeks)}): Avg return {clear_avg:+.2f}%")

    if warning_weeks:
        warning_avg = np.mean([w['return_pct'] for w in warning_weeks])
        print(f"⚠️  WARNING signal weeks ({len(warning_weeks)}): Avg return {warning_avg:+.2f}%")

    # Find optimal thresholds
    print(f"\n📊 OPTIMAL THRESHOLDS:")

    # Test different momentum thresholds
    for mom_thresh in [-0.5, -1.0, -1.5, -2.0, -2.5]:
        clear = [w for w in week_results if w['conditions']['momentum_5d'] >= mom_thresh]
        skip = [w for w in week_results if w['conditions']['momentum_5d'] < mom_thresh]

        if clear and skip:
            clear_avg = np.mean([w['return_pct'] for w in clear])
            skip_avg = np.mean([w['return_pct'] for w in skip])
            print(f"   Mom5d >= {mom_thresh:+.1f}%: Trade {len(clear)} weeks ({clear_avg:+.2f}%), Skip {len(skip)} weeks ({skip_avg:+.2f}%)")


if __name__ == "__main__":
    asyncio.run(analyze_november_week2())
    asyncio.run(find_timing_signals())
