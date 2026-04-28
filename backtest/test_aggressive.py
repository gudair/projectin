"""
Test aggressive strategy with different configurations
"""

import asyncio
import logging
from datetime import datetime, timedelta
from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig
from backtest.daily_data import DailyDataLoader

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')


async def test_configuration(
    start: datetime,
    end: datetime,
    name: str,
    config: AggressiveBacktestConfig,
) -> dict:
    """Test a specific configuration"""
    engine = AggressiveBacktestEngine(start, end, config)
    results = await engine.run()
    return {
        'name': name,
        'return_pct': results['performance']['total_return_pct'],
        'trades': results['trades']['total'],
        'win_rate': results['trades']['win_rate'],
        'max_dd': results['performance']['max_drawdown_pct'],
        'profit_factor': results['trades']['profit_factor'],
    }


async def compare_configurations():
    """Compare different configurations"""

    # Test October 2025 (known good month for dip buying)
    start = datetime(2025, 10, 1)
    end = datetime(2025, 10, 31)

    print(f"\n{'='*80}")
    print(f"CONFIGURATION COMPARISON - October 2025")
    print(f"{'='*80}")

    configs = {
        'Conservative (with regime)': AggressiveBacktestConfig(
            require_bullish_market=True,
            position_size_pct=0.25,
            max_positions=3,
        ),
        'No Regime Filter': AggressiveBacktestConfig(
            require_bullish_market=False,
            position_size_pct=0.25,
            max_positions=3,
        ),
        'Ultra Concentrated': AggressiveBacktestConfig(
            require_bullish_market=False,
            position_size_pct=0.40,  # 40% per position
            max_positions=2,  # Max 2 positions
            stop_loss_pct=0.02,  # Tighter stop
        ),
        'High Confidence Only': AggressiveBacktestConfig(
            require_bullish_market=False,
            position_size_pct=0.30,
            max_positions=3,
            min_prev_day_drop=-0.02,  # Need bigger red day
            min_day_range=0.03,  # Need bigger range
            max_rsi=35.0,  # More oversold
        ),
    }

    results = []
    for name, config in configs.items():
        result = await test_configuration(start, end, name, config)
        results.append(result)
        print(f"\n{name}:")
        print(f"   Return: {result['return_pct']:+.2f}%")
        print(f"   Trades: {result['trades']} | Win Rate: {result['win_rate']:.1f}%")
        print(f"   Max DD: {result['max_dd']:.1f}% | PF: {result['profit_factor']:.2f}")

    # Get SPY return
    loader = DailyDataLoader()
    await loader.load(['SPY'], start - timedelta(days=5), end)
    spy_start = loader.get_price('SPY', start)
    spy_end = loader.get_price('SPY', end)
    spy_return = (spy_end - spy_start) / spy_start * 100

    print(f"\n{'='*80}")
    print(f"BENCHMARK: SPY = {spy_return:+.2f}%")
    print(f"{'='*80}")

    # Find best config
    best = max(results, key=lambda x: x['return_pct'])
    print(f"\n🏆 BEST CONFIG: {best['name']} with {best['return_pct']:+.2f}%")

    return results, spy_return


async def run_best_config_multiple_periods():
    """Run the best configuration across multiple periods"""

    print(f"\n\n{'='*80}")
    print(f"MULTI-PERIOD TEST - Ultra Concentrated Strategy")
    print(f"{'='*80}")

    # Best config based on testing
    config = AggressiveBacktestConfig(
        require_bullish_market=False,
        position_size_pct=0.40,
        max_positions=2,
        stop_loss_pct=0.02,
        take_profit_pct=0.12,
        trailing_stop_pct=0.025,
    )

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dic 2025"),
    ]

    loader = DailyDataLoader()
    total_agg = 0
    total_spy = 0

    print(f"\n{'Period':<12} | {'SPY':>10} | {'Strategy':>10} | {'Alpha':>10} | {'Trades':>8}")
    print("-" * 60)

    for start, end, name in periods:
        result = await test_configuration(start, end, name, config)

        # Get SPY return
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start else 0

        alpha = result['return_pct'] - spy_return

        print(f"{name:<12} | {spy_return:>+9.2f}% | {result['return_pct']:>+9.2f}% | {alpha:>+9.2f}% | {result['trades']:>8}")

        total_agg += result['return_pct']
        total_spy += spy_return

    print("-" * 60)
    avg_agg = total_agg / len(periods)
    avg_spy = total_spy / len(periods)
    print(f"{'AVERAGE':<12} | {avg_spy:>+9.2f}% | {avg_agg:>+9.2f}% | {avg_agg - avg_spy:>+9.2f}% |")

    winner = "STRATEGY" if avg_agg > avg_spy else "SPY"
    print(f"\n🏁 OVERALL WINNER: {winner}")


async def main():
    await compare_configurations()
    await run_best_config_multiple_periods()


if __name__ == "__main__":
    asyncio.run(main())
