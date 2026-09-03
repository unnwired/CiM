"""
NSE historical index OHLC via /api/historicalOR/indicesHistory.

Used when Yahoo Finance has no series (e.g. ^CNXINDDEF / NIFTY INDIA DEFENCE).

Important: NSE returns only ~60-70 trading days per request regardless of the
requested date span. Callers must slide short calendar windows (see
NSE_CHUNK_CALENDAR_DAYS) and merge results — a single 360-day request does NOT
return the full range.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Optional
from urllib.parse import quote

import requests as req

NSE_HISTORICAL_REFERER = "https://www.nseindia.com/reports-indices-historical-index-data"
NSE_HISTORICAL_URL = "https://www.nseindia.com/api/historicalOR/indicesHistory"
# NSE caps each indicesHistory response at ~70 trading days; ~85 calendar days is safe.
NSE_CHUNK_CALENDAR_DAYS = 85
MAX_RANGE_DAYS = NSE_CHUNK_CALENDAR_DAYS

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HISTORICAL_REFERER,
}


def make_nse_history_session() -> req.Session:
    s = req.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=15)
        time.sleep(1.0)
        s.get(NSE_HISTORICAL_REFERER, timeout=15)
        time.sleep(0.8)
    except Exception:
        pass
    return s


def _parse_nse_eod_date(raw: str) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(text.upper(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return None


def normalize_nse_history_row(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Map NSE indicesHistory row to index_history columns."""
    date_str = _parse_nse_eod_date(row.get("EOD_TIMESTAMP") or row.get("HI_TIMESTAMP") or "")
    if not date_str:
        return None
    try:
        o = float(row.get("EOD_OPEN_INDEX_VAL"))
        h = float(row.get("EOD_HIGH_INDEX_VAL"))
        low = float(row.get("EOD_LOW_INDEX_VAL"))
        c = float(row.get("EOD_CLOSE_INDEX_VAL"))
        v = float(row.get("HIT_TRADED_QTY") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "date": date_str,
        "open": round(o, 2),
        "high": round(h, 2),
        "low": round(low, 2),
        "close": round(c, 2),
        "volume": round(v, 2),
    }


def iter_date_chunks(
    start: date,
    end: date,
    *,
    max_days: int = NSE_CHUNK_CALENDAR_DAYS,
) -> Iterator[tuple[date, date]]:
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def find_index_history_gaps(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    min_gap_days: int = 5,
) -> list[tuple[date, date]]:
    """Return (gap_start, gap_end) calendar ranges between stored bars (exclusive)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT SUBSTR(Date, 1, 10) AS d
        FROM index_history
        WHERE Symbol = ?
        ORDER BY d
        """,
        (symbol,),
    )
    dates = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in cursor.fetchall()]
    if len(dates) < 2:
        return []

    gaps: list[tuple[date, date]] = []
    for prev, nxt in zip(dates, dates[1:]):
        delta = (nxt - prev).days
        if delta > min_gap_days:
            gaps.append((prev + timedelta(days=1), nxt - timedelta(days=1)))
    return gaps


def fetch_nse_index_history_range(
    session: req.Session,
    nse_index_name: str,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    if from_date > to_date:
        return []
    q = (
        f"indexType={quote(nse_index_name, safe='')}"
        f"&from={from_date.strftime('%d-%m-%Y')}"
        f"&to={to_date.strftime('%d-%m-%Y')}"
    )
    url = f"{NSE_HISTORICAL_URL}?{q}"
    r = session.get(url, timeout=25)
    if r.status_code != 200:
        raise RuntimeError(f"NSE index history HTTP {r.status_code} for {nse_index_name}")
    payload = r.json()
    if payload.get("error"):
        msg = payload.get("showMessage") or payload.get("message") or "NSE index history error"
        raise RuntimeError(str(msg))
    return list(payload.get("data") or [])


def fetch_nse_index_history(
    nse_index_name: str,
    from_date: date,
    to_date: date,
    *,
    session: Optional[req.Session] = None,
) -> list[dict[str, Any]]:
    own_session = session is None
    s = session or make_nse_history_session()
    rows: list[dict[str, Any]] = []
    try:
        for chunk_start, chunk_end in iter_date_chunks(from_date, to_date):
            rows.extend(fetch_nse_index_history_range(s, nse_index_name, chunk_start, chunk_end))
            time.sleep(0.35)
    finally:
        if own_session:
            s.close()
    return rows


def write_index_history_rows(
    conn: sqlite3.Connection,
    symbol: str,
    rows: list[dict[str, Any]],
) -> int:
    cursor = conn.cursor()
    written = 0
    try:
        from movers_data import _is_nse_session_day as _session_ok
    except Exception:
        try:
            from server.movers_data import _is_nse_session_day as _session_ok
        except Exception:
            _session_ok = lambda d: d.weekday() < 5  # noqa: E731

    for row in rows:
        norm = normalize_nse_history_row(row)
        if not norm:
            continue
        try:
            day = datetime.strptime(str(norm["date"])[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not _session_ok(day):
            continue
        cursor.execute(
            """
            INSERT OR REPLACE INTO index_history
                (Symbol, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                norm["date"],
                norm["open"],
                norm["high"],
                norm["low"],
                norm["close"],
                norm["volume"],
            ),
        )
        written += 1
    if written:
        conn.commit()
    return written


def _resolve_fetch_range(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    history_start: str,
) -> tuple[date, date, bool]:
    """
    Decide [start, end] for NSE fetch.

    Returns (start, end, full_series) where full_series means re-walk from
    history_start (needed when gaps exist or history is sparse).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(SUBSTR(Date, 1, 10)), MAX(SUBSTR(Date, 1, 10)) FROM index_history WHERE Symbol = ?", (symbol,))
    first_date, last_date = cursor.fetchone()
    end = date.today() + timedelta(days=1)
    gaps = find_index_history_gaps(conn, symbol)

    if not last_date or gaps:
        start = datetime.strptime(history_start[:10], "%Y-%m-%d").date()
        return start, end, True

    start = datetime.strptime(str(last_date)[:10], "%Y-%m-%d").date() - timedelta(days=7)
    if first_date:
        first_d = datetime.strptime(str(first_date)[:10], "%Y-%m-%d").date()
        start = max(start, first_d)
    return start, end, False


def scrape_history_from_nse(
    conn: sqlite3.Connection,
    symbol: str,
    nse_index_name: str,
    *,
    history_start: str = "2010-01-01",
    session: Optional[req.Session] = None,
    force_full: bool = False,
) -> int:
    """
    Backfill or extend index_history for one Yahoo-missing symbol from NSE.

    history_start: YYYY-MM-DD when no rows exist yet or when repairing gaps.
    """
    start, end, needs_full = _resolve_fetch_range(conn, symbol, history_start=history_start)
    if force_full:
        start = datetime.strptime(history_start[:10], "%Y-%m-%d").date()
        needs_full = True

    raw = fetch_nse_index_history(nse_index_name, start, end, session=session)
    written = write_index_history_rows(conn, symbol, raw)

    if needs_full and find_index_history_gaps(conn, symbol):
        # One more pass from history_start if gaps remain (API hiccup).
        start = datetime.strptime(history_start[:10], "%Y-%m-%d").date()
        raw_retry = fetch_nse_index_history(nse_index_name, start, end, session=session)
        written += write_index_history_rows(conn, symbol, raw_retry)

    return written
