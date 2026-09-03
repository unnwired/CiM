"""
NSE session-aligned 4H bars (09:15–13:15 and 13:15–15:30 IST).

Built from 5m intraday on admin Update — not from daily EOD rows.
5m source: Upstox only (no Yahoo / NSE mix on the Update path).
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = dtime(9, 15)
SESSION_MID = dtime(13, 15)
SESSION_CLOSE = dtime(15, 30)

BARS_4H_HISTORY_SESSION_DAYS = 90
# Incremental refresh covers the latest N completed sessions so a missed mid-week
# day (e.g. Tue) is still filled after Wed's bars land — not "skip forever".
BARS_4H_INCREMENTAL_SESSION_DAYS = 5
BARS_4H_YAHOO_WINDOW_DAYS = 59  # retained for tests / legacy helpers only
BARS_4H_BATCH_SIZE = 50
BARS_4H_RATE_DELAY_MIN = 0.15
BARS_4H_RATE_DELAY_MAX = 0.35
# Faster pacing when Upstox is configured (primary and only Update source).
BARS_4H_UPSTOX_RATE_DELAY_MIN = 0.05
BARS_4H_UPSTOX_RATE_DELAY_MAX = 0.15
# Minimum distinct session days before we treat a symbol as "backfilled".
BARS_4H_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE = 20
# Defer full-universe 4H rebuild while the cash session is still open (live charts use quote overlay).
BARS_4H_DEFER_UNTIL_IST = dtime(15, 30)
# During live-session Update: catch up at most this many symbols missing 4H history.
BARS_4H_LIVE_CATCHUP_MAX = 40

META_LAST_SUCCESS = "bars_4h_last_success_ist"
META_BACKFILL_COMPLETE = "bars_4h_backfill_complete"
META_SOURCE_PREFIX = "bars_4h_source:"
META_SOURCE_UPDATED_PREFIX = "bars_4h_source_updated:"

IntradaySource = Literal["upstox", "yahoo", "nse_charting", "none"]


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


def should_defer_bars_4h_build(base_dir: Optional[Path] = None) -> tuple[bool, str]:
    """
    During an NSE session day before 15:30 IST, skip full-universe 4H rebuild
    inside Update price/volume — live 4H candles come from the quote overlay.

    Force build during session with CIM_BARS_4H_DURING_SESSION=1.
    """
    raw = os.getenv("CIM_BARS_4H_DURING_SESSION", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return False, "4H build forced during session (CIM_BARS_4H_DURING_SESSION=1)"

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
        return False, "non-session day — running 4H session bar build"
    if now.time() >= BARS_4H_DEFER_UNTIL_IST:
        return False, "post-close — running 4H session bar build"
    return (
        True,
        "live session — skipped full-universe 4H DB rebuild (live 4H uses quote overlay; "
        "full 4H build runs after 15:30 IST on Update)",
    )


def _batch_pace_delay_sec(*, upstox_primary: bool) -> float:
    if upstox_primary:
        return random.uniform(BARS_4H_UPSTOX_RATE_DELAY_MIN, BARS_4H_UPSTOX_RATE_DELAY_MAX)
    return random.uniform(BARS_4H_RATE_DELAY_MIN, BARS_4H_RATE_DELAY_MAX)


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
                f"(Upstox returned no 5m data). Daily charts may still work."
            )
    return (
        f"No 4H bars for {kind} '{sym}'. Run Update after 15:30 IST "
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
        FROM bars_4h
        WHERE Symbol IN ({placeholders})
        GROUP BY Symbol
        """,
        sym_list,
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def symbols_needing_4h_backfill(
    conn,
    symbols: Sequence[str],
    min_distinct_sessions: int = BARS_4H_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE,
) -> list[str]:
    """Symbols with no bars_4h or fewer than min_distinct_sessions trading days."""
    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not sym_list:
        return []
    have = _session_day_counts(conn, sym_list)
    return [s for s in sym_list if have.get(s, 0) < min_distinct_sessions]


