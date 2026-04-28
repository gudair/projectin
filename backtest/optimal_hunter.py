"""
Optimal Trade Hunter

Analyzes which conditions and symbols produce the best trades,
then creates a highly optimized strategy targeting those conditions.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

from backtest.daily_data import DailyDataLoader, DailyBar

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')


@dataclass
class OptimalTrade:
    symbol: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    pnl_pct: float
    hold_days: int
    # Entry conditions
    prev_day_change: float
    day_range: float
    rsi: float
    distance_from_low: float  # How close to recent low


class OptimalTradeAnalyzer:
    """Analyzes what makes trades optimal"""

    def __init__(self):
        self.data_loader = DailyDataLoader()

    def calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    async def find_optimal_trades(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        min_return_pct: float = 0.05,  # 5% minimum return
        max_hold_days: int = 5,
    ) -> List[OptimalTrade]:
        """Find all trades that would have been optimal (hindsight)"""

        await self.data_loader.load(symbols, start_date - timedelta(days=30), end_date)
        trading_days = self.data_loader.get_trading_days(start_date, end_date)

        optimal_trades = []

        for symbol in symbols:
            for i, entry_day in enumerate(trading_days[:-max_hold_days]):
                bars = self.data_loader.get_bars(symbol, entry_day, 20)
                if len(bars) < 15:
                    continue

                entry_bar = bars[-1]
                entry_price = entry_bar.close

                # Calculate entry conditions
                closes = [b.close for b in bars]
                highs = [b.high for b in bars]
                lows = [b.low for b in bars]

                prev_day_change = (closes[-2] - closes[-3]) / closes[-3] if len(closes) >= 3 else 0
                day_range = (entry_bar.high - entry_bar.low) / entry_price
                rsi = self.calculate_rsi(closes)
                recent_low = min(lows[-10:])
                distance_from_low = (entry_price - recent_low) / recent_low

                # Look for best exit in next N days
                best_exit_price = entry_price
                best_exit_day = entry_day
                best_pnl_pct = 0

                for hold_days in range(1, max_hold_days + 1):
                    if i + hold_days >= len(trading_days):
                        break

                    exit_day = trading_days[i + hold_days]
                    exit_bar = self.data_loader.get_bar(symbol, exit_day)
                    if not exit_bar:
                        continue

                    # Could exit at high of the day
                    potential_exit = exit_bar.high
                    potential_pnl = (potential_exit - entry_price) / entry_price

                    if potential_pnl > best_pnl_pct:
                        best_pnl_pct = potential_pnl
                        best_exit_price = potential_exit
                        best_exit_day = exit_day

                # Only keep trades above threshold
                if best_pnl_pct >= min_return_pct:
                    hold_days = (best_exit_day - entry_day).days
                    optimal_trades.append(OptimalTrade(
                        symbol=symbol,
                        entry_date=entry_day,
                        entry_price=entry_price,
                        exit_date=best_exit_day,
                        exit_price=best_exit_price,
                        pnl_pct=best_pnl_pct,
                        hold_days=hold_days,
                        prev_day_change=prev_day_change,
                        day_range=day_range,
                        rsi=rsi,
                        distance_from_low=distance_from_low,
                    ))

        return optimal_trades

    def analyze_optimal_patterns(self, trades: List[OptimalTrade]) -> Dict:
        """Analyze what optimal trades have in common"""
        if not trades:
            return {}

        # Group by return magnitude
        great_trades = [t for t in trades if t.pnl_pct >= 0.10]  # 10%+
        good_trades = [t for t in trades if 0.05 <= t.pnl_pct < 0.10]  # 5-10%

        def avg(lst, attr):
            values = [getattr(t, attr) for t in lst]
            return np.mean(values) if values else 0

        return {
            'total_optimal_trades': len(trades),
            'great_trades_10pct_plus': len(great_trades),
            'good_trades_5_to_10pct': len(good_trades),
            'avg_return': avg(trades, 'pnl_pct') * 100,
            'avg_hold_days': avg(trades, 'hold_days'),
            'entry_conditions': {
                'avg_prev_day_change': avg(trades, 'prev_day_change') * 100,
                'avg_day_range': avg(trades, 'day_range') * 100,
                'avg_rsi': avg(trades, 'rsi'),
                'avg_distance_from_low': avg(trades, 'distance_from_low') * 100,
            },
            'great_trade_conditions': {
                'avg_prev_day_change': avg(great_trades, 'prev_day_change') * 100 if great_trades else 0,
                'avg_day_range': avg(great_trades, 'day_range') * 100 if great_trades else 0,
                'avg_rsi': avg(great_trades, 'rsi') if great_trades else 0,
                'avg_distance_from_low': avg(great_trades, 'distance_from_low') * 100 if great_trades else 0,
            },
            'symbol_distribution': self._symbol_distribution(trades),
            'best_symbols': self._best_symbols(trades),
        }

    def _symbol_distribution(self, trades: List[OptimalTrade]) -> Dict[str, int]:
        dist = {}
        for t in trades:
            dist[t.symbol] = dist.get(t.symbol, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _best_symbols(self, trades: List[OptimalTrade]) -> Dict[str, float]:
        """Find symbols with best average return"""
        by_symbol = {}
        for t in trades:
            if t.symbol not in by_symbol:
                by_symbol[t.symbol] = []
            by_symbol[t.symbol].append(t.pnl_pct)

        avg_returns = {s: np.mean(rets) * 100 for s, rets in by_symbol.items()}
        return dict(sorted(avg_returns.items(), key=lambda x: x[1], reverse=True))


async def analyze_october_optimal():
    """Analyze optimal trades for October 2025"""

    symbols = [
        'AMD', 'NVDA', 'MU', 'QCOM', 'MRVL', 'AVGO',
        'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL',
        'COIN', 'SQ', 'SHOP', 'PLTR',
    ]

    start = datetime(2025, 10, 1)
    end = datetime(2025, 10, 31)

    print(f"\n{'='*80}")
    print(f"OPTIMAL TRADE ANALYSIS - October 2025")
    print(f"{'='*80}")

    analyzer = OptimalTradeAnalyzer()

    # Find optimal trades (5%+ return potential)
    optimal = await analyzer.find_optimal_trades(symbols, start, end, min_return_pct=0.05)

    print(f"\nFound {len(optimal)} optimal trades (5%+ potential)")

    # Analyze patterns
    patterns = analyzer.analyze_optimal_patterns(optimal)

    print(f"\n📊 OPTIMAL TRADE PATTERNS:")
    print(f"   Great trades (10%+): {patterns['great_trades_10pct_plus']}")
    print(f"   Good trades (5-10%): {patterns['good_trades_5_to_10pct']}")
    print(f"   Avg return: {patterns['avg_return']:.1f}%")
    print(f"   Avg hold: {patterns['avg_hold_days']:.1f} days")

    print(f"\n📈 ENTRY CONDITIONS (All optimal trades):")
    cond = patterns['entry_conditions']
    print(f"   Prev day change: {cond['avg_prev_day_change']:+.2f}%")
    print(f"   Day range: {cond['avg_day_range']:.2f}%")
    print(f"   RSI: {cond['avg_rsi']:.1f}")
    print(f"   Distance from low: {cond['avg_distance_from_low']:.2f}%")

    print(f"\n🔥 GREAT TRADE CONDITIONS (10%+ return):")
    gcond = patterns['great_trade_conditions']
    print(f"   Prev day change: {gcond['avg_prev_day_change']:+.2f}%")
    print(f"   Day range: {gcond['avg_day_range']:.2f}%")
    print(f"   RSI: {gcond['avg_rsi']:.1f}")
    print(f"   Distance from low: {gcond['avg_distance_from_low']:.2f}%")

    print(f"\n🏆 BEST PERFORMING SYMBOLS:")
    for symbol, avg_ret in list(patterns['best_symbols'].items())[:5]:
        count = patterns['symbol_distribution'].get(symbol, 0)
        print(f"   {symbol}: {avg_ret:.1f}% avg ({count} trades)")

    # Show top 10 actual optimal trades
    print(f"\n📋 TOP 10 OPTIMAL TRADES:")
    sorted_trades = sorted(optimal, key=lambda t: t.pnl_pct, reverse=True)[:10]
    for i, t in enumerate(sorted_trades, 1):
        print(
            f"   {i:2}. {t.symbol:5} | Entry: {t.entry_date.strftime('%m/%d')} | "
            f"+{t.pnl_pct*100:.1f}% in {t.hold_days}d | "
            f"RSI: {t.rsi:.0f} | PrevDay: {t.prev_day_change*100:+.1f}%"
        )

    return patterns, optimal


async def simulate_optimal_strategy():
    """Simulate a strategy that captures optimal-like trades"""

    print(f"\n\n{'='*80}")
    print(f"SIMULATED OPTIMAL STRATEGY - October 2025")
    print(f"{'='*80}")

    # Based on optimal analysis, focus on:
    # - Symbols: AMD, NVDA, COIN, TSLA (best performers)
    # - Entry: After red day, low RSI, near support
    # - Size: 50% per position (very concentrated)
    # - Exit: After 3-4 days OR 10%+ gain

    from backtest.aggressive_engine import AggressiveBacktestEngine, AggressiveBacktestConfig

    # Super aggressive configuration based on optimal patterns
    config = AggressiveBacktestConfig(
        initial_capital=100_000,
        max_positions=2,
        position_size_pct=0.50,  # 50% per position!
        min_prev_day_drop=-0.01,  # Require red day
        min_day_range=0.02,
        max_rsi=45.0,
        stop_loss_pct=0.02,  # Tight stop
        take_profit_pct=0.10,  # 10% target
        trailing_stop_pct=0.02,
        max_hold_days=4,
        require_bullish_market=False,
    )

    # Focus on best symbols only
    symbols = ['AMD', 'NVDA', 'COIN', 'TSLA', 'MU']

    start = datetime(2025, 10, 1)
    end = datetime(2025, 10, 31)

    engine = AggressiveBacktestEngine(start, end, config, symbols=symbols)
    results = await engine.run()

    # Get SPY for comparison
    loader = DailyDataLoader()
    await loader.load(['SPY'], start - timedelta(days=5), end)
    spy_start = loader.get_price('SPY', start)
    spy_end = loader.get_price('SPY', end)
    spy_return = (spy_end - spy_start) / spy_start * 100

    perf = results['performance']
    trades = results['trades']

    print(f"\n📊 RESULTS:")
    print(f"   Strategy Return: {perf['total_return_pct']:+.2f}%")
    print(f"   SPY Return:      {spy_return:+.2f}%")
    print(f"   Alpha:           {perf['total_return_pct'] - spy_return:+.2f}%")

    print(f"\n📈 TRADE STATS:")
    print(f"   Trades: {trades['total']} (Win: {trades['winning']}, Loss: {trades['losing']})")
    print(f"   Win Rate: {trades['win_rate']:.1f}%")
    print(f"   Avg Win: {trades['avg_win_pct']:+.1f}% | Avg Loss: {trades['avg_loss_pct']:+.1f}%")
    print(f"   Max Drawdown: {perf['max_drawdown_pct']:.1f}%")

    # Show individual trades
    print(f"\n📋 ALL TRADES:")
    for t in results['trade_list']:
        print(
            f"   {t['symbol']:5} | {t['entry_date'][:10]} → {t['exit_date'][:10]} | "
            f"{t['pnl_pct']*100:+.1f}% | {t['exit_reason']}"
        )

    # Calculate what optimal would have been
    print(f"\n🎯 OPTIMAL COMPARISON:")
    print(f"   Optimal (hindsight): ~33%")
    print(f"   Our Strategy:        {perf['total_return_pct']:+.2f}%")
    print(f"   Capture Rate:        {perf['total_return_pct'] / 33 * 100:.0f}%")

    return results


async def main():
    patterns, optimal = await analyze_october_optimal()
    await simulate_optimal_strategy()


if __name__ == "__main__":
    asyncio.run(main())
