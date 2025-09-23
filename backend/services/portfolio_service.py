from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import uuid
from decimal import Decimal

from models.database import Portfolio, Position, Trade, User

class PortfolioService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_default_portfolio(self) -> Portfolio:
        """Create a default portfolio for new users"""
        try:
            # Check if portfolio already exists
            result = await self.db.execute(
                select(Portfolio).where(Portfolio.name == "Trading Simulator")
            )
            existing_portfolio = result.scalar_one_or_none()

            if existing_portfolio:
                return existing_portfolio

            # Create new portfolio
            portfolio = Portfolio(
                id=uuid.uuid4(),
                name="Trading Simulator",
                initial_capital=Decimal("10000.00"),
                cash=Decimal("10000.00"),
                total_value=Decimal("10000.00"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            self.db.add(portfolio)
            await self.db.commit()
            await self.db.refresh(portfolio)

            print(f"✅ Created default portfolio with ID: {portfolio.id}")
            return portfolio

        except Exception as e:
            await self.db.rollback()
            print(f"❌ Error creating default portfolio: {e}")
            raise

    async def get_portfolio_by_id(self, portfolio_id: uuid.UUID) -> Portfolio:
        """Get portfolio by ID"""
        result = await self.db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        portfolio = result.scalar_one_or_none()

        if not portfolio:
            raise ValueError(f"Portfolio not found with ID: {portfolio_id}")

        return portfolio

    async def update_portfolio_value(self, portfolio_id: uuid.UUID) -> Portfolio:
        """Recalculate and update portfolio total value"""
        try:
            portfolio = await self.get_portfolio_by_id(portfolio_id)

            # Get all positions
            positions_result = await self.db.execute(
                select(Position).where(Position.portfolio_id == portfolio_id)
            )
            positions = positions_result.scalars().all()

            # Calculate total positions value (mock calculation for now)
            positions_value = Decimal("0.00")
            for position in positions:
                # In real implementation, you'd get current market price
                current_price = position.current_price  # Using current price
                position_value = position.shares * current_price
                positions_value += position_value

            # Update portfolio
            portfolio.total_value = portfolio.cash + positions_value
            portfolio.updated_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(portfolio)

            return portfolio

        except Exception as e:
            await self.db.rollback()
            print(f"❌ Error updating portfolio value: {e}")
            raise