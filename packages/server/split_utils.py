"""
Stock split detection ledger and helpers (SQLite stock_split_events).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

SPLIT_MAINTENANCE_DAYS = 20
SPLIT_CATCHUP_DAYS = 90
SPLIT_SCAN_SLEEP_SEC = 0.2
SPLIT_AUTO_APPLY_BATCH_CAP = 50

STATUS_PENDING = "pending"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"


def ensure_stock_split_events_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_split_events (
            symbol TEXT NOT NULL,
            split_date TEXT NOT NULL,
            ratio REAL NOT NULL,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            detected_at TEXT,
            applied_at TEXT,
            last_error TEXT,
            PRIMARY KEY (symbol, split_date, ratio)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_split_events_status ON stock_split_events(status)"
    )
    conn.commit()


def _norm_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _norm_split_date(split_date: str) -> str:
    s = str(split_date or "").strip()
    return s[:10] if len(s) >= 10 else s


def is_split_applied(
    conn: sqlite3.Connection,
    symbol: str,
    split_date: str,
    ratio: float,
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT status FROM stock_split_events
        WHERE symbol = ? AND split_date = ? AND ratio = ?
        """,
        (_norm_symbol(symbol), _norm_split_date(split_date), float(ratio)),
    )
    row = cur.fetchone()
    return bool(row and str(row[0]).strip().lower() == STATUS_APPLIED)


def get_split_event_status(
    conn: sqlite3.Connection,
    symbol: str,
    split_date: str,
    ratio: float,
) -> Optional[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT status FROM stock_split_events
        WHERE symbol = ? AND split_date = ? AND ratio = ?
        """,
        (_norm_symbol(symbol), _norm_split_date(split_date), float(ratio)),
    )
    row = cur.fetchone()
    return str(row[0]).strip().lower() if row and row[0] else None


def mark_pending(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    split_date: str,
    ratio: float,
    source: str,
) -> bool:
    """Insert pending if not already applied. Returns True if row is (or became) pending."""
    sym = _norm_symbol(symbol)
    sd = _norm_split_date(split_date)
    rat = float(ratio)
    if is_split_applied(conn, sym, sd, rat):
        return False
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    existing = get_split_event_status(conn, sym, sd, rat)
    if existing == STATUS_APPLIED:
        return False
    if existing in (STATUS_PENDING, STATUS_FAILED):
        cur.execute(
            """
            UPDATE stock_split_events
            SET status = ?, source = ?, detected_at = COALESCE(detected_at, ?),
                last_error = CASE WHEN status = 'failed' THEN last_error ELSE NULL END
            WHERE symbol = ? AND split_date = ? AND ratio = ?
            """,
            (STATUS_PENDING, source, now, sym, sd, rat),
        )
    else:
        cur.execute(
            """
            INSERT INTO stock_split_events
            (symbol, split_date, ratio, source, status, detected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sym, sd, rat, source, STATUS_PENDING, now),
        )
    conn.commit()
    return True


def mark_applied(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    split_date: str,
    ratio: float,
    source: Optional[str] = None,
) -> None:
    sym = _norm_symbol(symbol)
    sd = _norm_split_date(split_date)
    rat = float(ratio)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO stock_split_events
        (symbol, split_date, ratio, source, status, detected_at, applied_at, last_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(symbol, split_date, ratio) DO UPDATE SET
            status = excluded.status,
            applied_at = excluded.applied_at,
            source = COALESCE(excluded.source, stock_split_events.source),
            last_error = NULL
        """,
        (sym, sd, rat, source or "backfill", STATUS_APPLIED, now, now),
    )
    conn.commit()


def mark_failed(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    split_date: str,
    ratio: float,
    error: str,
) -> None:
    sym = _norm_symbol(symbol)
    sd = _norm_split_date(split_date)
    rat = float(ratio)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO stock_split_events
        (symbol, split_date, ratio, status, detected_at, last_error)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, split_date, ratio) DO UPDATE SET
            status = excluded.status,
            last_error = excluded.last_error
        """,
        (sym, sd, rat, STATUS_FAILED, now, str(error)[:500]),
    )
    conn.commit()


