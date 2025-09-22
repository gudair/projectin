import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class PerformanceMetrics:
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_trades: int
    days_active: int

class PerformanceTracker:
    def __init__(self, portfolio_manager):
        self.portfolio_manager = portfolio_manager
        self.logger = logging.getLogger(__name__)

        # Performance data storage
        self.daily_returns = []
        self.trade_analysis = []
        self.benchmark_data = []

        # Load existing data
        self.load_performance_data()

    def calculate_performance_metrics(self) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""
        try:
            # Get portfolio history
            portfolio_history = self.portfolio_manager.daily_pnl_history
            trade_history = self.portfolio_manager.trade_history

            if not portfolio_history:
                return self._get_default_metrics()

            # Calculate returns
            returns = self._calculate_daily_returns(portfolio_history)

            # Basic metrics
            total_return = self._calculate_total_return(portfolio_history)
            annualized_return = self._calculate_annualized_return(returns, len(portfolio_history))

            # Risk metrics
            sharpe_ratio = self._calculate_sharpe_ratio(returns)
            max_drawdown = self._calculate_max_drawdown(portfolio_history)

            # Trading metrics
            win_rate, avg_win, avg_loss, profit_factor = self._calculate_trading_metrics(trade_history)

            return PerformanceMetrics(
                total_return=total_return,
                annualized_return=annualized_return,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                total_trades=len(trade_history),
                days_active=len(portfolio_history)
            )

        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {e}")
            return self._get_default_metrics()

    def _calculate_daily_returns(self, portfolio_history: List[Dict]) -> List[float]:
        """Calculate daily returns from portfolio history"""
        if len(portfolio_history) < 2:
            return []

        returns = []
        for i in range(1, len(portfolio_history)):
            prev_value = portfolio_history[i-1]['portfolio_value']
            curr_value = portfolio_history[i]['portfolio_value']

            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)
            else:
                returns.append(0.0)

        return returns

    def _calculate_total_return(self, portfolio_history: List[Dict]) -> float:
        """Calculate total return since inception"""
        if not portfolio_history:
            return 0.0

        initial_value = 200.0  # Initial capital
        current_value = portfolio_history[-1]['portfolio_value']

        return ((current_value - initial_value) / initial_value) * 100

    def _calculate_annualized_return(self, returns: List[float], days: int) -> float:
        """Calculate annualized return"""
        if not returns or days == 0:
            return 0.0

        # Compound daily returns
        cumulative_return = 1.0
        for ret in returns:
            cumulative_return *= (1 + ret)

        # Annualize (assume 252 trading days per year)
        if days >= 1:
            annualized = (cumulative_return ** (252 / days)) - 1
            return annualized * 100

        return 0.0

    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if not returns:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - (risk_free_rate / 252)  # Daily risk-free rate

        if np.std(excess_returns) == 0:
            return 0.0

        sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
        return sharpe

    def _calculate_max_drawdown(self, portfolio_history: List[Dict]) -> float:
        """Calculate maximum drawdown"""
        if len(portfolio_history) < 2:
            return 0.0

        values = [entry['portfolio_value'] for entry in portfolio_history]
        peak = values[0]
        max_dd = 0.0

        for value in values:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)

        return max_dd * 100

    def _calculate_trading_metrics(self, trade_history: List) -> Tuple[float, float, float, float]:
        """Calculate trading-specific metrics"""
        if len(trade_history) < 2:
            return 0.0, 0.0, 0.0, 0.0

        # Group trades into round trips (buy/sell pairs)
        round_trips = self._get_round_trips(trade_history)

        if not round_trips:
            return 0.0, 0.0, 0.0, 0.0

        # Calculate P&L for each round trip
        wins = []
        losses = []

        for trip in round_trips:
            pnl = trip['pnl']
            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))

        # Calculate metrics
        total_trades = len(round_trips)
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0.0
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        total_profit = sum(wins)
        total_loss = sum(losses)
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        return win_rate, avg_win, avg_loss, profit_factor

    def _get_round_trips(self, trade_history: List) -> List[Dict]:
        """Convert trade history to round trips (complete buy/sell cycles)"""
        round_trips = []
        positions = {}  # Track open positions by symbol

        for trade in trade_history:
            symbol = trade.symbol

            if symbol not in positions:
                positions[symbol] = {'shares': 0, 'total_cost': 0, 'trades': []}

            position = positions[symbol]

            if trade.side == 'buy':
                position['shares'] += trade.shares
                position['total_cost'] += (trade.shares * trade.price) + trade.commission
                position['trades'].append(trade)

            elif trade.side == 'sell' and position['shares'] > 0:
                # Calculate P&L for this sell
                avg_cost = position['total_cost'] / position['shares'] if position['shares'] > 0 else 0
                proceeds = (trade.shares * trade.price) - trade.commission
                cost_basis = trade.shares * avg_cost
                pnl = proceeds - cost_basis

                round_trips.append({
                    'symbol': symbol,
                    'entry_date': position['trades'][0].timestamp,
                    'exit_date': trade.timestamp,
                    'shares': trade.shares,
                    'avg_entry_price': avg_cost,
                    'exit_price': trade.price,
                    'pnl': pnl,
                    'pnl_percent': (pnl / cost_basis) * 100 if cost_basis > 0 else 0
                })

                # Update position
                position['shares'] -= trade.shares
                if position['shares'] <= 0:
                    # Position closed
                    positions[symbol] = {'shares': 0, 'total_cost': 0, 'trades': []}
                else:
                    # Partial close - adjust cost basis proportionally
                    remaining_ratio = position['shares'] / (position['shares'] + trade.shares)
                    position['total_cost'] *= remaining_ratio

        return round_trips

    def _get_default_metrics(self) -> PerformanceMetrics:
        """Return default metrics when no data available"""
        return PerformanceMetrics(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            total_trades=0,
            days_active=0
        )

    def generate_performance_report(self) -> Dict:
        """Generate comprehensive performance report"""
        metrics = self.calculate_performance_metrics()
        portfolio_summary = self.portfolio_manager.get_portfolio_summary()

        # Calculate additional metrics
        current_positions = len(portfolio_summary['positions'])
        cash_percentage = (portfolio_summary['cash'] / portfolio_summary['total_value']) * 100

        # Risk assessment
        risk_level = self._assess_risk_level(metrics)

        # Performance grade
        grade = self._calculate_performance_grade(metrics)

        report = {
            'timestamp': datetime.now().isoformat(),
            'portfolio_summary': {
                'total_value': portfolio_summary['total_value'],
                'cash': portfolio_summary['cash'],
                'cash_percentage': cash_percentage,
                'positions_count': current_positions,
                'daily_pnl': portfolio_summary['daily_pnl']
            },
            'performance_metrics': {
                'total_return_percent': metrics.total_return,
                'annualized_return_percent': metrics.annualized_return,
                'sharpe_ratio': metrics.sharpe_ratio,
                'max_drawdown_percent': metrics.max_drawdown,
                'days_active': metrics.days_active
            },
            'trading_metrics': {
                'total_trades': metrics.total_trades,
                'win_rate_percent': metrics.win_rate,
                'average_win': metrics.avg_win,
                'average_loss': metrics.avg_loss,
                'profit_factor': metrics.profit_factor
            },
            'risk_assessment': {
                'risk_level': risk_level,
                'performance_grade': grade,
                'volatility': self._calculate_volatility()
            }
        }

        return report

    def _assess_risk_level(self, metrics: PerformanceMetrics) -> str:
        """Assess overall risk level"""
        risk_score = 0

        # Max drawdown contribution
        if metrics.max_drawdown > 20:
            risk_score += 3
        elif metrics.max_drawdown > 10:
            risk_score += 2
        elif metrics.max_drawdown > 5:
            risk_score += 1

        # Sharpe ratio contribution (inverse)
        if metrics.sharpe_ratio < 0:
            risk_score += 2
        elif metrics.sharpe_ratio < 0.5:
            risk_score += 1

        # Win rate contribution (inverse)
        if metrics.win_rate < 40:
            risk_score += 2
        elif metrics.win_rate < 50:
            risk_score += 1

        if risk_score >= 5:
            return 'high'
        elif risk_score >= 3:
            return 'medium'
        else:
            return 'low'

    def _calculate_performance_grade(self, metrics: PerformanceMetrics) -> str:
        """Calculate performance grade A-F"""
        score = 0

        # Total return (40% weight)
        if metrics.total_return > 20:
            score += 40
        elif metrics.total_return > 10:
            score += 30
        elif metrics.total_return > 5:
            score += 20
        elif metrics.total_return > 0:
            score += 10

        # Sharpe ratio (30% weight)
        if metrics.sharpe_ratio > 2:
            score += 30
        elif metrics.sharpe_ratio > 1:
            score += 25
        elif metrics.sharpe_ratio > 0.5:
            score += 15
        elif metrics.sharpe_ratio > 0:
            score += 5

        # Win rate (20% weight)
        if metrics.win_rate > 70:
            score += 20
        elif metrics.win_rate > 60:
            score += 15
        elif metrics.win_rate > 50:
            score += 10
        elif metrics.win_rate > 40:
            score += 5

        # Max drawdown penalty (10% weight)
        if metrics.max_drawdown < 5:
            score += 10
        elif metrics.max_drawdown < 10:
            score += 5

        # Assign grade
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

    def _calculate_volatility(self) -> float:
        """Calculate portfolio volatility"""
        portfolio_history = self.portfolio_manager.daily_pnl_history

        if len(portfolio_history) < 2:
            return 0.0

        returns = self._calculate_daily_returns(portfolio_history)
        return np.std(returns) * np.sqrt(252) * 100 if returns else 0.0

    def save_performance_data(self):
        """Save performance data to file"""
        try:
            os.makedirs('analytics', exist_ok=True)

            report = self.generate_performance_report()

            with open('analytics/performance_report.json', 'w') as f:
                json.dump(report, f, indent=2)

        except Exception as e:
            self.logger.error(f"Error saving performance data: {e}")

    def load_performance_data(self):
        """Load existing performance data"""
        try:
            if os.path.exists('analytics/performance_report.json'):
                with open('analytics/performance_report.json', 'r') as f:
                    self.historical_data = json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading performance data: {e}")

    def export_detailed_report(self, filename: str = None):
        """Export detailed performance report to CSV"""
        if not filename:
            filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        try:
            # Portfolio history
            portfolio_df = pd.DataFrame(self.portfolio_manager.daily_pnl_history)

            # Trade history
            trade_data = []
            for trade in self.portfolio_manager.trade_history:
                trade_data.append({
                    'date': trade.timestamp,
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'shares': trade.shares,
                    'price': trade.price,
                    'value': trade.shares * trade.price,
                    'commission': trade.commission,
                    'reason': trade.reason
                })

            trades_df = pd.DataFrame(trade_data)

            # Save to Excel with multiple sheets
            with pd.ExcelWriter(f'analytics/{filename}', engine='openpyxl') as writer:
                portfolio_df.to_excel(writer, sheet_name='Portfolio_History', index=False)
                trades_df.to_excel(writer, sheet_name='Trade_History', index=False)

                # Summary sheet
                metrics = self.calculate_performance_metrics()
                summary_data = {
                    'Metric': ['Total Return %', 'Annualized Return %', 'Sharpe Ratio',
                              'Max Drawdown %', 'Win Rate %', 'Total Trades', 'Days Active'],
                    'Value': [metrics.total_return, metrics.annualized_return, metrics.sharpe_ratio,
                             metrics.max_drawdown, metrics.win_rate, metrics.total_trades, metrics.days_active]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)

            self.logger.info(f"Detailed report exported to analytics/{filename}")

        except Exception as e:
            self.logger.error(f"Error exporting detailed report: {e}")

if __name__ == "__main__":
    # Test performance tracker
    from portfolio.portfolio_manager import PortfolioManager

    portfolio = PortfolioManager()
    tracker = PerformanceTracker(portfolio)

    report = tracker.generate_performance_report()
    print("Performance Report:")
    print(json.dumps(report, indent=2, default=str))