from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_database

router = APIRouter()

@router.get("/")
async def get_signals(
    db: AsyncSession = Depends(get_database)
):
    """Get trading signals"""
    # Mock data for now
    return [
        {
            "id": "1",
            "symbol": "AAPL",
            "signal_type": "BUY",
            "confidence": 85,
            "price": 175.50,
            "timestamp": "2024-01-01T10:00:00Z"
        },
        {
            "id": "2",
            "symbol": "GOOGL",
            "signal_type": "HOLD",
            "confidence": 72,
            "price": 2450.30,
            "timestamp": "2024-01-01T10:00:00Z"
        }
    ]