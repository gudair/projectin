"""
Supabase Logger - Writes trade events and agent heartbeat to Supabase.

Uses the service_role key (server-side only) so RLS policies don't block writes.
All reads from the frontend use the anon key with authenticated sessions.
"""
import logging
import os
from datetime import datetime
from typing import Optional, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        logger.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY not set — Supabase logging disabled")
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to init Supabase client: {e}")
        return None

    return _client


def log_trade(
    symbol: str,
    action: str,
    entry_price: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    confidence: float = 0.0,
    reasoning: str = "",
    executed: bool = False,
    order_id: Optional[str] = None,
) -> Optional[int]:
    """Insert a trade row. Returns the new row id or None on failure."""
    client = _get_client()
    if client is None:
        return None

    row = {
        "ts": datetime.now(ET).isoformat(),
        "symbol": symbol,
        "action": action,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence": confidence,
        "reasoning": reasoning[:500] if reasoning else "",
        "executed": executed,
        "order_id": order_id,
    }

    try:
        result = client.table("trades").insert(row).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        logger.error(f"Supabase log_trade failed: {e}")

    return None


def update_trade_outcome(
    order_id: str,
    exit_price: float,
    exit_reason: str,
    pnl_dollars: float,
    pnl_percent: float,
) -> None:
    """Update an existing trade row with its outcome."""
    client = _get_client()
    if client is None:
        return

    try:
        client.table("trades").update({
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl_dollars": pnl_dollars,
            "pnl_percent": pnl_percent,
        }).eq("order_id", order_id).execute()
    except Exception as e:
        logger.error(f"Supabase update_trade_outcome failed: {e}")


def write_heartbeat(is_running: bool, equity: float, open_positions: list) -> None:
    """Upsert the single agent_status row (id=1)."""
    client = _get_client()
    if client is None:
        return

    try:
        client.table("agent_status").upsert({
            "id": 1,
            "last_heartbeat": datetime.now(ET).isoformat(),
            "is_running": is_running,
            "equity": equity,
            "open_positions": open_positions,
        }).execute()
    except Exception as e:
        logger.error(f"Supabase write_heartbeat failed: {e}")


def get_active_symbols() -> list[str]:
    """Return symbols where is_active=true, ordered by id (insertion order).

    Falls back to empty list — caller should use hardcoded defaults in that case.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        result = client.table("symbols").select("symbol").eq("is_active", True).order("id").execute()
        return [row["symbol"] for row in result.data] if result.data else []
    except Exception as e:
        logger.error(f"Supabase get_active_symbols failed: {e}")
        return []


def add_discovered_candidate(symbol: str, reason: str, score: float, change_pct: float) -> None:
    """Write a discovery candidate as is_active=false for human review.

    Uses upsert so re-discovering the same symbol only updates the notes.
    """
    client = _get_client()
    if client is None:
        return

    try:
        client.table("symbols").upsert({
            "symbol": symbol,
            "is_active": False,
            "added_by": "discovery",
            "added_at": datetime.now(ET).isoformat(),
            "notes": f"{reason} | score={score:.1f} | change={change_pct:+.1f}%",
        }, on_conflict="symbol").execute()
    except Exception as e:
        logger.error(f"Supabase add_discovered_candidate failed for {symbol}: {e}")


def update_symbol_performance(symbol: str, pnl_dollars: float, won: bool) -> None:
    """Increment trade count and P&L for a symbol after a trade closes."""
    client = _get_client()
    if client is None:
        return

    try:
        result = client.table("symbols").select("total_trades,winning_trades,total_pnl").eq("symbol", symbol).single().execute()
        if not result.data:
            return
        row = result.data
        client.table("symbols").update({
            "total_trades": row["total_trades"] + 1,
            "winning_trades": row["winning_trades"] + (1 if won else 0),
            "total_pnl": float(row["total_pnl"] or 0) + pnl_dollars,
        }).eq("symbol", symbol).execute()
    except Exception as e:
        logger.error(f"Supabase update_symbol_performance failed for {symbol}: {e}")


def cleanup_old_trades(days: int = 30) -> int:
    """Delete trades older than `days` days. Returns count deleted."""
    client = _get_client()
    if client is None:
        return 0

    try:
        from datetime import timedelta
        cutoff = (datetime.now(ET) - timedelta(days=days)).isoformat()
        result = client.table("trades").delete().lt("ts", cutoff).execute()
        deleted = len(result.data) if result.data else 0
        logger.info(f"Supabase cleanup: deleted {deleted} rows older than {days} days")
        return deleted
    except Exception as e:
        logger.error(f"Supabase cleanup_old_trades failed: {e}")
        return 0
