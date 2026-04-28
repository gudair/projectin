"""
Portfolio Tracker for Backtesting

Tracks all simulated trades, positions, and P&L.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Record of a single trade"""
    timestamp: datetime
    symbol: str
    side: str  # 'buy' or 'sell'
    qty: float
    price: float
    value: float
    pnl: float = 0.0  # Only for sells
    pnl_pct: float = 0.0
    hold_duration_minutes: int = 0


@dataclass
class DailyStats:
    """Statistics for a single trading day"""
    date: datetime
    starting_equity: float
    ending_equity: float
    pnl: float
    pnl_pct: float
    trades_count: int
    winning_trades: int
    losing_trades: int
    total_volume: float
    max_drawdown: float


class PortfolioTracker:
    """
    Tracks simulated portfolio throughout the backtest.
    """

    def __init__(self, initial_cash: float = 100000.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash

        # Current positions: {symbol: {'qty': float, 'avg_price': float, 'entry_time': datetime}}
        self.positions: Dict[str, Dict] = {}

        # Trade history
        self.trades: List[Trade] = []

        # Daily stats
        self.daily_stats: List[DailyStats] = []

        # Tracking
        self.peak_equity = initial_cash
        self.current_date: Optional[datetime] = None
        self._day_start_equity = initial_cash
        self._day_trades = 0
        self._day_wins = 0
        self._day_losses = 0
        self._day_volume = 0.0
        self._day_max_equity = initial_cash
        self._day_min_equity = initial_cash

        # Price lookup function (set by BacktestEngine)
        self._get_price_func = None

    def set_price_lookup(self, func):
        """Set the function to look up current prices"""
        self._get_price_func = func

    def buy(self, symbol: str, qty: float, price: float, timestamp: datetime) -> bool:
        """Execute a buy order"""
        cost = qty * price

        if cost > self.cash:
            logger.warning(f"Insufficient cash for {symbol}: need ${cost:.2f}, have ${self.cash:.2f}")
            return False

        # Update position
        if symbol in self.positions:
            # Average into existing position
            existing = self.positions[symbol]
            total_qty = existing['qty'] + qty
            total_cost = (existing['qty'] * existing['avg_price']) + cost
            avg_price = total_cost / total_qty

            self.positions[symbol] = {
                'qty': total_qty,
                'avg_price': avg_price,
                'entry_time': existing['entry_time'],  # Keep original entry time
            }
        else:
            self.positions[symbol] = {
                'qty': qty,
                'avg_price': price,
                'entry_time': timestamp,
            }

        # Update cash
        self.cash -= cost

        # Record trade
        trade = Trade(
            timestamp=timestamp,
            symbol=symbol,
            side='buy',
            qty=qty,
            price=price,
            value=cost,
        )
        self.trades.append(trade)

        # Update daily tracking
        self._day_trades += 1
        self._day_volume += cost

        return True

    def sell(self, symbol: str, qty: float, price: float, timestamp: datetime) -> bool:
        """Execute a sell order"""
        if symbol not in self.positions:
            logger.warning(f"No position to sell: {symbol}")
            return False

        position = self.positions[symbol]
        if qty > position['qty']:
            qty = position['qty']  # Sell entire position

        # Calculate P&L
        proceeds = qty * price
        cost_basis = qty * position['avg_price']
        pnl = proceeds - cost_basis
        pnl_pct = (pnl / cost_basis) * 100 if cost_basis > 0 else 0

        # Calculate hold duration
        hold_duration = int((timestamp - position['entry_time']).total_seconds() / 60)

        # Update position
        remaining_qty = position['qty'] - qty
        if remaining_qty <= 0.0001:  # Close to zero
            del self.positions[symbol]
        else:
            self.positions[symbol]['qty'] = remaining_qty

        # Update cash
        self.cash += proceeds

        # Record trade
        trade = Trade(
            timestamp=timestamp,
            symbol=symbol,
            side='sell',
            qty=qty,
            price=price,
            value=proceeds,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_duration_minutes=hold_duration,
        )
        self.trades.append(trade)

        # Update daily tracking
        self._day_trades += 1
        self._day_volume += proceeds
        if pnl > 0:
            self._day_wins += 1
        else:
            self._day_losses += 1

        return True

    def get_total_position_value(self, current_time: datetime) -> float:
        """Get total value of all positions at current prices"""
        if not self._get_price_func:
            # Fallback: use avg_price
            return sum(
                pos['qty'] * pos['avg_price']
                for pos in self.positions.values()
            )

        total = 0.0
        for symbol, pos in self.positions.items():
            price = self._get_price_func(symbol, current_time)
            if price:
                total += pos['qty'] * price
            else:
                total += pos['qty'] * pos['avg_price']

        return total

    def get_equity(self, current_time: datetime) -> float:
        """Get total equity (cash + positions)"""
        return self.cash + self.get_total_position_value(current_time)

    def start_new_day(self, date: datetime, current_time: datetime):
        """Called at the start of each trading day"""
        # Save previous day stats if we have one
        if self.current_date is not None:
            self._save_daily_stats(current_time)

        # Reset daily tracking
        self.current_date = date
        self._day_start_equity = self.get_equity(current_time)
        self._day_trades = 0
        self._day_wins = 0
        self._day_losses = 0
        self._day_volume = 0.0
        self._day_max_equity = self._day_start_equity
        self._day_min_equity = self._day_start_equity

    def update_intraday(self, current_time: datetime):
        """Called periodically to update intraday stats"""
        equity = self.get_equity(current_time)
        self._day_max_equity = max(self._day_max_equity, equity)
        self._day_min_equity = min(self._day_min_equity, equity)

        # Update peak equity for drawdown
        self.peak_equity = max(self.peak_equity, equity)

    def end_day(self, current_time: datetime):
        """Called at the end of each trading day"""
        self._save_daily_stats(current_time)

    def _save_daily_stats(self, current_time: datetime):
        """Save statistics for the current day"""
        ending_equity = self.get_equity(current_time)
        pnl = ending_equity - self._day_start_equity
        pnl_pct = (pnl / self._day_start_equity) * 100 if self._day_start_equity > 0 else 0

        # Calculate max drawdown for the day
        max_drawdown = 0
        if self._day_max_equity > 0:
            max_drawdown = (self._day_max_equity - self._day_min_equity) / self._day_max_equity * 100

        stats = DailyStats(
            date=self.current_date,
            starting_equity=self._day_start_equity,
            ending_equity=ending_equity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            trades_count=self._day_trades,
            winning_trades=self._day_wins,
            losing_trades=self._day_losses,
            total_volume=self._day_volume,
            max_drawdown=max_drawdown,
        )

        self.daily_stats.append(stats)

    def get_summary(self) -> Dict[str, Any]:
        """Get overall performance summary"""
        if not self.trades:
            # Return consistent structure even with no trades
            final_equity = self.daily_stats[-1].ending_equity if self.daily_stats else self.initial_cash
            return {
                'initial_capital': self.initial_cash,
                'final_equity': final_equity,
                'total_return': final_equity - self.initial_cash,
                'total_return_pct': (final_equity - self.initial_cash) / self.initial_cash * 100 if self.initial_cash > 0 else 0,
                'total_trades': 0,
                'sell_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'total_wins': 0,
                'total_losses': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'avg_hold_duration_minutes': 0,
                'max_drawdown_pct': 0,
                'trading_days': len(self.daily_stats),
                'avg_daily_pnl': 0,
            }

        # Calculate metrics
        sell_trades = [t for t in self.trades if t.side == 'sell']
        winning_trades = [t for t in sell_trades if t.pnl > 0]
        losing_trades = [t for t in sell_trades if t.pnl <= 0]

        total_pnl = sum(t.pnl for t in sell_trades)
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = sum(t.pnl for t in losing_trades)

        win_rate = len(winning_trades) / len(sell_trades) * 100 if sell_trades else 0
        avg_win = total_wins / len(winning_trades) if winning_trades else 0
        avg_loss = total_losses / len(losing_trades) if losing_trades else 0
        profit_factor = abs(total_wins / total_losses) if total_losses != 0 else float('inf')

        avg_hold_duration = sum(t.hold_duration_minutes for t in sell_trades) / len(sell_trades) if sell_trades else 0

        # Calculate max drawdown
        peak = self.initial_cash
        max_drawdown = 0
        for stats in self.daily_stats:
            peak = max(peak, stats.ending_equity)
            drawdown = (peak - stats.ending_equity) / peak * 100 if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)

        # Final equity
        final_equity = self.daily_stats[-1].ending_equity if self.daily_stats else self.initial_cash

        return {
            'initial_capital': self.initial_cash,
            'final_equity': final_equity,
            'total_return': final_equity - self.initial_cash,
            'total_return_pct': (final_equity - self.initial_cash) / self.initial_cash * 100,
            'total_trades': len(self.trades),
            'sell_trades': len(sell_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_wins': total_wins,
            'total_losses': total_losses,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_hold_duration_minutes': avg_hold_duration,
            'max_drawdown_pct': max_drawdown,
            'trading_days': len(self.daily_stats),
            'avg_daily_pnl': total_pnl / len(self.daily_stats) if self.daily_stats else 0,
        }

    def get_trade_log(self) -> List[Dict]:
        """Get all trades as a list of dicts"""
        return [
            {
                'timestamp': t.timestamp.isoformat(),
                'symbol': t.symbol,
                'side': t.side,
                'qty': t.qty,
                'price': t.price,
                'value': t.value,
                'pnl': t.pnl,
                'pnl_pct': t.pnl_pct,
                'hold_duration_minutes': t.hold_duration_minutes,
            }
            for t in self.trades
        ]