def list_pending(
    conn: sqlite3.Connection,
    *,
    symbols: Optional[list[str]] = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    cur = conn.cursor()
    if symbols:
        syms = [_norm_symbol(s) for s in symbols if str(s).strip()]
        if not syms:
            return []
        placeholders = ",".join("?" * len(syms))
        cur.execute(
            f"""
            SELECT symbol, split_date, ratio, source, status, detected_at, last_error
            FROM stock_split_events
            WHERE status IN ('pending', 'failed') AND symbol IN ({placeholders})
            ORDER BY split_date DESC, symbol ASC
            LIMIT ?
            """,
            (*syms, int(limit)),
        )
    else:
        cur.execute(
            """
            SELECT symbol, split_date, ratio, source, status, detected_at, last_error
            FROM stock_split_events
            WHERE status IN ('pending', 'failed')
            ORDER BY split_date DESC, symbol ASC
            LIMIT ?
            """,
            (int(limit),),
        )
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "symbol": r[0],
                "split_date": r[1],
                "ratio": r[2],
                "source": r[3],
                "status": r[4],
                "detected_at": r[5],
                "last_error": r[6],
            }
        )
    return out


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT status, COUNT(*) FROM stock_split_events GROUP BY status
        """
    )
    counts = {STATUS_PENDING: 0, STATUS_APPLIED: 0, STATUS_FAILED: 0}
    for status, n in cur.fetchall():
        key = str(status or "").strip().lower()
        if key in counts:
            counts[key] = int(n)
    return counts


def symbol_has_historical_bars(conn: sqlite3.Connection, symbol: str, min_rows: int = 50) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM historical_data WHERE Symbol = ?",
        (_norm_symbol(symbol),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) >= min_rows)


def detect_recent_split(sym: str, cutoff: datetime) -> Optional[dict[str, Any]]:
    """
    Return {symbol, split_date, ratio, source, debug} if a split on/after cutoff, else None.
    """
    import yfinance as yf

    sym = _norm_symbol(sym)
    if not sym:
        return None

    ticker = yf.Ticker(f"{sym}.NS")

    try:
        splits = ticker.splits
        if splits is not None and len(splits) > 0:
            for split_dt, split_ratio in splits.items():
                try:
                    ratio = float(split_ratio)
                    if ratio <= 1.0001:
                        continue
                    dt_obj = (
                        split_dt.to_pydatetime()
                        if hasattr(split_dt, "to_pydatetime")
                        else split_dt
                    )
                    if getattr(dt_obj, "tzinfo", None) is not None:
                        dt_obj = dt_obj.replace(tzinfo=None)
                    if dt_obj >= cutoff:
                        return {
                            "symbol": sym,
                            "split_date": dt_obj.strftime("%Y-%m-%d"),
                            "ratio": ratio,
                            "source": "ticker_splits",
                            "debug": f"ticker_splits:{dt_obj.strftime('%Y-%m-%d')} ratio={ratio:g}",
                        }
                except Exception:
                    continue
    except Exception:
        pass

    try:
        hist = ticker.history(
            start=(cutoff - timedelta(days=7)).strftime("%Y-%m-%d"),
            end=(datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=False,
            actions=True,
        )
        if hist is not None and not hist.empty and "Stock Splits" in hist.columns:
            split_rows = hist[hist["Stock Splits"].fillna(0).astype(float) > 1.0001]
            if not split_rows.empty:
                row = split_rows.iloc[-1]
                split_dt = split_rows.index[-1]
                dt_obj = (
                    split_dt.to_pydatetime()
                    if hasattr(split_dt, "to_pydatetime")
                    else split_dt
                )
                if getattr(dt_obj, "tzinfo", None) is not None:
                    dt_obj = dt_obj.replace(tzinfo=None)
                if dt_obj >= cutoff:
                    ratio = float(row["Stock Splits"])
                    return {
                        "symbol": sym,
                        "split_date": dt_obj.strftime("%Y-%m-%d"),
                        "ratio": ratio,
                        "source": "history_actions",
                        "debug": (
                            f"history_actions:{dt_obj.strftime('%Y-%m-%d')} "
                            f"ratio={ratio:g}"
                        ),
                    }
    except Exception:
        pass

    return None


def apply_symbol_history_refresh(
    conn: sqlite3.Connection,
    sym: str,
) -> tuple[bool, str]:
    """
    Download max adjusted history, replace historical_data for symbol.
    Returns (ok, error_message).
    """
    import yfinance as yf

    sym = _norm_symbol(sym)
    insert_sql = """
        INSERT INTO historical_data
        (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
    """
    df = yf.download(f"{sym}.NS", period="max", progress=False, auto_adjust=True, threads=False)
    if df is None or df.empty:
        return False, "empty_download"

    if getattr(df.columns, "nlevels", 1) > 1:
        try:
            df = df.copy()
            df.columns = [
                c[0] if isinstance(c, tuple) and len(c) > 0 else c for c in df.columns
            ]
        except Exception:
            return False, "bad_columns"

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(set(df.columns)):
        return False, "missing_ohlcv"

    rows = []
    row_parse_errors = 0
    for dt_idx, row in df.iterrows():
        try:
            ds = dt_idx.strftime("%Y-%m-%d") + " 00:00:00+05:30"
            o = round(float(row["Open"]), 2)
            h = round(float(row["High"]), 2)
            l = round(float(row["Low"]), 2)
            c = round(float(row["Close"]), 2)
            v = round(float(row["Volume"]), 2)
            if c <= 0:
                continue
            rows.append((sym, ds, o, h, l, c, c, v))
        except Exception:
            row_parse_errors += 1
            continue
    if not rows:
        return False, f"no_rows_after_parse({row_parse_errors})"

    cur = conn.cursor()
    cur.execute("DELETE FROM historical_data WHERE Symbol = ?", (sym,))
    cur.executemany(insert_sql, rows)
    conn.commit()
    return True, ""


def recalc_screener_change_for_symbol(conn: sqlite3.Connection, sym: str) -> None:
    sym = _norm_symbol(sym)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE screener
            SET change_percent = ROUND((
                (SELECT Close FROM historical_data h1 WHERE h1.Symbol = screener.symbol ORDER BY h1.Date DESC LIMIT 1) -
                (SELECT Close FROM historical_data h2 WHERE h2.Symbol = screener.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
            ) / (SELECT Close FROM historical_data h3 WHERE h3.Symbol = screener.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1) * 100, 2)
            WHERE symbol = ?
            """,
            (sym,),
        )
        cur.execute(
            """
            UPDATE screener
            SET change_percent_monthly = ROUND((
                (SELECT Close FROM historical_data h1 WHERE h1.Symbol = screener.symbol ORDER BY h1.Date DESC LIMIT 1) -
                (SELECT Close FROM historical_data h2 WHERE h2.Symbol = screener.symbol AND SUBSTR(h2.Date,1,7) < SUBSTR((SELECT MAX(Date) FROM historical_data h3 WHERE h3.Symbol = screener.symbol),1,7) ORDER BY h2.Date DESC LIMIT 1)
            ) / (SELECT Close FROM historical_data h4 WHERE h4.Symbol = screener.symbol AND SUBSTR(h4.Date,1,7) < SUBSTR((SELECT MAX(Date) FROM historical_data h5 WHERE h5.Symbol = screener.symbol),1,7) ORDER BY h4.Date DESC LIMIT 1) * 100, 2)
            WHERE symbol = ?
            """,
            (sym,),
        )
        conn.commit()
    except Exception:
        pass
