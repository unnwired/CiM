"""
Official NSE EOD bhavcopy — canonical daily closes for screener list price / 1D%.

Chart OHLC in historical_data comes from Yahoo auto_adjust=True only.
Bhavcopy must not write into historical_data (nominal vs adjusted scale mismatch).
"""

from __future__ import annotations

import csv
import io
import sqlite3
import time
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)

_last_reconcile_metrics: dict = {}


def last_reconcile_metrics() -> dict:
    return dict(_last_reconcile_metrics)


def _cell(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key]).strip()
        spaced = f" {key}"
        if spaced in row and row[spaced] is not None:
            return str(row[spaced]).strip()
    return ""


def _parse_bhav_date(raw: str) -> Optional[str]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _finite_float(raw: str) -> Optional[float]:
    try:
        v = float(str(raw).replace(",", "").strip())
        if v > 0:
            return round(v, 2)
    except (TypeError, ValueError):
        pass
    return None


def fetch_bhavcopy_rows(trade_date: date, *, timeout: int = 45) -> dict[str, dict]:
    """
    Return EQ-series rows keyed by NSE symbol:
    {open, high, low, close, volume, trade_date: YYYY-MM-DD}
    """
    ddmmyyyy = trade_date.strftime("%d%m%Y")
    url = BHAVCOPY_URL.format(ddmmyyyy=ddmmyyyy)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError):
        return {}

    if text.lstrip().startswith("<!"):
        return {}

    out: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        if _cell(row, "SERIES") != "EQ":
            continue
        sym = _cell(row, "SYMBOL").upper()
        if not sym:
            continue
        ds = _parse_bhav_date(_cell(row, "DATE1"))
        if not ds:
            ds = trade_date.strftime("%Y-%m-%d")
        o = _finite_float(_cell(row, "OPEN_PRICE"))
        h = _finite_float(_cell(row, "HIGH_PRICE"))
        l = _finite_float(_cell(row, "LOW_PRICE"))
        c = _finite_float(_cell(row, "CLOSE_PRICE"))
        if c is None:
            continue
        vol_raw = _cell(row, "TTL_TRD_QNTY") or _cell(row, "TOTTRDQTY")
        try:
            vol = round(float(vol_raw.replace(",", "")), 2) if vol_raw else 0.0
        except (TypeError, ValueError):
            vol = 0.0
        out[sym] = {
            "open": o or c,
            "high": h or c,
            "low": l or c,
            "close": c,
            "volume": vol,
            "trade_date": ds,
        }
    return out


def upsert_bhav_bar(
    conn: sqlite3.Connection,
    symbol: str,
    trade_date: str,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float,
) -> None:
    """
    Legacy: write bhavcopy OHLC into historical_data.

    Deprecated — do not use for chart data. Kept for tests/migration reference only.
    """
    day = trade_date[:10]
    date_str = f"{day} 00:00:00+05:30"
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM historical_data WHERE Symbol=? AND substr(Date,1,10)=?",
        (symbol, day),
    )
    cur.execute(
        """
        INSERT INTO historical_data
          (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (symbol, date_str, o, h, l, c, c, v, None),
    )


def sync_screener_from_bhavcopy(
    conn: sqlite3.Connection,
    symbols: Iterable[str],
    *,
    lookback_calendar_days: int = 14,
    log_fn: Optional[Callable[[str], None]] = None,
) -> int:
    """
    Update screener.price and screener.change_percent from NSE bhavcopy closes only.
    Does not modify historical_data.
    Returns number of symbols updated.
    """
    sym_set = {str(s).strip().upper() for s in symbols if str(s).strip()}
    if not sym_set:
        return 0

    closes_by_sym: dict[str, dict[str, float]] = {s: {} for s in sym_set}
    bhav_days_fetched = 0
    today = date.today()

    for offset in range(0, lookback_calendar_days):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        rows = fetch_bhavcopy_rows(d)
        if not rows:
            time.sleep(0.35)
            continue
        bhav_days_fetched += 1
        for sym in sym_set:
            bar = rows.get(sym)
            if not bar:
                continue
            day = str(bar["trade_date"])[:10]
            closes_by_sym[sym][day] = float(bar["close"])
        time.sleep(0.35)

    cur = conn.cursor()
    updated = 0
    for sym, by_day in closes_by_sym.items():
        if not by_day:
            continue
        days_sorted = sorted(by_day.keys())
        latest_day = days_sorted[-1]
        latest_close = by_day[latest_day]
        prev_close = None
        if len(days_sorted) >= 2:
            prev_close = by_day[days_sorted[-2]]
        if prev_close is None or prev_close <= 0:
            cur.execute(
                """
                SELECT Close FROM historical_data
                WHERE Symbol = ? AND substr(Date, 1, 10) < ?
                ORDER BY Date DESC LIMIT 1
                """,
                (sym, latest_day),
            )
            row = cur.fetchone()
            if row and row[0] and float(row[0]) > 0:
                prev_close = float(row[0])

        if prev_close is None or prev_close <= 0:
            cur.execute(
                "UPDATE screener SET price = ? WHERE symbol = ?",
                (round(latest_close, 2), sym),
            )
        else:
            chg = round((latest_close - prev_close) / prev_close * 100.0, 2)
            cur.execute(
                """
                UPDATE screener SET price = ?, change_percent = ?
                WHERE symbol = ?
                """,
                (round(latest_close, 2), chg, sym),
            )
        updated += 1

    if updated:
        conn.commit()

    global _last_reconcile_metrics
    _last_reconcile_metrics = {
        "screener_updated": updated,
        "bhav_days_fetched": bhav_days_fetched,
        "historical_data_writes": 0,
    }

    if log_fn and updated:
        log_fn(
            f"[bhavcopy] screener overlay updated {updated} symbol(s); "
            f"0 historical_data writes ({bhav_days_fetched} bhav day(s) fetched)"
        )
    return updated


def reconcile_recent_eod_from_nse(
    conn: sqlite3.Connection,
    symbols: Iterable[str],
    *,
    lookback_calendar_days: int = 14,
    log_fn: Optional[Callable[[str], None]] = None,
) -> int:
    """
    Refresh screener price / 1D% from NSE bhavcopy for the given symbols.
    Does not write to historical_data (charts stay on Yahoo-adjusted OHLC).
    Returns number of screener symbols updated.
    """
    n = sync_screener_from_bhavcopy(
        conn,
        symbols,
        lookback_calendar_days=lookback_calendar_days,
        log_fn=log_fn,
    )
    if log_fn and n == 0:
        log_fn("[bhavcopy] screener overlay: 0 symbols updated (offline or no bhav rows)")
    return n
