from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database.connection import get_database

router = APIRouter()

@router.get("/")
async def get_performance(
    days: Optional[int] = 30,
    db: AsyncSession = Depends(get_database)
):
    """Get portfolio performance data"""
    # Mock performance data
    import datetime

    performance_data = []
    base_value = 10000

    for i in range(days):
        date = datetime.datetime.now() - datetime.timedelta(days=days-i-1)
        value = base_value + (i * 50) + (i % 3 * 100)  # Mock growth with some variance

        performance_data.append({
            "date": date.isoformat(),
            "portfolio_value": value,
            "daily_return": (value - base_value) / base_value * 100 if i > 0 else 0,
            "cumulative_return": (value - base_value) / base_value * 100
        })

    return {
        "period_days": days,
        "performance": performance_data,
        "total_return": performance_data[-1]["cumulative_return"] if performance_data else 0
    }