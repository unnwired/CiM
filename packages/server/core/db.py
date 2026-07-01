"""Database connection helpers."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from db_sqlite import connect_sqlite as _connect_sqlite

from server.core.config import DB_PATH

_thread_local = threading.local()


def get_db_connection(*, row_factory: bool = True) -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found: {DB_PATH}")
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = _connect_sqlite(DB_PATH, row_factory=row_factory)
        _thread_local.conn = conn
    return conn


def close_thread_connection() -> None:
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _thread_local.conn = None
