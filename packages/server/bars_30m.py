"""
NSE session-aligned 30-minute bars (09:15 IST buckets through 15:30).

Built from 5m intraday on admin Update after 15:30 IST — for EOD filter
snapshots and chart TF (no live mid-session overlay). Shares Upstox 5m
fetch with bars_4h when invoked from the combined build path.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional, Sequence
from zoneinfo import ZoneInfo

from server.bars_4h import (
    BARS_4H_BATCH_SIZE,
    BARS_4H_HISTORY_SESSION_DAYS,
    BARS_4H_INCREMENTAL_SESSION_DAYS,
    SESSION_CLOSE,
    SESSION_OPEN,
    Fetch5mResult,
    IntradaySource,
    _batch_pace_delay_sec,
    _ensure_tz,
    _session_dates_back,
    fetch_5m_with_fallback,
    get_meta,
    is_nse_session_day,
    latest_completed_4h_session_date,
    load_nse_calendar,
    recent_completed_4h_session_dates,
    set_meta,
)

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

BARS_30M_HISTORY_SESSION_DAYS = BARS_4H_HISTORY_SESSION_DAYS
BARS_30M_INCREMENTAL_SESSION_DAYS = BARS_4H_INCREMENTAL_SESSION_DAYS
BARS_30M_BATCH_SIZE = BARS_4H_BATCH_SIZE
BARS_30M_DEFER_UNTIL_IST = dtime(15, 30)
BARS_30M_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE = 20
# 09:15 → 15:30 = 375 minutes → buckets 0..12 (13 bars / session day).
BARS_30M_MAX_BUCKET = 12

META_LAST_SUCCESS = "bars_30m_last_success_ist"
META_BACKFILL_COMPLETE = "bars_30m_backfill_complete"
META_SOURCE_PREFIX = "bars_30m_source:"
META_SOURCE_UPDATED_PREFIX = "bars_30m_source_updated:"


@dataclass(frozen=True)
class Bar30m:
    symbol: str
    bar_start: datetime
    session_date: str
    bucket: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def should_defer_bars_30m_build(base_dir: Optional[Path] = None) -> tuple[bool, str]:
    """
    During an NSE session day before 15:30 IST, skip full-universe 30m rebuild.
    Force with CIM_BARS_30M_DURING_SESSION=1.
    """
    raw = os.getenv("CIM_BARS_30M_DURING_SESSION", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return False, "30m build forced during session (CIM_BARS_30M_DURING_SESSION=1)"

    now = datetime.now(IST)
    if base_dir is None:
        try:
            from server.core.install_root import get_install_root

            root = get_install_root()
        except Exception:
            root = Path(__file__).resolve().parents[2]
    else:
        root = Path(base_dir)
    cal = load_nse_calendar(root)
    if not is_nse_session_day(now.date(), cal["holidays"], cal["special_sessions"]):
        return False, "non-session day — running 30m session bar build"
    if now.time() >= BARS_30M_DEFER_UNTIL_IST:
        return False, "post-close — running 30m session bar build"
    return (
        True,
        "live session — skipped full-universe 30m DB rebuild "
        "(full 30m build runs after 15:30 IST on Update)",
    )


def assign_30m_bucket(ts: datetime) -> Optional[int]:
    """Return bucket index 0..12 for a timestamp inside the cash session, else None."""
    t = _ensure_tz(ts)
    tt = t.time()
    if tt < SESSION_OPEN or tt > SESSION_CLOSE:
        return None
    open_dt = datetime.combine(t.date(), SESSION_OPEN, tzinfo=IST)
    delta_min = int((t - open_dt).total_seconds() // 60)
    if delta_min < 0:
        return None
    # Cap so 15:15–15:30 stays in the last bucket.
    return min(delta_min // 30, BARS_30M_MAX_BUCKET)


def bucket_30m_bar_start(session_date: date, bucket: int) -> datetime:
    open_dt = datetime.combine(session_date, SESSION_OPEN, tzinfo=IST)
    return open_dt + timedelta(minutes=int(bucket) * 30)


def aggregate_intraday_to_30m(
    symbol: str,
    rows: Sequence[tuple],
    holidays: set[str],
    special_sessions: set[str],
) -> list[Bar30m]:
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
        bucket = assign_30m_bucket(ts)
        if bucket is None:
            continue
        session_d = ts.date()
        if not is_nse_session_day(session_d, holidays, special_sessions):
            continue
        key = (session_d.strftime("%Y-%m-%d"), bucket)
        groups.setdefault(key, []).append(row)

    bars: list[Bar30m] = []
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
        start = bucket_30m_bar_start(sd, bucket)
        bars.append(
            Bar30m(
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


def ensure_bars_30m_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bars_30m (
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
        "CREATE INDEX IF NOT EXISTS idx_bars_30m_symbol_session ON bars_30m(Symbol, SessionDate)"
    )
    conn.commit()


def bars_30m_source_meta_key(symbol: str) -> str:
    return f"{META_SOURCE_PREFIX}{str(symbol).strip().upper()}"


def bars_30m_source_updated_meta_key(symbol: str) -> str:
    return f"{META_SOURCE_UPDATED_PREFIX}{str(symbol).strip().upper()}"


def set_bars_30m_source(conn, symbol: str, source: IntradaySource) -> None:
    now = datetime.now(IST).isoformat()
    set_meta(conn, bars_30m_source_meta_key(symbol), source)
    set_meta(conn, bars_30m_source_updated_meta_key(symbol), now)


def get_bars_30m_source(conn, symbol: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM updater_meta WHERE key=?",
        (bars_30m_source_meta_key(symbol),),
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def format_30m_missing_detail(symbol: str, conn=None, *, is_index: bool = False) -> str:
    """User-facing 404 detail when bars_30m is empty."""
    sym = str(symbol or "").strip().upper()
    kind = "index" if is_index else "symbol"
    if conn is not None:
        src = get_bars_30m_source(conn, sym)
        if src == "none":
            return (
                f"No 30m intraday source available for {kind} '{sym}' after Update "
                f"(Upstox returned no 5m data). Daily charts may still work."
            )
    return (
        f"No 30m bars for {kind} '{sym}'. Run Update after 15:30 IST "
        f"(Upstox 5m only)."
    )


def _session_day_counts(conn, symbols: Sequence[str]) -> dict[str, int]:
    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not sym_list:
        return {}
    placeholders = ",".join(["?"] * len(sym_list))
    rows = conn.execute(
        f"""
        SELECT Symbol, COUNT(DISTINCT SessionDate)
        FROM bars_30m
        WHERE Symbol IN ({placeholders})
        GROUP BY Symbol
        """,
        sym_list,
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def symbols_needing_30m_backfill(
    conn,
    symbols: Sequence[str],
    min_distinct_sessions: int = BARS_30M_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE,
) -> list[str]:
    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not sym_list:
        return []
    have = _session_day_counts(conn, sym_list)
    return [s for s in sym_list if have.get(s, 0) < min_distinct_sessions]


def symbols_needing_30m_refresh(
    conn,
    symbols: Sequence[str],
    latest_session_date: date | str | Sequence[date | str],
) -> list[str]:
    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not sym_list:
        return []

    def _norm(d: date | str) -> str:
        if isinstance(d, date):
            return d.strftime("%Y-%m-%d")
        return str(d).strip()[:10]

    if isinstance(latest_session_date, (list, tuple)):
        targets = [_norm(x) for x in latest_session_date if _norm(x)]
    else:
        targets = [_norm(latest_session_date)]
    targets = [t for t in targets if t]
    if not targets:
        return list(sym_list)

    placeholders = ",".join(["?"] * len(sym_list))
    date_ph = ",".join(["?"] * len(targets))
    rows = conn.execute(
        f"""
        SELECT Symbol, SessionDate
        FROM bars_30m
        WHERE SessionDate IN ({date_ph}) AND Symbol IN ({placeholders})
        """,
        [*targets, *sym_list],
    ).fetchall()
    have: dict[str, set[str]] = {}
    for r in rows:
        if not r or not r[0]:
            continue
        sym = str(r[0]).strip().upper()
        sd = str(r[1] or "").strip()[:10]
        if not sd:
            continue
        have.setdefault(sym, set()).add(sd)
    wanted = set(targets)
    return [s for s in sym_list if not wanted.issubset(have.get(s) or set())]


def reconcile_30m_backfill_meta(conn, universe_symbols: Sequence[str]) -> None:
    if get_meta(conn, META_BACKFILL_COMPLETE) != "1":
        return
    needing = symbols_needing_30m_backfill(conn, universe_symbols)
    if needing:
        logger.info(
            "bars_30m: %d symbols still shallow (scoped depth catch-up only, e.g. %s)",
            len(needing),
            ", ".join(needing[:8]),
        )


def try_mark_universe_30m_backfill_complete(conn, universe_symbols: Sequence[str]) -> None:
    needing = symbols_needing_30m_backfill(conn, universe_symbols)
    if not needing:
        set_meta(conn, META_BACKFILL_COMPLETE, "1")


def upsert_bars_30m(conn, symbol: str, bars: Sequence[Bar30m]) -> int:
    if not bars:
        return 0
    ensure_bars_30m_table(conn)
    sym = str(symbol).strip().upper()
    session_dates = {b.session_date for b in bars}
    for sd in session_dates:
        conn.execute(
            "DELETE FROM bars_30m WHERE Symbol=? AND SessionDate=?",
            (sym, sd),
        )
    rows = []
    for b in bars:
        rows.append(
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
            )
        )
    conn.executemany(
        """
        INSERT INTO bars_30m
            (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_bars_30m_many(conn, symbol_bars: Sequence[tuple[str, Sequence[Bar30m]]]) -> int:
    ensure_bars_30m_table(conn)
    total = 0
    insert_rows: list[tuple] = []
    for symbol, bars in symbol_bars:
        if not bars:
            continue
        sym = str(symbol).strip().upper()
        session_dates = {b.session_date for b in bars}
        for sd in session_dates:
            conn.execute(
                "DELETE FROM bars_30m WHERE Symbol=? AND SessionDate=?",
                (sym, sd),
            )
        for b in bars:
            insert_rows.append(
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
                )
            )
            total += 1
    if insert_rows:
        conn.executemany(
            """
            INSERT INTO bars_30m
                (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            insert_rows,
        )
    conn.commit()
    return total


def load_bars_30m_candles_batch(conn, symbols: Sequence[str]) -> dict[str, list[tuple]]:
    ensure_bars_30m_table(conn)
    result = {str(s).strip().upper(): [] for s in symbols if str(s).strip()}
    if not result:
        return result
    syms = list(result.keys())
    placeholders = ",".join(["?"] * len(syms))
    rows = conn.execute(
        f"""
        SELECT Symbol, BarStart, Open, High, Low, Close
        FROM bars_30m WHERE Symbol IN ({placeholders})
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


def load_bars_30m_for_chart(conn, symbol: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    ensure_bars_30m_table(conn)
    sym = str(symbol).strip().upper()
    sql = (
        "SELECT BarStart, Open, High, Low, Close, Volume "
        "FROM bars_30m WHERE Symbol=? ORDER BY BarStart ASC"
    )
    params: list[Any] = [sym]
    if limit is not None and int(limit) > 0:
        sql = (
            "SELECT BarStart, Open, High, Low, Close, Volume FROM ("
            "  SELECT BarStart, Open, High, Low, Close, Volume, "
            "         ROW_NUMBER() OVER (ORDER BY BarStart DESC) AS rn "
            "  FROM bars_30m WHERE Symbol=?"
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


def write_30m_from_5m_rows(
    conn,
    symbol: str,
    rows: Sequence[tuple],
    holidays: set[str],
    special_sessions: set[str],
    *,
    source: IntradaySource = "upstox",
    target_session_strs: Optional[set[str]] = None,
) -> int:
    """Aggregate prefetched 5m rows into bars_30m (shared-fetch helper)."""
    bars = aggregate_intraday_to_30m(symbol, rows, holidays, special_sessions)
    if target_session_strs:
        bars = [b for b in bars if b.session_date in target_session_strs]
    if not bars:
        return 0
    n = upsert_bars_30m(conn, symbol, bars)
    set_bars_30m_source(conn, symbol, source)
    return n


def write_30m_many_from_5m(
    conn,
    fetched: dict[str, Fetch5mResult],
    holidays: set[str],
    special_sessions: set[str],
    *,
    target_session_strs: Optional[set[str]] = None,
) -> int:
    """Batch-write 30m bars from a fetch_5m_with_fallback result map."""
    pending: list[tuple[str, list[Bar30m]]] = []
    pending_sources: list[tuple[str, IntradaySource]] = []
    for sym, result in fetched.items():
        if not result or not result.rows:
            continue
        bars = aggregate_intraday_to_30m(sym, result.rows, holidays, special_sessions)
        if target_session_strs:
            bars = [b for b in bars if b.session_date in target_session_strs]
        if not bars:
            continue
        pending.append((sym, bars))
        pending_sources.append((sym, result.source))
    if not pending:
        return 0
    n = upsert_bars_30m_many(conn, pending)
    for sym, source in pending_sources:
        set_bars_30m_source(conn, sym, source)
    return n


def build_bars_30m_for_symbols(
    conn,
    symbols: Sequence[str],
    base_dir: Path,
    *,
    backfill: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    prefetched: Optional[dict[str, Fetch5mResult]] = None,
) -> dict[str, int]:
    """
    Build bars_30m for symbols. When `prefetched` is provided, skip Upstox fetch
    for those symbols (shared path with 4H build).
    """
    def log(msg: str) -> None:
        if message_callback:
            message_callback(msg)

    cal = load_nse_calendar(base_dir)
    holidays = cal["holidays"]
    special = cal["special_sessions"]
    ensure_bars_30m_table(conn)

    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    total = len(sym_list)
    empty = {
        "updated": 0,
        "failed": 0,
        "skipped": 0,
        "processed": 0,
        "sources": {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0, "failed": 0},
        "misses": [],
    }
    if not sym_list:
        return empty

    now = datetime.now(IST)
    target_sessions: list[date] = []
    if backfill:
        session_dates = _session_dates_back(BARS_30M_HISTORY_SESSION_DAYS, holidays, special)
        if not session_dates:
            session_dates = [now.date()]
        fetch_start = datetime.combine(session_dates[0], SESSION_OPEN, tzinfo=IST)
        end_d = now.date() + timedelta(days=1)
        win_end = datetime.combine(end_d, dtime.min, tzinfo=IST)
        windows = [(fetch_start, win_end)]
        target_session_strs: set[str] = set()
    else:
        target_sessions = recent_completed_4h_session_dates(
            BARS_30M_INCREMENTAL_SESSION_DAYS,
            holidays=holidays,
            special_sessions=special,
            base_dir=base_dir,
            now=now,
        )
        target_session = target_sessions[0]
        oldest = target_sessions[-1]
        fetch_start = datetime.combine(oldest, SESSION_OPEN, tzinfo=IST)
        fetch_end = datetime.combine(target_session, SESSION_CLOSE, tzinfo=IST) + timedelta(
            minutes=5
        )
        windows = [(fetch_start, fetch_end)]
        target_session_strs = {d.strftime("%Y-%m-%d") for d in target_sessions}

    updated = 0
    failed = 0
    skipped = 0
    processed = 0
    source_totals = {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0, "failed": 0}
    misses: list[str] = []

    upstox_primary = False
    try:
        from server import upstox_config

        upstox_primary = bool(upstox_config.market_data_enabled())
    except Exception:
        upstox_primary = False
    if message_callback and prefetched is None:
        if upstox_primary:
            message_callback("30m 5m source: Upstox only (parallel history fetch)")
        else:
            message_callback("30m 5m source: Upstox not configured — symbols will be skipped")

    def _bump_source(src: str) -> None:
        key = "nse" if src == "nse_charting" else (src if src in source_totals else "none")
        source_totals[key] = int(source_totals.get(key) or 0) + 1

    for batch_start in range(0, total, BARS_30M_BATCH_SIZE):
        if cancel_check and cancel_check():
            break
        batch = sym_list[batch_start : batch_start + BARS_30M_BATCH_SIZE]
        if prefetched is not None:
            fetched = {
                s: (prefetched.get(s) or Fetch5mResult(rows=[], source="none"))
                for s in batch
            }
        else:
            fetched = fetch_5m_with_fallback(batch, windows, base_dir)

        pending_upsert: list[tuple[str, list[Bar30m]]] = []
        pending_sources: list[tuple[str, IntradaySource]] = []
        batch_src_counts = {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0}

        for sym in batch:
            result = fetched.get(sym) or Fetch5mResult(rows=[], source="none")
            rows = result.rows
            source = result.source
            sk = "nse" if source == "nse_charting" else source
            if sk not in batch_src_counts:
                sk = "none"
            batch_src_counts[sk] = int(batch_src_counts.get(sk) or 0) + 1

            if not rows:
                if source == "none":
                    set_bars_30m_source(conn, sym, "none")
                    misses.append(sym)
                skipped += 1
                processed += 1
                _bump_source(source)
                continue
            bars = aggregate_intraday_to_30m(sym, rows, holidays, special)
            if target_session_strs:
                bars = [b for b in bars if b.session_date in target_session_strs]
            if not bars:
                skipped += 1
                processed += 1
                _bump_source(source)
                continue
            pending_upsert.append((sym, bars))
            pending_sources.append((sym, source))
            processed += 1

        try:
            if pending_upsert:
                upsert_bars_30m_many(conn, pending_upsert)
                for sym, source in pending_sources:
                    set_bars_30m_source(conn, sym, source)
                    updated += 1
                    _bump_source(source)
        except Exception:
            for sym, bars in pending_upsert:
                source = next((s for s0, s in pending_sources if s0 == sym), "upstox")
                try:
                    upsert_bars_30m(conn, sym, bars)
                    set_bars_30m_source(conn, sym, source)
                    updated += 1
                    _bump_source(source)
                except Exception:
                    failed += 1
                    source_totals["failed"] = int(source_totals.get("failed") or 0) + 1

        if progress_callback:
            progress_callback(processed, total)
        log(
            f"30m bars: {processed}/{total} (updated={updated}, skipped={skipped}, failed={failed}) | "
            f"Source batch: Upstox={batch_src_counts.get('upstox', 0)} "
            f"none={batch_src_counts.get('none', 0)}"
        )
        if prefetched is None:
            time.sleep(_batch_pace_delay_sec(upstox_primary=upstox_primary))

    set_meta(conn, META_LAST_SUCCESS, datetime.now(IST).isoformat())

    return {
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
        "processed": processed,
        "sources": source_totals,
        "misses": misses[:50],
    }
