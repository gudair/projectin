from sqlalchemy import Column, String, Decimal, Integer, DateTime, Date, Text, Boolean, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from datetime import datetime
from typing import Optional

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")

class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(100), nullable=False, default="Main Portfolio")
    initial_capital = Column(Decimal(15, 2), nullable=False, default=200.00)
    cash = Column(Decimal(15, 2), nullable=False, default=0.00)
    total_value = Column(Decimal(15, 2), nullable=False, default=200.00)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="portfolios")
    positions = relationship("Position", back_populates="portfolio", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="portfolio", cascade="all, delete-orphan")
    daily_performance = relationship("DailyPerformance", back_populates="portfolio", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="portfolio", cascade="all, delete-orphan")
    performance_metrics = relationship("PerformanceMetrics", back_populates="portfolio", cascade="all, delete-orphan")

class Position(Base):
    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol = Column(String(10), nullable=False)
    shares = Column(Decimal(15, 6), nullable=False)
    entry_price = Column(Decimal(10, 4), nullable=False)
    current_price = Column(Decimal(10, 4), nullable=False)
    entry_date = Column(DateTime(timezone=True), nullable=False)
    stop_loss = Column(Decimal(10, 4))
    take_profit = Column(Decimal(10, 4))
    position_type = Column(String(10), nullable=False, default="long")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")

    @property
    def current_value(self) -> float:
        return float(self.shares * self.current_price)

    @property
    def unrealized_pnl(self) -> float:
        if self.position_type == "long":
            return float((self.current_price - self.entry_price) * self.shares)
        else:
            return float((self.entry_price - self.current_price) * self.shares)

    @property
    def unrealized_pnl_percent(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.unrealized_pnl / float(self.entry_price * self.shares)) * 100

class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol = Column(String(10), nullable=False)
    side = Column(String(4), nullable=False)  # 'buy' or 'sell'
    shares = Column(Decimal(15, 6), nullable=False)
    price = Column(Decimal(10, 4), nullable=False)
    value = Column(Decimal(15, 2), nullable=False)  # shares * price
    commission = Column(Decimal(8, 2), nullable=False, default=0.00)
    trade_type = Column(String(10), nullable=False, default="market")
    reason = Column(Text)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="trades")

class DailyPerformance(Base):
    __tablename__ = "daily_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    portfolio_value = Column(Decimal(15, 2), nullable=False)
    cash = Column(Decimal(15, 2), nullable=False)
    daily_pnl = Column(Decimal(15, 2), nullable=False)
    daily_return_percent = Column(Decimal(8, 4), nullable=False)
    total_return_percent = Column(Decimal(8, 4), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="daily_performance")

class TradingSignal(Base):
    __tablename__ = "trading_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), nullable=False)
    signal_type = Column(String(20), nullable=False)
    confidence = Column(Decimal(3, 2), nullable=False)
    strength = Column(Decimal(3, 2), nullable=False)
    current_price = Column(Decimal(10, 4))
    target_price = Column(Decimal(10, 4))
    stop_loss = Column(Decimal(10, 4))
    reasoning = Column(Text)
    technical_score = Column(Decimal(3, 2))
    news_score = Column(Decimal(3, 2))
    volume_score = Column(Decimal(3, 2))
    momentum_score = Column(Decimal(3, 2))
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"))
    action = Column(String(10), nullable=False)
    symbol = Column(String(10), nullable=False)
    shares = Column(Decimal(15, 6), nullable=False)
    current_price = Column(Decimal(10, 4), nullable=False)
    target_price = Column(Decimal(10, 4))
    stop_loss = Column(Decimal(10, 4))
    reasoning = Column(Text, nullable=False)
    confidence = Column(Decimal(3, 2), nullable=False)
    urgency = Column(String(10), nullable=False)
    expected_return = Column(Decimal(8, 4))
    risk_level = Column(String(10), nullable=False)
    time_horizon = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="recommendations")

class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), nullable=False)
    current_price = Column(Decimal(10, 4), nullable=False)
    volume = Column(BigInteger)
    daily_change = Column(Decimal(8, 4))
    daily_change_percent = Column(Decimal(8, 4))
    rsi = Column(Decimal(5, 2))
    macd = Column(Decimal(8, 4))
    macd_signal = Column(Decimal(8, 4))
    sma_20 = Column(Decimal(10, 4))
    sma_50 = Column(Decimal(10, 4))
    bb_upper = Column(Decimal(10, 4))
    bb_lower = Column(Decimal(10, 4))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    url = Column(Text)
    source = Column(String(100))
    published_at = Column(DateTime(timezone=True), nullable=False)
    sentiment = Column(String(10))
    sentiment_score = Column(Decimal(3, 2))
    confidence = Column(Decimal(3, 2))
    impact = Column(Decimal(3, 2))
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(10), nullable=False)
    module = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    metadata = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class PerformanceMetrics(Base):
    __tablename__ = "performance_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"))
    total_return = Column(Decimal(8, 4), nullable=False)
    annualized_return = Column(Decimal(8, 4), nullable=False)
    sharpe_ratio = Column(Decimal(8, 4), nullable=False)
    max_drawdown = Column(Decimal(8, 4), nullable=False)
    win_rate = Column(Decimal(5, 2), nullable=False)
    avg_win = Column(Decimal(10, 4), nullable=False)
    avg_loss = Column(Decimal(10, 4), nullable=False)
    profit_factor = Column(Decimal(8, 4), nullable=False)
    total_trades = Column(Integer, nullable=False)
    days_active = Column(Integer, nullable=False)
    risk_level = Column(String(10), nullable=False)
    performance_grade = Column(String(1), nullable=False)
    volatility = Column(Decimal(8, 4), nullable=False)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    portfolio = relationship("Portfolio", back_populates="performance_metrics")