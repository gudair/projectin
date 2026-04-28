"""Debug regime filter"""
import asyncio
from datetime import datetime, timedelta
from backtest.regime_filtered import RegimeFilter
from backtest.daily_data import DailyDataLoader

async def debug_regime():
    rf = RegimeFilter()

    dates = [
        datetime(2025, 10, 1),
        datetime(2025, 10, 15),
        datetime(2025, 11, 1),
        datetime(2025, 11, 10),
        datetime(2025, 11, 17),
        datetime(2025, 11, 24),
        datetime(2025, 12, 1),
    ]

    print("Date         | Should Trade | Reason")
    print("-" * 60)

    for d in dates:
        should, reason = await rf.should_trade(d)
        print(f"{d.strftime('%Y-%m-%d')} | {'YES' if should else 'NO ':>12} | {reason}")

asyncio.run(debug_regime())
