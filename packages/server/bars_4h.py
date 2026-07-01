"""
NSE session-aligned 4H bars (09:15–13:15 and 13:15–15:30 IST).

Built from yfinance 5m data on admin Update — not from daily EOD rows.

Yahoo 5m history is capped at ~60 calendar days from "today"; two 59-day windows
are used for backfill but only the recent window returns data beyond that wall.
Expect ~40–45 trading sessions of 4H history, not the full 90-session target.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = dtime(9, 15)
SESSION_MID = dtime(13, 15)
SESSION_CLOSE = dtime(15, 30)

BARS_4H_HISTORY_SESSION_DAYS = 90
BARS_4H_INCREMENTAL_SESSION_DAYS = 3
BARS_4H_YAHOO_WINDOW_DAYS = 59
BARS_4H_BATCH_SIZE = 50
BARS_4H_RATE_DELAY_MIN = 0.8
BARS_4H_RATE_DELAY_MAX = 1.5
# Minimum distinct session days before we treat a symbol as "backfilled" (~60d Yahoo cap ≈ 40–45 sessions).
BARS_4H_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE = 20

META_LAST_SUCCESS = "bars_4h_last_success_ist"
META_BACKFILL_COMPLETE = "bars_4h_backfill_complete"
META_SOURCE_PREFIX = "bars_4h_source:"
META_SOURCE_UPDATED_PREFIX = "bars_4h_source_updated:"

IntradaySource = Literal["yahoo", "nse_charting", "none"]


@dataclass(frozen=True)
class Fetch5mResult:
    rows: list[tuple]
    source: IntradaySource


@dataclass(frozen=True)
class Bar4H:
    symbol: str
    bar_start: datetime
    session_date: str
    bucket: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def yahoo_ticker_for_symbol(symbol: str) -> str:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return sym
    if sym.startswith("^") or sym.endswith("=F") or ".NS" in sym:
        return sym
    return f"{sym}.NS"


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def load_nse_calendar(base_dir: Path) -> dict[str, set[str]]:
    path = base_dir / "data" / "nse_calendar.json"
    default = {"holidays": set(), "special_sessions": set()}
    if not path.is_file():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {
            "holidays": {str(x) for x in (raw.get("holidays") or []) if x},
            "special_sessions": {str(x) for x in (raw.get("special_sessions") or []) if x},
        }
    except Exception:
        return default


def is_nse_session_day(d: date, holidays: set[str], special_sessions: set[str]) -> bool:
    ds = d.strftime("%Y-%m-%d")
    w = d.weekday()
    if w < 5:
        return ds not in holidays
    return ds in special_sessions


def assign_session_bucket(ts: datetime) -> Optional[int]:
    """Return 1 (morning), 2 (afternoon), or None outside session."""
    t = _ensure_tz(ts)
    tt = t.time()
    if tt < SESSION_OPEN or tt > SESSION_CLOSE:
        return None
    if tt < SESSION_MID:
        return 1
    return 2


def bucket_bar_start(session_date: date, bucket: int) -> datetime:
    if bucket == 1:
        return datetime.combine(session_date, SESSION_OPEN, tzinfo=IST)
    return datetime.combine(session_date, SESSION_MID, tzinfo=IST)


def aggregate_intraday_to_4h(
    symbol: str,
    rows: Sequence[tuple],
    holidays: set[str],
    special_sessions: set[str],
) -> list[Bar4H]:
    """
    rows: (ts, open, high, low, close, volume) — ts may be datetime or pandas Timestamp.
    """
    groups: dict[tuple[str, int], list[tuple]] = {}
    for row in rows:
        if not row or len(row) < 5:
            continue
        ts = row[0]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else datetime.fromisoformat(str(ts))
        ts = _ensure_tz(ts)
        bucket = assign_session_bucket(ts)
        if bucket is None:
            continue
        session_d = ts.date()
        if not is_nse_session_day(session_d, holidays, special_sessions):
            continue
        key = (session_d.strftime("%Y-%m-%d"), bucket)
        groups.setdefault(key, []).append(row)

    bars: list[Bar4H] = []
    for (session_date, bucket) in sorted(groups.keys()):
        chunk = sorted(groups[(session_date, bucket)], key=lambda r: r[0])
        try:
            o = round(float(chunk[0][1]), 2)
            h = round(max(float(r[2]) for r in chunk), 2)
            l = round(min(float(r[3]) for r in chunk), 2)
            c = round(float(chunk[-1][4]), 2)
            vol = round(sum(float(r[5]) if len(r) > 5 and r[5] is not None else 0.0 for r in chunk), 2)
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        sd = datetime.strptime(session_date, "%Y-%m-%d").date()
        start = bucket_bar_start(sd, bucket)
        bars.append(
            Bar4H(
                symbol=symbol,
                bar_start=start,
                session_date=session_date,
                bucket=bucket,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=vol,
            )
        )
    return bars


def ensure_bars_4h_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bars_4h (
            Symbol TEXT NOT NULL,
            BarStart TEXT NOT NULL,
            SessionDate TEXT NOT NULL,
            Bucket INTEGER NOT NULL,
            Open REAL,
            High REAL,
            Low REAL,
            Close REAL,
            Volume REAL,
            PRIMARY KEY (Symbol, BarStart)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bars_4h_symbol_session ON bars_4h(Symbol, SessionDate)"
    )
    conn.commit()


def ensure_updater_meta_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS updater_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )


def get_meta(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM updater_meta WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def set_meta(conn, key: str, value: str) -> None:
    ensure_updater_meta_table(conn)
    conn.execute(
        """
        INSERT INTO updater_meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )
    conn.commit()


