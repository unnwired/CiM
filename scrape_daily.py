"""
NSE Daily OHLCV Updater — uses yfinance
Fetches missing candles since last date in historical_data and appends them.
On an NSE session day, before 16:00 Asia/Kolkata, re-fetches today's bar (upsert) so
post-close price changes are visible. After 16:00 IST, new appends only (no forced today refresh).
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
SESSION_FINAL_IST = dtime(16, 0)  # after this time, do not force-refresh "today"

BATCH_SIZE          = 50    # yfinance handles bulk well
RATE_DELAY_MIN      = 0.8
RATE_DELAY_MAX      = 1.5
MAX_CONSEC_FAILURES = 15
PAUSE_ON_BLOCK      = 60
MAX_FAILURE_RATE    = 0.30
SNAPSHOT_TIMEFRAMES = ("1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W", "4W", "1M")
SNAPSHOT_LIGHT_TIMEFRAMES = ("1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W")
SNAPSHOT_PARALLEL_MODE = str(os.getenv("FLOWX_SNAPSHOT_PARALLEL_MODE", "auto")).strip().lower()
if SNAPSHOT_PARALLEL_MODE not in {"auto", "process", "thread"}:
    SNAPSHOT_PARALLEL_MODE = "auto"
MACD_HIST_CHAIN_MAX_BARS = 30


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


def session_refresh_enabled(session_day: bool, now: datetime) -> bool:
    """True = before 16:00 IST on a session day: may upsert today's bar."""
    if not session_day:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)
    return now.time() < SESSION_FINAL_IST


def get_today_ist() -> date:
    return now_ist().date()


def sync_screener_prices_from_latest_bars(conn, log_fn=None) -> int:
    """
    After OHLCV writes today's bar, align screener.price and change_percent with
    the latest two daily closes so movers / screeners show the current session.
    """
    today_iso = get_today_ist().strftime("%Y-%m-%d")
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
        WHERE EXISTS (
            SELECT 1 FROM historical_data h
            WHERE h.Symbol = screener.symbol AND substr(h.Date, 1, 10) = ?
        )
        """,
        (today_iso,),
    )
    n = cursor.rowcount
    conn.commit()
    if log_fn and n:
        log_fn(f"✓ Screener prices synced for {n} symbols with today's bar ({today_iso})")
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
        cursor.executemany(
            "INSERT OR IGNORE INTO historical_data (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap) VALUES (?,?,?,?,?,?,?,?,?)",
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
    Fetch OHLCV for a batch of symbols using yfinance bulk download.
    Returns dict of symbol -> list of (date, o, h, l, c, v)
    """
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

    if df.empty:
        return {}, "empty"

    result = {}

    for sym, yf_sym in zip(symbols, yf_symbols):
        try:
            if len(symbols) == 1:
                sym_df = df
            else:
                if yf_sym not in df.columns.get_level_values(0):
                    continue
                sym_df = df[yf_sym]

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


def build_snapshot_payload(symbol, timeframe, candles):
    if len(candles) < 3:
        return None
    closes = [float(c[4]) for c in candles]
    last = candles[-1]
    prev = candles[-2]
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "close_curr": round(float(last[4]), 4),
        "close_prev": round(float(prev[4]), 4),
        "open_curr": round(float(last[1]), 4),
        "open_prev": round(float(prev[1]), 4),
        "high_curr": round(float(last[2]), 4),
        "high_prev": round(float(prev[2]), 4),
        "low_curr": round(float(last[3]), 4),
        "low_prev": round(float(prev[3]), 4),
    }
    for period in (9, 21, 50, 100, 200):
        curr, prev_val = last_two(calc_ema_series_local(closes, period))
        payload[f"ema{period}"] = curr
        payload[f"ema{period}_prev"] = prev_val
    macd = calculate_macd_local(closes, fast=12, slow=26, signal=9)
    payload["macd"], payload["macd_prev"] = last_two(macd["macd"])
    payload["macd_signal"], payload["macd_signal_prev"] = last_two(macd["signal"])
    hist_valid = [round(float(v), 4) for v in macd["histogram"] if v is not None]
    payload["macd_hist_chain"] = "|".join(
        f"{v:.4f}" for v in hist_valid[-MACD_HIST_CHAIN_MAX_BARS:]
    ) if hist_valid else None
    stoch = calculate_stochrsi_local(closes, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3)
    payload["stoch_k"], payload["stoch_k_prev"] = last_two(stoch["k"])
    payload["stoch_d"], payload["stoch_d_prev"] = last_two(stoch["d"])
    return payload


