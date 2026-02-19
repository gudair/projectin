"""
Alpaca API Integration Module

Provides real-time market data and paper trading execution via Alpaca.
"""
from alpaca.client import AlpacaClient
from alpaca.stream import AlpacaStreamer
from alpaca.executor import OrderExecutor

__all__ = ['AlpacaClient', 'AlpacaStreamer', 'OrderExecutor']
