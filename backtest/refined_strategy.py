"""
Refined Strategy Based on Optimal Trade Analysis

Key findings:
- Optimal trades DON'T require previous red day
- Focus on volatility (day range) not direction
- Semiconductors are the best performers
- RSI doesn't need to be oversold
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np

from backtest.daily_data import DailyDataLoader, DailyBar

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')


@dataclass
class RefinedPosition:
    symbol: str
    qty: float
    entry_price: float
    entry_date: datetime
    stop_loss: float
    high_since_entry: float


@dataclass
class RefinedTrade:
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str


@dataclass
class RefinedConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 2
    position_size_pct: float = 0.50  # 50% per position (VERY concentrated)

    # Entry - focus on VOLATILITY not direction
    min_day_range: float = 0.025  # 2.5% daily range
    min_volume_ratio: float = 1.0  # Above average volume

    # Exit
    stop_loss_pct: float = 0.02  # 2% stop loss
    trailing_stop_pct: float = 0.02  # 2% trailing
    take_profit_pct: float = 0.08  # 8% take profit
    max_hold_days: int = 5


class RefinedEngine:
    """Backtest engine based on optimal trade patterns"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: RefinedConfig = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or RefinedConfig()

        # ONLY the best performing semiconductors
        self.symbols = ['AMD', 'NVDA', 'MU', 'QCOM', 'MRVL']

        self.data_loader = DailyDataLoader()

        # State
        self.cash = self.config.initial_capital
        self.positions: Dict[str, RefinedPosition] = {}
        self.trades: List[RefinedTrade] = []
        self.daily_equity: List[Dict] = []

    def calculate_day_range(self, bar: DailyBar) -> float:
        """Calculate day range as percentage"""
        return (bar.high - bar.low) / bar.close if bar.close > 0 else 0

    def calculate_volume_ratio(self, bars: List[DailyBar]) -> float:
        """Calculate volume vs average"""
        if len(bars) < 2:
            return 1.0
        current_vol = bars[-1].volume
        avg_vol = np.mean([b.volume for b in bars[:-1]])
        return current_vol / avg_vol if avg_vol > 0 else 1.0

    def should_enter(self, bars: List[DailyBar]) -> bool:
        """Entry signal based on volatility opportunity"""
        if len(bars) < 10:
            return False

        current_bar = bars[-1]

        # 1. High day range (volatility = opportunity)
        day_range = self.calculate_day_range(current_bar)
        if day_range < self.config.min_day_range:
            return False

        # 2. Above average volume
        vol_ratio = self.calculate_volume_ratio(bars)
        if vol_ratio < self.config.min_volume_ratio:
            return False

        # 3. Not at 52-week high (avoid chasing)
        closes = [b.close for b in bars]
        if current_bar.close >= max(closes) * 0.98:
            return False

        return True

    async def run(self) -> Dict:
        """Run backtest"""
        load_start = self.start_date - timedelta(days=30)
        await self.data_loader.load(self.symbols, load_start, self.end_date)

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)

        for day in trading_days:
            await self._process_day(day)

        # Close remaining
        if self.positions:
            last_day = trading_days[-1]
            for symbol in list(self.positions.keys()):
                await self._close_position(symbol, last_day, "backtest_end")

        return self._generate_results()

    async def _process_day(self, day: datetime):
        equity = self._get_equity(day)
        self.daily_equity.append({'date': day.isoformat(), 'equity': equity})

        # Check exits
        for symbol in list(self.positions.keys()):
            await self._check_exit(symbol, day)

        # Check entries
        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            bars = self.data_loader.get_bars(symbol, day, 20)
            if self.should_enter(bars):
                await self._open_position(symbol, day, bars[-1].close)

    def _get_equity(self, date: datetime) -> float:
        equity = self.cash
        for symbol, pos in self.positions.items():
            price = self.data_loader.get_price(symbol, date)
            if price:
                equity += pos.qty * price
        return equity

    async def _check_exit(self, symbol: str, day: datetime):
        pos = self.positions.get(symbol)
        if not pos:
            return

        bar = self.data_loader.get_bar(symbol, day)
        if not bar:
            return

        # Update high
        if bar.high > pos.high_since_entry:
            pos.high_since_entry = bar.high

        # Stop loss
        if bar.low <= pos.stop_loss:
            await self._close_at_price(symbol, day, pos.stop_loss, "Stop loss")
            return

        # Trailing stop
        if pos.high_since_entry > pos.entry_price:
            trailing = pos.high_since_entry * (1 - self.config.trailing_stop_pct)
            if bar.low <= trailing:
                await self._close_at_price(symbol, day, max(trailing, bar.low), "Trailing stop")
                return

        # Take profit
        if bar.high >= pos.entry_price * (1 + self.config.take_profit_pct):
            await self._close_at_price(
                symbol, day,
                pos.entry_price * (1 + self.config.take_profit_pct),
                "Take profit"
            )
            return

        # Max hold
        hold = (day - pos.entry_date).days
        if hold >= self.config.max_hold_days:
            await self._close_position(symbol, day, "Max hold")

    async def _open_position(self, symbol: str, day: datetime, price: float):
        value = self.cash * self.config.position_size_pct
        if value > self.cash:
            return

        qty = value / price
        self.positions[symbol] = RefinedPosition(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            entry_date=day,
            stop_loss=price * (1 - self.config.stop_loss_pct),
            high_since_entry=price,
        )
        self.cash -= value

    async def _close_position(self, symbol: str, day: datetime, reason: str):
        price = self.data_loader.get_price(symbol, day)
        if price:
            await self._close_at_price(symbol, day, price, reason)

    async def _close_at_price(self, symbol: str, day: datetime, price: float, reason: str):
        pos = self.positions.get(symbol)
        if not pos:
            return

        pnl = (price - pos.entry_price) * pos.qty
        pnl_pct = (price - pos.entry_price) / pos.entry_price

        self.trades.append(RefinedTrade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=(day - pos.entry_date).days,
            exit_reason=reason,
        ))

        self.cash += pos.qty * price
        del self.positions[symbol]

    def _generate_results(self) -> Dict:
        final_equity = self.cash
        for pos in self.positions.values():
            final_equity += pos.qty * pos.entry_price

        total_return = final_equity - self.config.initial_capital
        total_return_pct = total_return / self.config.initial_capital * 100

        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]

        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0
        avg_win_pct = np.mean([t.pnl_pct for t in winning]) * 100 if winning else 0
        avg_loss_pct = np.mean([t.pnl_pct for t in losing]) * 100 if losing else 0

        # Max drawdown
        max_dd = 0
        peak = self.config.initial_capital
        for day in self.daily_equity:
            eq = day['equity']
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return {
            'return_pct': total_return_pct,
            'trades': len(self.trades),
            'win_rate': win_rate,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct,
            'max_dd': max_dd,
            'trade_list': self.trades,
        }


