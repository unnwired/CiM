"""
Full-universe NSE live price refresh for screener.

During an active NSE session (before 16:00 IST), preserves NSE lastPrice/pChange
and does not overwrite with stale two-bar historical %.
"""

from __future__ import annotations

import random
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import requests

from server import market_cap_live
from server.admin_job_control import JobCancelled, raise_if_cancelled, sleep_interruptible

IST = ZoneInfo("Asia/Kolkata")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

BULK_INDICES = ["NIFTY TOTAL MARKET", "SECURITIES IN F&O"]
WORKERS = 5
BATCH_SIZE = 15
RATE_DELAY = 1.5
MAX_CONSEC_FAILURES = 10
PAUSE_ON_BLOCK = 60
MAX_FAILURE_RATE = 0.30
RETRY_PASS_DELAY = 2.0

SQL_DAILY_CHANGE = """
UPDATE screener SET change_percent = ROUND(
    (
        (SELECT Close FROM historical_data h1 WHERE h1.Symbol = screener.symbol ORDER BY h1.Date DESC LIMIT 1)
        - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = screener.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
    )
    / (SELECT Close FROM historical_data h3 WHERE h3.Symbol = screener.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1)
    * 100, 2)
WHERE EXISTS (SELECT 1 FROM historical_data WHERE Symbol = screener.symbol)
"""

SQL_MONTHLY_CHANGE = """
UPDATE screener SET change_percent_monthly = ROUND(
    (
        (SELECT Close FROM historical_data h1 WHERE h1.Symbol = screener.symbol ORDER BY h1.Date DESC LIMIT 1)
        - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = screener.symbol
           AND SUBSTR(h2.Date,1,7) < SUBSTR((SELECT MAX(Date) FROM historical_data h3 WHERE h3.Symbol = screener.symbol),1,7)
           ORDER BY h2.Date DESC LIMIT 1)
    )
    / (SELECT Close FROM historical_data h4 WHERE h4.Symbol = screener.symbol
       AND SUBSTR(h4.Date,1,7) < SUBSTR((SELECT MAX(Date) FROM historical_data h5 WHERE h5.Symbol = screener.symbol),1,7)
       ORDER BY h4.Date DESC LIMIT 1)
    * 100, 2)
WHERE EXISTS (SELECT 1 FROM historical_data WHERE Symbol = screener.symbol)
"""


def _now_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _session_intraday_active() -> bool:
    try:
        from server import movers_data as md

        return bool(md._session_day_intraday_active())
    except Exception:
        return False


def should_skip_live_nse_quote_refresh(*, bhav_screener_written: int = 0) -> tuple[bool, str]:
    """
    After NSE close, bhavcopy / EOD bars already set screener price and 1D%.
    Skip thousands of quote-equity calls that trigger WAF blocks.
    """
    if _session_intraday_active():
        return False, ""
    if bhav_screener_written > 0:
        return (
            True,
            f"Post-close — bhavcopy updated {bhav_screener_written} symbol(s); "
            "skipping NSE live quote refresh.",
        )
    return (
        True,
        "Post-close — skipping NSE live quote refresh (EOD bhavcopy / bars are source of truth).",
    )


