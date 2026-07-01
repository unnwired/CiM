"""Read Earnings+ qualified flags from earnings_plus_cache (shared by Market Map, etc.)."""

from __future__ import annotations

import sqlite3
from typing import Iterable


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").strip().upper()


def _cache_entry_is_stale(entry: dict | None) -> bool:
    if not entry:
        return True
    decision = str(entry.get("decision") or "").strip().lower()
    if decision in ("qualified", "not_qualified"):
        return False
    return True


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_plus_cache (
            symbol TEXT NOT NULL PRIMARY KEY,
            decision TEXT NOT NULL,
            basis_used TEXT,
            latest_period TEXT,
            latest_period_date_key TEXT,
            previous_period TEXT,
            previous_year_period TEXT,
            note TEXT,
            source_fetched_at TEXT,
            computed_at TEXT NOT NULL,
            refresh_after TEXT NOT NULL,
            last_error TEXT
        )
        """
    )


def read_qualified_symbols(conn: sqlite3.Connection, symbols: Iterable[str]) -> set[str]:
    """Symbols with non-stale decision == qualified."""
    normalized = [
        s for s in dict.fromkeys(_normalize_symbol(x) for x in symbols) if s
    ]
    if not normalized:
        return set()
    _ensure_table(conn)
    placeholders = ",".join("?" * len(normalized))
    cur = conn.cursor()
    cur.execute(
        f"SELECT symbol, decision FROM earnings_plus_cache WHERE symbol IN ({placeholders})",
        normalized,
    )
    out: set[str] = set()
    for sym, decision in cur.fetchall():
        entry = {"symbol": sym, "decision": decision, "is_stale": False}
        entry["is_stale"] = _cache_entry_is_stale(entry)
        if str(decision or "").strip().lower() == "qualified" and not entry["is_stale"]:
            out.add(_normalize_symbol(sym))
    return out


def attach_earnings_plus_flags(conn: sqlite3.Connection, rows: list[dict]) -> None:
    qualified = read_qualified_symbols(conn, [r.get("symbol") for r in rows])
    for row in rows:
        sym = _normalize_symbol(row.get("symbol"))
        row["earnings_plus"] = sym in qualified
