"""
AI Trading Agent Configuration
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import os
from dotenv import load_dotenv

load_dotenv()


class MarketRegime(Enum):
    """Market regime classification"""
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"
    HIGH_VOLATILITY = "high_volatility"


class AlertLevel(Enum):
    """Alert priority levels"""
    IMMEDIATE = "immediate"  # Requires immediate attention
    STANDARD = "standard"    # Normal priority
    INFORMATIONAL = "info"   # FYI alerts


class TradingMode(Enum):
    """Trading mode"""
    PAPER = "paper"
    LIVE = "live"


@dataclass
class AlpacaConfig:
    """Alpaca API Configuration"""
    api_key: str = field(default_factory=lambda: os.getenv('ALPACA_API_KEY', ''))
    secret_key: str = field(default_factory=lambda: os.getenv('ALPACA_SECRET_KEY', ''))
    base_url: str = field(default_factory=lambda: os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets'))
    data_url: str = 'https://data.alpaca.markets'
    stream_url: str = 'wss://stream.data.alpaca.markets/v2/iex'

    @property
    def is_paper(self) -> bool:
        return 'paper' in self.base_url.lower()

    def validate(self) -> tuple[bool, str]:
        """Validate Alpaca configuration"""
        if not self.api_key:
            return False, "ALPACA_API_KEY not set"
        if not self.secret_key:
            return False, "ALPACA_SECRET_KEY not set"
        return True, "Configuration valid"


class LLMProvider(Enum):
    """LLM Provider selection"""
    OLLAMA = "ollama"      # Local, free
    CLAUDE = "claude"      # Cloud, paid


@dataclass
class OllamaConfig:
    """Ollama Local LLM Configuration"""
    base_url: str = field(default_factory=lambda: os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'))
    model: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'llama3.1:latest'))
    max_tokens: int = 256  # Reduced for compact prompts (was 1024)
    temperature: float = 0.3

    def validate(self) -> tuple[bool, str]:
        """Validate Ollama configuration"""
        # Just check if server is reachable (will be done at runtime)
        return True, "Configuration valid (server check at runtime)"


@dataclass
class ClaudeConfig:
    """Claude API Configuration"""
    api_key: str = field(default_factory=lambda: os.getenv('ANTHROPIC_API_KEY', ''))
    model: str = 'claude-sonnet-4-20250514'  # Cost-effective for analysis
    max_tokens: int = 1024                    # Reduced for cost savings (was 4096)
    temperature: float = 0.3                  # Lower for more consistent analysis

    def validate(self) -> tuple[bool, str]:
        """Validate Claude configuration"""
        if not self.api_key:
            return False, "ANTHROPIC_API_KEY not set"
        return True, "Configuration valid"


@dataclass
class CostOptimizationConfig:
    """Cost Optimization Settings - Adjusted for Ollama (local, free)"""
    # Analysis caching - shorter cache since Ollama is free
    cache_analysis_minutes: int = 10          # Cache for 10 min (was 30)
    min_price_change_pct: float = 0.5         # Re-analyze on 0.5% change (was 1.5%)

    # Batch processing
    batch_analysis: bool = True               # Analyze multiple stocks in one API call
    max_stocks_per_batch: int = 10            # More stocks per batch (was 5)

    # Analysis frequency - more frequent since free
    min_analysis_interval_seconds: int = 120  # 2 min between analyses (was 5 min)
    max_analyses_per_hour: int = 100          # Much higher limit (was 20)

    # Smart filtering - less strict since analysis is free
    min_volume_ratio: float = 1.0             # Any volume OK (was 1.5x)
    min_price_momentum: float = 0.3           # Lower momentum threshold (was 0.5)

    # Skip analysis conditions
    skip_if_no_position_change: bool = False  # Analyze even if can't trade (was True)
    skip_outside_market_hours: bool = True    # Still skip when market closed


@dataclass
class RiskConfig:
    """Risk Management Configuration"""
    # Position limits
    max_position_pct: float = 0.20        # 20% max per position
    max_positions: int = 5                 # Max concurrent positions
    max_daily_loss_pct: float = 0.03      # 3% max daily loss

    # Trade limits
    default_stop_loss_pct: float = 0.02   # 2% default stop loss
    default_take_profit_ratio: float = 2.5 # 2.5:1 reward/risk
    min_risk_reward: float = 1.5          # Minimum R:R to consider

    # PDT Rule tracking (Pattern Day Trader)
    pdt_enabled: bool = True
    pdt_limit: int = 3                    # Max day trades per 5 business days

    # Confidence thresholds - lower since Ollama analysis is free
    min_confidence_buy: float = 0.65      # Min confidence to generate BUY alert
    min_confidence_sell: float = 0.60     # Min confidence to generate SELL alert

    # Position sizing
    kelly_fraction: float = 0.25          # Fraction of Kelly criterion to use


@dataclass
class DiscoveryConfig:
    """Stock Discovery Configuration - Optimized for Ollama (free analysis)"""
    enabled: bool = True                   # Enable dynamic stock discovery

    # Scanning - more frequent since analysis is free
    scan_interval_minutes: int = 10        # Scan every 10 min (was 30)

    # Filters - less strict to find more opportunities
    min_price: float = 5.0                 # Lower min price (was 10)
    max_price: float = 500.0               # Higher max price (was 300)
    min_volume: int = 500_000              # Lower volume requirement (was 1M)
    min_market_cap: float = 1e9            # $1B min market cap (was $5B)
    min_change_pct: float = 2.0            # 2% change to be interesting (was 3%)

    # Quality-based limits - expanded for more opportunities
    min_score: float = 3.0                 # Lower threshold (was 5.0)
    max_discovered: int = 30               # Track more stocks (was 10)
    max_total_watchlist: int = 40          # Max 40 stocks to track (was 15)

    # Sources
    scan_top_gainers: bool = True          # Scan for top gainers
    scan_top_losers: bool = True           # Scan for top losers
    scan_unusual_volume: bool = True       # Scan for unusual volume

    # Exclusions (symbols to never add)
    excluded_symbols: List[str] = field(default_factory=lambda: [
        'SPY', 'QQQ', 'IWM', 'DIA',        # ETFs used for context only
        'VXX', 'UVXY', 'SVXY',              # Volatility products (too risky)
    ])


@dataclass
class AgentConfig:
    """Main Agent Configuration"""
    # Trading mode
    mode: TradingMode = TradingMode.PAPER

    # LLM Provider - OLLAMA is default (free, local)
    llm_provider: LLMProvider = LLMProvider.OLLAMA

    # Watchlist (empty = 100% dynamic discovery)
    watchlist: List[str] = field(default_factory=list)  # Dynamic mode: starts empty

    # Market context symbols
    market_context_symbols: Dict[str, str] = field(default_factory=lambda: {
        'spy': 'SPY',    # S&P 500
        'vix': '^VIX',   # Volatility Index
        'qqq': 'QQQ',    # NASDAQ 100
        'iwm': 'IWM',    # Russell 2000
    })

    # Update intervals (seconds) - more frequent with Ollama
    quote_update_interval: int = 5        # Real-time quote refresh
    signal_update_interval: int = 60      # Signal regeneration every 1 min
    market_context_interval: int = 120    # Market context refresh every 2 min

    # Autonomous mode - execute trades without user confirmation
    autonomous_mode: bool = True  # True = auto-execute, False = require confirmation

    # Alert settings
    alert_sound_enabled: bool = True
    alert_desktop_notification: bool = True

    # Memory settings
    memory_file: str = 'agent/data/memory.json'
    max_memory_trades: int = 500          # Max trades to keep in memory

    # Logging
    log_level: str = 'INFO'
    log_file: str = 'logs/agent.log'

    # Sub-configs
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    cost: CostOptimizationConfig = field(default_factory=CostOptimizationConfig)

    def validate(self) -> tuple[bool, List[str]]:
        """Validate all configurations"""
        errors = []

        alpaca_valid, alpaca_msg = self.alpaca.validate()
        if not alpaca_valid:
            errors.append(f"Alpaca: {alpaca_msg}")

        # Only validate Claude if using Claude provider
        if self.llm_provider == LLMProvider.CLAUDE:
            claude_valid, claude_msg = self.claude.validate()
            if not claude_valid:
                errors.append(f"Claude: {claude_msg}")

        # Watchlist can be empty if discovery is enabled (100% dynamic mode)
        if not self.watchlist and not self.discovery.enabled:
            errors.append("Watchlist is empty and discovery is disabled")

        return len(errors) == 0, errors


# Default configuration instance
DEFAULT_CONFIG = AgentConfig()


# Market hours configuration (US Eastern Time)
MARKET_HOURS = {
    'pre_market_start': '04:00',
    'market_open': '09:30',
    'market_close': '16:00',
    'after_hours_end': '20:00',
}

# VIX thresholds for regime classification
VIX_THRESHOLDS = {
    'low': 15,           # Below this = RISK_ON
    'medium': 20,        # Below this = NEUTRAL
    'high': 30,          # Below this = RISK_OFF
    'extreme': 40,       # Above this = HIGH_VOLATILITY
}

# Signal strength thresholds
SIGNAL_THRESHOLDS = {
    'strong_buy': 0.7,
    'buy': 0.5,
    'weak_buy': 0.3,
    'weak_sell': -0.3,
    'sell': -0.5,
    'strong_sell': -0.7,
}
