from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, date
import uuid

from database.connection import get_database
from models.database import Portfolio, Position, Trade, DailyPerformance, User
from services.portfolio_service import PortfolioService

router = APIRouter()

@router.get("/")
async def get_portfolios(
    db: AsyncSession = Depends(get_database)
):
    """Get all portfolios for the user"""
    try:
        # For now, get default portfolio (single user system)
        result = await db.execute(
            select(Portfolio).where(Portfolio.name == "Trading Simulator")
        )
        portfolio = result.scalar_one_or_none()

        if not portfolio:
            # Create default portfolio if doesn't exist
            portfolio_service = PortfolioService(db)
            portfolio = await portfolio_service.create_default_portfolio()

        # Get positions count
        positions_result = await db.execute(
            select(func.count(Position.id)).where(Position.portfolio_id == portfolio.id)
        )
        positions_count = positions_result.scalar()

        # Calculate total return
        total_return_percent = 0.0
        if portfolio.initial_capital > 0:
            total_return_percent = ((portfolio.total_value - portfolio.initial_capital) / portfolio.initial_capital) * 100

        return {
            "id": str(portfolio.id),
            "name": portfolio.name,
            "initial_capital": float(portfolio.initial_capital),
            "cash": float(portfolio.cash),
            "total_value": float(portfolio.total_value),
            "total_return_percent": float(total_return_percent),
            "positions_count": positions_count,
            "created_at": portfolio.created_at.isoformat(),
            "updated_at": portfolio.updated_at.isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving portfolios: {str(e)}")

@router.get("/{portfolio_id}")
async def get_portfolio_summary(
    portfolio_id: str,
    db: AsyncSession = Depends(get_database)
):
    """Get detailed portfolio summary"""
    try:
        portfolio_uuid = uuid.UUID(portfolio_id)

        # Get portfolio
        result = await db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_uuid)
        )
        portfolio = result.scalar_one_or_none()

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Get positions
        positions_result = await db.execute(
            select(Position).where(Position.portfolio_id == portfolio_uuid)
        )
        positions = positions_result.scalars().all()

        # Get recent trades (last 10)
        trades_result = await db.execute(
            select(Trade)
            .where(Trade.portfolio_id == portfolio_uuid)
            .order_by(Trade.executed_at.desc())
            .limit(10)
        )
        recent_trades = trades_result.scalars().all()

        # Get today's performance
        today = date.today()
        daily_perf_result = await db.execute(
            select(DailyPerformance)
            .where(DailyPerformance.portfolio_id == portfolio_uuid)
            .where(DailyPerformance.date == today)
        )
        today_performance = daily_perf_result.scalar_one_or_none()

        daily_pnl = float(today_performance.daily_pnl) if today_performance else 0.0

        # Calculate total return
        total_return_percent = 0.0
        if portfolio.initial_capital > 0:
            total_return_percent = ((portfolio.total_value - portfolio.initial_capital) / portfolio.initial_capital) * 100

        # Format positions
        positions_data = []
        for pos in positions:
            positions_data.append({
                "id": str(pos.id),
                "symbol": pos.symbol,
                "shares": float(pos.shares),
                "entry_price": float(pos.entry_price),
                "current_price": float(pos.current_price),
                "current_value": pos.current_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_percent": pos.unrealized_pnl_percent,
                "stop_loss": float(pos.stop_loss) if pos.stop_loss else None,
                "take_profit": float(pos.take_profit) if pos.take_profit else None,
                "entry_date": pos.entry_date.isoformat(),
                "position_type": pos.position_type
            })

        # Format trades
        trades_data = []
        for trade in recent_trades:
            trades_data.append({
                "id": str(trade.id),
                "symbol": trade.symbol,
                "side": trade.side,
                "shares": float(trade.shares),
                "price": float(trade.price),
                "value": float(trade.value),
                "commission": float(trade.commission),
                "reason": trade.reason,
                "executed_at": trade.executed_at.isoformat()
            })

        return {
            "id": str(portfolio.id),
            "name": portfolio.name,
            "timestamp": datetime.now().isoformat(),
            "total_value": float(portfolio.total_value),
            "cash": float(portfolio.cash),
            "initial_capital": float(portfolio.initial_capital),
            "total_return_percent": float(total_return_percent),
            "daily_pnl": daily_pnl,
            "positions_count": len(positions),
            "positions": positions_data,
            "recent_trades": trades_data,
            "created_at": portfolio.created_at.isoformat(),
            "updated_at": portfolio.updated_at.isoformat()
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid portfolio ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving portfolio: {str(e)}")

@router.get("/{portfolio_id}/positions")
async def get_positions(
    portfolio_id: str,
    db: AsyncSession = Depends(get_database)
):
    """Get all positions for a portfolio"""
    try:
        portfolio_uuid = uuid.UUID(portfolio_id)

        # Verify portfolio exists
        portfolio_result = await db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_uuid)
        )
        portfolio = portfolio_result.scalar_one_or_none()

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Get positions
        result = await db.execute(
            select(Position).where(Position.portfolio_id == portfolio_uuid)
        )
        positions = result.scalars().all()

        positions_data = []
        for pos in positions:
            positions_data.append({
                "id": str(pos.id),
                "symbol": pos.symbol,
                "shares": float(pos.shares),
                "entry_price": float(pos.entry_price),
                "current_price": float(pos.current_price),
                "current_value": pos.current_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_percent": pos.unrealized_pnl_percent,
                "stop_loss": float(pos.stop_loss) if pos.stop_loss else None,
                "take_profit": float(pos.take_profit) if pos.take_profit else None,
                "entry_date": pos.entry_date.isoformat(),
                "position_type": pos.position_type,
                "updated_at": pos.updated_at.isoformat()
            })

        return {
            "portfolio_id": portfolio_id,
            "positions": positions_data,
            "total_positions": len(positions_data)
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid portfolio ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving positions: {str(e)}")

@router.get("/{portfolio_id}/performance")
async def get_portfolio_performance(
    portfolio_id: str,
    days: int = Query(30, description="Number of days of performance history"),
    db: AsyncSession = Depends(get_database)
):
    """Get portfolio performance history"""
    try:
        portfolio_uuid = uuid.UUID(portfolio_id)

        # Verify portfolio exists
        portfolio_result = await db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_uuid)
        )
        portfolio = portfolio_result.scalar_one_or_none()

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Get performance history
        result = await db.execute(
            select(DailyPerformance)
            .where(DailyPerformance.portfolio_id == portfolio_uuid)
            .order_by(DailyPerformance.date.desc())
            .limit(days)
        )
        performance_history = result.scalars().all()

        # Format performance data
        performance_data = []
        for perf in reversed(performance_history):  # Reverse to get chronological order
            performance_data.append({
                "date": perf.date.isoformat(),
                "portfolio_value": float(perf.portfolio_value),
                "cash": float(perf.cash),
                "daily_pnl": float(perf.daily_pnl),
                "daily_return_percent": float(perf.daily_return_percent),
                "total_return_percent": float(perf.total_return_percent)
            })

        # Calculate summary metrics
        total_return = 0.0
        if portfolio.initial_capital > 0:
            total_return = ((portfolio.total_value - portfolio.initial_capital) / portfolio.initial_capital) * 100

        current_date = date.today()
        days_active = len(performance_data)

        return {
            "portfolio_id": portfolio_id,
            "current_value": float(portfolio.total_value),
            "initial_capital": float(portfolio.initial_capital),
            "total_return_percent": float(total_return),
            "days_active": days_active,
            "performance_history": performance_data
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid portfolio ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving performance: {str(e)}")

@router.post("/{portfolio_id}/update")
async def update_portfolio_values(
    portfolio_id: str,
    db: AsyncSession = Depends(get_database)
):
    """Manually trigger portfolio value update"""
    try:
        portfolio_uuid = uuid.UUID(portfolio_id)

        # Use portfolio service to update values
        portfolio_service = PortfolioService(db)
        updated_portfolio = await portfolio_service.update_portfolio_values(portfolio_uuid)

        if not updated_portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        return {
            "message": "Portfolio updated successfully",
            "portfolio_id": portfolio_id,
            "total_value": float(updated_portfolio.total_value),
            "updated_at": updated_portfolio.updated_at.isoformat()
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid portfolio ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating portfolio: {str(e)}")