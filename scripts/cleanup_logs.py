"""
Weekly cleanup: removes JSONL log files older than 30 days and old Supabase rows.

Run via crontab:
  0 4 * * 0  /path/to/venv/bin/python /path/to/projectin/scripts/cleanup_logs.py
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

LOGS_DIR = Path(__file__).parent.parent / "logs" / "trades"
KEEP_DAYS = 30


def cleanup_local_jsonl():
    if not LOGS_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    deleted = 0
    for f in LOGS_DIR.glob("trades_*.jsonl"):
        try:
            date_str = f.stem.replace("trades_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                f.unlink()
                deleted += 1
        except ValueError:
            continue
    print(f"Local JSONL cleanup: deleted {deleted} files older than {KEEP_DAYS} days")


def cleanup_supabase():
    try:
        from agent.core.supabase_logger import cleanup_old_trades
        deleted = cleanup_old_trades(days=KEEP_DAYS)
        print(f"Supabase cleanup: deleted {deleted} rows")
    except Exception as e:
        print(f"Supabase cleanup skipped: {e}")


if __name__ == "__main__":
    print(f"Running log cleanup at {datetime.now().isoformat()}")
    cleanup_local_jsonl()
    cleanup_supabase()
    print("Done.")
