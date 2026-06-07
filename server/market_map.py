"""
Market Map — advance/decline breadth per index and constituent heatmap data.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from nse_constituents import (
    NSE_INDEX_MAP,
    fetch_constituents_for_symbol,
    make_nse_session,
)

IST = ZoneInfo("Asia/Kolkata")

# Canonical catalog (25 indices) — default display order matches product spec.
MARKET_MAP_CATALOG: list[dict[str, str]] = [
    {"symbol": "^NSEI", "name": "Nifty 50"},
    {"symbol": "^NSEBANK", "name": "Nifty Bank"},
    {"symbol": "^NSMIDCP", "name": "Nifty Midcap 100"},
    {"symbol": "^NSEMDCP50", "name": "Nifty Midcap 50"},
    {"symbol": "^CNXSC", "name": "Nifty Smallcap 100"},
    {"symbol": "^CNXIT", "name": "Nifty IT"},
    {"symbol": "^CNXFMCG", "name": "Nifty FMCG"},
    {"symbol": "^CNXPHARMA", "name": "Nifty Pharma"},
    {"symbol": "^CNXAUTO", "name": "Nifty Auto"},
    {"symbol": "^CNXMETAL", "name": "Nifty Metal"},
    {"symbol": "^CNXREALTY", "name": "Nifty Realty"},
    {"symbol": "^CNXENERGY", "name": "Nifty Energy"},
    {"symbol": "^CNXINFRA", "name": "Nifty Infra"},
    {"symbol": "^CNXINDDEF", "name": "Nifty India Defence"},
    {"symbol": "^CNXPSUBANK", "name": "Nifty PSU Bank"},
    {"symbol": "^CNXPSE", "name": "Nifty PSE"},
    {"symbol": "^CNXMNC", "name": "Nifty MNC"},
    {"symbol": "^CNXSERVICE", "name": "Nifty Services Sector"},
    {"symbol": "^CNXMEDIA", "name": "Nifty Media"},
    {"symbol": "^CNXDIVOP", "name": "Nifty Dividend Opportunities 50"},
    {"symbol": "^CNXNXT50", "name": "Nifty Next 50"},
    {"symbol": "^CNX100", "name": "Nifty 100"},
    {"symbol": "^CNX200", "name": "Nifty 200"},
    {"symbol": "^CRSLDX", "name": "Nifty 500"},
    {"symbol": "^CNXSMLCP50", "name": "Nifty Smallcap 50"},
]

_CACHE_TTL_SEC = 300
_cache_lock = threading.Lock()
_summary_cache: dict[str, Any] = {"fetched_at": 0.0, "period": None, "items": []}
_index_cache: dict[str, dict[str, Any]] = {}

_get_db_connection = None
_index_live_day_change_map = None
_index_day_change_pct_single = None


def configure(db_conn_factory, live_map_fn, day_pct_fn) -> None:
    global _get_db_connection, _index_live_day_change_map, _index_day_change_pct_single
    _get_db_connection = db_conn_factory
    _index_live_day_change_map = live_map_fn
    _index_day_change_pct_single = day_pct_fn


def catalog_payload() -> dict[str, Any]:
    return {
        "indices": [{"symbol": e["symbol"], "name": e["name"]} for e in MARKET_MAP_CATALOG],
        "default_order": [e["symbol"] for e in MARKET_MAP_CATALOG],
        "periods": [{"id": "1D", "enabled": True}],
    }


def _summarize_constituents(rows: list[dict[str, Any]]) -> dict[str, Any]:
    with_chg = [r for r in rows if r.get("change_pct") is not None]
    advances = sum(1 for r in with_chg if float(r["change_pct"]) > 0)
    declines = sum(1 for r in with_chg if float(r["change_pct"]) < 0)
    unchanged = sum(1 for r in with_chg if float(r["change_pct"]) == 0)
    total = len(with_chg)
    pct_positive = round(advances / total * 100, 1) if total else None
    return {
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "total": total,
        "pct_positive": pct_positive,
    }


def _index_header(symbol: str, conn: sqlite3.Connection) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        "SELECT name, last_price, change_pct FROM indices WHERE symbol = ?",
        (symbol,),
    )
    row = cur.fetchone()
    name = next((e["name"] for e in MARKET_MAP_CATALOG if e["symbol"] == symbol), symbol)
    last_price = None
    change_pct = None
    if row:
        name = row[0] or name
        last_price = round(float(row[1]), 2) if row[1] is not None else None
        change_pct = round(float(row[2]), 2) if row[2] is not None else None
    if _index_live_day_change_map and _index_day_change_pct_single:
        try:
            lk = _index_live_day_change_map(conn, [symbol]).get(str(symbol).strip())
            if lk is not None:
                change_pct = round(float(lk), 2)
            elif change_pct is None:
                single = _index_day_change_pct_single(symbol, conn)
                if single is not None:
                    change_pct = round(float(single), 2)
        except Exception:
            pass
    return {"name": name, "last_price": last_price, "change_pct": change_pct}


def _load_index_bundle(
    symbol: str,
    period: str,
    *,
    session=None,
) -> dict[str, Any]:
    if period != "1D":
        raise ValueError(f"Unsupported period: {period}")
    nse_name = NSE_INDEX_MAP.get(symbol)
    if not nse_name:
        raise ValueError(f"Unknown index: {symbol}")

    conn = _get_db_connection()
    try:
        header = _index_header(symbol, conn)
        constituents, source, error = fetch_constituents_for_symbol(
            symbol, conn, session=session
        )
        summary = _summarize_constituents(constituents)
        return {
            "symbol": symbol,
            "nse_name": nse_name,
            "period": period,
            "as_of": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "index": header,
            "summary": summary,
            "constituents": constituents,
            "source": source or None,
            "error": error if not constituents else None,
        }
    finally:
        conn.close()


def _cache_get_index(
    symbol: str,
    period: str,
    force: bool = False,
    *,
    session=None,
) -> dict[str, Any]:
    key = f"{symbol}:{period}"
    now = time.time()
    with _cache_lock:
        entry = _index_cache.get(key)
        if not force and entry and (now - entry.get("_ts", 0)) < _CACHE_TTL_SEC:
            return entry["data"]
    data = _load_index_bundle(symbol, period, session=session)
    with _cache_lock:
        _index_cache[key] = {"_ts": now, "data": data}
    return data


def invalidate_cache(symbol: Optional[str] = None) -> None:
    with _cache_lock:
        if symbol is None:
            _index_cache.clear()
            _summary_cache["fetched_at"] = 0.0
            _summary_cache["items"] = []
        else:
            for k in list(_index_cache.keys()):
                if k.startswith(f"{symbol}:"):
                    del _index_cache[k]
            _summary_cache["fetched_at"] = 0.0


def filter_constituents_by_magnitude(
    rows: list[dict[str, Any]],
    magnitude: Optional[float],
) -> list[dict[str, Any]]:
    """+N: gainers with change_pct >= N; −N: losers with change_pct <= −N."""
    if magnitude is None or not math.isfinite(float(magnitude)):
        return rows
    m = float(magnitude)
    if m > 0:
        return [
            r for r in rows
            if r.get("change_pct") is not None and float(r["change_pct"]) >= m
        ]
    if m < 0:
        thr = abs(m)
        return [
            r for r in rows
            if r.get("change_pct") is not None and float(r["change_pct"]) <= -thr
        ]
    return [r for r in rows if r.get("change_pct") is not None]


def sort_constituents_by_pct_desc(rows: list[dict[str, Any]]) -> None:
    """Highest 1D % first → lowest; missing % last; tie-break symbol A–Z."""
    rows.sort(
        key=lambda r: (
            r.get("change_pct") is None,
            -(float(r["change_pct"])) if r.get("change_pct") is not None else 0.0,
            str(r.get("symbol", "")).upper(),
        ),
    )


def get_index_detail(
    symbol: str,
    period: str = "1D",
    layout: str = "equal",
    magnitude: Optional[float] = None,
    sort: str = "major",
    force: bool = False,
) -> dict[str, Any]:
    data = _cache_get_index(symbol, period, force=force)
    rows = list(data.get("constituents") or [])

    rows = filter_constituents_by_magnitude(rows, magnitude)

    if sort == "alpha":
        rows.sort(key=lambda r: str(r.get("symbol", "")).upper())
    elif sort == "alpha_desc":
        rows.sort(key=lambda r: str(r.get("symbol", "")).upper(), reverse=True)
    else:
        sort_constituents_by_pct_desc(rows)

    if _get_db_connection and rows:
        conn = _get_db_connection()
        try:
            from earnings_plus_lookup import attach_earnings_plus_flags

            attach_earnings_plus_flags(conn, rows)
        except Exception:
            for row in rows:
                row.setdefault("earnings_plus", False)
        finally:
            conn.close()
    else:
        for row in rows:
            row.setdefault("earnings_plus", False)

    try:
        from earnings_beat_lookup import attach_earnings_beat_flags

        attach_earnings_beat_flags(rows)
    except Exception:
        for row in rows:
            row.setdefault("earnings_beat", False)

    out = dict(data)
    out["layout"] = layout
    out["sort"] = sort
    out["constituents"] = rows
    return out


def get_summary(period: str = "1D", force: bool = False) -> dict[str, Any]:
    if period != "1D":
        raise ValueError(f"Unsupported period: {period}")

    now = time.time()
    with _cache_lock:
        if (
            not force
            and _summary_cache.get("period") == period
            and (now - float(_summary_cache.get("fetched_at") or 0)) < _CACHE_TTL_SEC
            and _summary_cache.get("items")
        ):
            return {
                "period": period,
                "as_of": _summary_cache.get("as_of"),
                "items": _summary_cache["items"],
                "cached": True,
            }

    items = []
    as_of = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    session = make_nse_session()
    for entry in MARKET_MAP_CATALOG:
        sym = entry["symbol"]
        try:
            bundle = _cache_get_index(sym, period, force=force, session=session)
            items.append({
                "symbol": sym,
                "name": entry["name"],
                "index_change_pct": bundle.get("index", {}).get("change_pct"),
                "last_price": bundle.get("index", {}).get("last_price"),
                "advances": bundle["summary"]["advances"],
                "declines": bundle["summary"]["declines"],
                "unchanged": bundle["summary"]["unchanged"],
                "total": bundle["summary"]["total"],
                "pct_positive": bundle["summary"]["pct_positive"],
                "error": bundle.get("error"),
            })
        except Exception as e:
            items.append({
                "symbol": sym,
                "name": entry["name"],
                "index_change_pct": None,
                "last_price": None,
                "advances": None,
                "declines": None,
                "unchanged": None,
                "total": 0,
                "pct_positive": None,
                "error": str(e),
            })

    with _cache_lock:
        _summary_cache["fetched_at"] = now
        _summary_cache["period"] = period
        _summary_cache["as_of"] = as_of
        _summary_cache["items"] = items

    return {"period": period, "as_of": as_of, "items": items, "cached": False}
