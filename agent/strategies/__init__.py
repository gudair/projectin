"""
Trading Strategies Module
"""
from agent.strategies.base import BaseStrategy
from agent.strategies.day_trading import DayTradingStrategy

__all__ = ['BaseStrategy', 'DayTradingStrategy']
