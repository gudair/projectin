import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
import json
import os
from dataclasses import dataclass
from config.settings import (
    INITIAL_CAPITAL, INITIAL_STOCK, INITIAL_SHARES,
    MAX_POSITION_SIZE, MAX_DAILY_LOSS, STOP_LOSS_PERCENT,
    TAKE_PROFIT_RATIO, MAX_POSITIONS
)

@dataclass
class Position:
    symbol: str
    shares: float
    entry_price: float
    entry_date: datetime
    current_price: float
    stop_loss: float
    take_profit: float
    position_type: str  # 'long' or 'short'

    def get_current_value(self) -> float:
        return self.shares * self.current_price

    def get_unrealized_pnl(self) -> float:
        if self.position_type == 'long':
            return (self.current_price - self.entry_price) * self.shares
        else:
            return (self.entry_price - self.current_price) * self.shares

    def get_unrealized_pnl_percent(self) -> float:
        if self.entry_price == 0:
            return 0
        return (self.get_unrealized_pnl() / (self.entry_price * self.shares)) * 100

@dataclass
class Trade:
    symbol: str
    side: str  # 'buy' or 'sell'
    shares: float
    price: float
    timestamp: datetime
    commission: float
    trade_type: str  # 'market', 'limit', 'stop'
    reason: str

