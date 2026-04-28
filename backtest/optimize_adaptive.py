"""
Optimize Adaptive Timing Parameters

Test different circuit breaker configurations to find the best balance
between protecting against losses and capturing gains.
"""

import asyncio
from datetime import datetime, timedelta
import numpy as np
from itertools import product

from backtest.daily_data import DailyDataLoader
from backtest.adaptive_timing import AdaptiveTimingEngine, AdaptiveConfig
from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig


async def grid_search_adaptive():
    """Grid search for optimal adaptive parameters"""

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30)),
        (datetime(2025, 10, 1), datetime(2025, 10, 31)),
        (datetime(2025, 11, 1), datetime(2025, 11, 30)),
        (datetime(2025, 12, 1), datetime(2025, 12, 31)),
    ]

    # Parameters to test
    max_losses_options = [2, 3, 4, 5]  # More lenient options
    cooldown_options = [1, 2, 3]
    momentum_options = [-0.5, -1.0, -1.5, -2.0]

    print(f"{'='*100}")
    print(f"GRID SEARCH: Optimal Adaptive Parameters")
    print(f"Testing {len(max_losses_options) * len(cooldown_options) * len(momentum_options)} combinations")
    print(f"{'='*100}")

    # Get baseline first
    loader = DailyDataLoader()
    total_basic = 0

    for start, end in periods:
        basic_config = AggressiveBacktestConfig(
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,
        )
        engine = AggressiveBacktestEngine(start, end, basic_config, symbols=symbols)
        results = await engine.run()
        total_basic += results['performance']['total_return_pct']

    avg_basic = total_basic / len(periods)
    print(f"\n📊 Baseline (no adaptive): {avg_basic:+.2f}% average monthly return")
    print(f"\nSearching for configurations that beat baseline...\n")

    best_configs = []

    for max_losses, cooldown, momentum in product(max_losses_options, cooldown_options, momentum_options):
        total_return = 0
        cb_triggers = 0

        for start, end in periods:
            config = AdaptiveConfig(
                base_position_size_pct=0.50,
                max_positions=2,
                stop_loss_pct=0.02,
                take_profit_pct=0.10,
                trailing_stop_pct=0.02,
                max_hold_days=4,
                max_consecutive_losses=max_losses,
                cooldown_days=cooldown,
                min_spy_momentum_3d=momentum,
                max_atr_pct=2.0,  # More lenient
                scale_down_after_loss=0.7,  # Less aggressive scaling
                scale_up_after_win=1.1,  # Less aggressive scaling
            )

            engine = AdaptiveTimingEngine(start, end, config, symbols=symbols)
            results = await engine.run()
            total_return += results['performance']['total_return_pct']
            cb_triggers += results['adaptive']['circuit_breaker_triggers']

        avg_return = total_return / len(periods)

        if avg_return > avg_basic * 0.9:  # Within 10% of baseline
            best_configs.append({
                'max_losses': max_losses,
                'cooldown': cooldown,
                'momentum': momentum,
                'avg_return': avg_return,
                'cb_triggers': cb_triggers,
                'improvement': avg_return - avg_basic,
            })

    # Sort by average return
    best_configs.sort(key=lambda x: x['avg_return'], reverse=True)

    print(f"{'Max Losses':<12} | {'Cooldown':<10} | {'Mom Thresh':<12} | {'Avg Return':>12} | {'vs Basic':>10} | {'CB Triggers':>11}")
    print("-" * 85)

    for config in best_configs[:15]:  # Top 15
        print(
            f"{config['max_losses']:<12} | "
            f"{config['cooldown']:<10} | "
            f"{config['momentum']:>+11.1f}% | "
            f"{config['avg_return']:>+11.2f}% | "
            f"{config['improvement']:>+9.2f}% | "
            f"{config['cb_triggers']:>11}"
        )

    if best_configs:
        best = best_configs[0]
        print(f"\n✅ BEST CONFIGURATION:")
        print(f"   Max consecutive losses: {best['max_losses']}")
        print(f"   Cooldown days: {best['cooldown']}")
        print(f"   Min SPY momentum: {best['momentum']:+.1f}%")
        print(f"   Average return: {best['avg_return']:+.2f}%")
        print(f"   Improvement vs basic: {best['improvement']:+.2f}%")

        return best

    return None


