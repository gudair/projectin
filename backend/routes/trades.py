from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel

from database.connection import get_database

router = APIRouter()

class TradeRequest(BaseModel):
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: int
    price: float
    trade_type: str = 'MARKET'

@router.post("/")
async def create_trade(
    trade: TradeRequest,
    db: AsyncSession = Depends(get_database)
):
    """Create a new trade"""
    # For now, return a mock response
    return {
        "id": "mock-trade-id",
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "total": trade.quantity * trade.price,
        "status": "executed",
        "message": f"Trade executed: {trade.side} {trade.quantity} shares of {trade.symbol}"
    }

@router.get("/")
async def get_trades(
    db: AsyncSession = Depends(get_database)
):
    """Get user's trades"""
    return []