"""
Backtesting Module for AI Trading Agent

Runs the agent against historical data without modifying the agent code.
Uses monkey-patching to inject historical data instead of live data.
"""
from backtest.engine import BacktestEngine
from backtest.historical_data import HistoricalDataLoader
from backtest.portfolio_tracker import PortfolioTracker
from backtest.report import ReportGenerator

__all__ = [
    'BacktestEngine',
    'HistoricalDataLoader',
    'PortfolioTracker',
    'ReportGenerator',
]
