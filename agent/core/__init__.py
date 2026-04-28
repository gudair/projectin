"""
Agent Core Components
"""
from agent.core.agent import TradingAgent
from agent.core.reasoning import ReasoningEngine
from agent.core.memory import TradingMemory
from agent.core.context import MarketContext
from agent.core.summary import DailySummary
from agent.core.discovery import StockDiscovery
from agent.core.trade_logger import TradeLogger, TradeDecisionLog
from agent.core.analyst_ratings import AnalystRatingsProvider, AnalystRating
from agent.core.risk_manager import RiskManager, RiskConfig, RiskCheckResult
from agent.core.news_sentiment import NewsSentimentAnalyzer, NewsSentiment
from agent.core.trade_intelligence import TradeIntelligence, DebateResult, ReflectionInsight
from agent.core.atr_stops import ATRStopManager, ATRResult, DynamicStopLevels
from agent.core.periodic_reflection import PeriodicReflectionAgent, ReflectionReport
from agent.core.layered_memory import LayeredMemorySystem, MemoryItem, LayeredMemoryQuery
from agent.core.position_intelligence import PositionIntelligence, PositionRecommendation, MarketSession
from agent.core.hindsight import HindsightAnalyzer, OptimalTrade, DailyHindsightReport, HindsightPattern
from agent.core.pattern_analyzer import PatternAnalyzer, PatternType, PatternStats, SetupQuality
from agent.core.volatility_detector import VolatilityDetector, VolatilityAssessment, VolatilityRegime, TradingMode as VolTradingMode

__all__ = [
    'TradingAgent',
    'ReasoningEngine',
    'TradingMemory',
    'MarketContext',
    'DailySummary',
    'StockDiscovery',
    'TradeLogger',
    'TradeDecisionLog',
    'AnalystRatingsProvider',
    'AnalystRating',
    'RiskManager',
    'RiskConfig',
    'RiskCheckResult',
    'NewsSentimentAnalyzer',
    'NewsSentiment',
    'TradeIntelligence',
    'DebateResult',
    'ReflectionInsight',
    # New modules (GitHub research improvements)
    'ATRStopManager',
    'ATRResult',
    'DynamicStopLevels',
    'PeriodicReflectionAgent',
    'ReflectionReport',
    'LayeredMemorySystem',
    'MemoryItem',
    'LayeredMemoryQuery',
    # Position Intelligence (Kelly, Drawdown, Sessions)
    'PositionIntelligence',
    'PositionRecommendation',
    'MarketSession',
    # Hindsight Analysis (Learning from optimal scenarios)
    'HindsightAnalyzer',
    'OptimalTrade',
    'DailyHindsightReport',
    'HindsightPattern',
    # Pattern Analysis (Statistical backtesting)
    'PatternAnalyzer',
    'PatternType',
    'PatternStats',
    'SetupQuality',
    # Volatility Detection (Pre-market assessment)
    'VolatilityDetector',
    'VolatilityAssessment',
    'VolatilityRegime',
    'VolTradingMode',
]
