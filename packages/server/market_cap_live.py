"""
Live market cap = issued_shares × displayed price.

issued_shares: refreshed via admin job (Yahoo → Screener.in → NSE on desktop), typically weekly.
Display price: last close from historical_data (via _apply_live_screener_ohlc).
"""

from __future__ import annotations

import json
import sqlite3
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
    base_dir: Path,
    set_job: Callable[..., None],
    job_state: dict,
    fail_job: Callable[[str], None],
    invalidate_stock_df: Callable[[], None],
    finish_job: Callable[[str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
) -> None:
    import random
    import sqlite3 as sq

    from server.admin_job_control import JobCancelled, sleep_interruptible
    from server.issued_shares_fetch import (
        IssuedSharesCascadeState,
        make_nse_session,
        process_symbol_batch,
        set_issued_shares_source,
    )
    from server.product_config import yahoo_primary_pipeline

    DB = str(db_path)
    BATCH_SIZE = 20
    RATE_DELAY = 0.8
    MAX_FAILURE_RATE = 0.50

    def _check_cancel() -> None:
        if cancel_check and cancel_check():
            raise JobCancelled()

    def write_batch(conn, rows: list[tuple[str, int, str]]) -> None:
        cur = conn.cursor()
        for sym, shares, source in rows:
            cur.execute(
                "UPDATE screener SET issued_shares = ? WHERE symbol = ?",
                (int(shares), sym),
            )
            set_issued_shares_source(conn, sym, source)
        conn.commit()

    source_counts = {"yahoo": 0, "screener": 0, "nse": 0, "failed": 0}
    batch_pending: list[tuple[str, int, str]] = []
    conn = None

    try:
        allow_nse = not yahoo_primary_pipeline(base_dir)
        data_dir = base_dir / "data"
        if not data_dir.is_dir():
            data_dir = base_dir

        init_msg = (
            "Fetching issued share counts (Yahoo → Screener.in)…"
            if not allow_nse
            else "Fetching issued share counts (Yahoo → Screener.in → NSE)…"
        )
        set_job("issued_shares", init_msg)

        conn = sq.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT symbol, price FROM screener ORDER BY symbol")
        rows = cur.fetchall()
        all_symbols = [str(r[0]).strip().upper() for r in rows if r and r[0]]
        prices: dict[str, float] = {}
        for sym, px in rows:
            if sym and px is not None:
                try:
                    prices[str(sym).strip().upper()] = float(px)
                except (TypeError, ValueError):
                    pass
        conn.close()
        conn = None

        job_state["total"] = len(all_symbols)
        job_state["message"] = (
            f"{init_msg} {len(all_symbols)} symbols (market cap = shares × price)…"
        )

        state = IssuedSharesCascadeState(allow_nse=allow_nse)
        nse_session = make_nse_session() if allow_nse else None
        processed = 0

        for batch_start in range(0, len(all_symbols), BATCH_SIZE):
            _check_cancel()
            if processed > 50 and source_counts["failed"] / processed > MAX_FAILURE_RATE:
                job_state["message"] = "Failure rate too high. Stopping share-count refresh."
                break

            batch = all_symbols[batch_start : batch_start + BATCH_SIZE]
            results = process_symbol_batch(
                batch,
                prices,
                data_dir=data_dir,
                state=state,
                nse_session=nse_session,
                cancel_check=cancel_check,
            )

            for res in results:
                _check_cancel()
                processed += 1
                if res.issued_shares is not None and res.source in ("yahoo", "screener", "nse"):
                    batch_pending.append((res.symbol, res.issued_shares, res.source))
                    source_counts[res.source] += 1
                else:
                    source_counts["failed"] += 1
                    if res.nse_status == "blocked" and state.nse_blocked:
                        job_state["message"] = (
                            "NSE blocked — skipping NSE tier for remaining symbols."
                        )

            if batch_pending:
                conn = sq.connect(DB)
                write_batch(conn, batch_pending)
                conn.close()
                conn = None
                batch_pending = []

            job_state["progress"] = min(processed, job_state["total"])
            job_state["message"] = (
                f"Share counts: {source_counts['yahoo']} yahoo, "
                f"{source_counts['screener']} screener, {source_counts['nse']} nse, "
                f"{source_counts['failed']} failed ({processed}/{len(all_symbols)})"
            )
            sleep_interruptible(random.uniform(0.4, RATE_DELAY), cancel_check=cancel_check)

        if batch_pending:
            conn = sq.connect(DB)
            write_batch(conn, batch_pending)
            conn.close()

        _check_cancel()
        job_state["message"] = "Syncing market_cap cache (shares × stored price)…"
        cached = sync_market_cap_cache(db_path)
        invalidate_stock_df()
        finish_job(
            f"Share counts done — {source_counts['yahoo']} yahoo, "
            f"{source_counts['screener']} screener, {source_counts['nse']} nse, "
            f"{source_counts['failed']} failed. Cached market_cap refreshed for {cached} rows."
        )
    except JobCancelled:
        if batch_pending:
            flush_conn = sq.connect(DB)
            try:
                write_batch(flush_conn, batch_pending)
            finally:
                flush_conn.close()
        raise
    except Exception as e:
        fail_job(str(e))
    finally:
        if conn:
            conn.close()
