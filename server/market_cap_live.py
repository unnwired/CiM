"""
Option A — live market cap = NSE issued_shares × displayed price.

issued_shares: refreshed via admin job (NSE quote-equity), typically weekly.
Display price: last close from historical_data (via _apply_live_screener_ohlc).
"""

from __future__ import annotations

import json
import sqlite3
import time as time_module
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

# SQL expression for filters / sorts when issued_shares + price exist.
EFFECTIVE_MCAP_SQL = """
CASE
  WHEN issued_shares IS NOT NULL AND price IS NOT NULL AND price > 0
  THEN CAST(issued_shares AS REAL) * price
  ELSE market_cap
END
""".strip()

PILOT_ISSUED_FILE = "mcap_pilot_issued.json"


def ensure_issued_shares_column(db_path: Path) -> None:
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(screener)")
        cols = {r[1] for r in cur.fetchall()}
        if "issued_shares" not in cols:
            cur.execute("ALTER TABLE screener ADD COLUMN issued_shares INTEGER")
        conn.commit()
    finally:
        conn.close()


def seed_issued_from_pilot_json(db_path: Path, data_dir: Path) -> int:
    """One-time: copy pilot JSON into DB where issued_shares is still NULL."""
    p = data_dir / PILOT_ISSUED_FILE
    if not p.is_file():
        return 0
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(raw, dict):
        return 0
    conn = sqlite3.connect(str(db_path))
    n = 0
    try:
        cur = conn.cursor()
        for sym, val in raw.items():
            if val is None:
                continue
            s = str(sym).strip().upper()
            try:
                shares = int(val)
            except (TypeError, ValueError):
                continue
            cur.execute(
                """
                UPDATE screener SET issued_shares = ?
                WHERE UPPER(symbol) = ? AND issued_shares IS NULL
                """,
                (shares, s),
            )
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n


def nse_issued_from_quote(quote: dict) -> Optional[int]:
    if not isinstance(quote, dict):
        return None
    sec = quote.get("securityInfo") or {}
    raw = sec.get("issuedSize")
    if raw is None:
        return None
    try:
        v = int(float(raw))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def apply_live_market_cap(df: pd.DataFrame, conn) -> None:
    """
    After live OHLC price refresh: Market Cap = issued_shares × Price.
    Symbols without issued_shares keep stored market_cap.
    """
    if df is None or getattr(df, "empty", False):
        return
    if "Market Cap" not in df.columns or "Price" not in df.columns or "Symbol" not in df.columns:
        return
    try:
        shares_df = pd.read_sql_query(
            "SELECT symbol, issued_shares FROM screener WHERE issued_shares IS NOT NULL",
            conn,
        )
    except Exception:
        return
    if shares_df.empty:
        return
    shares_df["Symbol"] = shares_df["symbol"].astype(str).str.strip().str.upper()
    shares_df["issued_shares"] = pd.to_numeric(shares_df["issued_shares"], errors="coerce")
    m = df[["Symbol"]].merge(
        shares_df[["Symbol", "issued_shares"]], on="Symbol", how="left"
    )
    shares = pd.to_numeric(m["issued_shares"], errors="coerce")
    live_price = pd.to_numeric(df["Price"], errors="coerce")
    mask = shares.notna() & live_price.notna() & (live_price > 0)
    if not mask.any():
        return
    computed = (shares[mask] * live_price[mask]).round(0)
    df.loc[mask, "Market Cap"] = computed


def sync_market_cap_cache(db_path: Path) -> int:
    """Persist issued_shares × screener.price into market_cap for SQL filters/sorts."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE screener
            SET market_cap = CAST(issued_shares AS REAL) * price
            WHERE issued_shares IS NOT NULL
              AND price IS NOT NULL
              AND price > 0
            """
        )
        n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


