from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_database

router = APIRouter()

@router.get("/price/{symbol}")
async def get_stock_price(
    symbol: str,
    db: AsyncSession = Depends(get_database)
):
    """Get current stock price"""
    # Mock data for now
    prices = {
        "AAPL": 175.50,
        "GOOGL": 2450.30,
        "MSFT": 380.20,
        "TSLA": 215.30,
        "AMZN": 145.20,
        "NVDA": 875.45
    }

    return {
        "symbol": symbol,
        "price": prices.get(symbol.upper(), 100.00),
        "change": 2.30,
        "change_percent": 1.33,
        "timestamp": "2024-01-01T10:00:00Z"
    }

@router.get("/search")
async def search_stocks(
    q: str,
    db: AsyncSession = Depends(get_database)
):
    """Search for stocks"""
    stocks = [
        {"symbol": "AAPL", "name": "Apple Inc."},
        {"symbol": "GOOGL", "name": "Alphabet Inc."},
        {"symbol": "MSFT", "name": "Microsoft Corp."},
        {"symbol": "TSLA", "name": "Tesla Inc."},
    ]

    # Simple filter by query
    filtered = [s for s in stocks if q.upper() in s["symbol"] or q.lower() in s["name"].lower()]
    return filtered