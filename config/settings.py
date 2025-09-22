import os
from dotenv import load_dotenv

load_dotenv()

# API Keys (get free keys from respective services)
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', 'demo')
NEWS_API_KEY = os.getenv('NEWS_API_KEY', 'demo')

# Trading Configuration
INITIAL_CAPITAL = 200.0
INITIAL_STOCK = 'TSLA'
INITIAL_SHARES = 0.8  # Approximately $200 worth at ~$250/share

# Risk Management
MAX_POSITION_SIZE = 0.15  # 15% of portfolio per trade
MAX_DAILY_LOSS = 0.05     # 5% max daily loss
STOP_LOSS_PERCENT = 0.02  # 2% stop loss
TAKE_PROFIT_RATIO = 3     # 3:1 reward/risk
MAX_POSITIONS = 3         # Maximum concurrent positions

# Trading Hours (EST)
MARKET_OPEN = "09:30"
MARKET_CLOSE = "16:00"
PRE_MARKET_START = "07:00"
AFTER_HOURS_END = "20:00"

# Data Sources
DATA_SOURCES = {
    'primary': 'yfinance',
    'backup': 'alpha_vantage',
    'news': 'newsapi'
}

# Signal Weights
SIGNAL_WEIGHTS = {
    'technical': 0.40,
    'news_sentiment': 0.35,
    'volume': 0.15,
    'social_sentiment': 0.10
}

# Database
DATABASE_URL = 'sqlite:///trading_simulator.db'

# Dashboard
DASHBOARD_HOST = '127.0.0.1'
DASHBOARD_PORT = 8050
DASHBOARD_DEBUG = True

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = 'logs/trading_simulator.log'

# Update Intervals (minutes)
DATA_UPDATE_INTERVAL = 5
SIGNAL_UPDATE_INTERVAL = 5
PORTFOLIO_UPDATE_INTERVAL = 1

# Watchlist (besides initial TSLA)
WATCHLIST = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'NFLX', 'AMD']