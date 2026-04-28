"""
Dip Buyer Backtest Engine

Tests the dip buying strategy based on optimal trade analysis.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from backtest.daily_data import DailyDataLoader, DailyBar
from agent.strategies.dip_buyer import DipBuyerStrategy, DipBuyerConfig, DipSignal

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_date: datetime
    stop_loss: float
    take_profit: float


@dataclass
class Trade:
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str


@dataclass
class DipBacktestConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 5
    position_size_pct: float = 0.10  # 10% per position (more aggressive)
    # Strategy params
    min_prev_day_drop: float = -0.01
    min_day_range: float = 0.02
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.08
    max_hold_days: int = 4


class DipBacktestEngine:
    """Backtest engine for dip buying strategy"""

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: DipBacktestConfig = None,
        symbols: List[str] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or DipBacktestConfig()

        # Focus on high-beta symbols (best performers)
        self.symbols = symbols or [
            'AMD', 'NVDA', 'QCOM', 'MU', 'INTC', 'AVGO', 'MRVL',
            'TSLA', 'META', 'NFLX', 'CRM', 'ORCL', 'AMZN', 'GOOGL',
            'AAPL', 'MSFT', 'JPM', 'V', 'BA', 'CAT',
            'COIN', 'SQ', 'SHOP', 'PLTR', 'SNOW',
        ]

        self.data_loader = DailyDataLoader()
        self.strategy = DipBuyerStrategy(DipBuyerConfig(
            min_prev_day_drop=self.config.min_prev_day_drop,
            min_day_range=self.config.min_day_range,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            max_hold_days=self.config.max_hold_days,
        ))

        # State
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_equity: List[Dict] = []

        self.stats = {
            'signals_generated': 0,
            'buy_signals': 0,
            'trades_executed': 0,
        }

    async def run(self) -> Dict[str, Any]:
        """Run backtest"""
        logger.info(f"Starting Dip Buyer Backtest")
        logger.info(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        logger.info(f"Symbols: {len(self.symbols)}")

        # Load data
        load_start = self.start_date - timedelta(days=30)
        await self.data_loader.load(self.symbols, load_start, self.end_date)

        trading_days = self.data_loader.get_trading_days(self.start_date, self.end_date)
        logger.info(f"Trading days: {len(trading_days)}")

        if not trading_days:
            return self._generate_results()

        for i, day in enumerate(trading_days):
            await self._process_day(day)

            if (i + 1) % 5 == 0:
                equity = self._get_equity(day)
                pnl = equity - self.config.initial_capital
                logger.info(f"Day {i+1}/{len(trading_days)}: Equity ${equity:,.0f} ({pnl:+,.0f})")

        # Close remaining positions
        if self.positions:
            last_day = trading_days[-1]
            for symbol in list(self.positions.keys()):
                await self._close_position(symbol, last_day, "backtest_end")

        return self._generate_results()

    def _get_equity(self, date: datetime) -> float:
        equity = self.cash
        for symbol, pos in self.positions.items():
            price = self.data_loader.get_price(symbol, date)
            if price:
                equity += pos.qty * price
        return equity

    async def _process_day(self, day: datetime):
        """Process a trading day"""
        equity = self._get_equity(day)
        self.daily_equity.append({
            'date': day.isoformat(),
            'equity': equity,
        })

        # Check exits first (using high/low for realistic simulation)
        for symbol in list(self.positions.keys()):
            await self._check_exit(symbol, day)

        # Check entries
        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.config.max_positions:
                break

            await self._check_entry(symbol, day)

    async def _check_exit(self, symbol: str, day: datetime):
        """Check position for exit using intraday high/low"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        bar = self.data_loader.get_bar(symbol, day)
        if not bar:
            return

        # Check stop loss (using low)
        if bar.low <= pos.stop_loss:
            await self._close_position_at_price(
                symbol, day, pos.stop_loss,
                f"Stop loss (low ${bar.low:.2f})"
            )
            return

        # Check take profit (using high)
        if bar.high >= pos.take_profit:
            await self._close_position_at_price(
                symbol, day, pos.take_profit,
                f"Take profit (high ${bar.high:.2f})"
            )
            return

        # Check max hold
        hold_days = (day - pos.entry_date).days
        if hold_days >= self.config.max_hold_days:
            await self._close_position(symbol, day, f"Max hold ({hold_days}d)")

    async def _check_entry(self, symbol: str, day: datetime):
        """Check for entry signal"""
        bars = self.data_loader.get_bars(symbol, day, 10)
        if len(bars) < 5:
            return

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        signal = self.strategy.generate_signal(
            symbol=symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            has_position=False,
        )

        self.stats['signals_generated'] += 1

        if signal.action == 'BUY' and signal.confidence >= 0.7:
            self.stats['buy_signals'] += 1
            await self._open_position(symbol, day, signal)

    async def _open_position(self, symbol: str, day: datetime, signal: DipSignal):
        """Open a position"""
        price = signal.entry_price
        position_value = self.cash * self.config.position_size_pct

        if position_value > self.cash:
            return

        qty = position_value / price

        self.positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            entry_date=day,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

        self.cash -= position_value
        self.stats['trades_executed'] += 1

        logger.debug(
            f"BUY {symbol}: {qty:.2f} @ ${price:.2f} | "
            f"{signal.reasoning}"
        )

    async def _close_position(self, symbol: str, day: datetime, reason: str):
        """Close position at close price"""
        price = self.data_loader.get_price(symbol, day)
        if price:
            await self._close_position_at_price(symbol, day, price, reason)

    async def _close_position_at_price(
        self, symbol: str, day: datetime, price: float, reason: str
    ):
        """Close position at specific price"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        pnl = (price - pos.entry_price) * pos.qty
        pnl_pct = (price - pos.entry_price) / pos.entry_price
        hold_days = (day - pos.entry_date).days

        self.trades.append(Trade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=price,
            qty=pos.qty,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
            exit_reason=reason,
        ))

        self.cash += pos.qty * price
        del self.positions[symbol]

        logger.debug(f"SELL {symbol} @ ${price:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1%}) | {reason}")

    def _generate_results(self) -> Dict[str, Any]:
        """Generate results"""
        final_equity = self.cash
        for pos in self.positions.values():
            final_equity += pos.qty * pos.entry_price

        total_return = final_equity - self.config.initial_capital
        total_return_pct = total_return / self.config.initial_capital * 100

        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]

        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0
        avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0
        avg_loss = sum(t.pnl for t in losing) / len(losing) if losing else 0

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999

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
            'performance': {
                'final_equity': final_equity,
                'total_return': total_return,
                'total_return_pct': total_return_pct,
                'max_drawdown_pct': max_dd,
            },
            'trades': {
                'total': len(self.trades),
                'winning': len(winning),
                'losing': len(losing),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
            },
            'stats': self.stats,
            'trade_list': [
                {
                    'symbol': t.symbol,
                    'entry_date': t.entry_date.isoformat(),
                    'exit_date': t.exit_date.isoformat(),
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                    'hold_days': t.hold_days,
                    'exit_reason': t.exit_reason,
                }
                for t in self.trades
            ],
        }


async def run_dip_backtest(
    start_date: datetime,
    end_date: datetime,
    config: DipBacktestConfig = None,
) -> Dict[str, Any]:
    """Run dip buyer backtest"""
    engine = DipBacktestEngine(start_date, end_date, config)
    return await engine.run()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    async def main():
        # Test October 2025
        start = datetime(2025, 10, 1)
        end = datetime(2025, 10, 31)

        print(f"\n=== DIP BUYER BACKTEST - Octubre 2025 ===\n")

        results = await run_dip_backtest(start, end)

        perf = results['performance']
        trades = results['trades']

        print(f"Return: ${perf['total_return']:+,.2f} ({perf['total_return_pct']:+.2f}%)")
        print(f"Max Drawdown: {perf['max_drawdown_pct']:.2f}%")
        print(f"Trades: {trades['total']} (Win: {trades['winning']}, Loss: {trades['losing']})")
        print(f"Win Rate: {trades['win_rate']:.1f}%")
        print(f"Profit Factor: {trades['profit_factor']:.2f}")

    asyncio.run(main())