def latest_completed_4h_session_date(
    *,
    now: Optional[datetime] = None,
    holidays: Optional[set[str]] = None,
    special_sessions: Optional[set[str]] = None,
    base_dir: Optional[Path] = None,
) -> date:
    """
    Latest NSE session whose 4H bars should already be complete.

    On a session day before 15:30 IST, that is the previous session day.
    At/after 15:30 IST (or any non-open session), that is today if today is a
    session day, else the prior session day.
    """
    clock = now or datetime.now(IST)
    if holidays is None or special_sessions is None:
        root = Path(base_dir) if base_dir is not None else None
        if root is None:
            try:
                from server.core.install_root import get_install_root

                root = get_install_root()
            except Exception:
                root = Path(__file__).resolve().parents[2]
        cal = load_nse_calendar(root)
        holidays = cal["holidays"] if holidays is None else holidays
        special_sessions = cal["special_sessions"] if special_sessions is None else special_sessions
    hol = holidays or set()
    special = special_sessions or set()
    d = clock.date()
    if is_nse_session_day(d, hol, special) and clock.time() >= BARS_4H_DEFER_UNTIL_IST:
        return d
    d = d - timedelta(days=1)
    for _ in range(400):
        if is_nse_session_day(d, hol, special):
            return d
        d -= timedelta(days=1)
    return clock.date()


def recent_completed_4h_session_dates(
    n: int = BARS_4H_INCREMENTAL_SESSION_DAYS,
    *,
    now: Optional[datetime] = None,
    holidays: Optional[set[str]] = None,
    special_sessions: Optional[set[str]] = None,
    base_dir: Optional[Path] = None,
) -> list[date]:
    """Newest-first list of completed 4H session dates (length up to n)."""
    latest = latest_completed_4h_session_date(
        now=now,
        holidays=holidays,
        special_sessions=special_sessions,
        base_dir=base_dir,
    )
    if n <= 1:
        return [latest]
    clock = now or datetime.now(IST)
    if holidays is None or special_sessions is None:
        root = Path(base_dir) if base_dir is not None else None
        if root is None:
            try:
                from server.core.install_root import get_install_root

                root = get_install_root()
            except Exception:
                root = Path(__file__).resolve().parents[2]
        cal = load_nse_calendar(root)
        holidays = cal["holidays"] if holidays is None else holidays
        special_sessions = cal["special_sessions"] if special_sessions is None else special_sessions
    hol = holidays or set()
    special = special_sessions or set()
    out: list[date] = [latest]
    d = latest - timedelta(days=1)
    while len(out) < max(1, int(n)) and (latest - d).days < 400:
        if is_nse_session_day(d, hol, special):
            out.append(d)
        d -= timedelta(days=1)
    return out


def symbols_needing_4h_refresh(
    conn,
    symbols: Sequence[str],
    latest_session_date: date | str | Sequence[date | str],
) -> list[str]:
    """Symbols missing bars_4h for any of the given completed session date(s)."""
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
        FROM bars_4h
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


def pick_live_session_4h_catchup(
    conn,
    symbols: Sequence[str],
    *,
    max_symbols: int = BARS_4H_LIVE_CATCHUP_MAX,
    min_distinct_sessions: int = BARS_4H_MIN_SESSION_DAYS_FOR_BACKFILL_COMPLETE,
) -> list[str]:
    """
    Cap catch-up during a live-session Update: prefer symbols with zero 4H rows,
    then shallow history — never the full universe on every click.
    """
    needing = symbols_needing_4h_backfill(
        conn, symbols, min_distinct_sessions=min_distinct_sessions
    )
    if not needing or max_symbols <= 0:
        return []
    have = _session_day_counts(conn, needing)
    zero = [s for s in needing if have.get(s, 0) <= 0]
    rest = [s for s in needing if have.get(s, 0) > 0]
    return (zero + rest)[: int(max_symbols)]


