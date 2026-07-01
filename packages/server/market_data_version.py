"""EOD publish metadata — clients poll to invalidate local intraday patches."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))
_ROW_ID = 1


def ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            eod_trade_date TEXT,
            published_at TEXT,
            bars_reconciled INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO market_data_version (id, status) VALUES (?, 'pending')",
        (_ROW_ID,),
    )


def _read_row(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_table(conn)
    row = conn.execute(
        "SELECT eod_trade_date, published_at, bars_reconciled, status FROM market_data_version WHERE id = ?",
        (_ROW_ID,),
    ).fetchone()
    if not row:
        return {
            "eod_trade_date": None,
            "published_at": None,
            "bars_reconciled": 0,
            "status": "pending",
        }
    return {
        "eod_trade_date": row[0],
        "published_at": row[1],
        "bars_reconciled": int(row[2] or 0),
        "status": row[3] or "pending",
    }


def get_version(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        return {
            "eod_trade_date": None,
            "published_at": None,
            "bars_reconciled": 0,
            "status": "pending",
        }
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        return _read_row(conn)
    finally:
        conn.close()


def record_data_refresh(
    db_path: Path,
    *,
    bars: int = 0,
    status: str = "complete",
) -> dict[str, Any]:
    """
    Bump published_at after OHLCV / screener refresh (including intraday).
    Clients compare published_at to invalidate local intraday patch overlays.
    """
    published_at = datetime.now(IST).isoformat()
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        ensure_table(conn)
        row = _read_row(conn)
        trade = row.get("eod_trade_date") or ist_today()
        reconciled = int(row.get("bars_reconciled") or 0)
        if bars > 0:
            reconciled = max(reconciled, int(bars))
        conn.execute(
            """
            UPDATE market_data_version
            SET eod_trade_date = COALESCE(eod_trade_date, ?),
                published_at = ?,
                bars_reconciled = ?,
                status = ?
            WHERE id = ?
            """,
            (trade, published_at, reconciled, status, _ROW_ID),
        )
        conn.commit()
        return _read_row(conn)
    finally:
        conn.close()


def record_eod_publish(
    db_path: Path,
    *,
    bars: int,
    trade_date: Optional[str] = None,
    status: str = "complete",
) -> dict[str, Any]:
    trade = (trade_date or ist_today()).strip()[:10]
    published_at = datetime.now(IST).isoformat()
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        ensure_table(conn)
        conn.execute(
            """
            UPDATE market_data_version
            SET eod_trade_date = ?, published_at = ?, bars_reconciled = ?, status = ?
            WHERE id = ?
            """,
            (trade, published_at, int(bars or 0), status, _ROW_ID),
        )
        conn.commit()
        return _read_row(conn)
    finally:
        conn.close()


def mark_eod_failed(db_path: Path, *, error: str = "") -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        ensure_table(conn)
        conn.execute(
            """
            UPDATE market_data_version
            SET status = 'failed', published_at = ?
            WHERE id = ?
            """,
            (datetime.now(IST).isoformat(), _ROW_ID),
        )
        conn.commit()
        return _read_row(conn)
    finally:
        conn.close()
