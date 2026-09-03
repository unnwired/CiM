"""Read Earnings+ qualified flags from earnings_plus_cache (shared by Market Map, etc.)."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterable


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").strip().upper()


def _payload_latest_date_key(payload_json: str | None) -> str:
    if not payload_json:
        return ""
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    periods = payload.get("periods") or []
    if not periods or not isinstance(periods[-1], dict):
        return ""
    return str(periods[-1].get("date_key") or "").strip()


def _read_local_latest_period_keys(conn: sqlite3.Connection, symbols: list[str]) -> dict[str, str]:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    try:
        rows = conn.execute(
            f"""
            SELECT symbol, basis, payload_json
            FROM screener_quarterly
            WHERE symbol IN ({placeholders})
            """,
            symbols,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    by_sym: dict[str, dict[str, str]] = {}
    for symbol, basis, payload_json in rows:
        sym = _normalize_symbol(symbol)
        date_key = _payload_latest_date_key(payload_json)
        if not sym or not date_key:
            continue
        bucket = by_sym.setdefault(sym, {})
        basis_key = str(basis or "").strip().lower()
        if basis_key in ("consolidated", "standalone"):
            bucket[basis_key] = date_key
    def _parse_ymd(value: str):
        raw = str(value or "").strip()[:10]
        if len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
            return None
        try:
            y, m, d = int(raw[0:4]), int(raw[5:7]), int(raw[8:10])
            from datetime import date
            return date(y, m, d)
        except ValueError:
            return None

    out: dict[str, str] = {}
    for sym, bases in by_sym.items():
        consol = bases.get("consolidated") or ""
        stand = bases.get("standalone") or ""
        if consol and stand:
            c_day = _parse_ymd(consol)
            s_day = _parse_ymd(stand)
            if c_day and s_day:
                key = stand if s_day >= c_day else consol
            else:
                key = consol or stand
        else:
            key = consol or stand
        if key:
            out[sym] = key
    return out


def _entry_is_stale(decision: str | None, cached_period_key: str | None, local_period_key: str | None) -> bool:
    local = str(local_period_key or "").strip()
    cached = str(cached_period_key or "").strip()
    if local and cached and local != cached:
        return True
    if local and not cached:
        return True
    decision_l = str(decision or "").strip().lower()
    if decision_l in ("qualified", "not_qualified"):
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
    """Symbols with non-stale decision == qualified (matches latest local Screener quarter)."""
    normalized = [
        s for s in dict.fromkeys(_normalize_symbol(x) for x in symbols) if s
    ]
    if not normalized:
        return set()
    _ensure_table(conn)
    placeholders = ",".join("?" * len(normalized))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT symbol, decision, latest_period_date_key
        FROM earnings_plus_cache
        WHERE symbol IN ({placeholders})
        """,
        normalized,
    )
    local_keys = _read_local_latest_period_keys(conn, normalized)
    out: set[str] = set()
    for sym, decision, period_key in cur.fetchall():
        nsym = _normalize_symbol(sym)
        if _entry_is_stale(decision, period_key, local_keys.get(nsym)):
            continue
        if str(decision or "").strip().lower() == "qualified":
            out.add(nsym)
    return out


def attach_earnings_plus_flags(conn: sqlite3.Connection, rows: list[dict]) -> None:
    qualified = read_qualified_symbols(conn, [r.get("symbol") for r in rows])
    for row in rows:
        sym = _normalize_symbol(row.get("symbol"))
        row["earnings_plus"] = sym in qualified
