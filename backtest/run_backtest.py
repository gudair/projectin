#!/usr/bin/env python3
"""
Backtest Runner

Run backtests against historical data.

Usage:
    # Full Q4 2025 with Ollama
    python -m backtest.run_backtest

    # Q4 2025 without Ollama (faster)
    python -m backtest.run_backtest --no-ollama

    # Custom period
    python -m backtest.run_backtest --start 2025-10-01 --end 2025-10-31

    # Run both with and without Ollama for comparison
    python -m backtest.run_backtest --compare
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime

# Setup logging - minimal during backtest
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
)

# Reduce noise from libraries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('alpaca').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


async def run_single_backtest(
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    use_ollama: bool,
):
    """Run a single backtest"""
    from backtest.engine import run_backtest

    mode = "WITH Ollama" if use_ollama else "WITHOUT Ollama"
    print(f"\n{'='*60}")
    print(f"RUNNING BACKTEST {mode}")
    print(f"{'='*60}\n")

    results = await run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        use_ollama=use_ollama,
        save_report=True,
    )

    return results


async def run_comparison(
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
):
    """Run backtests with and without Ollama for comparison"""

    # Run without Ollama first (faster)
    results_no_ollama = await run_single_backtest(
        start_date, end_date, initial_capital, use_ollama=False
    )

    # Run with Ollama
    results_with_ollama = await run_single_backtest(
        start_date, end_date, initial_capital, use_ollama=True
    )

    # Print comparison
    print("\n" + "="*70)
    print("COMPARISON: WITH vs WITHOUT OLLAMA")
    print("="*70)

    no_ollama = results_no_ollama.get('agent_performance', {})
    with_ollama = results_with_ollama.get('agent_performance', {})

    print(f"\n{'Metric':<30} {'Without Ollama':>18} {'With Ollama':>18}")
    print("-"*70)

    metrics = [
        ('Total Return ($)', 'total_return', '${:+,.2f}'),
        ('Total Return (%)', 'total_return_pct', '{:+.2f}%'),
        ('Total Trades', 'total_trades', '{:d}'),
        ('Win Rate', 'win_rate', '{:.1f}%'),
        ('Profit Factor', 'profit_factor', '{:.2f}'),
        ('Max Drawdown', 'max_drawdown_pct', '{:.2f}%'),
    ]

    for name, key, fmt in metrics:
        val_no = no_ollama.get(key, 0)
        val_with = with_ollama.get(key, 0)

        # Handle formatting
        if 'int' in str(type(val_no)):
            formatted_no = fmt.format(int(val_no))
            formatted_with = fmt.format(int(val_with))
        else:
            formatted_no = fmt.format(val_no)
            formatted_with = fmt.format(val_with)

        print(f"{name:<30} {formatted_no:>18} {formatted_with:>18}")

    print("\n" + "="*70)

    # Determine winner
    ret_no = no_ollama.get('total_return_pct', 0)
    ret_with = with_ollama.get('total_return_pct', 0)

    if ret_with > ret_no:
        diff = ret_with - ret_no
        print(f"✅ OLLAMA performed BETTER by {diff:.2f}%")
    elif ret_no > ret_with:
        diff = ret_no - ret_with
        print(f"⚠️ Simple strategy performed better by {diff:.2f}%")
    else:
        print("🤝 Both performed equally")

    print("="*70 + "\n")

    return {
        'without_ollama': results_no_ollama,
        'with_ollama': results_with_ollama,
    }


def parse_date(date_str: str) -> datetime:
    """Parse date string"""
    return datetime.strptime(date_str, '%Y-%m-%d')


def main():
    parser = argparse.ArgumentParser(
        description='Run backtests against historical data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full Q4 2025 with Ollama
    python -m backtest.run_backtest

    # October 2025 only, without Ollama (faster test)
    python -m backtest.run_backtest --start 2025-10-01 --end 2025-10-31 --no-ollama

    # Compare with and without Ollama
    python -m backtest.run_backtest --compare

    # Custom capital
    python -m backtest.run_backtest --capital 50000
        """,
    )

    parser.add_argument(
        '--start',
        type=parse_date,
        default=datetime(2025, 10, 1),
        help='Start date (YYYY-MM-DD). Default: 2025-10-01',
    )
    parser.add_argument(
        '--end',
        type=parse_date,
        default=datetime(2025, 12, 31),
        help='End date (YYYY-MM-DD). Default: 2025-12-31',
    )
    parser.add_argument(
        '--capital',
        type=float,
        default=100000.0,
        help='Initial capital. Default: $100,000',
    )
    parser.add_argument(
        '--no-ollama',
        action='store_true',
        help='Run without Ollama analysis (faster)',
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Run both with and without Ollama for comparison',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show verbose output',
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "="*60)
    print("AI TRADING AGENT - BACKTEST")
    print("="*60)
    print(f"Period: {args.start.date()} to {args.end.date()}")
    print(f"Capital: ${args.capital:,.2f}")
    print("="*60 + "\n")

    try:
        if args.compare:
            results = asyncio.run(run_comparison(
                args.start,
                args.end,
                args.capital,
            ))
        else:
            results = asyncio.run(run_single_backtest(
                args.start,
                args.end,
                args.capital,
                use_ollama=not args.no_ollama,
            ))

        print("\n✅ Backtest complete! Check backtest/reports/ for detailed results.")

    except KeyboardInterrupt:
        print("\n\n⚠️ Backtest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Backtest failed: {e}")
        logging.exception("Backtest error")
        sys.exit(1)


if __name__ == '__main__':
    main()
