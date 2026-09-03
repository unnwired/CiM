"""
NSE Daily OHLCV Updater — Upstox only (no Yahoo on Update path)
Fetches missing candles since last date in historical_data and appends them.
On an NSE session day from 09:15–15:30 Asia/Kolkata, re-fetches today's bar (upsert) so
intraday price changes are visible. Before cash open, target the prior session (today's bar
cannot exist yet — a full-universe fetch would empty-fail). After 15:30 IST, new appends only
(no forced today refresh) unless the prior successful run was still before close.
Skip-if-current compares against the latest available NSE session date (not calendar today),
so weekend/holiday/pre-open Updates do not re-fetch the full universe when the prior session
bars are already present.
See data/nse_calendar.json (Tier A: explicit holidays + weekend special sessions).
"""

import json
import sqlite3
import sys
import time
import random
import os
import concurrent.futures
from pathlib import Path
from datetime import datetime, timedelta, date, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent


def console_safe_text(msg) -> str:
    """Strip symbols that break Windows cp1252 console encoding."""
    s = str(msg)
    for src, dst in (
        ("\u26a0\ufe0f", "[!]"),
        ("\u26a0", "[!]"),
        ("\u2713", "[OK]"),
        ("\u2014", "-"),
    ):
        s = s.replace(src, dst)
    return s


def safe_console_print(msg) -> None:
    text = console_safe_text(msg)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
DB_PATH = BASE_DIR / "data" / "nse_data.db"


