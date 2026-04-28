"""
Swing Trading Backtest Engine

Backtests mean reversion strategy using daily data.
Positions are held for multiple days (not day trading).

Key differences from day trading backtest:
- Uses daily closing prices for decisions
- Positions held overnight
- No intraday simulation
- Faster execution (daily vs minute-by-minute)
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import json
from pathlib import Path

from backtest.daily_data import DailyDataLoader, DailyBar
from backtest.screener import DynamicScreener, ScreenerCriteria
from agent.strategies.mean_reversion import (
    MeanReversionStrategy,
    TechnicalIndicators,
    SwingSignal,
)

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """An open position"""
    symbol: str
    qty: float
    entry_price: float
    entry_date: datetime
    stop_loss: float
    take_profit: float


@dataclass
class Trade:
    """A completed trade"""
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
class SwingBacktestConfig:
    """Configuration for swing trading backtest"""
    initial_capital: float = 100_000.0
    max_positions: int = 5
    position_size_pct: float = 0.02  # 2% of portfolio per trade
    stop_loss_pct: float = 0.03  # 3% stop loss
    take_profit_pct: float = 0.05  # 5% take profit
    max_hold_days: int = 5
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    min_price: float = 5.0  # Skip penny stocks
    min_volume: int = 500_000  # Minimum average daily volume
    # Dynamic screening options
    use_dynamic_screening: bool = False  # Enable dynamic symbol selection
    max_screened_symbols: int = 50  # Max symbols after screening


class SwingBacktestEngine:
    """
    Backtesting engine for Mean Reversion Swing Trading

    Uses daily OHLCV data to simulate swing trades over multiple days.
    """

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        config: SwingBacktestConfig = None,
        symbols: List[str] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.config = config or SwingBacktestConfig()

        # Default symbols - liquid stocks with good volume
        self.symbols = symbols or [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
            'JPM', 'V', 'JNJ', 'WMT', 'PG', 'UNH', 'HD', 'BAC',
            'XOM', 'CVX', 'PFE', 'ABBV', 'KO', 'PEP', 'MRK', 'COST',
            'AVGO', 'MU', 'AMD', 'INTC', 'QCOM', 'TXN', 'NFLX',
            'DIS', 'NKE', 'MCD', 'SBUX', 'BA', 'CAT', 'GE', 'MMM',
            'SPY', 'QQQ', 'IWM',  # ETFs for reference
        ]

        # Components
        self.data_loader = DailyDataLoader()
        self.strategy = MeanReversionStrategy(
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            max_hold_days=self.config.max_hold_days,
            rsi_oversold=self.config.rsi_oversold,
            rsi_overbought=self.config.rsi_overbought,
        )

        # State
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_equity: List[Dict] = []

        # Statistics
        self.stats = {
            'signals_generated': 0,
            'buy_signals': 0,
            'sell_signals': 0,
            'trades_executed': 0,
            'skipped_no_cash': 0,
            'skipped_max_positions': 0,
        }

    async def run(self) -> Dict[str, Any]:
        """Run the backtest"""
        logger.info(f"Starting Swing Trading Backtest")
        logger.info(f"Period: {self.start_date.date()} to {self.end_date.date()}")

        # Dynamic symbol screening if enabled
        if self.config.use_dynamic_screening:
            logger.info("Running dynamic symbol screening...")
            self.symbols = await self._screen_symbols()
            logger.info(f"Screened to {len(self.symbols)} symbols")

        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info(f"Config: {self.config}")

        # Load historical data (includes 60-day buffer for indicators)
        logger.info("Loading historical data...")
        await self._load_data()

        # Get trading days for the target period
        trading_days = self._get_trading_days()
        logger.info(f"Trading days: {len(trading_days)}")

        if not trading_days:
            logger.error("No trading days found!")
            return self._generate_results()

        # Process each trading day
        for i, day in enumerate(trading_days):
            await self._process_day(day, trading_days[:i])

            # Log progress every 10 days
            if (i + 1) % 10 == 0:
                equity = self._get_equity(day)
                pnl = equity - self.config.initial_capital
                logger.info(f"Day {i+1}/{len(trading_days)}: {day.date()} | Equity: ${equity:,.0f} ({pnl:+,.0f})")

        # Close any remaining positions at end
        if self.positions:
            last_day = trading_days[-1]
            for symbol in list(self.positions.keys()):
                await self._close_position(symbol, last_day, "backtest_end")

        # Generate results
        results = self._generate_results()

        # Log summary
        self._log_summary(results)

        return results

    async def _load_data(self):
        """Load historical daily data for all symbols"""
        # Load with extra buffer for indicator calculation
        load_start = self.start_date - timedelta(days=60)

        await self.data_loader.load(
            symbols=self.symbols,
            start_date=load_start,
            end_date=self.end_date,
        )

    async def _screen_symbols(self) -> List[str]:
        """
        Dynamically screen for symbols based on criteria.

        Uses volume, price, and optionally mean reversion signals
        to select the best candidates for trading.
        """
        criteria = ScreenerCriteria(
            min_price=self.config.min_price,
            min_avg_volume=self.config.min_volume,
            max_symbols=self.config.max_screened_symbols,
        )

        screener = DynamicScreener(criteria)

        # Get tradeable symbols from Alpaca
        all_symbols = await screener.get_tradeable_symbols()
        logger.info(f"Found {len(all_symbols)} tradeable symbols")

        # Screen by volume and price as of start date
        screened = await screener.screen_by_volume_and_price(
            all_symbols[:300],  # Limit initial batch for speed
            self.start_date,
            lookback_days=20,
        )

        symbols = [s['symbol'] for s in screened]
        logger.info(f"Screened to {len(symbols)} symbols by volume/price")

        return symbols

    def _get_trading_days(self) -> List[datetime]:
        """Get list of trading days in the period"""
        return self.data_loader.get_trading_days(self.start_date, self.end_date)

    def _get_price(self, symbol: str, date: datetime) -> Optional[float]:
        """Get closing price for a symbol on a date"""
        return self.data_loader.get_price(symbol, date)

    def _get_daily_ohlcv(
        self, symbol: str, end_date: datetime, lookback: int = 30
    ) -> Optional[Dict]:
        """Get OHLCV data for indicator calculation"""
        bars = self.data_loader.get_bars(symbol, end_date, lookback)
        
        if len(bars) < 20:
            return None
            
        return {
            'closes': [b.close for b in bars],
            'highs': [b.high for b in bars],
            'lows': [b.low for b in bars],
            'volumes': [b.volume for b in bars],
        }

    def _get_equity(self, date: datetime) -> float:
        """Calculate current portfolio equity"""
        equity = self.cash

        for symbol, pos in self.positions.items():
            price = self._get_price(symbol, date)
            if price:
                equity += pos.qty * price

        return equity

    async def _process_day(self, day: datetime, history: List[datetime]):
        """Process a single trading day"""

        # Record daily equity
        equity = self._get_equity(day)
        self.daily_equity.append({
            'date': day.isoformat(),
            'equity': equity,
            'cash': self.cash,
            'positions': len(self.positions),
        })

        # First, check existing positions for exit signals
        for symbol in list(self.positions.keys()):
            await self._check_position_exit(symbol, day)

        # Then, look for new entry signals
        for symbol in self.symbols:
            if symbol in self.positions:
                continue  # Already have position

            await self._check_entry_signal(symbol, day)

    async def _check_position_exit(self, symbol: str, day: datetime):
        """
        Check if we should exit a position.

        REALISTIC SIMULATION: Uses high/low of the day to detect if stop loss
        or take profit was hit during intraday trading, not just at close.
        """
        pos = self.positions.get(symbol)
        if not pos:
            return

        # Get full daily bar with high/low for realistic intraday simulation
        bar = self.data_loader.get_bar(symbol, day)
        if not bar:
            return

        # ===== INTRADAY STOP LOSS / TAKE PROFIT CHECK =====
        # This simulates what the real agent would do: monitor prices
        # and execute when levels are hit, not wait for close

        # Check if STOP LOSS was hit (price went below stop level)
        if bar.low <= pos.stop_loss:
            self.stats['signals_generated'] += 1
            self.stats['sell_signals'] += 1
            # Execute at stop loss price (worst case: it hit and triggered)
            await self._close_position_at_price(
                symbol, day, pos.stop_loss,
                f"Stop loss triggered (low=${bar.low:.2f} <= stop=${pos.stop_loss:.2f})"
            )
            return

        # Check if TAKE PROFIT was hit (price went above target)
        if bar.high >= pos.take_profit:
            self.stats['signals_generated'] += 1
            self.stats['sell_signals'] += 1
            # Execute at take profit price
            await self._close_position_at_price(
                symbol, day, pos.take_profit,
                f"Take profit triggered (high=${bar.high:.2f} >= target=${pos.take_profit:.2f})"
            )
            return

        # ===== INDICATOR-BASED EXIT CHECK (at close) =====
        # If no stop/take profit hit, check indicators at close
        ohlcv = self._get_daily_ohlcv(symbol, day)
        if not ohlcv:
            return

        indicators = self.strategy.calculate_indicators(
            closes=ohlcv['closes'],
            highs=ohlcv['highs'],
            lows=ohlcv['lows'],
            volumes=ohlcv['volumes'],
        )

        # Generate signal using close price
        signal = self.strategy.generate_signal(
            symbol=symbol,
            current_price=bar.close,
            indicators=indicators,
            has_position=True,
            position_entry_price=pos.entry_price,
            position_entry_date=pos.entry_date,
            current_date=day,
        )

        self.stats['signals_generated'] += 1

        if signal.action == 'SELL':
            self.stats['sell_signals'] += 1
            await self._close_position(symbol, day, signal.reasoning)

    async def _check_entry_signal(self, symbol: str, day: datetime):
        """Check if we should enter a new position"""

        # Check if we have room for more positions
        if len(self.positions) >= self.config.max_positions:
            return

        price = self._get_price(symbol, day)
        if not price:
            return

        # Skip if price too low
        if price < self.config.min_price:
            return

        # Get indicators
        ohlcv = self._get_daily_ohlcv(symbol, day)
        if not ohlcv:
            return

        # Check volume filter
        avg_volume = sum(ohlcv['volumes'][-20:]) / 20
        if avg_volume < self.config.min_volume:
            return

        indicators = self.strategy.calculate_indicators(
            closes=ohlcv['closes'],
            highs=ohlcv['highs'],
            lows=ohlcv['lows'],
            volumes=ohlcv['volumes'],
        )

        # Generate signal
        signal = self.strategy.generate_signal(
            symbol=symbol,
            current_price=price,
            indicators=indicators,
            has_position=False,
        )

        self.stats['signals_generated'] += 1

        if signal.action == 'BUY' and signal.confidence >= 0.7:
            self.stats['buy_signals'] += 1
            await self._open_position(symbol, day, price, signal)

    async def _open_position(
        self, symbol: str, day: datetime, price: float, signal: SwingSignal
    ):
        """Open a new position"""

        # Calculate position size (2% of equity)
        equity = self._get_equity(day)
        position_value = equity * self.config.position_size_pct

        # Check if we have enough cash
        if position_value > self.cash:
            self.stats['skipped_no_cash'] += 1
            return

        qty = position_value / price

        # Open position
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
            f"RSI={signal.indicators.rsi:.0f} BB%={signal.indicators.bb_percent:.0%} | "
            f"{signal.reasoning}"
        )

    async def _close_position(self, symbol: str, day: datetime, reason: str):
        """Close an existing position"""
        pos = self.positions.get(symbol)
        if not pos:
            return

        price = self._get_price(symbol, day)
        if not price:
            # Use last known price
            price = pos.entry_price

        # Calculate P&L
        pnl = (price - pos.entry_price) * pos.qty
        pnl_pct = (price - pos.entry_price) / pos.entry_price
        hold_days = (day - pos.entry_date).days

        # Record trade
        trade = Trade(
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
        )
        self.trades.append(trade)

        # Update cash
        self.cash += pos.qty * price

        # Remove position
        del self.positions[symbol]

        status = "+" if pnl > 0 else ""
        logger.debug(
            f"SELL {symbol}: {pos.qty:.2f} @ ${price:.2f} | "
            f"P&L: {status}${pnl:.2f} ({pnl_pct:+.1%}) | "
            f"Hold: {hold_days}d | {reason}"
        )

    async def _close_position_at_price(
        self, symbol: str, day: datetime, exit_price: float, reason: str
    ):
        """
        Close position at a specific price (for stop loss / take profit).

        This simulates realistic execution where the order triggers at the
        specified price level, not at the day's close.
        """
        pos = self.positions.get(symbol)
        if not pos:
            return

        # Calculate P&L at the specified exit price
        pnl = (exit_price - pos.entry_price) * pos.qty
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        hold_days = (day - pos.entry_date).days

        # Record trade
        trade = Trade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.qty,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
            exit_reason=reason,
        )
        self.trades.append(trade)

        # Update cash
        self.cash += pos.qty * exit_price

        # Remove position
        del self.positions[symbol]

        status = "+" if pnl > 0 else ""
        logger.debug(
            f"SELL {symbol}: {pos.qty:.2f} @ ${exit_price:.2f} (triggered) | "
            f"P&L: {status}${pnl:.2f} ({pnl_pct:+.1%}) | "
            f"Hold: {hold_days}d | {reason}"
        )

    def _generate_results(self) -> Dict[str, Any]:
        """Generate backtest results"""

        # Calculate metrics
        final_equity = self.cash
        for pos in self.positions.values():
            # Value remaining positions at last known price
            final_equity += pos.qty * pos.entry_price  # Conservative

        total_return = final_equity - self.config.initial_capital
        total_return_pct = total_return / self.config.initial_capital * 100

        # Trade statistics
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl < 0]

        win_rate = len(winning_trades) / len(self.trades) * 100 if self.trades else 0

        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

        profit_factor = abs(sum(t.pnl for t in winning_trades) / sum(t.pnl for t in losing_trades)) if losing_trades and sum(t.pnl for t in losing_trades) != 0 else 0

        avg_hold_days = sum(t.hold_days for t in self.trades) / len(self.trades) if self.trades else 0

        # Max drawdown
        max_equity = self.config.initial_capital
        max_drawdown = 0
        for daily in self.daily_equity:
            equity = daily['equity']
            if equity > max_equity:
                max_equity = equity
            drawdown = (max_equity - equity) / max_equity * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return {
            'period': {
                'start': self.start_date.isoformat(),
                'end': self.end_date.isoformat(),
                'trading_days': len(self.daily_equity),
            },
            'config': {
                'initial_capital': self.config.initial_capital,
                'max_positions': self.config.max_positions,
                'position_size_pct': self.config.position_size_pct,
                'stop_loss_pct': self.config.stop_loss_pct,
                'take_profit_pct': self.config.take_profit_pct,
                'max_hold_days': self.config.max_hold_days,
            },
            'performance': {
                'final_equity': final_equity,
                'total_return': total_return,
                'total_return_pct': total_return_pct,
                'max_drawdown_pct': max_drawdown,
            },
            'trades': {
                'total': len(self.trades),
                'winning': len(winning_trades),
                'losing': len(losing_trades),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'avg_hold_days': avg_hold_days,
            },
            'stats': self.stats,
            'trade_list': [
                {
                    'symbol': t.symbol,
                    'entry_date': t.entry_date.isoformat(),
                    'exit_date': t.exit_date.isoformat(),
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                    'hold_days': t.hold_days,
                    'exit_reason': t.exit_reason,
                }
                for t in self.trades
            ],
            'daily_equity': self.daily_equity,
        }

    def _log_summary(self, results: Dict):
        """Log a summary of the backtest results"""
        perf = results['performance']
        trades = results['trades']

        logger.info("=" * 60)
        logger.info("SWING TRADING BACKTEST RESULTS")
        logger.info("=" * 60)
        logger.info(f"Period: {results['period']['start'][:10]} to {results['period']['end'][:10]}")
        logger.info(f"Trading Days: {results['period']['trading_days']}")
        logger.info("")
        logger.info("PERFORMANCE:")
        logger.info(f"  Final Equity: ${perf['final_equity']:,.2f}")
        logger.info(f"  Total Return: ${perf['total_return']:+,.2f} ({perf['total_return_pct']:+.2f}%)")
        logger.info(f"  Max Drawdown: {perf['max_drawdown_pct']:.2f}%")
        logger.info("")
        logger.info("TRADES:")
        logger.info(f"  Total: {trades['total']}")
        logger.info(f"  Wins: {trades['winning']} | Losses: {trades['losing']}")
        logger.info(f"  Win Rate: {trades['win_rate']:.1f}%")
        logger.info(f"  Profit Factor: {trades['profit_factor']:.2f}")
        logger.info(f"  Avg Win: ${trades['avg_win']:+,.2f}")
        logger.info(f"  Avg Loss: ${trades['avg_loss']:+,.2f}")
        logger.info(f"  Avg Hold: {trades['avg_hold_days']:.1f} days")
        logger.info("=" * 60)

    def save_results(self, results: Dict) -> str:
        """Save results to file"""
        reports_dir = Path("backtest/reports")
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"swing_backtest_{timestamp}.json"
        filepath = reports_dir / filename

        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results saved to: {filepath}")
        return str(filepath)


async def run_swing_backtest(
    start_date: datetime = None,
    end_date: datetime = None,
    config: SwingBacktestConfig = None,
    symbols: List[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to run a swing trading backtest

    Args:
        start_date: Start date (default: 3 months ago)
        end_date: End date (default: today)
        config: Backtest configuration
        symbols: List of symbols to trade

    Returns:
        Dict with backtest results
    """
    # Default dates
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(days=90)

    engine = SwingBacktestEngine(
        start_date=start_date,
        end_date=end_date,
        config=config,
        symbols=symbols,
    )

    results = await engine.run()

    # Save results
    engine.save_results(results)

    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Parse arguments
    # Default: last 3 months
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    # Check for --year argument
    if '--year' in sys.argv:
        idx = sys.argv.index('--year')
        year = int(sys.argv[idx + 1])
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

    # Check for --month argument
    if '--month' in sys.argv:
        idx = sys.argv.index('--month')
        month = int(sys.argv[idx + 1])
        year = 2025  # Default year
        if '--year' in sys.argv:
            year_idx = sys.argv.index('--year')
            year = int(sys.argv[year_idx + 1])
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    # Check for --dynamic flag
    use_dynamic = '--dynamic' in sys.argv

    # Configure
    config = SwingBacktestConfig(
        use_dynamic_screening=use_dynamic,
        max_screened_symbols=50,
    )

    print(f"\nRunning Swing Trading Backtest")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Dynamic Screening: {'ENABLED' if use_dynamic else 'DISABLED'}")
    print("-" * 50)

    results = asyncio.run(run_swing_backtest(
        start_date=start_date,
        end_date=end_date,
        config=config,
        symbols=None if use_dynamic else None,  # Will use default or screened
    ))

    print("\nDone!")
