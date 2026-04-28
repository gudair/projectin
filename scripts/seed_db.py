"""
Seed Supabase with initial data.

Run ONCE after creating the Supabase tables:
  source .venv/bin/activate
  python scripts/seed_db.py

What it inserts:
  - symbols table: the 8 core symbols (is_active=true, added_by='backtest')
  - agent_status: initial row (id=1)

Safe to re-run — uses upsert so it won't duplicate rows.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

CORE_SYMBOLS = [
    ("SOXL", "3x semiconductor ETF — highest volatility, best backtest performer"),
    ("SMCI", "AI/server manufacturer — high beta, volatile"),
    ("MARA", "Crypto miner — high correlation to BTC"),
    ("COIN", "Crypto exchange — retail interest, volatile"),
    ("MU",   "Memory semiconductors — cyclical, responds to AI narrative"),
    ("AMD",  "Semiconductors — strong retail following"),
    ("NVDA", "AI/GPU leader — high institutional + retail interest"),
    ("TSLA", "EV — highest retail sentiment exposure"),
]


def seed(url: str, key: str):
    from supabase import create_client
    client = create_client(url, key)

    print("Seeding symbols table...")
    for symbol, notes in CORE_SYMBOLS:
        result = client.table("symbols").upsert({
            "symbol": symbol,
            "is_active": True,
            "added_by": "backtest",
            "notes": notes,
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0,
        }, on_conflict="symbol").execute()
        print(f"  ✓ {symbol}")

    print("\nEnsuring agent_status row exists...")
    from datetime import datetime, timezone
    client.table("agent_status").upsert({
        "id": 1,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "is_running": False,
        "equity": 0,
        "open_positions": [],
    }).execute()
    print("  ✓ agent_status row ready")

    print("\nDone. Active symbols in DB:")
    rows = client.table("symbols").select("symbol,is_active,added_by,notes").eq("is_active", True).order("id").execute()
    for row in rows.data:
        print(f"  {'✅' if row['is_active'] else '⏸ '} {row['symbol']:6}  {row['notes'][:60]}")


if __name__ == "__main__":
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")

    if not url or not key:
        print("❌ SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        sys.exit(1)

    seed(url, key)
