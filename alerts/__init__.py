"""
Alert System Module

Provides CLI-based alerts with rich terminal formatting for trading signals.
"""
from alerts.manager import AlertManager, Alert, AlertQueue
from alerts.formatters import AlertFormatter

__all__ = ['AlertManager', 'Alert', 'AlertQueue', 'AlertFormatter']