def connect_db():
    import sys
    root = str(BASE_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    from db_sqlite import connect_sqlite

    return connect_sqlite(DB_PATH)


NSE_CALENDAR_PATH = BASE_DIR / "data" / "nse_calendar.json"
IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN_IST = dtime(9, 15)  # cash open — today's forming bar only exists from here
SESSION_FINAL_IST = dtime(15, 30)  # after this time, do not force-refresh "today"

BATCH_SIZE          = 50    # yfinance handles bulk well
RATE_DELAY_MIN      = 0.8
RATE_DELAY_MAX      = 1.5
# Faster pacing when a batch succeeded via Upstox only (stay under ~50/s with per-request throttle).
RATE_DELAY_UPSTOX_MIN = 0.05
RATE_DELAY_UPSTOX_MAX = 0.15
MAX_CONSEC_FAILURES = 15
PAUSE_ON_BLOCK      = 60
MAX_FAILURE_RATE    = 0.30
SNAPSHOT_TIMEFRAMES = ("30m", "4H", "1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W", "4W", "1M")
SNAPSHOT_LIGHT_TIMEFRAMES = ("30m", "4H", "1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W")
SNAPSHOT_PARALLEL_MODE = str(os.getenv("FLOWX_SNAPSHOT_PARALLEL_MODE", "auto")).strip().lower()
if SNAPSHOT_PARALLEL_MODE not in {"auto", "process", "thread"}:
    SNAPSHOT_PARALLEL_MODE = "auto"
MACD_HIST_CHAIN_MAX_BARS = 60
SNAPSHOT_INDICATOR_FAMILIES = frozenset({"ohlc", "ema", "macd", "stochrsi"})
SNAPSHOT_ALL_FAMILIES = frozenset(SNAPSHOT_INDICATOR_FAMILIES)


def _normalize_snapshot_families(families) -> frozenset:
    if families is None:
        return SNAPSHOT_ALL_FAMILIES
    if isinstance(families, str):
        families = [families]
    out = {str(f).strip().lower() for f in families if str(f).strip()}
    out = {f for f in out if f in SNAPSHOT_INDICATOR_FAMILIES}
    return frozenset(out) if out else SNAPSHOT_ALL_FAMILIES
# Incremental rebuild: trailing daily bars per symbol (EMA200 + MACD chain + weekly rollups).
# 900 daily bars ≈ 191 weekly bars — not enough for EMA200 on 1W; see
# _min_daily_bars_for_snapshot_timeframes() for per-run requirements.
SNAPSHOT_INCREMENTAL_MAX_DAILY_BARS = max(
    260,
    int(os.environ.get("NSE_PULSE_SNAPSHOT_INCREMENTAL_MAX_DAILY_BARS", "1100")),
)

# Longest EMA stored in indicator_snapshots (must stay in sync with build_snapshot_payload).
SNAPSHOT_MAX_EMA_PERIOD = 200
SNAPSHOT_EMA_BUFFER_DAYS = 60
SNAPSHOT_TRADING_DAYS_PER_WEEK = 5


def _min_daily_bars_for_snapshot_timeframes(
    timeframes,
    max_ema_period: int = SNAPSHOT_MAX_EMA_PERIOD,
    buffer_days: int = SNAPSHOT_EMA_BUFFER_DAYS,
) -> int:
    """
    Minimum trailing daily OHLC rows so every requested TF can compute ema{max_ema_period}.
    Incremental rebuild must load at least this many bars or weekly EMA200 stays NULL.
    """
    need = max(max_ema_period + buffer_days, 260)
    for tf in timeframes or ():
        t = str(tf).strip()
        if t in ("30m", "4H"):
            continue
        if t == "1M":
            need = max(need, max_ema_period * 21 + buffer_days)
        elif t.endswith("W"):
            mult = int(t[:-1]) if t[:-1].isdigit() else 1
            need = max(
                need,
                max_ema_period * mult * SNAPSHOT_TRADING_DAYS_PER_WEEK + buffer_days,
            )
        elif t.endswith("D") and t[:-1].isdigit():
            mult = int(t[:-1])
            need = max(need, max_ema_period * mult + buffer_days)
        elif t == "1D":
            need = max(need, max_ema_period + buffer_days)
    return need

_SNAPSHOT_FAMILY_FIELDS = {
    "ohlc": [
        "close_curr", "close_prev", "open_curr", "open_prev",
        "high_curr", "high_prev", "low_curr", "low_prev",
    ],
    "ema": [
        "ema9", "ema9_prev", "ema21", "ema21_prev", "ema50", "ema50_prev",
        "ema100", "ema100_prev", "ema200", "ema200_prev",
    ],
    "macd": [
        "macd", "macd_prev", "macd_signal", "macd_signal_prev", "macd_hist_chain",
    ],
    "stochrsi": ["stoch_k", "stoch_k_prev", "stoch_d", "stoch_d_prev"],
}
_SNAPSHOT_DATA_FIELDS = [
    f for fs in _SNAPSHOT_FAMILY_FIELDS.values() for f in fs
]


def _snapshot_merge_needed(families) -> bool:
    fam = _normalize_snapshot_families(families)
    return fam != SNAPSHOT_ALL_FAMILIES


def _merge_snapshot_rows_with_existing(cursor, rows, families):
    """Preserve columns outside the rebuilt families when upserting partial payloads."""
    if not rows or not _snapshot_merge_needed(families):
        return rows
    fam = _normalize_snapshot_families(families)
    preserve_fields = set()
    for skip in SNAPSHOT_ALL_FAMILIES - fam:
        preserve_fields.update(_SNAPSHOT_FAMILY_FIELDS.get(skip, []))
    merged = []
    col_sql = ", ".join(_SNAPSHOT_DATA_FIELDS)
    for row in rows:
        sym = row["symbol"]
        tf = row["timeframe"]
        cursor.execute(
            f"SELECT {col_sql} FROM indicator_snapshots WHERE symbol = ? AND timeframe = ?",
            (sym, tf),
        )
        existing = cursor.fetchone()
        new_row = {"symbol": sym, "timeframe": tf}
        if existing:
            for i, field in enumerate(_SNAPSHOT_DATA_FIELDS):
                if field in preserve_fields:
                    new_row[field] = existing[i]
                else:
                    new_row[field] = row.get(field, existing[i])
        else:
            for field in _SNAPSHOT_DATA_FIELDS:
                new_row[field] = row.get(field)
        merged.append(new_row)
    return merged


_SNAPSHOT_UPSERT_SQL = """
            INSERT INTO indicator_snapshots (
                symbol, timeframe, close_curr, close_prev, open_curr, open_prev,
                high_curr, high_prev, low_curr, low_prev,
                ema9, ema9_prev, ema21, ema21_prev, ema50, ema50_prev,
                ema100, ema100_prev, ema200, ema200_prev,
                macd, macd_prev, macd_signal, macd_signal_prev,
                macd_hist_chain,
                stoch_k, stoch_k_prev, stoch_d, stoch_d_prev, updated_at
            ) VALUES (
                :symbol, :timeframe, :close_curr, :close_prev, :open_curr, :open_prev,
                :high_curr, :high_prev, :low_curr, :low_prev,
                :ema9, :ema9_prev, :ema21, :ema21_prev, :ema50, :ema50_prev,
                :ema100, :ema100_prev, :ema200, :ema200_prev,
                :macd, :macd_prev, :macd_signal, :macd_signal_prev,
                :macd_hist_chain,
                :stoch_k, :stoch_k_prev, :stoch_d, :stoch_d_prev, CURRENT_TIMESTAMP
            )
            ON CONFLICT(symbol, timeframe) DO UPDATE SET
                close_curr=excluded.close_curr,
                close_prev=excluded.close_prev,
                open_curr=excluded.open_curr,
                open_prev=excluded.open_prev,
                high_curr=excluded.high_curr,
                high_prev=excluded.high_prev,
                low_curr=excluded.low_curr,
                low_prev=excluded.low_prev,
                ema9=excluded.ema9,
                ema9_prev=excluded.ema9_prev,
                ema21=excluded.ema21,
                ema21_prev=excluded.ema21_prev,
                ema50=excluded.ema50,
                ema50_prev=excluded.ema50_prev,
                ema100=excluded.ema100,
                ema100_prev=excluded.ema100_prev,
                ema200=excluded.ema200,
                ema200_prev=excluded.ema200_prev,
                macd=excluded.macd,
                macd_prev=excluded.macd_prev,
                macd_signal=excluded.macd_signal,
                macd_signal_prev=excluded.macd_signal_prev,
                macd_hist_chain=excluded.macd_hist_chain,
                stoch_k=excluded.stoch_k,
                stoch_k_prev=excluded.stoch_k_prev,
                stoch_d=excluded.stoch_d,
                stoch_d_prev=excluded.stoch_d_prev,
                updated_at=CURRENT_TIMESTAMP
        """


def load_nse_calendar():
    """
    Tier A: explicit JSON lists. Missing file => treat as no holidays, no special weekend sessions.
    """
    default = {"holidays": set(), "special_sessions": set()}
    if not NSE_CALENDAR_PATH.is_file():
        return default
    try:
        with open(NSE_CALENDAR_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        h = {str(x) for x in (raw.get("holidays") or []) if x}
        s = {str(x) for x in (raw.get("special_sessions") or []) if x}
        return {"holidays": h, "special_sessions": s}
    except Exception:
        return default


def is_nse_session_day(d: date, holidays: set, special_sessions: set) -> bool:
    """
    Mon–Fri: session unless listed in holidays.
    Sat–Sun: session only if listed in special_sessions.
    """
    ds = d.strftime("%Y-%m-%d")
    w = d.weekday()  # Mon=0 .. Sun=6
    if w < 5:
        return ds not in holidays
    return ds in special_sessions


def now_ist() -> datetime:
    return datetime.now(IST)


def _ist_wall_time(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def after_nse_cash_open(now: datetime) -> bool:
    """True from 09:15 IST onward (matches upstox_history / movers_live cash-open gate)."""
    return _ist_wall_time(now).time() >= SESSION_OPEN_IST


def session_refresh_enabled(session_day: bool, now: datetime) -> bool:
    """True = 09:15–15:30 IST on a session day: may upsert today's forming bar."""
    if not session_day:
        return False
    now = _ist_wall_time(now)
    t = now.time()
    return SESSION_OPEN_IST <= t < SESSION_FINAL_IST


def latest_target_ohlcv_session_date(
    now: datetime,
    holidays: set,
    special_sessions: set,
) -> date:
    """
    Latest NSE session date whose daily bar is the skip-if-current target.

    On a session day from cash open onward: that calendar date (mid-session refreshes
    today's bar via refresh_today; post-close keeps today as the completed target).
    Before 09:15 IST on a session day, and on weekends/holidays: walk back to the prior
    session day so a complete prior-session DB is not treated as stale (Upstox has no
    incomplete daily candle yet, and pre-open quotes must not stamp today).
    """
    now = _ist_wall_time(now)
    d = now.date()
    if is_nse_session_day(d, holidays, special_sessions) and after_nse_cash_open(now):
        return d
    d = d - timedelta(days=1)
    for _ in range(400):
        if is_nse_session_day(d, holidays, special_sessions):
            return d
        d -= timedelta(days=1)
    return now.date()


def symbol_needs_daily_ohlcv_update(
    last_d: Optional[date],
    *,
    target_session: date,
    today_ist: date,
    session_day: bool,
    refresh_today: bool,
    force_post_close_refresh: bool = False,
) -> bool:
    """True if this symbol should be fetched on the current daily Update pass."""
    if force_post_close_refresh:
        return True
    if last_d is None:
        return True
    if last_d < target_session:
        return True
    if refresh_today and session_day and last_d == today_ist:
        return True
    return False


def get_today_ist() -> date:
    return now_ist().date()


def sync_screener_prices_from_latest_bars(conn, log_fn=None) -> int:
    """
    After OHLCV refresh, align screener.price and change_percent with the latest
    two daily closes (works after market close — not only when today's bar exists).
    Skipped during live session on legacy NSE-primary installs only.
    """
    try:
        import sys
        from pathlib import Path

        pkg = Path(__file__).resolve().parents[1]
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        from server import movers_data as md
        from server.product_config import yahoo_primary_pipeline

        if md._session_day_intraday_active() and not yahoo_primary_pipeline():
            if log_fn:
                log_fn("[skip] Screener EOD sync deferred during live session (NSE quotes are authoritative)")
            return 0
    except Exception:
        pass
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE screener SET
            price = (
                SELECT Close FROM historical_data h1
                WHERE h1.Symbol = screener.symbol
                ORDER BY h1.Date DESC LIMIT 1
            ),
            change_percent = ROUND(
                (
                    (SELECT Close FROM historical_data h1
                     WHERE h1.Symbol = screener.symbol ORDER BY h1.Date DESC LIMIT 1)
                    - (SELECT Close FROM historical_data h2
                       WHERE h2.Symbol = screener.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
                )
                / (SELECT Close FROM historical_data h3
                   WHERE h3.Symbol = screener.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1)
                * 100, 2)
        WHERE (
            SELECT COUNT(*) FROM historical_data h
            WHERE h.Symbol = screener.symbol
        ) >= 2
        """
    )
    n = cursor.rowcount
    conn.commit()
    if log_fn and n:
        log_fn(f"[OK] Screener prices synced from latest EOD bars for {n} symbols")
    return n


def write_rows(conn, symbol, rows, overwrite=False):
    cursor = conn.cursor()
    if overwrite:
        for date_str, o, h, l, c, v in rows:
            day = str(date_str)[:10]
            cursor.execute(
                "DELETE FROM historical_data WHERE Symbol=? AND substr(Date,1,10)=?",
                (symbol, day),
            )
    data = [
        (symbol, date_str, o, h, l, c, c, v, None)
        for date_str, o, h, l, c, v in rows
    ]
    if overwrite:
        cursor.executemany(
            "INSERT INTO historical_data (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap) VALUES (?,?,?,?,?,?,?,?,?)",
            data,
        )
    else:
        for date_str, o, h, l, c, v in rows:
            day = str(date_str)[:10]
            cursor.execute(
                "DELETE FROM historical_data WHERE Symbol=? AND substr(Date,1,10)=?",
                (symbol, day),
            )
        cursor.executemany(
            "INSERT INTO historical_data (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap) VALUES (?,?,?,?,?,?,?,?,?)",
            data,
        )
    conn.commit()


def get_last_dates(conn):
    """Returns dict of symbol -> last date in DB."""
    cursor = conn.cursor()
    cursor.execute("SELECT Symbol, MAX(Date) FROM historical_data GROUP BY Symbol")
    result = {}
    for symbol, date_str in cursor.fetchall():
        if date_str:
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                result[symbol] = dt
            except Exception:
                pass
    return result


def get_all_screener_symbols(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM screener WHERE symbol IS NOT NULL AND TRIM(symbol) != ''")
    return [row[0] for row in cursor.fetchall()]


def ensure_updater_meta_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS updater_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()


def get_last_ohlcv_success_ist(conn):
    ensure_updater_meta_table(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM updater_meta WHERE key='ohlcv_last_success_ist'")
    row = cursor.fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(str(row[0]))
    except Exception:
        return None


def set_last_ohlcv_success_ist(conn, dt_obj: datetime):
    ensure_updater_meta_table(conn)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO updater_meta(key, value)
        VALUES ('ohlcv_last_success_ist', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (dt_obj.isoformat(),),
    )
    conn.commit()


def fetch_batch(symbols, start_date, end_date):
    """
    Fetch OHLCV for a batch of symbols — Upstox only (no Yahoo on Update path).
    Returns (dict of symbol -> list of (date, o, h, l, c, v), status_str).
    """
    result = {}
    stats = {"upstox": 0, "yahoo_fallback": 0, "failed": 0}

    try:
        from server import upstox_config, upstox_history

        if not upstox_config.market_data_enabled():
            stats["failed"] = len(symbols)
            fetch_batch.last_stats = stats  # type: ignore[attr-defined]
            return {}, "empty"
        ux_map, _ux_stats = upstox_history.fetch_daily_batch(symbols, start_date, end_date)
        for sym, rows in (ux_map or {}).items():
            if rows:
                result[sym] = rows
                stats["upstox"] += 1
    except Exception:
        stats["failed"] = len(symbols)
        fetch_batch.last_stats = stats  # type: ignore[attr-defined]
        return {}, "empty"

    for sym in symbols:
        if sym not in result:
            stats["failed"] += 1

    fetch_batch.last_stats = stats  # type: ignore[attr-defined]
    if not result:
        return {}, "empty"
    return result, "ok"


def _fetch_batch_yfinance(symbols, start_date, end_date):
    """Yahoo auto_adjust bulk download (fallback)."""
    import yfinance as yf

    # Convert NSE symbols to Yahoo format
    yf_symbols = [f"{s}.NS" for s in symbols]
    start_str  = start_date.strftime("%Y-%m-%d")
    end_str    = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        df = yf.download(
            yf_symbols,
            start=start_str,
            end=end_str,
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
        )
    except Exception as e:
        return {}, str(e)

    if df is None or getattr(df, "empty", True):
        return {}, "empty"

    result = {}

    for sym, yf_sym in zip(symbols, yf_symbols):
        try:
            sym_df = _yfinance_symbol_frame(df, yf_sym, single=len(symbols) == 1)
            if sym_df is None or sym_df.empty:
                continue
            if "Close" not in sym_df.columns:
                continue
            sym_df = sym_df.dropna(subset=["Close"])
            if sym_df.empty:
                continue

            rows = []
            for date, row in sym_df.iterrows():
                try:
                    date_str = date.strftime("%Y-%m-%d") + " 00:00:00+05:30"
                    o = round(float(row["Open"]),   2)
                    h = round(float(row["High"]),   2)
                    l = round(float(row["Low"]),    2)
                    c = round(float(row["Close"]),  2)
                    v = round(float(row["Volume"]), 2)
                    if c <= 0:
                        continue
                    rows.append((date_str, o, h, l, c, v))
                except Exception:
                    continue

            if rows:
                result[sym] = rows

        except Exception:
            continue

    return result, "ok"


def _yfinance_symbol_frame(df, yf_sym: str, *, single: bool):
    """
    Normalize yfinance output to a per-symbol OHLCV frame with flat columns.
    group_by='ticker' yields MultiIndex columns even for a one-symbol download;
    dropna(subset=['Close']) then KeyErrors and silently drops the symbol.
    """
    if df is None or getattr(df, "empty", True):
        return None
    cols = getattr(df, "columns", None)
    if cols is None:
        return None

    # Flat columns already (Open/High/Low/Close/Volume)
    try:
        flat_names = set(str(c) for c in cols)
    except Exception:
        flat_names = set()
    if "Close" in flat_names and not isinstance(cols, getattr(__import__("pandas"), "MultiIndex")):
        return df

    import pandas as pd

    if isinstance(cols, pd.MultiIndex):
        level0 = set(cols.get_level_values(0))
        # (Ticker, Price) — preferred group_by=ticker shape
        if yf_sym in level0:
            return df[yf_sym]
        # Single-ticker download sometimes nests as (Price, Ticker)
        if "Close" in level0 and yf_sym in set(cols.get_level_values(1)):
            out = df.xs(yf_sym, axis=1, level=1)
            return out
        if single and "Close" in level0 and len(level0) <= 6:
            # Only one ticker present under Price-first MultiIndex
            try:
                return df.droplevel(1, axis=1)
            except Exception:
                pass
        if single and len(level0) == 1:
            only = next(iter(level0))
            return df[only]
        return None

    if single:
        return df
    return None


def ensure_indicator_snapshot_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS indicator_snapshots (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            close_curr REAL,
            close_prev REAL,
            open_curr REAL,
            open_prev REAL,
            high_curr REAL,
            high_prev REAL,
            low_curr REAL,
            low_prev REAL,
            ema9 REAL,
            ema9_prev REAL,
            ema21 REAL,
            ema21_prev REAL,
            ema50 REAL,
            ema50_prev REAL,
            ema100 REAL,
            ema100_prev REAL,
            ema200 REAL,
            ema200_prev REAL,
            macd REAL,
            macd_prev REAL,
            macd_signal REAL,
            macd_signal_prev REAL,
            macd_hist_chain TEXT,
            stoch_k REAL,
            stoch_k_prev REAL,
            stoch_d REAL,
            stoch_d_prev REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, timeframe)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_indicator_snapshots_tf_symbol ON indicator_snapshots(timeframe, symbol)"
    )
    # Lightweight migration for existing databases.
    cursor.execute("PRAGMA table_info(indicator_snapshots)")
    cols = {str(r[1]).strip().lower() for r in cursor.fetchall() if len(r) > 1}
    if "macd_hist_chain" not in cols:
        cursor.execute("ALTER TABLE indicator_snapshots ADD COLUMN macd_hist_chain TEXT")
    conn.commit()


def aggregate_to_weekly(candles):
    groups = {}
    for c in candles:
        try:
            dt = datetime.strptime(str(c[0])[:10], "%Y-%m-%d")
            monday = dt - timedelta(days=dt.weekday())
            key = monday.strftime("%Y-%m-%d")
            groups.setdefault(key, []).append(c)
        except Exception:
            continue
    out = []
    for key in sorted(groups.keys()):
        g0 = groups[key]
        # Some historical rows can have NULL OHLC fields; skip incomplete candles.
        g = [x for x in g0 if x[1] is not None and x[2] is not None and x[3] is not None and x[4] is not None]
        if not g:
            continue
        out.append((key, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]))
    return out


def aggregate_to_monthly(candles):
    groups = {}
    for c in candles:
        key = str(c[0])[:7]
        groups.setdefault(key, []).append(c)
    out = []
    for key in sorted(groups.keys()):
        g0 = groups[key]
        g = [x for x in g0 if x[1] is not None and x[2] is not None and x[3] is not None and x[4] is not None]
        if not g:
            continue
        out.append((key, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]))
    return out


def aggregate_to_nday_local(candles, n):
    """Backward compatibility wrapper (default day-based bucketing)."""
    return aggregate_to_nperiod_local(candles, n, "day")


def _parse_bucket_date_local(raw_dt):
    s = str(raw_dt)
    if len(s) >= 7 and s[4] == "-" and len(s) < 10:
        return datetime.strptime(s[:7] + "-01", "%Y-%m-%d")
    return datetime.strptime(s[:10], "%Y-%m-%d")


def aggregate_to_nperiod_local(candles, n, unit):
    """
    Aggregate into fixed calendar buckets so the latest forming bar is always
    the active last bar (applies consistently across D/W/M families).
    """
    if n <= 1:
        return candles
    groups = {}
    for c in candles:
        try:
            if c[1] is None or c[2] is None or c[3] is None or c[4] is None:
                continue
            dt = _parse_bucket_date_local(c[0])
            if unit == "week":
                anchor = datetime(1970, 1, 5)  # Monday anchor
                weeks_from_anchor = (dt - anchor).days // 7
                bucket_weeks = (weeks_from_anchor // n) * n
                bucket_start = anchor + timedelta(weeks=bucket_weeks)
            elif unit == "month":
                month_index = dt.year * 12 + (dt.month - 1)
                bucket_index = (month_index // n) * n
                bucket_start = datetime(bucket_index // 12, (bucket_index % 12) + 1, 1)
            else:
                anchor = datetime(1970, 1, 1)
                days_from_anchor = (dt - anchor).days
                bucket_days = (days_from_anchor // n) * n
                bucket_start = anchor + timedelta(days=bucket_days)
            key = bucket_start.strftime("%Y-%m-%d")
            groups.setdefault(key, []).append(c)
        except Exception:
            continue
    out = []
    for key in sorted(groups.keys()):
        g = groups[key]
        if not g:
            continue
        out.append((key, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]))
    return out


def calc_ema_series_local(closes, period):
    if len(closes) < period:
        return []
    arr = [float(x) for x in closes]
    k = 2.0 / (period + 1)
    result = [arr[0]]
    for i in range(1, len(arr)):
        result.append(arr[i] * k + result[-1] * (1 - k))
    return result


def calculate_macd_local(closes, fast=12, slow=26, signal=9):
    n = len(closes)
    if n < slow:
        return {"macd": [None] * n, "signal": [None] * n, "histogram": [None] * n}

    def ema_full(data, period):
        k = 2.0 / (period + 1)
        ema = data[0]
        out = [ema]
        for p in data[1:]:
            ema = p * k + ema * (1 - k)
            out.append(ema)
        return out

    arr = [float(x) for x in closes]
    fast_ema = ema_full(arr, fast)
    slow_ema = ema_full(arr, slow)
    macd_raw = [f - s for f, s in zip(fast_ema, slow_ema)]
    sig_input = macd_raw[slow - 1:]
    if len(sig_input) < signal:
        return {"macd": [None] * n, "signal": [None] * n, "histogram": [None] * n}
    sig_ema = ema_full(sig_input, signal)
    macd_out = [None] * (slow - 1) + macd_raw[slow - 1:]
    sig_out = [None] * (slow - 1 + signal - 1) + sig_ema[signal - 1:]
    hist_out = []
    for m, s in zip(macd_out, sig_out):
        if m is not None and s is not None:
            hist_out.append(m - s)
        else:
            hist_out.append(None)
    return {"macd": macd_out, "signal": sig_out, "histogram": hist_out}


def calculate_stochrsi_local(closes, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3):
    arr = [float(x) for x in closes]
    n = len(arr)
    if n <= rsi_period:
        return {"k": [None] * n, "d": [None] * n}

    deltas = [arr[i] - arr[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [abs(min(d, 0.0)) for d in deltas]

    rsi = [None] * n
    avg_gain = sum(gains[:rsi_period]) / rsi_period
    avg_loss = sum(losses[:rsi_period]) / rsi_period
    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    rsi[rsi_period] = 100 - (100 / (1 + rs))
    for i in range(rsi_period + 1, n):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = ((avg_gain * (rsi_period - 1)) + gain) / rsi_period
        avg_loss = ((avg_loss * (rsi_period - 1)) + loss) / rsi_period
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        rsi[i] = 100 - (100 / (1 + rs))

    stoch_raw = [None] * n
    for i in range(n):
        if i < rsi_period + stoch_period - 1:
            continue
        window = [v for v in rsi[i - stoch_period + 1:i + 1] if v is not None]
        if len(window) < stoch_period:
            continue
        lo = min(window)
        hi = max(window)
        stoch_raw[i] = 0.0 if hi == lo else ((rsi[i] - lo) / (hi - lo)) * 100

    def sma(series, period):
        out = [None] * len(series)
        for i in range(period - 1, len(series)):
            window = [v for v in series[i - period + 1:i + 1] if v is not None]
            if len(window) == period:
                out[i] = sum(window) / period
        return out

    k = sma(stoch_raw, k_smooth)
    d = sma(k, d_smooth)
    return {"k": k, "d": d}


def last_two(series):
    valid = [v for v in series if v is not None]
    if len(valid) < 2:
        return None, None
    return round(float(valid[-1]), 4), round(float(valid[-2]), 4)


def _load_snapshot_bars_module():
    """Chart-parity bars + MACD (repo: packages/server; distro: server/)."""
    import importlib.util
    import sys
    root = Path(__file__).resolve().parent
    mod_name = "cim_snapshot_bars"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    candidates = (
        root / "packages" / "server" / "snapshot_bars.py",
        root / "server" / "snapshot_bars.py",
    )
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise RuntimeError(
            "Cannot load snapshot_bars.py — expected at "
            + " or ".join(str(p) for p in candidates)
        )
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load snapshot_bars from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[mod_name] = mod
    return mod


def build_snapshot_payload(symbol, timeframe, candles, families=None):
    if len(candles) < 3:
        return None
    fam = _normalize_snapshot_families(families)
    closes = [float(c[4]) for c in candles]
    last = candles[-1]
    prev = candles[-2]
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
    }
    if "ohlc" in fam:
        payload.update({
            "close_curr": round(float(last[4]), 4),
            "close_prev": round(float(prev[4]), 4),
            "open_curr": round(float(last[1]), 4),
            "open_prev": round(float(prev[1]), 4),
            "high_curr": round(float(last[2]), 4),
            "high_prev": round(float(prev[2]), 4),
            "low_curr": round(float(last[3]), 4),
            "low_prev": round(float(prev[3]), 4),
        })
    if "ema" in fam:
        for period in (9, 21, 50, 100, 200):
            curr, prev_val = last_two(calc_ema_series_local(closes, period))
            payload[f"ema{period}"] = curr
            payload[f"ema{period}_prev"] = prev_val
    if "macd" in fam:
        sb = _load_snapshot_bars_module()
        macd = sb.calculate_macd(closes, fast=12, slow=26, signal=9)
        payload["macd"], payload["macd_prev"] = last_two(macd["macd"])
        payload["macd_signal"], payload["macd_signal_prev"] = last_two(macd["signal"])
        hist_valid = [round(float(v), 4) for v in macd["histogram"] if v is not None]
        payload["macd_hist_chain"] = "|".join(
            f"{v:.4f}" for v in hist_valid[-MACD_HIST_CHAIN_MAX_BARS:]
        ) if hist_valid else None
    if "stochrsi" in fam:
        stoch = calculate_stochrsi_local(closes, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3)
        payload["stoch_k"], payload["stoch_k_prev"] = last_two(stoch["k"])
        payload["stoch_d"], payload["stoch_d_prev"] = last_two(stoch["d"])
    return payload


def _build_snapshot_rows_for_symbol(
    sym, candles, allowed_timeframes=None, bars_4h_series=None, bars_30m_series=None, families=None
):
    rows = []
    allowed = set(allowed_timeframes) if allowed_timeframes else None
    sb = _load_snapshot_bars_module()
    for timeframe in SNAPSHOT_TIMEFRAMES:
        if allowed is not None and timeframe not in allowed:
            continue
        if timeframe == "4H":
            series = list(bars_4h_series or [])
        elif timeframe == "30m":
            series = list(bars_30m_series or [])
        else:
            series = sb.chart_candles_for_timeframe(candles, timeframe)
        if len(series) < 3:
            continue
        payload = build_snapshot_payload(sym, timeframe, series, families=families)
        if payload is not None:
            rows.append(payload)
    return rows


def _build_snapshot_rows_for_chunk(
    chunk_items,
    allowed_timeframes=None,
    bars_4h_by_symbol=None,
    families=None,
    bars_30m_by_symbol=None,
):
    out = []
    bars_map = bars_4h_by_symbol or {}
    bars_30m_map = bars_30m_by_symbol or {}
    for sym, candles in chunk_items:
        out.extend(
            _build_snapshot_rows_for_symbol(
                sym,
                candles,
                allowed_timeframes=allowed_timeframes,
                bars_4h_series=bars_map.get(sym),
                bars_30m_series=bars_30m_map.get(sym),
                families=families,
            )
        )
    return out, len(chunk_items)


def _is_incremental_snapshot_run(symbols_override, clear_first) -> bool:
    return symbols_override is not None and not clear_first


def _load_candles_batch(cursor, sym_batch, max_daily_bars=None):
    """Load OHLC tuples per symbol; optional cap on trailing daily bars (incremental safe path)."""
    if not sym_batch:
        return {}
    placeholders = ",".join(["?"] * len(sym_batch))
    candles_by_symbol = {sym: [] for sym in sym_batch}
    params = list(sym_batch)
    if max_daily_bars is None or int(max_daily_bars) <= 0:
        cursor.execute(
            f"SELECT Symbol, SUBSTR(Date,1,10) as dt, Open, High, Low, Close "
            f"FROM historical_data WHERE Symbol IN ({placeholders}) "
            f"ORDER BY Symbol ASC, Date ASC",
            params,
        )
    else:
        n = int(max_daily_bars)
        cursor.execute(
            f"SELECT Symbol, dt, Open, High, Low, Close FROM ("
            f"  SELECT Symbol, SUBSTR(Date,1,10) as dt, Open, High, Low, Close,"
            f"         ROW_NUMBER() OVER (PARTITION BY Symbol ORDER BY Date DESC) AS rn"
            f"  FROM historical_data WHERE Symbol IN ({placeholders})"
            f") WHERE rn <= ? ORDER BY Symbol ASC, dt ASC",
            params + [n],
        )
    for row in cursor:
        if row[2] is None or row[3] is None or row[4] is None or row[5] is None:
            continue
        candles_by_symbol.setdefault(row[0], []).append((row[1], row[2], row[3], row[4], row[5]))
    return candles_by_symbol


def _delete_snapshots_for_symbols(conn, symbols, timeframes):
    if not symbols or not timeframes:
        return
    tf_placeholders = ",".join(["?"] * len(timeframes))
    sym_placeholders = ",".join(["?"] * len(symbols))
    conn.execute(
        f"DELETE FROM indicator_snapshots WHERE timeframe IN ({tf_placeholders}) AND symbol IN ({sym_placeholders})",
        list(timeframes) + list(symbols),
    )


def _compute_snapshot_rows_parallel(
    items, requested_timeframes, log, bars_4h_by_symbol=None, families=None, bars_30m_by_symbol=None
):
    snapshot_rows = []
    if not items:
        return snapshot_rows
    workers = max(1, min(4, os.cpu_count() or 1))
    chunk_size = max(5, len(items) // max(1, workers * 2))
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
    effective_mode = SNAPSHOT_PARALLEL_MODE
    if effective_mode == "auto":
        effective_mode = "thread" if os.name == "nt" else "process"

    def _consume_chunk(chunk):
        rows_chunk, _processed = _build_snapshot_rows_for_chunk(
            chunk,
            requested_timeframes,
            bars_4h_by_symbol,
            families=families,
            bars_30m_by_symbol=bars_30m_by_symbol,
        )
        return rows_chunk

    if workers <= 1 or len(chunks) <= 1:
        for chunk in chunks:
            snapshot_rows.extend(_consume_chunk(chunk))
    elif effective_mode == "process":
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(
                        _build_snapshot_rows_for_chunk,
                        c,
                        requested_timeframes,
                        bars_4h_by_symbol,
                        families,
                        bars_30m_by_symbol,
                    )
                    for c in chunks
                ]
                for fut in concurrent.futures.as_completed(futures):
                    snapshot_rows.extend(fut.result()[0])
        except Exception:
            log("[perf] snapshots: Process mode unavailable; falling back to thread mode.")
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, workers)) as pool:
                futures = [
                    pool.submit(
                        _build_snapshot_rows_for_chunk,
                        c,
                        requested_timeframes,
                        bars_4h_by_symbol,
                        families,
                        bars_30m_by_symbol,
                    )
                    for c in chunks
                ]
                for fut in concurrent.futures.as_completed(futures):
                    snapshot_rows.extend(fut.result()[0])
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, workers)) as pool:
            futures = [
                pool.submit(
                    _build_snapshot_rows_for_chunk,
                    c,
                    requested_timeframes,
                    bars_4h_by_symbol,
                    families,
                    bars_30m_by_symbol,
                )
                for c in chunks
            ]
            for fut in concurrent.futures.as_completed(futures):
                snapshot_rows.extend(fut.result()[0])
    return snapshot_rows


def _rebuild_indicator_snapshots_incremental_safe(
    conn,
    cursor,
    symbols,
    requested_timeframes,
    max_daily_bars,
    log,
    progress_callback,
    t_total_start,
    families=None,
):
    """Bounded OHLC load, per-batch compute, delete+write only after successful compute."""
    total_syms = len(symbols)
    upsert_sql = _SNAPSHOT_UPSERT_SQL
    default_batch = int(os.environ.get("NSE_PULSE_SNAPSHOT_INCREMENTAL_BATCH", "50"))
    load_batch = int(os.environ.get("NSE_PULSE_SNAPSHOT_LOAD_BATCH", str(default_batch)))
    load_batch = max(1, min(load_batch, 200))
    symbol_batches = [symbols[i:i + load_batch] for i in range(0, len(symbols), load_batch)]
    n_sym_batches = len(symbol_batches)
    effective_max_bars = max(
        int(max_daily_bars),
        _min_daily_bars_for_snapshot_timeframes(requested_timeframes),
    )
    log(
        f"Incremental safe path: {n_sym_batches} batch(es) (~{load_batch} symbols), "
        f"last {effective_max_bars} daily bars/symbol "
        f"(requested {max_daily_bars}, min for TFs {effective_max_bars}), "
        f"delete-after-compute per batch."
    )
    if progress_callback:
        progress_callback(0, total_syms)

    processed_syms = 0
    total_rows = 0
    hist_chain_rows = 0
    hist_chain_full = 0

    for bi, sym_batch in enumerate(symbol_batches):
        t_batch = time.perf_counter()
        candles_by_symbol = _load_candles_batch(
            cursor, sym_batch, max_daily_bars=effective_max_bars
        )
        items = list(candles_by_symbol.items())
        bars_4h_batch = {}
        if "4H" in requested_timeframes:
            try:
                from server.bars_4h import load_bars_4h_candles_batch

                bars_4h_batch = load_bars_4h_candles_batch(conn, sym_batch)
            except Exception:
                bars_4h_batch = {}
        bars_30m_batch = {}
        if "30m" in requested_timeframes:
            try:
                from server.bars_30m import load_bars_30m_candles_batch

                bars_30m_batch = load_bars_30m_candles_batch(conn, sym_batch)
            except Exception:
                bars_30m_batch = {}
        snapshot_rows = _compute_snapshot_rows_parallel(
            items,
            requested_timeframes,
            log,
            bars_4h_by_symbol=bars_4h_batch,
            families=families,
            bars_30m_by_symbol=bars_30m_batch,
        )
        if snapshot_rows:
            if not _snapshot_merge_needed(families):
                _delete_snapshots_for_symbols(conn, sym_batch, requested_timeframes)
            snapshot_rows = _merge_snapshot_rows_with_existing(cursor, snapshot_rows, families)
            cursor.executemany(upsert_sql, snapshot_rows)
            conn.commit()
            total_rows += len(snapshot_rows)
            hist_chain_rows += sum(1 for r in snapshot_rows if r.get("macd_hist_chain"))
            hist_chain_full += sum(
                1 for r in snapshot_rows
                if r.get("macd_hist_chain")
                and len(str(r["macd_hist_chain"]).split("|")) >= MACD_HIST_CHAIN_MAX_BARS
            )
        processed_syms += len(sym_batch)
        if progress_callback:
            p = min(total_syms, max(0, processed_syms))
            if processed_syms < total_syms:
                p = min(p, max(0, total_syms - 1))
            progress_callback(p, total_syms)
        del candles_by_symbol, snapshot_rows, items
        t_batch_ms = int((time.perf_counter() - t_batch) * 1000)
        log(f"[perf] snapshots batch {bi + 1}/{n_sym_batches}: {len(sym_batch)} symbols in {t_batch_ms}ms")

    if progress_callback:
        progress_callback(total_syms, total_syms)
    hist_pct = (100.0 * hist_chain_full / hist_chain_rows) if hist_chain_rows else 0.0
    total_ms = int((time.perf_counter() - t_total_start) * 1000)
    log(
        f"[perf] snapshots incremental safe: {total_rows} rows for {total_syms} symbols in {total_ms}ms"
    )
    log(
        f"macd_hist_chain: {hist_chain_rows} rows with chain, "
        f"{hist_chain_full} with >={MACD_HIST_CHAIN_MAX_BARS} bars ({hist_pct:.1f}%)"
    )
    log(
        f"✓ Indicator snapshots updated for {len(symbols)} stocks across {', '.join(requested_timeframes)}"
    )
    return len(symbols)


def rebuild_indicator_snapshots_universe(
    clear_first=False,
    log_fn=None,
    progress_callback=None,
    message_callback=None,
    symbols_override=None,
    timeframes_override=None,
    families_override=None,
):
    """
    Rebuild indicator_snapshots for all screener symbols from historical_data.
    If clear_first is True, deletes all snapshot rows first (full rebuild).
    Returns the number of screener symbols processed.
    """
    def log(msg):
        line = console_safe_text(msg)
        if log_fn:
            log_fn(line)
        else:
            safe_console_print(line)
        if message_callback:
            message_callback(line)

    t_total_start = time.perf_counter()
    conn = connect_db()
    try:
        ensure_indicator_snapshot_table(conn)
        requested_timeframes = tuple(
            tf for tf in (timeframes_override or SNAPSHOT_TIMEFRAMES)
            if tf in SNAPSHOT_TIMEFRAMES
        )
        if not requested_timeframes:
            requested_timeframes = SNAPSHOT_TIMEFRAMES
        families = _normalize_snapshot_families(families_override)
        if clear_first:
            log("Clearing existing indicator snapshot rows...")
            conn.execute("DELETE FROM indicator_snapshots")
            conn.commit()

        cursor = conn.cursor()
        if symbols_override is not None:
            symbols = [str(s).strip().upper() for s in symbols_override if str(s).strip()]
        else:
            cursor.execute("SELECT symbol FROM screener")
            symbols_rows = cursor.fetchall()
            symbols = [r[0] for r in symbols_rows if r[0]]
        total_syms = len(symbols)
        if not symbols:
            log("No symbols in screener; nothing to snapshot.")
            return 0

        incremental_safe = _is_incremental_snapshot_run(symbols_override, clear_first)
        if incremental_safe:
            max_bars = SNAPSHOT_INCREMENTAL_MAX_DAILY_BARS
            return _rebuild_indicator_snapshots_incremental_safe(
                conn,
                cursor,
                symbols,
                requested_timeframes,
                max_bars,
                log,
                progress_callback,
                t_total_start,
                families=families,
            )

        if progress_callback:
            progress_callback(0, total_syms)

        # Progress mapping: load 0–40%, compute 40–95%, write 95–100% of [0, total_syms].
        def report_load_batch(batch_index: int, n_batches: int) -> None:
            if not progress_callback or n_batches <= 0:
                return
            p = min(
                total_syms,
                max(0, round(total_syms * 0.40 * (batch_index + 1) / n_batches)),
            )
            progress_callback(p, total_syms)

        def report_compute_progress(processed_symbols: int) -> None:
            if not progress_callback or total_syms <= 0:
                return
            frac = min(1.0, max(0.0, processed_symbols / total_syms))
            p = round(total_syms * (0.40 + 0.55 * frac))
            if processed_symbols < total_syms:
                p = min(p, max(0, total_syms - 1))
            else:
                p = min(total_syms, max(0, p))
            progress_callback(p, total_syms)

        t_load_start = time.perf_counter()
        candles_by_symbol = {sym: [] for sym in symbols}
        load_batch = int(os.environ.get("NSE_PULSE_SNAPSHOT_LOAD_BATCH", "120"))
        load_batch = max(1, min(load_batch, 400))
        symbol_batches = [symbols[i : i + load_batch] for i in range(0, len(symbols), load_batch)]
        n_sym_batches = len(symbol_batches)
        log(
            f"Loading OHLC from historical_data in {n_sym_batches} batch(es) "
            f"(~{load_batch} symbols each; first progress may take a minute on large DBs)…"
        )
        for bi, sym_batch in enumerate(symbol_batches):
            placeholders = ",".join(["?"] * len(sym_batch))
            cursor.execute(
                f"SELECT Symbol, SUBSTR(Date,1,10) as dt, Open, High, Low, Close "
                f"FROM historical_data WHERE Symbol IN ({placeholders}) "
                f"ORDER BY Symbol ASC, Date ASC",
                sym_batch,
            )
            for row in cursor:
                if row[2] is None or row[3] is None or row[4] is None or row[5] is None:
                    continue
                candles_by_symbol.setdefault(row[0], []).append((row[1], row[2], row[3], row[4], row[5]))
            report_load_batch(bi, n_sym_batches)
        t_load_ms = int((time.perf_counter() - t_load_start) * 1000)
        log(f"[perf] snapshots: loaded candles for {len(symbols)} symbols in {t_load_ms}ms")

        bars_4h_by_symbol = {}
        if "4H" in requested_timeframes:
            try:
                from server.bars_4h import load_bars_4h_candles_batch

                bars_4h_by_symbol = load_bars_4h_candles_batch(conn, symbols)
                log(f"Loaded 4H bars for snapshot rebuild ({len(bars_4h_by_symbol)} symbols).")
            except Exception as e4:
                log(f"[!] 4H snapshot load warning: {e4}")

        bars_30m_by_symbol = {}
        if "30m" in requested_timeframes:
            try:
                from server.bars_30m import load_bars_30m_candles_batch

                bars_30m_by_symbol = load_bars_30m_candles_batch(conn, symbols)
                log(f"Loaded 30m bars for snapshot rebuild ({len(bars_30m_by_symbol)} symbols).")
            except Exception as e30:
                log(f"[!] 30m snapshot load warning: {e30}")

        upsert_sql = _SNAPSHOT_UPSERT_SQL

        t_compute_start = time.perf_counter()
        snapshot_rows = []
        done = 0
        items = list(candles_by_symbol.items())
        workers = max(1, min(8, os.cpu_count() or 1))
        chunk_size = max(10, len(items) // (workers * 4) if workers > 0 else 25)
        chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

        effective_mode = SNAPSHOT_PARALLEL_MODE
        if effective_mode == "auto":
            # Windows packaged/runtime installs often hit ProcessPool pickling issues.
            effective_mode = "thread" if os.name == "nt" else "process"

        if workers <= 1 or len(chunks) <= 1:
            for chunk in chunks:
                rows_chunk, processed = _build_snapshot_rows_for_chunk(
                    chunk,
                    requested_timeframes,
                    bars_4h_by_symbol,
                    families=families,
                    bars_30m_by_symbol=bars_30m_by_symbol,
                )
                snapshot_rows.extend(rows_chunk)
                done += processed
                report_compute_progress(done)
        elif effective_mode == "process":
            # Prefer process pool when explicitly requested or on stable environments.
            try:
                with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = [
                        pool.submit(
                            _build_snapshot_rows_for_chunk,
                            c,
                            requested_timeframes,
                            bars_4h_by_symbol,
                            families,
                            bars_30m_by_symbol,
                        )
                        for c in chunks
                    ]
                    for fut in concurrent.futures.as_completed(futures):
                        rows_chunk, processed = fut.result()
                        snapshot_rows.extend(rows_chunk)
                        done += processed
                        report_compute_progress(done)
            except Exception as e:
                log("[perf] snapshots: Process mode unavailable; falling back to thread mode.")
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, min(8, workers))) as pool:
                    futures = [
                        pool.submit(
                            _build_snapshot_rows_for_chunk,
                            c,
                            requested_timeframes,
                            bars_4h_by_symbol,
                            families,
                            bars_30m_by_symbol,
                        )
                        for c in chunks
                    ]
                    for fut in concurrent.futures.as_completed(futures):
                        rows_chunk, processed = fut.result()
                        snapshot_rows.extend(rows_chunk)
                        done += processed
                        report_compute_progress(done)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, min(8, workers))) as pool:
                futures = [
                    pool.submit(
                        _build_snapshot_rows_for_chunk,
                        c,
                        requested_timeframes,
                        bars_4h_by_symbol,
                        families,
                        bars_30m_by_symbol,
                    )
                    for c in chunks
                ]
                for fut in concurrent.futures.as_completed(futures):
                    rows_chunk, processed = fut.result()
                    snapshot_rows.extend(rows_chunk)
                    done += processed
                    report_compute_progress(done)
        t_compute_ms = int((time.perf_counter() - t_compute_start) * 1000)
        hist_chain_rows = sum(1 for r in snapshot_rows if r.get("macd_hist_chain"))
        hist_chain_full = sum(
            1 for r in snapshot_rows
            if r.get("macd_hist_chain") and len(str(r["macd_hist_chain"]).split("|")) >= MACD_HIST_CHAIN_MAX_BARS
        )
        hist_pct = (100.0 * hist_chain_full / hist_chain_rows) if hist_chain_rows else 0.0
        log(
            f"[perf] snapshots: computed {len(snapshot_rows)} rows in {t_compute_ms}ms "
            f"(symbols={total_syms}, workers={workers}, chunks={len(chunks)}, mode={effective_mode})"
        )
        log(
            f"macd_hist_chain: {hist_chain_rows} rows with chain, "
            f"{hist_chain_full} with >={MACD_HIST_CHAIN_MAX_BARS} bars ({hist_pct:.1f}%)"
        )

        t_write_start = time.perf_counter()
        if snapshot_rows:
            if progress_callback:
                p = min(total_syms, max(0, round(total_syms * 0.96)))
                progress_callback(p, total_syms)
            snapshot_rows = _merge_snapshot_rows_with_existing(cursor, snapshot_rows, families)
            cursor.executemany(upsert_sql, snapshot_rows)
            conn.commit()
        if progress_callback:
            progress_callback(total_syms, total_syms)
        t_write_ms = int((time.perf_counter() - t_write_start) * 1000)
        total_ms = int((time.perf_counter() - t_total_start) * 1000)
        log(f"[perf] snapshots: wrote rows in {t_write_ms}ms; total rebuild stage {total_ms}ms")
        log(
            f"✓ Indicator snapshots updated for {len(symbols)} stocks across {', '.join(requested_timeframes)}"
        )
        return len(symbols)
    finally:
        conn.close()


def run(progress_callback=None, message_callback=None, refresh_snapshots=False, cancel_check=None):
    try:
        from server.admin_job_control import JobCancelled, sleep_interruptible
    except ImportError:
        class JobCancelled(Exception):
            pass

        def sleep_interruptible(seconds, cancel_check=None):
            time.sleep(seconds)

    def _check_cancel():
        if cancel_check and cancel_check():
            try:
                conn.close()
            except Exception:
                pass
            raise JobCancelled()

    def log(msg):
        line = console_safe_text(msg)
        safe_console_print(line)
        if message_callback:
            message_callback(line)

    log("Connecting to database...")
    conn = connect_db()

    log("Reading last dates from database...")
    last_dates = get_last_dates(conn)

    try:
        from symbol_lineage import (
            lineage_backfill_needed,
            list_lineage_canonicals,
            run_lineage_backfill,
        )

        for sym in list_lineage_canonicals():
            _check_cancel()
            if lineage_backfill_needed(conn, sym):
                log(f"Lineage backfill required for {sym} (rename-aware history)…")
                result = run_lineage_backfill(conn, sym, log=log)
                if result.get("ok"):
                    log(
                        f"✓ Lineage {sym}: {result.get('rows_written')} rows "
                        f"({result.get('min_date')} → {result.get('max_date')})"
                    )
                else:
                    log(f"[!] Lineage {sym} failed: {result.get('error')}")
        last_dates = get_last_dates(conn)
    except Exception as e:
        log(f"[!] Lineage backfill step skipped: {e}")

    cal      = load_nse_calendar()
    holidays = cal["holidays"]
    special  = cal["special_sessions"]

    ist_clock = now_ist()
    today_ist = ist_clock.date()
    today_end = datetime.combine(today_ist, datetime.min.time())
    after_cutoff = ist_clock.time() >= SESSION_FINAL_IST

    session_day = is_nse_session_day(today_ist, holidays, special)
    refresh_today = session_refresh_enabled(session_day, ist_clock)
    target_session = latest_target_ohlcv_session_date(ist_clock, holidays, special)
    last_success_ist = get_last_ohlcv_success_ist(conn)
    force_post_close_refresh = (
        session_day
        and after_cutoff
        and last_success_ist is not None
        and last_success_ist.date() == today_ist
        and last_success_ist.time() < SESSION_FINAL_IST
    )

    log(
        f"IST now: {ist_clock.strftime('%Y-%m-%d %H:%M')} — "
        f"session_day={session_day}, target_session={target_session.isoformat()}, "
        f"refresh_today_0915_1530_IST={refresh_today}, "
        f"force_post_close_refresh={force_post_close_refresh}"
    )
    if last_success_ist is not None:
        log(f"Last successful OHLCV run (IST): {last_success_ist.strftime('%Y-%m-%d %H:%M:%S')}")

    universe_syms = get_all_screener_symbols(conn)
    to_update = {}
    if force_post_close_refresh:
        # If the prior run was before close, force-refresh today's bar for all symbols.
        anchor = datetime.combine(today_ist, datetime.min.time())
        for sym in universe_syms:
            to_update[sym] = anchor
    else:
        for sym, dt in last_dates.items():
            last_d = dt.date() if hasattr(dt, "date") else dt
            if symbol_needs_daily_ohlcv_update(
                last_d,
                target_session=target_session,
                today_ist=today_ist,
                session_day=session_day,
                refresh_today=refresh_today,
            ):
                to_update[sym] = dt
        # Screener symbols with no historical_data yet (never picked up by incremental-only loop)
        hist_syms = set(last_dates.keys())
        for sym in universe_syms:
            if sym not in hist_syms and sym not in to_update:
                to_update[sym] = datetime(1989, 12, 31)

    skipped_current = sum(1 for s in universe_syms if s not in to_update)
    if not to_update:
        log(f"All symbols are up to date (skipped_current={skipped_current}).")
        conn.close()
        return {
            "updated": 0,
            "bhav_screener_written": 0,
            "skipped_current": skipped_current,
            "fetch_stats": {"upstox": 0, "yahoo_fallback": 0, "nse": 0, "failed": 0},
        }

    log(f"Found {len(to_update)} symbols needing updates ({skipped_current} already current).")

    symbols  = list(to_update.keys())
    total    = len(symbols)
    updated  = 0
    failed   = 0
    skipped  = 0
    consec_failures = 0

    date_groups = {}
    for sym, last_dt in to_update.items():
        last_d = last_dt.date() if hasattr(last_dt, "date") else last_dt
        if force_post_close_refresh:
            # Re-pull today's bar when current; otherwise backfill from day after last bar
            # (EQ-only Upstox maps used to leave T2T/BE symbols months behind — today's-only
            # fetch would permanently leave a hole between last_d and today).
            if last_d < today_ist:
                from_dt = datetime.combine(last_d + timedelta(days=1), datetime.min.time())
            else:
                from_dt = datetime.combine(today_ist, datetime.min.time())
        elif refresh_today and session_day and last_d == today_ist:
            from_dt = datetime.combine(today_ist, datetime.min.time())
        else:
            from_dt = last_dt + timedelta(days=1)
            if hasattr(from_dt, "date") and getattr(from_dt, "tzinfo", None) is not None:
                from_dt = datetime.combine(from_dt.date(), datetime.min.time())
        key = from_dt.strftime("%Y-%m-%d")
        date_groups.setdefault(key, []).append(sym)

    log(f"Date groups: {len(date_groups)} unique start dates")
    log(f"Fetching new candles (Upstox only)...\n")

    processed = 0
    today_iso = today_ist.strftime("%Y-%m-%d")
    fetch_totals = {"upstox": 0, "yahoo_fallback": 0, "nse": 0, "failed": 0}

    for from_str, group_symbols in date_groups.items():
        from_dt = datetime.strptime(from_str, "%Y-%m-%d")

        for batch_start in range(0, len(group_symbols), BATCH_SIZE):
            _check_cancel()
            batch = group_symbols[batch_start:batch_start + BATCH_SIZE]

            # Safety: stop if failure rate too high
            if processed > 100:
                fail_rate = failed / processed
                if fail_rate > MAX_FAILURE_RATE:
                    log(f"\n⚠ Failure rate {fail_rate:.0%} exceeds threshold. Stopping to protect connection.")
                    conn.close()
                    return {
                        "updated": updated,
                        "bhav_screener_written": 0,
                        "skipped_current": skipped_current,
                        "fetch_stats": fetch_totals,
                    }

            result, status = fetch_batch(batch, from_dt, today_end)
            batch_stats = getattr(fetch_batch, "last_stats", None) or {}
            for k in ("upstox", "yahoo_fallback", "failed"):
                fetch_totals[k] = fetch_totals.get(k, 0) + int(batch_stats.get(k) or 0)
            batch_upstox = int(batch_stats.get("upstox") or 0)
            batch_yahoo = int(batch_stats.get("yahoo_fallback") or 0)
            batch_failed = int(batch_stats.get("failed") or 0)
            batch_today_q = int(batch_stats.get("today_quote") or 0)
            if batch_today_q:
                log(f"  Upstox session-day quotes filled {batch_today_q} symbol(s)")
            if batch_failed:
                log(f"  Upstox miss (no Yahoo): {batch_failed} symbol(s) in batch")
            log(
                f"Source: batch Upstox={batch_upstox} failed={batch_failed} | "
                f"totals Upstox={fetch_totals.get('upstox', 0)} "
                f"failed={fetch_totals.get('failed', 0)} | skipped_current={skipped_current}"
            )

            if status not in ("ok", "empty"):
                log(f"⚠ Batch error: {status}. Pausing...")
                sleep_interruptible(random.uniform(PAUSE_ON_BLOCK, PAUSE_ON_BLOCK + 15), cancel_check=cancel_check)
                consec_failures += len(batch)
                failed          += len(batch)
            else:
                batch_successes = 0
                for sym in batch:
                    if sym in result and result[sym]:
                        rows = result[sym]
                        touches_today = any(str(r[0])[:10] == today_iso for r in rows)
                        write_rows(
                            conn,
                            sym,
                            rows,
                            overwrite=((refresh_today and session_day and touches_today) or (force_post_close_refresh and touches_today)),
                        )
                        updated         += 1
                        batch_successes += 1
                    else:
                        skipped += 1
                if batch_successes > 0:
                    consec_failures = 0
                else:
                    # One empty batch = one strike (not per-symbol) — tail delisteds shouldn't trigger 60s pause.
                    consec_failures += 1

            if consec_failures >= MAX_CONSEC_FAILURES:
                log(f"⚠ {MAX_CONSEC_FAILURES} consecutive failures. Pausing {PAUSE_ON_BLOCK}s...")
                sleep_interruptible(random.uniform(PAUSE_ON_BLOCK, PAUSE_ON_BLOCK + 15), cancel_check=cancel_check)
                consec_failures = 0

            processed += len(batch)

            msg = (
                f"Progress: {processed}/{total}\n"
                f"Updated: {updated}\n"
                f"Skipped: {skipped}\n"
                f"Failed: {failed}"
            )
            log(msg)

            if progress_callback:
                progress_callback(processed, total)

            # Short delay — Update path is Upstox-only.
            upstox_only = batch_yahoo == 0 and status in ("ok", "empty")
            if upstox_only:
                delay = random.uniform(RATE_DELAY_UPSTOX_MIN, RATE_DELAY_UPSTOX_MAX)
            else:
                delay = random.uniform(RATE_DELAY_MIN, RATE_DELAY_MAX)
            sleep_interruptible(delay, cancel_check=cancel_check)

    _check_cancel()
    log("\nReconciling screener price/1D% from NSE bhavcopy (charts unchanged)...")
    bhav_written = 0
    try:
        from server.nse_bhavcopy import reconcile_recent_eod_from_nse

        all_syms = list(get_all_screener_symbols(conn))
        bhav_written = reconcile_recent_eod_from_nse(conn, all_syms, log_fn=log)
        if bhav_written == 0:
            sync_screener_prices_from_latest_bars(conn, log_fn=log)
        else:
            updated = max(updated, 1)
    except Exception as e:
        log(f"[!] NSE bhavcopy screener overlay warning: {e}")

    # Recalculate EMA columns for updated symbols
    log("\nRecalculating EMA values...")
    try:
        import numpy as np
        conn2   = connect_db()
        cursor2 = conn2.cursor()
        PERIODS = [9, 21, 50, 100, 200]

        def calc_ema_local(closes, period):
            arr = np.array(closes, dtype=np.float64)
            if len(arr) < period:
                return None, None
            k    = 2.0 / (period + 1)
            ema  = arr[0]
            prev = None
            for i in range(1, len(arr)):
                prev = ema
                ema  = arr[i] * k + ema * (1 - k)
            return round(float(ema), 4), round(float(prev), 4) if prev else None

        ema_updated = 0
        for sym in to_update.keys():
            cursor2.execute("SELECT Close FROM historical_data WHERE Symbol=? ORDER BY Date ASC", (sym,))
            rows2 = cursor2.fetchall()
            if not rows2:
                continue
            closes  = [r[0] for r in rows2]
            updates = {"symbol": sym}
            for p in PERIODS:
                curr, prev = calc_ema_local(closes, p)
                updates[f"ema{p}"]      = curr
                updates[f"ema{p}_prev"] = prev
            sql = "UPDATE screener SET ema9=:ema9, ema21=:ema21, ema50=:ema50, ema100=:ema100, ema200=:ema200, ema9_prev=:ema9_prev, ema21_prev=:ema21_prev, ema50_prev=:ema50_prev, ema100_prev=:ema100_prev, ema200_prev=:ema200_prev WHERE symbol=:symbol"
            cursor2.execute(sql, updates)
            ema_updated += 1
            if ema_updated % 200 == 0:
                conn2.commit()

        conn2.commit()
        conn2.close()
        log(f"✓ EMA values updated for {ema_updated} stocks")
    except Exception as e:
        log(f"⚠ EMA update warning: {e}")

    if refresh_snapshots:
        log("\nRefreshing indicator snapshots (1D–6D / 1W / 2W / 4W / 1M)...")
        try:
            rebuild_indicator_snapshots_universe(
                clear_first=False,
                log_fn=log,
                progress_callback=progress_callback,
                message_callback=message_callback,
            )
        except Exception as e:
            log(f"⚠ Indicator snapshot warning: {e}")
    else:
        log("\nSkipping indicator snapshots in OHLCV update flow (decoupled).")

    if updated > 0 or bhav_written > 0:
        try:
            sync_screener_prices_from_latest_bars(conn, log_fn=log)
        except Exception as e:
            log(f"⚠ Screener price sync warning: {e}")

    set_last_ohlcv_success_ist(conn, now_ist())
    conn.close()
    log(
        f"\n✓ Done. Updated: {updated} | Skipped: {skipped} | Failed: {failed} | "
        f"skipped_current={skipped_current} | "
        f"Upstox: {fetch_totals.get('upstox', 0)} | failed: {fetch_totals.get('failed', 0)}"
    )
    return {
        "updated": updated,
        "bhav_screener_written": int(bhav_written or 0),
        "skipped_current": skipped_current,
        "fetch_stats": fetch_totals,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("NSE Daily OHLCV Updater")
    print(f"Started: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
    print("=" * 60)
    run()
    print(f"\nFinished: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
