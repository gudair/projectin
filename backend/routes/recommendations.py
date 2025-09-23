from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_database

router = APIRouter()

@router.get("/")
async def get_recommendations(
    db: AsyncSession = Depends(get_database)
):
    """Get trading recommendations"""
    # Mock data for now
    return [
        {
            "id": "1",
            "symbol": "AAPL",
            "recommendation": "BUY",
            "target_price": 190.00,
            "current_price": 175.50,
            "reason": "Strong quarterly earnings and positive outlook",
            "analyst": "Goldman Sachs",
            "timestamp": "2024-01-01T10:00:00Z"
        }
    ]