def _build_snapshot_rows_for_symbol(sym, candles, allowed_timeframes=None):
    rows = []
    allowed = set(allowed_timeframes) if allowed_timeframes else None
    daily = candles
    weekly = aggregate_to_weekly(candles)
    two_w = aggregate_to_nperiod_local(weekly, 2, "week")
    four_w = aggregate_to_nperiod_local(weekly, 4, "week")
    monthly = aggregate_to_monthly(candles)
    series_tuples = [("1D", daily)]
    for nd in range(2, 7):
        series_tuples.append((f"{nd}D", aggregate_to_nperiod_local(daily, nd, "day")))
    series_tuples.extend(
        [
            ("1W", weekly),
            ("2W", two_w),
            ("4W", four_w),
            ("1M", monthly),
        ]
    )
    for timeframe, series in series_tuples:
        if allowed is not None and timeframe not in allowed:
            continue
        payload = build_snapshot_payload(sym, timeframe, series)
        if payload is not None:
            rows.append(payload)
    return rows


def _build_snapshot_rows_for_chunk(chunk_items, allowed_timeframes=None):
    out = []
    for sym, candles in chunk_items:
        out.extend(_build_snapshot_rows_for_symbol(sym, candles, allowed_timeframes=allowed_timeframes))
    return out, len(chunk_items)


