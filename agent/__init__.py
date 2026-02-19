"""
AI Trading Agent Module

Core AI-powered trading agent with Claude reasoning and Alpaca execution.
"""
from agent.core.agent import TradingAgent
from agent.core.reasoning import ReasoningEngine
from agent.core.memory import TradingMemory
from agent.core.context import MarketContext

__all__ = ['TradingAgent', 'ReasoningEngine', 'TradingMemory', 'MarketContext']