async def run_multi_period():
    """Test across multiple periods"""

    periods = [
        (datetime(2025, 9, 1), datetime(2025, 9, 30), "Sep 2025"),
        (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
        (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
        (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dic 2025"),
        (datetime(2025, 10, 1), datetime(2025, 12, 31), "Q4 2025"),
    ]

    print(f"\n{'='*80}")
    print(f"REFINED VOLATILITY STRATEGY - Multi-Period Test")
    print(f"Focus: AMD, NVDA, MU, QCOM, MRVL | 50% positions | 2% stops")
    print(f"{'='*80}")

    loader = DailyDataLoader()

    print(f"\n{'Period':<12} | {'SPY':>10} | {'Strategy':>10} | {'Alpha':>10} | {'Trades':>8} | {'WinRate':>8}")
    print("-" * 75)

    total_strat = 0
    total_spy = 0

    for start, end, name in periods:
        engine = RefinedEngine(start, end)
        results = await engine.run()

        # SPY
        await loader.load(['SPY'], start - timedelta(days=5), end)
        spy_start = loader.get_price('SPY', start)
        spy_end = loader.get_price('SPY', end)
        spy_return = (spy_end - spy_start) / spy_start * 100 if spy_start else 0

        alpha = results['return_pct'] - spy_return

        print(
            f"{name:<12} | {spy_return:>+9.2f}% | {results['return_pct']:>+9.2f}% | "
            f"{alpha:>+9.2f}% | {results['trades']:>8} | {results['win_rate']:>7.1f}%"
        )

        if name != "Q4 2025":  # Don't double count
            total_strat += results['return_pct']
            total_spy += spy_return

    print("-" * 75)
    avg_strat = total_strat / 4
    avg_spy = total_spy / 4
    print(f"{'AVERAGE':<12} | {avg_spy:>+9.2f}% | {avg_strat:>+9.2f}% | {avg_strat - avg_spy:>+9.2f}% |")

    winner = "STRATEGY" if avg_strat > avg_spy else "SPY"
    print(f"\n🏁 OVERALL WINNER: {winner}")

    # Show October details
    print(f"\n📋 OCTOBER 2025 TRADES:")
    oct_engine = RefinedEngine(datetime(2025, 10, 1), datetime(2025, 10, 31))
    oct_results = await oct_engine.run()
    for t in oct_results['trade_list']:
        print(
            f"   {t.symbol:5} | {t.entry_date.strftime('%m/%d')} → {t.exit_date.strftime('%m/%d')} | "
            f"{t.pnl_pct*100:+.1f}% | {t.exit_reason}"
        )


if __name__ == "__main__":
    asyncio.run(run_multi_period())