def reconcile_4h_backfill_meta(conn, universe_symbols: Sequence[str]) -> None:
    """
    Log shallow symbols without clearing bars_4h_backfill_complete.

    Clearing the flag used to force a full-universe 90d rebuild on the next
    Update. Depth catch-up stays symbol-scoped via symbols_needing_4h_backfill.
    """
    if get_meta(conn, META_BACKFILL_COMPLETE) != "1":
        return
    needing = symbols_needing_4h_backfill(conn, universe_symbols)
    if needing:
        logger.info(
            "bars_4h: %d symbols still shallow (scoped depth catch-up only, e.g. %s)",
            len(needing),
            ", ".join(needing[:8]),
        )


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
        n += 1
    conn.executemany(
        """
        INSERT INTO bars_4h
            (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return n


def upsert_bars_4h_many(conn, symbol_bars: Sequence[tuple[str, Sequence[Bar4H]]]) -> int:
    """Upsert many symbols in one transaction (one commit)."""
    ensure_bars_4h_table(conn)
    total = 0
    insert_rows: list[tuple] = []
    for symbol, bars in symbol_bars:
        if not bars:
            continue
        sym = str(symbol).strip().upper()
        session_dates = {b.session_date for b in bars}
        for sd in session_dates:
            conn.execute(
                "DELETE FROM bars_4h WHERE Symbol=? AND SessionDate=?",
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
            INSERT INTO bars_4h
                (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            insert_rows,
        )
    conn.commit()
    return total


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
    """Yahoo 5m helper — prefer fetch_5m_with_fallback."""
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


def _fetch_5m_upstox(
    symbols: Sequence[str],
    windows: Sequence[tuple[datetime, datetime]],
) -> dict[str, list[tuple]]:
    try:
        from server import upstox_config, upstox_history

        if not upstox_config.market_data_enabled():
            return {}
    except Exception:
        return {}

    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not sym_list or not windows:
        return {}
    accum: dict[str, list[tuple]] = {s: [] for s in sym_list}
    for win_start, win_end in windows:
        chunk = upstox_history.fetch_minutes_for_symbols(sym_list, win_start, win_end, interval="5")
        for sym, rows in chunk.items():
            accum.setdefault(sym, []).extend(rows)
    out: dict[str, list[tuple]] = {}
    for sym, rows in accum.items():
        if not rows:
            continue
        by_ts = {r[0].isoformat(): r for r in rows if r and r[0] is not None}
        out[sym] = [by_ts[k] for k in sorted(by_ts.keys())]
    return out


def fetch_5m_with_fallback(
    symbols: Sequence[str],
    windows: Sequence[tuple[datetime, datetime]],
    base_dir: Path,
) -> dict[str, Fetch5mResult]:
    """
    Upstox 5m only (Update path). No Yahoo / NSE fallback.
    `base_dir` kept for call-site compatibility.
    """
    del base_dir  # unused — Upstox-only path
    sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    out: dict[str, Fetch5mResult] = {}
    if not sym_list or not windows:
        for sym in sym_list:
            out[sym] = Fetch5mResult(rows=[], source="none")
        return out

    # Collapse to one continuous window — Upstox chunks internally (28d).
    win_start = min(w[0] for w in windows)
    win_end = max(w[1] for w in windows)
    upstox_rows = _fetch_5m_upstox(sym_list, [(win_start, win_end)])
    for sym in sym_list:
        rows = upstox_rows.get(sym) or []
        if rows:
            out[sym] = Fetch5mResult(rows=rows, source="upstox")
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
    also_30m: bool = True,
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
        return {
            "updated": 0,
            "failed": 0,
            "skipped": 0,
            "processed": 0,
            "sources": {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0, "failed": 0},
            "misses": [],
        }

    now = datetime.now(IST)
    target_sessions: list[date] = []
    target_session: Optional[date] = None
    if backfill:
        session_dates = _session_dates_back(BARS_4H_HISTORY_SESSION_DAYS, holidays, special)
        if not session_dates:
            session_dates = [now.date()]
        fetch_start = datetime.combine(session_dates[0], SESSION_OPEN, tzinfo=IST)
        end_d = now.date() + timedelta(days=1)
        win_end = datetime.combine(end_d, dtime.min, tzinfo=IST)
        # Single continuous window — Upstox chunks by MINUTE_CHUNK_DAYS internally.
        windows = [(fetch_start, win_end)]
    else:
        # Incremental: cover the latest N completed sessions so mid-window holes refill.
        target_sessions = recent_completed_4h_session_dates(
            BARS_4H_INCREMENTAL_SESSION_DAYS,
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

    updated = 0
    failed = 0
    skipped = 0
    processed = 0
    source_totals = {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0, "failed": 0}
    misses: list[str] = []
    target_session_strs = {d.strftime("%Y-%m-%d") for d in target_sessions}

    upstox_primary = False
    try:
        from server import upstox_config

        upstox_primary = bool(upstox_config.market_data_enabled())
    except Exception:
        upstox_primary = False
    if message_callback:
        if upstox_primary:
            message_callback("4H 5m source: Upstox only (parallel history fetch)")
        else:
            message_callback("4H 5m source: Upstox not configured — symbols will be skipped")

    def _bump_source(src: str) -> None:
        key = "nse" if src == "nse_charting" else (src if src in source_totals else "none")
        source_totals[key] = int(source_totals.get(key) or 0) + 1

    for batch_start in range(0, total, BARS_4H_BATCH_SIZE):
        if cancel_check and cancel_check():
            break
        batch = sym_list[batch_start : batch_start + BARS_4H_BATCH_SIZE]
        fetched = fetch_5m_with_fallback(batch, windows, base_dir)
        pending_upsert: list[tuple[str, list[Bar4H]]] = []
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
                    set_bars_4h_source(conn, sym, "none")
                    misses.append(sym)
                skipped += 1
                processed += 1
                _bump_source(source)
                continue
            bars = aggregate_intraday_to_4h(sym, rows, holidays, special)
            if not backfill and target_session_strs:
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
                upsert_bars_4h_many(conn, pending_upsert)
                for sym, source in pending_sources:
                    set_bars_4h_source(conn, sym, source)
                    updated += 1
                    _bump_source(source)
        except Exception:
            # Fall back per-symbol so one bad row does not lose the whole batch.
            for sym, bars in pending_upsert:
                source = next((s for s0, s in pending_sources if s0 == sym), "upstox")
                try:
                    upsert_bars_4h(conn, sym, bars)
                    set_bars_4h_source(conn, sym, source)
                    updated += 1
                    _bump_source(source)
                except Exception:
                    failed += 1
                    source_totals["failed"] = int(source_totals.get("failed") or 0) + 1

        # Share the same 5m fetch: also write EOD 30m filter bars (no extra Upstox call).
        if also_30m and fetched:
            try:
                from server.bars_30m import META_LAST_SUCCESS as META_30M_LAST_SUCCESS
                from server.bars_30m import write_30m_many_from_5m

                write_30m_many_from_5m(
                    conn,
                    fetched,
                    holidays,
                    special,
                    target_session_strs=(None if backfill else target_session_strs) or None,
                )
                set_meta(conn, META_30M_LAST_SUCCESS, datetime.now(IST).isoformat())
            except Exception as e_30:
                log(f"30m co-write warning: {e_30}")

        if progress_callback:
            progress_callback(processed, total)
        log(
            f"4H bars: {processed}/{total} (updated={updated}, skipped={skipped}, failed={failed}) | "
            f"Source batch: Upstox={batch_src_counts.get('upstox', 0)} "
            f"none={batch_src_counts.get('none', 0)} | "
            f"totals Upstox={source_totals.get('upstox', 0)} none={source_totals.get('none', 0)} "
            f"failed={source_totals.get('failed', 0)}"
        )
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


def bar_start_to_chart_time(bar_start: str) -> Optional[int]:
    try:
        dt = datetime.fromisoformat(str(bar_start))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return int(dt.timestamp())
    except Exception:
        return None