def ensure_screener_price_columns(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for col, typ in (("previous_close", "REAL"), ("price_updated_at", "TEXT")):
        try:
            cur.execute(f"ALTER TABLE screener ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def recalculate_screener_change_from_bars(
    conn: sqlite3.Connection,
    *,
    include_monthly: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Recompute screener change % from last two EOD bars (post-close / non-session only)."""
    if not force and _session_intraday_active():
        try:
            from server.product_config import yahoo_primary_pipeline

            if not yahoo_primary_pipeline():
                return {"skipped": True, "reason": "live_session"}
        except Exception:
            return {"skipped": True, "reason": "live_session"}
    cur = conn.cursor()
    cur.execute(SQL_DAILY_CHANGE)
    daily = cur.rowcount
    monthly = 0
    if include_monthly:
        cur.execute(SQL_MONTHLY_CHANGE)
        monthly = cur.rowcount
    conn.commit()
    return {"skipped": False, "daily": daily, "monthly": monthly}


def _make_session() -> requests.Session:
    raise_if_cancelled()
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com", timeout=15)
    sleep_interruptible(2)
    s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
    sleep_interruptible(2)
    return s


def _refresh_session(s: requests.Session, *, cancel_check: Optional[Callable[[], bool]] = None) -> bool:
    try:
        s.get("https://www.nseindia.com", timeout=15)
        sleep_interruptible(2, cancel_check=cancel_check)
        s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
        sleep_interruptible(2, cancel_check=cancel_check)
        return True
    except JobCancelled:
        raise
    except Exception:
        return False


def _fetch_bulk(s: requests.Session, index_name: str) -> tuple[list, str]:
    encoded = index_name.replace(" ", "%20").replace("&", "%26")
    url = f"https://www.nseindia.com/api/equity-stockIndices?index={encoded}"
    try:
        r = s.get(url, timeout=20)
        if r.status_code == 200:
            return r.json().get("data", []), "ok"
        if r.status_code in (401, 403):
            return [], "blocked"
    except Exception:
        pass
    return [], "failed"


def _quote_row_from_equity(data: dict, symbol: str) -> Optional[dict[str, Any]]:
    pi = data.get("priceInfo") or {}
    meta = data.get("metadata") or {}
    price = pi.get("lastPrice")
    chg = pi.get("pChange")
    if price is None and chg is None:
        return None
    row: dict[str, Any] = {
        "symbol": symbol,
        "price": price,
        "change_percent": chg,
        "change_percent_monthly": pi.get("perChange30d") or pi.get("pChange30d"),
        "pe": meta.get("pdSymbolPe"),
        "previous_close": pi.get("previousClose"),
        "price_updated_at": _now_ist_str(),
    }
    issued = market_cap_live.nse_issued_from_quote(data)
    if issued is not None:
        row["issued_shares"] = issued
    return row


def _fetch_single(s: requests.Session, symbol: str) -> tuple[Optional[dict], str]:
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    for delay in (1, 3, 10):
        try:
            r = s.get(url, timeout=10)
            if r.status_code in (401, 403):
                return None, "blocked"
            if r.status_code == 200:
                row = _quote_row_from_equity(r.json(), symbol)
                return (row, "ok") if row else (None, "failed")
            time.sleep(delay)
        except requests.exceptions.Timeout:
            time.sleep(delay)
        except Exception:
            time.sleep(delay)
    return None, "failed"


def _write_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    ensure_screener_price_columns(conn)
    cur = conn.cursor()
    written = 0
    stamp = _now_ist_str()
    for row in rows:
        sym = row.get("symbol")
        if not sym:
            continue
        fields, vals = [], []
        for col in (
            "price",
            "change_percent",
            "change_percent_monthly",
            "issued_shares",
            "pe",
            "previous_close",
        ):
            v = row.get(col)
            if v is None:
                continue
            try:
                fields.append(f"{col} = ?")
                if col == "issued_shares":
                    vals.append(int(v))
                else:
                    vals.append(round(float(v), 2))
            except (TypeError, ValueError):
                continue
        fields.append("price_updated_at = ?")
        vals.append(str(row.get("price_updated_at") or stamp))
        if not fields:
            continue
        sql = f"UPDATE screener SET {', '.join(fields)} WHERE symbol = ?"
        vals.append(sym)
        try:
            cur.execute(sql, vals)
            if cur.rowcount:
                written += 1
        except Exception:
            continue
    conn.commit()
    return written


def _fetch_symbol_batches(
    conn: sqlite3.Connection,
    session: requests.Session,
    symbols: list[str],
    *,
    message_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    total_hint: int = 0,
    bulk_offset: int = 0,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> tuple[int, int, set[str]]:
    updated = 0
    failed = 0
    failed_syms: set[str] = set()
    consec_failures = 0
    batch_rows: list[dict] = []

    def _flush():
        nonlocal batch_rows
        if not batch_rows:
            return
        _write_rows(conn, batch_rows)
        batch_rows = []

    for batch_start in range(0, len(symbols), BATCH_SIZE):
        if cancel_check and cancel_check():
            raise JobCancelled()
        processed = updated + failed
        if processed > 50 and failed / processed > MAX_FAILURE_RATE:
            if message_callback:
                message_callback("WARN: Failure rate high — pausing before retry pass.")
            break

        batch = symbols[batch_start : batch_start + BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(_fetch_single, session, sym): sym for sym in batch}
            for future in as_completed(futures):
                sym = futures[future]
                result, status = future.result()
                if status == "blocked":
                    if message_callback:
                        message_callback(f"WARN: NSE block detected. Pausing {PAUSE_ON_BLOCK}s...")
                    sleep_interruptible(PAUSE_ON_BLOCK, cancel_check=cancel_check)
                    _refresh_session(session, cancel_check=cancel_check)
                    failed += 1
                    failed_syms.add(sym)
                    consec_failures += 1
                elif result:
                    batch_rows.append(result)
                    updated += 1
                    consec_failures = 0
                else:
                    failed += 1
                    failed_syms.add(sym)
                    consec_failures += 1

                if consec_failures >= MAX_CONSEC_FAILURES:
                    if message_callback:
                        message_callback(
                            f"WARN: {MAX_CONSEC_FAILURES} consecutive failures. Pausing {PAUSE_ON_BLOCK}s..."
                        )
                    sleep_interruptible(
                        random.uniform(PAUSE_ON_BLOCK, PAUSE_ON_BLOCK + 15),
                        cancel_check=cancel_check,
                    )
                    _refresh_session(session, cancel_check=cancel_check)
                    consec_failures = 0

        _flush()
        done = bulk_offset + updated + failed
        if progress_callback and total_hint:
            progress_callback(min(done, total_hint), total_hint)
        if message_callback and total_hint:
            message_callback(f"NSE quotes: {done}/{total_hint} symbols processed...")
        sleep_interruptible(random.uniform(0.8, RATE_DELAY), cancel_check=cancel_check)

    return updated, failed, failed_syms


def refresh_universe_nse_prices(
    db_path: str | Path,
    *,
    message_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    """
    Fetch NSE lastPrice + pChange for every screener symbol.
    Returns stats dict with bulk, quote_updated, failed, failed_symbols.
    """
    db_path = Path(db_path)
    session = _make_session()
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_screener_price_columns(conn)
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM screener ORDER BY symbol")
        all_symbols = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
    finally:
        conn.close()

    total = len(all_symbols)
    if message_callback:
        message_callback(f"Refreshing NSE live quotes for {total} symbols...")

    bulk_data: dict[str, dict] = {}
    for index_name in BULK_INDICES:
        if cancel_check and cancel_check():
            raise JobCancelled()
        items, status = _fetch_bulk(session, index_name)
        if status == "blocked":
            if message_callback:
                message_callback(f"NSE block on bulk fetch. Pausing {PAUSE_ON_BLOCK}s...")
            sleep_interruptible(PAUSE_ON_BLOCK, cancel_check=cancel_check)
            _refresh_session(session, cancel_check=cancel_check)
            items, status = _fetch_bulk(session, index_name)

        for item in items:
            sym = str(item.get("symbol", "") or "").strip().upper()
            if not sym or sym in bulk_data:
                continue
            bulk_data[sym] = {
                "symbol": sym,
                "price": item.get("lastPrice"),
                "change_percent": item.get("pChange"),
                "change_percent_monthly": item.get("perChange30d"),
                "previous_close": item.get("previousClose"),
                "price_updated_at": _now_ist_str(),
            }
        sleep_interruptible(random.uniform(0.8, 1.5), cancel_check=cancel_check)

    bulk_written = 0
    if bulk_data:
        conn = sqlite3.connect(str(db_path))
        try:
            bulk_written = _write_rows(conn, list(bulk_data.values()))
        finally:
            conn.close()

    if progress_callback:
        progress_callback(bulk_written, total)

    remaining = [s for s in all_symbols if s not in bulk_data]
    if message_callback:
        message_callback(
            f"Bulk: {bulk_written} symbols. Fetching remaining {len(remaining)} individually..."
        )

    conn = sqlite3.connect(str(db_path))
    try:
        updated, failed, failed_syms = _fetch_symbol_batches(
            conn,
            session,
            remaining,
            message_callback=message_callback,
            progress_callback=progress_callback,
            total_hint=total,
            bulk_offset=bulk_written,
            cancel_check=cancel_check,
        )

        if failed_syms:
            if message_callback:
                message_callback(f"Retry pass for {len(failed_syms)} failed symbols...")
            sleep_interruptible(RETRY_PASS_DELAY, cancel_check=cancel_check)
            retry_list = sorted(failed_syms)
            r_up, r_fail, r_failed = _fetch_symbol_batches(
                conn,
                session,
                retry_list,
                message_callback=message_callback,
                progress_callback=progress_callback,
                total_hint=total,
                bulk_offset=bulk_written + updated,
                cancel_check=cancel_check,
            )
            updated += r_up
            failed = len(r_failed)
            failed_syms = r_failed
    finally:
        conn.close()

    quote_updated = bulk_written + updated
    return {
        "total": total,
        "bulk": bulk_written,
        "quote_updated": quote_updated,
        "failed": failed,
        "failed_symbols": sorted(failed_syms),
    }


def refresh_screener_from_upstox_quotes(
    db_path: Path | str,
    *,
    symbols: Optional[list[str]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
    batch_size: int = 400,
) -> dict[str, Any]:
    """
    Write screener price / 1D% from Upstox OHLC quotes.
    Falls back to empty result when Upstox is disabled (caller keeps bar sync / bhavcopy).
    """
    try:
        from server import upstox_client, upstox_config
    except Exception as e:
        return {"skipped": True, "reason": f"import:{e}", "quote_updated": 0}

    if not upstox_config.market_data_enabled():
        return {"skipped": True, "reason": "upstox_disabled", "quote_updated": 0}

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    try:
        ensure_screener_price_columns(conn)
        cur = conn.cursor()
        if symbols:
            wanted = [str(s).strip().upper() for s in symbols if str(s).strip()]
            all_symbols = wanted
        else:
            cur.execute("SELECT symbol FROM screener WHERE symbol IS NOT NULL AND TRIM(symbol) != ''")
            all_symbols = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
        if not all_symbols:
            return {"skipped": True, "reason": "no_symbols", "quote_updated": 0}

        if message_callback:
            message_callback(f"Refreshing screener 1D% from Upstox quotes ({len(all_symbols)} symbols)...")

        written = 0
        failed = 0
        last_err = None
        for i in range(0, len(all_symbols), max(1, batch_size)):
            chunk = all_symbols[i : i + batch_size]
            entries, err = upstox_client.fetch_quotes(chunk)
            if err:
                last_err = err
            by_sym = {str(e.get("symbol") or "").upper(): e for e in entries if e}
            rows = []
            for sym in chunk:
                ent = by_sym.get(sym)
                if not ent:
                    failed += 1
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "price": ent.get("price"),
                        "change_percent": ent.get("change_pct"),
                        "previous_close": ent.get("previous_close"),
                        "price_updated_at": _now_ist_str(),
                    }
                )
            written += _write_rows(conn, rows)
            if message_callback and (i // batch_size) % 5 == 0:
                message_callback(f"Upstox screener quotes: {min(i + batch_size, len(all_symbols))}/{len(all_symbols)}")
    finally:
        conn.close()

    return {
        "skipped": False,
        "source": "upstox",
        "total": len(all_symbols),
        "quote_updated": written,
        "failed": failed,
        "last_error": last_err,
    }