def bars_4h_source_meta_key(symbol: str) -> str:
    return f"{META_SOURCE_PREFIX}{str(symbol).strip().upper()}"


def bars_4h_source_updated_meta_key(symbol: str) -> str:
    return f"{META_SOURCE_UPDATED_PREFIX}{str(symbol).strip().upper()}"


def get_bars_4h_source(conn, symbol: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM updater_meta WHERE key=?",
        (bars_4h_source_meta_key(symbol),),
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def set_bars_4h_source(conn, symbol: str, source: IntradaySource) -> None:
    now = datetime.now(IST).isoformat()
    set_meta(conn, bars_4h_source_meta_key(symbol), source)
    set_meta(conn, bars_4h_source_updated_meta_key(symbol), now)


def format_4h_missing_detail(symbol: str, conn=None, *, is_index: bool = False) -> str:
    """User-facing 404 detail when bars_4h is empty."""
    sym = str(symbol or "").strip().upper()
    kind = "index" if is_index else "symbol"
    if conn is not None:
        src = get_bars_4h_source(conn, sym)
        if src == "none":
            return (
                f"No 4H intraday source available for {kind} '{sym}' after Update "
                f"(Yahoo and NSE charting returned no 5m data). Daily charts may still work."
            )
    return (
        f"No 4H bars for {kind} '{sym}'. Run Update to build 4H session bars "
        f"(Yahoo 5m first, NSE charting fallback for NSE indices)."
    )


def symbols_needing_4h_backfill(
    conn,
    symbols: Sequence[str],
    min_distinct_sessions: int = BARS_4H_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE,
) -> list[str]:
    """Symbols with no bars_4h or fewer than min_distinct_sessions trading days."""
    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not sym_list:
        return []
    placeholders = ",".join(["?"] * len(sym_list))
    rows = conn.execute(
        f"""
        SELECT Symbol, COUNT(DISTINCT SessionDate)
        FROM bars_4h
        WHERE Symbol IN ({placeholders})
        GROUP BY Symbol
        """,
        sym_list,
    ).fetchall()
    have = {str(r[0]): int(r[1]) for r in rows}
    return [s for s in sym_list if have.get(s, 0) < min_distinct_sessions]


def reconcile_4h_backfill_meta(conn, universe_symbols: Sequence[str]) -> None:
    """Clear stale 'backfill complete' if symbols still lack 4H depth."""
    if get_meta(conn, META_BACKFILL_COMPLETE) != "1":
        return
    needing = symbols_needing_4h_backfill(conn, universe_symbols)
    if needing:
        set_meta(conn, META_BACKFILL_COMPLETE, "0")


def try_mark_universe_backfill_complete(conn, universe_symbols: Sequence[str]) -> None:
    needing = symbols_needing_4h_backfill(conn, universe_symbols)
    if not needing:
        set_meta(conn, META_BACKFILL_COMPLETE, "1")


def upsert_bars_4h(conn, symbol: str, bars: Sequence[Bar4H]) -> int:
    if not bars:
        return 0
    ensure_bars_4h_table(conn)
    sym = str(symbol).strip().upper()
    session_dates = {b.session_date for b in bars}
    for sd in session_dates:
        conn.execute(
            "DELETE FROM bars_4h WHERE Symbol=? AND SessionDate=?",
            (sym, sd),
        )
    n = 0
    for b in bars:
        conn.execute(
            """
            INSERT INTO bars_4h
                (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sym,
                b.bar_start.isoformat(),
                b.session_date,
                b.bucket,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
            ),
        )
        n += 1
    conn.commit()
    return n


def load_bars_4h_for_chart(conn, symbol: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    ensure_bars_4h_table(conn)
    sym = str(symbol).strip().upper()
    sql = (
        "SELECT BarStart, Open, High, Low, Close, Volume "
        "FROM bars_4h WHERE Symbol=? ORDER BY BarStart ASC"
    )
    params: list[Any] = [sym]
    if limit is not None and int(limit) > 0:
        sql = (
            "SELECT BarStart, Open, High, Low, Close, Volume FROM ("
            "  SELECT BarStart, Open, High, Low, Close, Volume, "
            "         ROW_NUMBER() OVER (ORDER BY BarStart DESC) AS rn "
            "  FROM bars_4h WHERE Symbol=?"
            ") WHERE rn <= ? ORDER BY BarStart ASC"
        )
        params = [sym, int(limit)]
    rows = conn.execute(sql, params).fetchall()
    out = []
    for bar_start, o, h, l, c, v in rows:
        try:
            dt = datetime.fromisoformat(str(bar_start))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            unix_ts = int(dt.timestamp())
        except Exception:
            continue
        out.append({
            "time": unix_ts,
            "open": round(float(o), 2),
            "high": round(float(h), 2),
            "low": round(float(l), 2),
            "close": round(float(c), 2),
            "volume": round(float(v or 0), 2),
        })
    return out


def load_bars_4h_candles_batch(conn, symbols: Sequence[str]) -> dict[str, list[tuple]]:
    ensure_bars_4h_table(conn)
    result = {str(s).strip().upper(): [] for s in symbols if str(s).strip()}
    if not result:
        return result
    syms = list(result.keys())
    placeholders = ",".join(["?"] * len(syms))
    rows = conn.execute(
        f"""
        SELECT Symbol, BarStart, Open, High, Low, Close
        FROM bars_4h WHERE Symbol IN ({placeholders})
        ORDER BY Symbol ASC, BarStart ASC
        """,
        syms,
    ).fetchall()
    for sym, bar_start, o, h, l, c in rows:
        if sym not in result:
            continue
        if o is None or h is None or l is None or c is None:
            continue
        result[sym].append((str(bar_start), float(o), float(h), float(l), float(c)))
    return result


def _fetch_5m_window(yf_symbols: list[str], start: datetime, end: datetime):
    import yfinance as yf

    start_str = start.strftime("%Y-%m-%d")
    end_str = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    return yf.download(
        yf_symbols,
        start=start_str,
        end=end_str,
        interval="5m",
        progress=False,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
    )


def _parse_yf_5m_frame(df, sym: str, yf_sym: str) -> list[tuple]:
    import pandas as pd

    if df is None or (hasattr(df, "empty") and df.empty):
        return []
    if len([sym]) == 1 and not isinstance(df.columns, pd.MultiIndex):
        sym_df = df
    else:
        if yf_sym not in df.columns.get_level_values(0):
            return []
        sym_df = df[yf_sym]
    sym_df = sym_df.dropna(subset=["Close"])
    if sym_df.empty:
        return []
    rows = []
    for ts, row in sym_df.iterrows():
        try:
            if hasattr(ts, "to_pydatetime"):
                dt = ts.to_pydatetime()
            else:
                dt = pd.Timestamp(ts).to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            else:
                dt = dt.astimezone(IST)
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            v = float(row.get("Volume", 0) or 0)
            if c <= 0:
                continue
            rows.append((dt, round(o, 2), round(h, 2), round(l, 2), round(c, 2), round(v, 2)))
        except Exception:
            continue
    return rows


def fetch_5m_for_symbols(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
) -> dict[str, list[tuple]]:
    import yfinance as yf  # noqa: F401

    symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not symbols:
        return {}
    yf_map = {s: yahoo_ticker_for_symbol(s) for s in symbols}
    yf_syms = list(yf_map.values())
    try:
        df = _fetch_5m_window(yf_syms, start, end)
    except Exception:
        return {}
    if df is None or getattr(df, "empty", True):
        return {}
    out: dict[str, list[tuple]] = {}
    for sym, yf_sym in yf_map.items():
        rows = _parse_yf_5m_frame(df, sym, yf_sym)
        if rows:
            out[sym] = rows
    return out


def fetch_5m_with_fallback(
    symbols: Sequence[str],
    windows: Sequence[tuple[datetime, datetime]],
    base_dir: Path,
) -> dict[str, Fetch5mResult]:
    """
    Layer 1: Yahoo 5m for all windows.
    Layer 2: NSE charting 5m for all windows (only if Yahoo empty and token exists).
    Never merge Yahoo + NSE rows for the same symbol in one build.
    """
    from server.nse_charting_intraday import fetch_nse_charting_5m, get_nse_chart_token

    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    out: dict[str, Fetch5mResult] = {}
    if not sym_list or not windows:
        return out

    yahoo_accum: dict[str, list[tuple]] = {s: [] for s in sym_list}
    for win_start, win_end in windows:
        chunk = fetch_5m_for_symbols(sym_list, win_start, win_end)
        for sym, rows in chunk.items():
            yahoo_accum.setdefault(sym, []).extend(rows)

    for sym in sym_list:
        yahoo_rows = yahoo_accum.get(sym) or []
        if yahoo_rows:
            out[sym] = Fetch5mResult(rows=yahoo_rows, source="yahoo")
            continue

        token_cfg = get_nse_chart_token(sym, base_dir)
        if not token_cfg:
            out[sym] = Fetch5mResult(rows=[], source="none")
            continue

        nse_rows: list[tuple] = []
        for win_start, win_end in windows:
            nse_rows.extend(
                fetch_nse_charting_5m(
                    token_cfg["token"],
                    win_start,
                    win_end,
                    chart_symbol=token_cfg.get("chartSymbol") or sym,
                    pause_sec=0.0,
                )
            )
        if nse_rows:
            out[sym] = Fetch5mResult(rows=nse_rows, source="nse_charting")
        else:
            out[sym] = Fetch5mResult(rows=[], source="none")

    return out


def _session_dates_back(n_sessions: int, holidays: set[str], special_sessions: set[str]) -> list[date]:
    out: list[date] = []
    d = datetime.now(IST).date()
    while len(out) < n_sessions and len(out) < n_sessions + 400:
        if is_nse_session_day(d, holidays, special_sessions):
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def build_bars_4h_for_symbols(
    conn,
    symbols: Sequence[str],
    base_dir: Path,
    *,
    backfill: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict[str, int]:
    def log(msg: str) -> None:
        if message_callback:
            message_callback(msg)

    cal = load_nse_calendar(base_dir)
    holidays = cal["holidays"]
    special = cal["special_sessions"]
    ensure_bars_4h_table(conn)

    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    total = len(sym_list)
    if not sym_list:
        return {"updated": 0, "failed": 0, "skipped": 0}

    now = datetime.now(IST)
    if backfill:
        session_dates = _session_dates_back(BARS_4H_HISTORY_SESSION_DAYS, holidays, special)
        if not session_dates:
            session_dates = [now.date()]
        fetch_start = datetime.combine(session_dates[0], SESSION_OPEN, tzinfo=IST)
        windows = []
        end_d = now.date() + timedelta(days=1)
        win_end = datetime.combine(end_d, dtime.min, tzinfo=IST)
        cur_end = win_end
        while cur_end > fetch_start:
            cur_start = max(fetch_start, cur_end - timedelta(days=BARS_4H_YAHOO_WINDOW_DAYS))
            windows.append((cur_start, cur_end))
            cur_end = cur_start
    else:
        session_dates = _session_dates_back(BARS_4H_INCREMENTAL_SESSION_DAYS, holidays, special)
        fetch_start = datetime.combine(session_dates[0], SESSION_OPEN, tzinfo=IST)
        windows = [(fetch_start, now + timedelta(days=1))]

    updated = 0
    failed = 0
    skipped = 0
    processed = 0

    for batch_start in range(0, total, BARS_4H_BATCH_SIZE):
        if cancel_check and cancel_check():
            break
        batch = sym_list[batch_start : batch_start + BARS_4H_BATCH_SIZE]
        fetched = fetch_5m_with_fallback(batch, windows, base_dir)
        batch_rows: dict[str, list[tuple]] = {s: [] for s in batch}
        batch_sources: dict[str, IntradaySource] = {}
        for sym in batch:
            result = fetched.get(sym) or Fetch5mResult(rows=[], source="none")
            batch_rows[sym] = result.rows
            batch_sources[sym] = result.source

        for sym in batch:
            rows = batch_rows.get(sym) or []
            source = batch_sources.get(sym) or "none"
            if not rows:
                if source == "none":
                    set_bars_4h_source(conn, sym, "none")
                skipped += 1
                processed += 1
                continue
            bars = aggregate_intraday_to_4h(sym, rows, holidays, special)
            if not bars:
                skipped += 1
                processed += 1
                continue
            try:
                upsert_bars_4h(conn, sym, bars)
                set_bars_4h_source(conn, sym, source)
                updated += 1
                log(f"4H {sym}: {source} ({len(rows)} x 5m -> {len(bars)} session bars)")
            except Exception:
                failed += 1
            processed += 1

        if progress_callback:
            progress_callback(processed, total)
        log(f"4H bars: {processed}/{total} (updated={updated}, skipped={skipped}, failed={failed})")
        time.sleep(random.uniform(BARS_4H_RATE_DELAY_MIN, BARS_4H_RATE_DELAY_MAX))

    set_meta(conn, META_LAST_SUCCESS, datetime.now(IST).isoformat())

    return {"updated": updated, "failed": failed, "skipped": skipped, "processed": processed}


def bar_start_to_chart_time(bar_start: str) -> Optional[int]:
    try:
        dt = datetime.fromisoformat(str(bar_start))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return int(dt.timestamp())
    except Exception:
        return None