async def test_best_config():
    """Test the best configuration in detail"""

    best = await grid_search_adaptive()

    if not best:
        print("\n❌ No configuration beats baseline")
        return

    print(f"\n{'='*100}")
    print(f"DETAILED TEST OF BEST CONFIGURATION")
    print(f"{'='*100}")

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
    loader = DailyDataLoader()

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
    ]

    print(f"\n{'Period':<12} | {'SPY':>8} | {'Basic':>10} | {'Adaptive':>10} | {'Winner':>10}")
    print("-" * 70)

    for start, end, name in periods:
        # SPY
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

        # Basic
        basic_config = AggressiveBacktestConfig(
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,
        )
        basic_engine = AggressiveBacktestEngine(start, end, basic_config, symbols=symbols)
        basic_results = await basic_engine.run()
        basic_return = basic_results['performance']['total_return_pct']

        # Adaptive with best params
        config = AdaptiveConfig(
            base_position_size_pct=0.50,
            max_positions=2,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            max_consecutive_losses=best['max_losses'],
            cooldown_days=best['cooldown'],
            min_spy_momentum_3d=best['momentum'],
            max_atr_pct=2.0,
            scale_down_after_loss=0.7,
            scale_up_after_win=1.1,
        )
        adaptive_engine = AdaptiveTimingEngine(start, end, config, symbols=symbols)
        adaptive_results = await adaptive_engine.run()
        adaptive_return = adaptive_results['performance']['total_return_pct']

        winner = "ADAPTIVE" if adaptive_return > basic_return else "BASIC"

        print(
            f"{name:<12} | {spy_return:>+7.2f}% | {basic_return:>+9.2f}% | "
            f"{adaptive_return:>+9.2f}% | {winner:>10}"
        )


async def test_simple_momentum_filter():
    """Test just using momentum filter without circuit breakers"""

    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']
    loader = DailyDataLoader()

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
    ]

    print(f"\n{'='*100}")
    print(f"SIMPLE MOMENTUM FILTER ONLY (No Circuit Breaker)")
    print(f"Only trade when SPY 3d momentum > -1.5%")
    print(f"{'='*100}")

    print(f"\n{'Period':<12} | {'SPY':>8} | {'Basic':>10} | {'Momentum Filter':>16}")
    print("-" * 60)

    total_basic = 0
    total_filtered = 0

    for start, end, name in periods:
        # SPY
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start and spy_end else 0

        # Basic
        basic_config = AggressiveBacktestConfig(
            max_positions=2,
            position_size_pct=0.50,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            require_bullish_market=False,
        )
        basic_engine = AggressiveBacktestEngine(start, end, basic_config, symbols=symbols)
        basic_results = await basic_engine.run()
        basic_return = basic_results['performance']['total_return_pct']

        # Just momentum filter, no circuit breaker
        config = AdaptiveConfig(
            base_position_size_pct=0.50,
            max_positions=2,
            stop_loss_pct=0.02,
            take_profit_pct=0.10,
            trailing_stop_pct=0.02,
            max_hold_days=4,
            max_consecutive_losses=100,  # Effectively disabled
            cooldown_days=0,
            min_spy_momentum_3d=-1.5,
            max_atr_pct=2.5,  # More lenient
            scale_down_after_loss=1.0,  # No scaling
            scale_up_after_win=1.0,  # No scaling
        )
        filtered_engine = AdaptiveTimingEngine(start, end, config, symbols=symbols)
        filtered_results = await filtered_engine.run()
        filtered_return = filtered_results['performance']['total_return_pct']

        total_basic += basic_return
        total_filtered += filtered_return

        print(
            f"{name:<12} | {spy_return:>+7.2f}% | {basic_return:>+9.2f}% | "
            f"{filtered_return:>+15.2f}%"
        )

    print("-" * 60)
    avg_basic = total_basic / len(periods)
    avg_filtered = total_filtered / len(periods)

    print(
        f"{'AVERAGE':<12} | {'':>8} | {avg_basic:>+9.2f}% | "
        f"{avg_filtered:>+15.2f}%"
    )

    if avg_filtered > avg_basic:
        print(f"\n✅ Momentum filter IMPROVES returns by {avg_filtered - avg_basic:+.2f}%")
    else:
        print(f"\n❌ Momentum filter REDUCES returns by {avg_filtered - avg_basic:.2f}%")


if __name__ == "__main__":
    asyncio.run(test_simple_momentum_filter())
    asyncio.run(test_best_config())