def rebuild_indicator_snapshots_universe(
    clear_first=False,
    log_fn=None,
    progress_callback=None,
    message_callback=None,
    symbols_override=None,
    timeframes_override=None,
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

        if not clear_first:
            tf_placeholders = ",".join(["?"] * len(requested_timeframes))
            sym_placeholders = ",".join(["?"] * len(symbols))
            conn.execute(
                f"DELETE FROM indicator_snapshots WHERE timeframe IN ({tf_placeholders}) AND symbol IN ({sym_placeholders})",
                list(requested_timeframes) + list(symbols),
            )
            conn.commit()

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

        upsert_sql = """
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
                rows_chunk, processed = _build_snapshot_rows_for_chunk(chunk, requested_timeframes)
                snapshot_rows.extend(rows_chunk)
                done += processed
                report_compute_progress(done)
        elif effective_mode == "process":
            # Prefer process pool when explicitly requested or on stable environments.
            try:
                with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(_build_snapshot_rows_for_chunk, c, requested_timeframes) for c in chunks]
                    for fut in concurrent.futures.as_completed(futures):
                        rows_chunk, processed = fut.result()
                        snapshot_rows.extend(rows_chunk)
                        done += processed
                        report_compute_progress(done)
            except Exception as e:
                log("[perf] snapshots: Process mode unavailable; falling back to thread mode.")
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, min(8, workers))) as pool:
                    futures = [pool.submit(_build_snapshot_rows_for_chunk, c, requested_timeframes) for c in chunks]
                    for fut in concurrent.futures.as_completed(futures):
                        rows_chunk, processed = fut.result()
                        snapshot_rows.extend(rows_chunk)
                        done += processed
                        report_compute_progress(done)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, min(8, workers))) as pool:
                futures = [pool.submit(_build_snapshot_rows_for_chunk, c, requested_timeframes) for c in chunks]
                for fut in concurrent.futures.as_completed(futures):
                    rows_chunk, processed = fut.result()
                    snapshot_rows.extend(rows_chunk)
                    done += processed
                    report_compute_progress(done)
        t_compute_ms = int((time.perf_counter() - t_compute_start) * 1000)
        log(
            f"[perf] snapshots: computed {len(snapshot_rows)} rows in {t_compute_ms}ms "
            f"(symbols={total_syms}, workers={workers}, chunks={len(chunks)}, mode={effective_mode})"
        )

        t_write_start = time.perf_counter()
        if snapshot_rows:
            if progress_callback:
                p = min(total_syms, max(0, round(total_syms * 0.96)))
                progress_callback(p, total_syms)
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


def run(progress_callback=None, message_callback=None, refresh_snapshots=False):
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
        f"session_day={session_day}, refresh_today_until_16_IST={refresh_today}, "
        f"force_post_close_refresh={force_post_close_refresh}"
    )
    if last_success_ist is not None:
        log(f"Last successful OHLCV run (IST): {last_success_ist.strftime('%Y-%m-%d %H:%M:%S')}")

    to_update = {}
    if force_post_close_refresh:
        # If the prior run was before close, force-refresh today's bar for all symbols.
        anchor = datetime.combine(today_ist, datetime.min.time())
        for sym in get_all_screener_symbols(conn):
            to_update[sym] = anchor
    else:
        for sym, dt in last_dates.items():
            last_d = dt.date() if hasattr(dt, "date") else dt
            if last_d < today_ist:
                to_update[sym] = dt
            elif refresh_today and session_day and last_d == today_ist:
                to_update[sym] = dt
        # Screener symbols with no historical_data yet (never picked up by incremental-only loop)
        hist_syms = set(last_dates.keys())
        for sym in get_all_screener_symbols(conn):
            if sym not in hist_syms and sym not in to_update:
                to_update[sym] = datetime(1989, 12, 31)

    if not to_update:
        log("All symbols are up to date.")
        conn.close()
        return 0

    log(f"Found {len(to_update)} symbols needing updates.")

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
            from_dt = datetime.combine(today_ist, datetime.min.time())
        elif refresh_today and session_day and last_d == today_ist:
            from_dt = datetime.combine(today_ist, datetime.min.time())
        else:
            from_dt = last_dt + timedelta(days=1)
        key = from_dt.strftime("%Y-%m-%d")
        date_groups.setdefault(key, []).append(sym)

    log(f"Date groups: {len(date_groups)} unique start dates")
    log(f"Fetching new candles using yfinance...\n")

    processed = 0
    today_iso = today_ist.strftime("%Y-%m-%d")

    for from_str, group_symbols in date_groups.items():
        from_dt = datetime.strptime(from_str, "%Y-%m-%d")

        for batch_start in range(0, len(group_symbols), BATCH_SIZE):
            batch = group_symbols[batch_start:batch_start + BATCH_SIZE]

            # Safety: stop if failure rate too high
            if processed > 100:
                fail_rate = failed / processed
                if fail_rate > MAX_FAILURE_RATE:
                    log(f"\n⚠ Failure rate {fail_rate:.0%} exceeds threshold. Stopping to protect connection.")
                    conn.close()
                    return updated

            result, status = fetch_batch(batch, from_dt, today_end)

            if status not in ("ok", "empty"):
                log(f"⚠ Batch error: {status}. Pausing...")
                time.sleep(random.uniform(PAUSE_ON_BLOCK, PAUSE_ON_BLOCK + 15))
                consec_failures += len(batch)
                failed          += len(batch)
            else:
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
                        consec_failures  = 0
                    else:
                        skipped         += 1
                        consec_failures += 1

            if consec_failures >= MAX_CONSEC_FAILURES:
                log(f"⚠ {MAX_CONSEC_FAILURES} consecutive failures. Pausing {PAUSE_ON_BLOCK}s...")
                time.sleep(random.uniform(PAUSE_ON_BLOCK, PAUSE_ON_BLOCK + 15))
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

            time.sleep(random.uniform(RATE_DELAY_MIN, RATE_DELAY_MAX))

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

    if session_day and refresh_today and updated > 0:
        try:
            sync_screener_prices_from_latest_bars(conn, log_fn=log)
        except Exception as e:
            log(f"⚠ Screener price sync warning: {e}")

    set_last_ohlcv_success_ist(conn, now_ist())
    conn.close()
    log(f"\n✓ Done. Updated: {updated} | Skipped: {skipped} | Failed: {failed}")
    return updated


if __name__ == "__main__":
    print("=" * 60)
    print("NSE Daily OHLCV Updater")
    print(f"Started: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
    print("=" * 60)
    run()
    print(f"\nFinished: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