def run_fetch_issued_shares(
    db_path: Path,
    *,
    set_job: Callable[..., None],
    job_state: dict,
    fail_job: Callable[[str], None],
    invalidate_stock_df: Callable[[], None],
    finish_job: Callable[[str], None],
    pause_on_block: int = 60,
) -> None:
    import random
    import requests
    import sqlite3 as sq
    from concurrent.futures import ThreadPoolExecutor, as_completed

    DB = str(db_path)
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    WORKERS = 5
    BATCH_SIZE = 20
    RATE_DELAY = 1.2
    MAX_CONSEC_FAILURES = 10
    MAX_FAILURE_RATE = 0.30

    def make_session():
        s = requests.Session()
        s.headers.update(HEADERS)
        s.get("https://www.nseindia.com", timeout=15)
        time_module.sleep(2)
        s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
        time_module.sleep(2)
        return s

    def refresh_session(s):
        try:
            s.get("https://www.nseindia.com", timeout=15)
            time_module.sleep(2)
            return True
        except Exception:
            return False

    def fetch_issued(s, symbol):
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        backoff = [1, 3, 8]
        for delay in backoff:
            try:
                r = s.get(url, timeout=12)
                if r.status_code in (401, 403):
                    return None, "blocked"
                if r.status_code == 200:
                    issued = nse_issued_from_quote(r.json())
                    if issued is not None:
                        return {"symbol": symbol, "issued_shares": issued}, "ok"
                    return None, "failed"
                time_module.sleep(delay)
            except requests.exceptions.Timeout:
                time_module.sleep(delay)
            except Exception:
                time_module.sleep(delay)
        return None, "failed"

    def write_batch(rows):
        conn = sq.connect(DB)
        cur = conn.cursor()
        for row in rows:
            sym = row.get("symbol")
            shares = row.get("issued_shares")
            if not sym or shares is None:
                continue
            cur.execute(
                "UPDATE screener SET issued_shares = ? WHERE symbol = ?",
                (int(shares), sym),
            )
        conn.commit()
        conn.close()

    try:
        set_job("issued_shares", "Initialising NSE session for share counts…")
        session = make_session()
        conn = sq.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM screener ORDER BY symbol")
        all_symbols = [r[0] for r in cur.fetchall()]
        conn.close()

        job_state["total"] = len(all_symbols)
        job_state["message"] = (
            f"Fetching NSE issued share count for {len(all_symbols)} symbols "
            "(market cap = shares × price on screen)…"
        )

        updated = 0
        failed = 0
        consec_failures = 0
        batch_rows = []

        for batch_start in range(0, len(all_symbols), BATCH_SIZE):
            processed = updated + failed
            if processed > 50 and failed / processed > MAX_FAILURE_RATE:
                job_state["message"] = "Failure rate too high. Stopping share-count refresh."
                break

            batch = all_symbols[batch_start : batch_start + BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                futures = {
                    executor.submit(fetch_issued, session, sym): sym for sym in batch
                }
                for future in as_completed(futures):
                    result, status = future.result()
                    if status == "blocked":
                        job_state["message"] = f"NSE block. Pausing {pause_on_block}s…"
                        time_module.sleep(pause_on_block)
                        refresh_session(session)
                        failed += 1
                        consec_failures += 1
                    elif result:
                        batch_rows.append(result)
                        updated += 1
                        consec_failures = 0
                    else:
                        failed += 1
                        consec_failures += 1

                    if consec_failures >= MAX_CONSEC_FAILURES:
                        time_module.sleep(random.uniform(pause_on_block, pause_on_block + 10))
                        refresh_session(session)
                        consec_failures = 0

            if batch_rows:
                write_batch(batch_rows)
                batch_rows = []

            done = updated + failed
            job_state["progress"] = min(done, job_state["total"])
            job_state["message"] = f"Share counts: {updated} updated, {failed} failed ({done}/{len(all_symbols)})"
            time_module.sleep(random.uniform(0.6, RATE_DELAY))

        job_state["message"] = "Syncing market_cap cache (shares × stored price)…"
        cached = sync_market_cap_cache(db_path)
        invalidate_stock_df()
        finish_job(
            f"Share counts done — {updated} updated, {failed} failed. "
            f"Cached market_cap refreshed for {cached} rows."
        )
    except Exception as e:
        fail_job(str(e))