class PortfolioManager:
    def __init__(self, portfolio_file: str = "portfolio/portfolio_state.json"):
        self.portfolio_file = portfolio_file
        self.logger = logging.getLogger(__name__)

        # Portfolio state
        self.cash = 0.0
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Trade] = []
        self.daily_pnl_history: List[Dict] = []

        # Risk management
        self.daily_loss_limit = 0.0
        self.position_size_limit = 0.0

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_commission = 0.0

        # Initialize or load portfolio
        self._initialize_portfolio()

    def _initialize_portfolio(self):
        """Initialize portfolio with starting position or load from file"""
        if os.path.exists(self.portfolio_file):
            self._load_portfolio()
        else:
            # Start with initial Tesla position
            self.cash = INITIAL_CAPITAL - (INITIAL_SHARES * 250)  # Assume $250/share initially
            self._create_initial_position()
            self._save_portfolio()

    def _create_initial_position(self):
        """Create initial Tesla position"""
        from data.collectors.market_data import MarketDataCollector

        collector = MarketDataCollector()
        current_price = collector.get_current_price(INITIAL_STOCK)

        if current_price:
            # Calculate actual shares we can buy with $200
            shares = INITIAL_CAPITAL / current_price
            shares = round(shares, 6)  # Round to 6 decimal places for fractional shares

            # Create initial position
            position = Position(
                symbol=INITIAL_STOCK,
                shares=shares,
                entry_price=current_price,
                entry_date=datetime.now(),
                current_price=current_price,
                stop_loss=current_price * (1 - STOP_LOSS_PERCENT),
                take_profit=current_price * (1 + STOP_LOSS_PERCENT * TAKE_PROFIT_RATIO),
                position_type='long'
            )

            self.positions[INITIAL_STOCK] = position
            self.cash = 0.0  # All money invested initially

            # Record the trade
            trade = Trade(
                symbol=INITIAL_STOCK,
                side='buy',
                shares=shares,
                price=current_price,
                timestamp=datetime.now(),
                commission=0.0,  # No commission for initial position
                trade_type='market',
                reason='Initial portfolio setup'
            )
            self.trade_history.append(trade)

            self.logger.info(f"Created initial position: {shares:.6f} shares of {INITIAL_STOCK} at ${current_price:.2f}")

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value"""
        total_value = self.cash

        for position in self.positions.values():
            total_value += position.get_current_value()

        return total_value

    def get_portfolio_summary(self) -> Dict:
        """Get comprehensive portfolio summary"""
        total_value = self.get_portfolio_value()
        total_unrealized_pnl = sum(pos.get_unrealized_pnl() for pos in self.positions.values())
        total_unrealized_pnl_percent = (total_unrealized_pnl / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0

        # Calculate daily P&L
        daily_pnl = 0.0
        if self.daily_pnl_history:
            today = datetime.now().date()
            today_entry = next((entry for entry in self.daily_pnl_history if entry['date'] == today), None)
            if today_entry:
                daily_pnl = today_entry['pnl']

        # Performance metrics
        win_rate = (self.winning_trades / self.total_trades) * 100 if self.total_trades > 0 else 0

        return {
            'timestamp': datetime.now(),
            'total_value': total_value,
            'cash': self.cash,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_unrealized_pnl_percent': total_unrealized_pnl_percent,
            'daily_pnl': daily_pnl,
            'total_return_percent': ((total_value - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100,
            'positions_count': len(self.positions),
            'total_trades': self.total_trades,
            'win_rate': win_rate,
            'positions': {
                symbol: {
                    'shares': pos.shares,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'current_value': pos.get_current_value(),
                    'unrealized_pnl': pos.get_unrealized_pnl(),
                    'unrealized_pnl_percent': pos.get_unrealized_pnl_percent(),
                    'stop_loss': pos.stop_loss,
                    'take_profit': pos.take_profit
                }
                for symbol, pos in self.positions.items()
            }
        }

    def update_positions(self, market_data: Dict):
        """Update current prices and check stop loss/take profit"""
        for symbol, position in self.positions.items():
            if symbol in market_data:
                new_price = market_data[symbol].get('current_price')
                if new_price:
                    position.current_price = new_price

                    # Check for stop loss or take profit
                    if position.position_type == 'long':
                        if new_price <= position.stop_loss:
                            self._execute_stop_loss(symbol, "Stop loss triggered")
                        elif new_price >= position.take_profit:
                            self._execute_take_profit(symbol, "Take profit triggered")
                    else:  # short position
                        if new_price >= position.stop_loss:
                            self._execute_stop_loss(symbol, "Stop loss triggered (short)")
                        elif new_price <= position.take_profit:
                            self._execute_take_profit(symbol, "Take profit triggered (short)")

        self._save_portfolio()

    def can_open_position(self, symbol: str, shares: float, price: float) -> Tuple[bool, str]:
        """Check if we can open a new position"""
        # Check if we already have max positions
        if len(self.positions) >= MAX_POSITIONS and symbol not in self.positions:
            return False, f"Maximum positions limit reached ({MAX_POSITIONS})"

        # Check position size limit
        position_value = shares * price
        max_position_value = self.get_portfolio_value() * MAX_POSITION_SIZE

        if position_value > max_position_value:
            return False, f"Position size too large. Max allowed: ${max_position_value:.2f}"

        # Check if we have enough cash
        if position_value > self.cash:
            return False, f"Insufficient cash. Available: ${self.cash:.2f}, Required: ${position_value:.2f}"

        # Check daily loss limit
        daily_pnl = self._get_daily_pnl()
        daily_loss_limit = self.get_portfolio_value() * MAX_DAILY_LOSS

        if daily_pnl < -daily_loss_limit:
            return False, f"Daily loss limit reached. Current daily P&L: ${daily_pnl:.2f}"

        return True, "Position can be opened"

    def execute_buy_order(self, symbol: str, shares: float, price: float, reason: str = "Manual buy") -> bool:
        """Execute a buy order"""
        can_trade, message = self.can_open_position(symbol, shares, price)
        if not can_trade:
            self.logger.warning(f"Cannot buy {symbol}: {message}")
            return False

        try:
            # Calculate commission (assume $1 minimum or 0.5%)
            commission = max(1.0, shares * price * 0.005)
            total_cost = (shares * price) + commission

            if total_cost > self.cash:
                self.logger.warning(f"Insufficient cash for buy order including commission")
                return False

            # Execute the trade
            if symbol in self.positions:
                # Add to existing position (average down/up)
                existing_pos = self.positions[symbol]
                total_shares = existing_pos.shares + shares
                total_cost_existing = (existing_pos.shares * existing_pos.entry_price) + (shares * price)
                new_avg_price = total_cost_existing / total_shares

                existing_pos.shares = total_shares
                existing_pos.entry_price = new_avg_price
                existing_pos.stop_loss = new_avg_price * (1 - STOP_LOSS_PERCENT)
                existing_pos.take_profit = new_avg_price * (1 + STOP_LOSS_PERCENT * TAKE_PROFIT_RATIO)
            else:
                # Create new position
                position = Position(
                    symbol=symbol,
                    shares=shares,
                    entry_price=price,
                    entry_date=datetime.now(),
                    current_price=price,
                    stop_loss=price * (1 - STOP_LOSS_PERCENT),
                    take_profit=price * (1 + STOP_LOSS_PERCENT * TAKE_PROFIT_RATIO),
                    position_type='long'
                )
                self.positions[symbol] = position

            # Update cash and record trade
            self.cash -= total_cost
            self.total_commission += commission

            trade = Trade(
                symbol=symbol,
                side='buy',
                shares=shares,
                price=price,
                timestamp=datetime.now(),
                commission=commission,
                trade_type='market',
                reason=reason
            )
            self.trade_history.append(trade)
            self.total_trades += 1

            self.logger.info(f"Executed BUY: {shares} shares of {symbol} at ${price:.2f}")
            self._save_portfolio()
            return True

        except Exception as e:
            self.logger.error(f"Error executing buy order for {symbol}: {e}")
            return False

    def execute_sell_order(self, symbol: str, shares: float, price: float, reason: str = "Manual sell") -> bool:
        """Execute a sell order"""
        if symbol not in self.positions:
            self.logger.warning(f"Cannot sell {symbol}: No position exists")
            return False

        position = self.positions[symbol]

        if shares > position.shares:
            self.logger.warning(f"Cannot sell {shares} shares of {symbol}: Only {position.shares} available")
            return False

        try:
            # Calculate commission
            commission = max(1.0, shares * price * 0.005)
            proceeds = (shares * price) - commission

            # Update position or close it
            if shares == position.shares:
                # Close entire position
                pnl = (price - position.entry_price) * shares - commission
                if pnl > 0:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1

                del self.positions[symbol]
            else:
                # Partial sell
                position.shares -= shares

            # Update cash and record trade
            self.cash += proceeds
            self.total_commission += commission

            trade = Trade(
                symbol=symbol,
                side='sell',
                shares=shares,
                price=price,
                timestamp=datetime.now(),
                commission=commission,
                trade_type='market',
                reason=reason
            )
            self.trade_history.append(trade)
            self.total_trades += 1

            self.logger.info(f"Executed SELL: {shares} shares of {symbol} at ${price:.2f}")
            self._save_portfolio()
            return True

        except Exception as e:
            self.logger.error(f"Error executing sell order for {symbol}: {e}")
            return False

    def _execute_stop_loss(self, symbol: str, reason: str):
        """Execute stop loss for a position"""
        if symbol in self.positions:
            position = self.positions[symbol]
            self.execute_sell_order(symbol, position.shares, position.stop_loss, reason)

    def _execute_take_profit(self, symbol: str, reason: str):
        """Execute take profit for a position"""
        if symbol in self.positions:
            position = self.positions[symbol]
            self.execute_sell_order(symbol, position.shares, position.take_profit, reason)

    def _get_daily_pnl(self) -> float:
        """Calculate today's P&L"""
        today = datetime.now().date()
        today_entry = next((entry for entry in self.daily_pnl_history if entry['date'] == today), None)
        return today_entry['pnl'] if today_entry else 0.0

    def update_daily_pnl(self):
        """Update daily P&L tracking"""
        today = datetime.now().date()
        current_value = self.get_portfolio_value()

        # Find yesterday's value
        yesterday = today - timedelta(days=1)
        yesterday_entry = next((entry for entry in self.daily_pnl_history if entry['date'] == yesterday), None)
        yesterday_value = yesterday_entry['portfolio_value'] if yesterday_entry else INITIAL_CAPITAL

        daily_pnl = current_value - yesterday_value

        # Update or add today's entry
        today_entry = next((entry for entry in self.daily_pnl_history if entry['date'] == today), None)
        if today_entry:
            today_entry['pnl'] = daily_pnl
            today_entry['portfolio_value'] = current_value
        else:
            self.daily_pnl_history.append({
                'date': today,
                'pnl': daily_pnl,
                'portfolio_value': current_value
            })

        # Keep only last 30 days
        cutoff_date = today - timedelta(days=30)
        self.daily_pnl_history = [entry for entry in self.daily_pnl_history if entry['date'] >= cutoff_date]

        self._save_portfolio()

    def _save_portfolio(self):
        """Save portfolio state to file"""
        try:
            os.makedirs(os.path.dirname(self.portfolio_file), exist_ok=True)

            data = {
                'cash': self.cash,
                'positions': {},
                'trade_history': [],
                'daily_pnl_history': [],
                'performance': {
                    'total_trades': self.total_trades,
                    'winning_trades': self.winning_trades,
                    'losing_trades': self.losing_trades,
                    'total_commission': self.total_commission
                }
            }

            # Convert positions to dict
            for symbol, pos in self.positions.items():
                data['positions'][symbol] = {
                    'shares': pos.shares,
                    'entry_price': pos.entry_price,
                    'entry_date': pos.entry_date.isoformat(),
                    'current_price': pos.current_price,
                    'stop_loss': pos.stop_loss,
                    'take_profit': pos.take_profit,
                    'position_type': pos.position_type
                }

            # Convert trades to dict
            for trade in self.trade_history[-100:]:  # Keep last 100 trades
                data['trade_history'].append({
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'shares': trade.shares,
                    'price': trade.price,
                    'timestamp': trade.timestamp.isoformat(),
                    'commission': trade.commission,
                    'trade_type': trade.trade_type,
                    'reason': trade.reason
                })

            # Convert daily P&L history
            for entry in self.daily_pnl_history:
                data['daily_pnl_history'].append({
                    'date': entry['date'].isoformat(),
                    'pnl': entry['pnl'],
                    'portfolio_value': entry['portfolio_value']
                })

            with open(self.portfolio_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.logger.error(f"Error saving portfolio: {e}")

    def _load_portfolio(self):
        """Load portfolio state from file"""
        try:
            with open(self.portfolio_file, 'r') as f:
                data = json.load(f)

            self.cash = data.get('cash', 0.0)

            # Load positions
            for symbol, pos_data in data.get('positions', {}).items():
                position = Position(
                    symbol=symbol,
                    shares=pos_data['shares'],
                    entry_price=pos_data['entry_price'],
                    entry_date=datetime.fromisoformat(pos_data['entry_date']),
                    current_price=pos_data['current_price'],
                    stop_loss=pos_data['stop_loss'],
                    take_profit=pos_data['take_profit'],
                    position_type=pos_data['position_type']
                )
                self.positions[symbol] = position

            # Load trade history
            for trade_data in data.get('trade_history', []):
                trade = Trade(
                    symbol=trade_data['symbol'],
                    side=trade_data['side'],
                    shares=trade_data['shares'],
                    price=trade_data['price'],
                    timestamp=datetime.fromisoformat(trade_data['timestamp']),
                    commission=trade_data['commission'],
                    trade_type=trade_data['trade_type'],
                    reason=trade_data['reason']
                )
                self.trade_history.append(trade)

            # Load daily P&L history
            for pnl_data in data.get('daily_pnl_history', []):
                self.daily_pnl_history.append({
                    'date': datetime.fromisoformat(pnl_data['date']).date(),
                    'pnl': pnl_data['pnl'],
                    'portfolio_value': pnl_data['portfolio_value']
                })

            # Load performance metrics
            performance = data.get('performance', {})
            self.total_trades = performance.get('total_trades', 0)
            self.winning_trades = performance.get('winning_trades', 0)
            self.losing_trades = performance.get('losing_trades', 0)
            self.total_commission = performance.get('total_commission', 0.0)

            self.logger.info("Portfolio loaded successfully")

        except Exception as e:
            self.logger.error(f"Error loading portfolio: {e}")
            self._create_initial_position()

if __name__ == "__main__":
    # Test the portfolio manager
    portfolio = PortfolioManager()
    summary = portfolio.get_portfolio_summary()

    print("Portfolio Summary:")
    print(f"Total Value: ${summary['total_value']:.2f}")
    print(f"Cash: ${summary['cash']:.2f}")
    print(f"Total Return: {summary['total_return_percent']:.2f}%")
    print(f"Positions: {summary['positions_count']}")

    for symbol, pos in summary['positions'].items():
        print(f"\n{symbol}:")
        print(f"  Shares: {pos['shares']:.6f}")
        print(f"  Current Value: ${pos['current_value']:.2f}")
        print(f"  Unrealized P&L: ${pos['unrealized_pnl']:.2f} ({pos['unrealized_pnl_percent']:.2f}%)")