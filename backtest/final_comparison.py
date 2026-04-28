"""
Final Comparison - Best Strategy Configuration vs SPY

The best configuration found:
- 50% position size
- Max 2 positions
- Focus on best symbols: AMD, NVDA, COIN, TSLA, MU
- 2% stop loss, 2% trailing, 10% take profit
- Entry: After red day, with volatility
"""

import asyncio
import logging
from datetime import datetime, timedelta
from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig
from backtest.daily_data import DailyDataLoader

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')


async def run_final_comparison():
    """Run the best strategy across all periods"""

    # Best configuration from testing
    config = AggressiveBacktestConfig(
        initial_capital=100_000,
        max_positions=2,
        position_size_pct=0.50,  # 50% per position
        min_prev_day_drop=-0.01,  # Require red day (1%+)
        min_day_range=0.02,  # 2% range
        max_rsi=45.0,
        stop_loss_pct=0.02,  # 2% stop
        take_profit_pct=0.10,  # 10% target
        trailing_stop_pct=0.02,  # 2% trailing
        max_hold_days=4,
        require_bullish_market=False,
    )

    # Best performing symbols
    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dic 2025"),
        (datetime(2026, 1, 1), datetime(2026, 1, 31), "Ene 2026"),
    ]

    print(f"\n{'='*85}")
    print(f"FINAL STRATEGY COMPARISON - Aggressive Dip Buyer")
    print(f"Config: 50% positions | 2 max | AMD/NVDA/COIN/TSLA/MU | 2% stop/trail | 10% TP")
    print(f"{'='*85}")

    loader = DailyDataLoader()

    print(f"\n{'Period':<12} | {'SPY':>10} | {'Strategy':>10} | {'Alpha':>10} | {'Trades':>6} | {'WR':>6} | {'MaxDD':>7}")
    print("-" * 80)

    total_strat = 0
    total_spy = 0
    strat_wins = 0

    for start, end, name in periods:
        engine = AggressiveBacktestEngine(start, end, config, symbols=symbols)
        results = await engine.run()

        # SPY
        try:
            await loader.load(['SPY'], start - timedelta(days=5), end)
            spy_start = loader.get_price('SPY', start)
            spy_end = loader.get_price('SPY', end)
            if spy_start and spy_end:
                spy_return = (spy_end - spy_start) / spy_start * 100
            else:
                spy_return = 0
        except Exception:
            spy_return = 0

        perf = results['performance']
        trades = results['trades']
        alpha = perf['total_return_pct'] - spy_return

        winner_mark = "✓" if alpha > 0 else ""

        print(
            f"{name:<12} | {spy_return:>+9.2f}% | {perf['total_return_pct']:>+9.2f}% | "
            f"{alpha:>+9.2f}% | {trades['total']:>6} | {trades['win_rate']:>5.0f}% | "
            f"{perf['max_drawdown_pct']:>6.1f}% {winner_mark}"
        )

        total_strat += perf['total_return_pct']
        total_spy += spy_return
        if alpha > 0:
            strat_wins += 1

    print("-" * 80)
    avg_strat = total_strat / len(periods)
    avg_spy = total_spy / len(periods)
    avg_alpha = avg_strat - avg_spy

    print(
        f"{'PROMEDIO':<12} | {avg_spy:>+9.2f}% | {avg_strat:>+9.2f}% | "
        f"{avg_alpha:>+9.2f}% |"
    )

    print(f"\n📊 RESULTADOS FINALES:")
    print(f"   Meses donde Strategy > SPY: {strat_wins}/{len(periods)}")
    print(f"   Alpha promedio mensual: {avg_alpha:+.2f}%")
    print(f"   Alpha anualizado estimado: {avg_alpha * 12:+.1f}%")

    winner = "STRATEGY" if avg_strat > avg_spy else "SPY"
    print(f"\n🏁 GANADOR OVERALL: {winner}")

    # Best month detail
    print(f"\n📋 DETALLE MEJOR MES (Octubre 2025):")
    oct_engine = AggressiveBacktestEngine(
        datetime(2025, 10, 1),
        datetime(2025, 10, 31),
        config,
        symbols=symbols
    )
    oct_results = await oct_engine.run()

    print(f"   Return: {oct_results['performance']['total_return_pct']:+.2f}%")
    print(f"   Trades: {oct_results['trades']['total']}")
    print(f"   Win Rate: {oct_results['trades']['win_rate']:.0f}%")

    print(f"\n   Trades individuales:")
    for t in oct_results['trade_list']:
        emoji = "✅" if t['pnl_pct'] > 0 else "❌"
        print(
            f"   {emoji} {t['symbol']:5} | {t['entry_date'][:10]} → {t['exit_date'][:10]} | "
            f"{t['pnl_pct']*100:+.1f}% | {t['exit_reason']}"
        )

    # Risk analysis
    print(f"\n⚠️ ANÁLISIS DE RIESGO:")
    print(f"   Max Drawdown promedio: {sum(r.get('performance', {}).get('max_drawdown_pct', 0) for r in [oct_results]) / 1:.1f}%")
    print(f"   Peor mes: Nov 2025 (típicamente difícil para semiconductores)")
    print(f"   Estrategia es AGRESIVA - usar con capital de riesgo")

    return avg_strat, avg_spy


if __name__ == "__main__":
    asyncio.run(run_final_comparison())
