"""
Shared SQLite connection settings for FlowX / NSE Pulse.

WAL + busy_timeout let OHLCV writes coexist with API reads (movers live, charts)
instead of failing immediately with "database is locked".
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "nse_data.db"


def configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    # Set busy_timeout before any pragma that may need to wait on a lock.
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        if mode and str(mode[0]).lower() != "wal":
            conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
    except sqlite3.OperationalError:
        pass


def connect_sqlite(
    db_path: str | Path | None = None,
    *,
    row_factory: bool = False,
    timeout: float = 30.0,
) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path), timeout=timeout, check_same_thread=False)
    if row_factory:
        conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn)
    return conn


def ensure_wal_mode(db_path: str | Path | None = None, *, attempts: int = 5) -> str:
    """Try to switch the DB to WAL when idle (safe to call at startup)."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    last_mode = "unknown"
    for i in range(attempts):
        try:
            conn = sqlite3.connect(str(path), timeout=30.0)
            conn.execute("PRAGMA busy_timeout=30000")
            row = conn.execute("PRAGMA journal_mode").fetchone()
            last_mode = str(row[0]) if row else "unknown"
            if last_mode.lower() != "wal":
                row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
                last_mode = str(row[0]) if row else last_mode
            conn.close()
            return last_mode
        except sqlite3.OperationalError:
            time.sleep(1.0 + i)
    return last_mode
