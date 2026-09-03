import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "--quiet", "--break-system-packages"])

import sqlite3
import yfinance as yf
import requests
import time
import random
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "nse_data.db"


def _log(msg: str) -> None:
    """Console-safe log for Windows cp1252 (no Unicode checkmarks)."""
    text = str(msg).replace("\u2713", "[OK]").replace("\u2717", "[X]")
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def connect_db():
    import sys
    root = str(BASE_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    from db_sqlite import connect_sqlite

    return connect_sqlite(DB_PATH)


def _load_index_catalog():
    """Import catalog from packages/server (works from repo root or install root)."""
    import sys

    pkg = BASE_DIR / "packages"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    from server.cim_index_catalog import (
        NSE_INDEX_HISTORY_START,
        NSE_ONLY_FALLBACK_SYMBOLS,
        nse_name_map,
        scrape_indices_tuples,
    )

    return scrape_indices_tuples(), nse_name_map(), NSE_ONLY_FALLBACK_SYMBOLS, NSE_INDEX_HISTORY_START


try:
    INDICES, NSE_NAME_MAP, NSE_ONLY_INDEX_SYMBOLS, NSE_INDEX_HISTORY_START = _load_index_catalog()
except Exception as _cat_err:
    _log(f"[indices] catalog import warning: {_cat_err}")
    INDICES = [
        ("^NSEI", "NIFTY 50", "equity"),
        ("^NSEBANK", "NIFTY Bank", "equity"),
        ("GC=F", "Gold Futures", "commodity"),
        ("SI=F", "Silver Futures", "commodity"),
    ]
    NSE_NAME_MAP = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK"}
    NSE_ONLY_INDEX_SYMBOLS = frozenset()
    NSE_INDEX_HISTORY_START = {}

SKIP_KEYWORDS = ["G-SEC", "BOND", "BHARAT BOND", "COMPOSITE G-SEC"]
CHARTABLE_NAMES = set(NSE_NAME_MAP.values())

# Daily OHLC: Upstox primary, Yahoo secondary only (no NSE history mix).
# 4H intraday: Upstox → Yahoo (see bars_4h.py).


def _write_index_ohlc_rows(cursor, symbol, rows_iter, category, usd_inr) -> int:
    """Persist daily index OHLC. Equity indices skip non-NSE-session calendar days."""
    session_filter = str(category or "").strip().lower() == "equity"
    is_session = None
    if session_filter:
        try:
            from movers_data import _is_nse_session_day as is_session
        except Exception:
            try:
                from server.movers_data import _is_nse_session_day as is_session
            except Exception:
                is_session = lambda d: d.weekday() < 5  # noqa: E731

    rows = 0
    for date_str, o, h, l, c, v in rows_iter:
        try:
            day_s = str(date_str)[:10]
            if session_filter and is_session is not None:
                try:
                    day = datetime.strptime(day_s, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if not is_session(day):
                    continue
            o, h, l, c = float(o), float(h), float(l), float(c)
            v = float(v or 0)
            if category == "commodity":
                o = convert_commodity(symbol, o, usd_inr)
                h = convert_commodity(symbol, h, usd_inr)
                l = convert_commodity(symbol, l, usd_inr)
                c = convert_commodity(symbol, c, usd_inr)
            cursor.execute(
                "INSERT OR REPLACE INTO index_history (Symbol, Date, Open, High, Low, Close, Volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (symbol, day_s, round(o, 2), round(h, 2), round(l, 2), round(c, 2), round(v, 2)),
            )
            rows += 1
        except Exception:
            continue
    return rows


def _scrape_history_from_upstox(symbol, start, end, cursor, category, usd_inr, conn) -> int:
    """Pull daily index/equity candles from Upstox into index_history. Returns rows written."""
    import sys

    pkg = BASE_DIR / "packages"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    from server import upstox_config, upstox_history, upstox_instruments

    if not upstox_config.market_data_enabled():
        return 0

    data_dir = BASE_DIR / "data"
    upstox_instruments.configure_paths(data_dir=data_dir)
    upstox_history.configure_paths(data_dir=data_dir)
    try:
        upstox_instruments.instrument_map()
    except Exception as exc:
        _log(f"    Upstox instrument map failed: {exc}")
        return 0

    candles, err = upstox_history.fetch_daily_for_symbol(symbol, start, end, adjust=False)
    if err:
        _log(f"    Upstox daily: {err}")
        return 0
    if not candles:
        return 0

    written = _write_index_ohlc_rows(cursor, symbol, candles, category, usd_inr)
    if written:
        conn.commit()
    return written


def scrape_history(symbol, name, category, usd_inr, conn):
    _log(f"  Scraping {name} ({symbol})...")
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(Date) FROM index_history WHERE Symbol = ?", (symbol,))
    last_date = cursor.fetchone()[0]

    if last_date:
        start = (datetime.strptime(last_date[:10], "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        start = NSE_INDEX_HISTORY_START.get(symbol, "2010-01-01")

    end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    # 1) Upstox primary for equity indices (and any symbol with an Upstox key).
    if category == "equity":
        try:
            up_rows = _scrape_history_from_upstox(symbol, start, end, cursor, category, usd_inr, conn)
            if up_rows:
                _log(f"    [OK] {up_rows} rows from Upstox")
                return up_rows
        except Exception as exc:
            _log(f"    Upstox history failed: {exc}")

    # 2) Yahoo secondary (commodities + Upstox miss).
    yahoo_sym = symbol
    try:
        df = yf.download(yahoo_sym, start=start, end=end, progress=False, auto_adjust=True)
    except Exception as exc:
        _log(f"    Yahoo download failed: {exc}")
        df = None

    if df is None or getattr(df, "empty", True):
        _log("    No data returned")
        return 0

    df = df.reset_index()
    df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]

    y_rows = []
    for _, row in df.iterrows():
        try:
            date_str = row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"])[:10]
            y_rows.append(
                (
                    date_str,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row.get("Volume", 0) or 0),
                )
            )
        except Exception:
            continue

    rows = _write_index_ohlc_rows(cursor, symbol, y_rows, category, usd_inr)
    if rows:
        conn.commit()
        _log(f"    [OK] {rows} rows from Yahoo (fallback)")
    else:
        _log("    No data returned")
    return rows


def get_nse_chart_token(symbol: str):
    """NSE charting scripcode for 4H fallback (config/nse_index_chart_tokens.json)."""
    import sys

    root = str(BASE_DIR)
    pkg = BASE_DIR / "packages"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    if root not in sys.path:
        sys.path.insert(0, root)
    from server.nse_charting_intraday import get_nse_chart_token as _get

    return _get(symbol, BASE_DIR)


def get_usd_inr():
    try:
        df = yf.download("INR=X", period="5d", progress=False, auto_adjust=True)
        return float(df["Close"].iloc[-1].values[0])
    except Exception:
        return 86.0


def convert_commodity(symbol, price, usd_inr):
    if symbol == "GC=F":
        return round(price * (10 / 31.1035) * usd_inr, 2)
    elif symbol == "SI=F":
        return round(price * (1 / 0.0311035) * usd_inr, 2)
    return price


def setup_db(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indices (
            symbol      TEXT PRIMARY KEY,
            name        TEXT,
            category    TEXT,
            last_price  REAL,
            change_pct  REAL,
            change_30d  REAL,
            change_1y   REAL,
            updated_at  TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS index_history (
            Symbol   TEXT,
            Date     TEXT,
            Open     REAL,
            High     REAL,
            Low      REAL,
            Close    REAL,
            Volume   REAL,
            PRIMARY KEY (Symbol, Date)
        )
    """)
    conn.commit()
    _log("[OK] Tables ready")


def fetch_all_nse_indices(conn):
    _log("\nFetching all NSE indices from allIndices API...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
        "Referer":    "https://www.nseindia.com/",
    }
    session = requests.Session()
    session.headers.update(headers)

    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(random.uniform(1, 2))
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
        if r.status_code != 200:
            _log(f"  NSE allIndices failed: {r.status_code}")
            return
        all_indices = r.json().get("data", [])
    except Exception as e:
        _log(f"  NSE allIndices error: {e}")
        return

    cursor = conn.cursor()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    added  = 0

    for item in all_indices:
        name = item.get("index", "")
        if not name:
            continue
        if any(kw in name.upper() for kw in SKIP_KEYWORDS):
            continue
        if name.upper() in CHARTABLE_NAMES:
            continue

        symbol  = "NSE:" + name.upper().replace(" ", "_")
        last    = float(item.get("last", 0) or 0)
        chg_pct = float(item.get("percentChange", 0) or 0)
        chg_30d = float(item.get("perChange30d", 0) or 0)
        chg_1y  = float(item.get("perChange365d", 0) or 0)

        cursor.execute(
            "INSERT OR REPLACE INTO indices (symbol, name, category, last_price, change_pct, change_30d, change_1y, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, name, "equity_nse", round(last,2), round(chg_pct,2), round(chg_30d,2), round(chg_1y,2), now)
        )
        added += 1

    conn.commit()
    _log(f"  [OK] {added} non-chartable NSE indices stored")


def update_live_prices(usd_inr, conn):
    _log("\nUpdating live index prices...")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _has_index_history_closes(sym):
        cursor.execute(
            "SELECT COUNT(*) FROM index_history WHERE Symbol = ? AND Close IS NOT NULL",
            (sym,),
        )
        return (cursor.fetchone() or [0])[0] >= 2

    # Upstox primary for chartable equity indices; Yahoo secondary.
    upstox_quotes: dict[str, dict] = {}
    try:
        import sys

        pkg = BASE_DIR / "packages"
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        from server import upstox_config, upstox_client, upstox_instruments

        if upstox_config.market_data_enabled():
            data_dir = BASE_DIR / "data"
            upstox_instruments.configure_paths(data_dir=data_dir)
            eq_syms = [s for s, _n, c in INDICES if c == "equity"]
            if eq_syms:
                rows, err = upstox_client.fetch_quotes(eq_syms, index_names=dict(NSE_NAME_MAP))
                for r in rows or []:
                    sym = str((r or {}).get("symbol") or "").strip().upper()
                    if sym:
                        upstox_quotes[sym] = r
                if err and not upstox_quotes:
                    _log(f"  Upstox quotes: {err}")
                elif upstox_quotes:
                    _log(f"  Upstox returned {len(upstox_quotes)} index quotes")
    except Exception as e:
        _log(f"  Upstox quote fetch failed: {e}")

    for symbol, name, category in INDICES:
        try:
            last = chg_pct = chg_30d = chg_1y = None
            history_closes = _has_index_history_closes(symbol)

            if category == "equity" and symbol in upstox_quotes:
                snap = upstox_quotes[symbol]
                last = float(snap.get("price") or 0)
                if last > 0:
                    if not history_closes:
                        chg_pct = snap.get("change_pct")
                        if chg_pct is not None:
                            chg_pct = float(chg_pct)
                    _log(f"  [OK] {name}: {last} (Upstox)")

            if last is None or last <= 0:
                df = yf.download(symbol, period="400d", progress=False, auto_adjust=True)
                if df.empty:
                    _log(f"  [X] {name}: no data")
                    continue

                last = float(df["Close"].iloc[-1].values[0])
                prev = float(df["Close"].iloc[-2].values[0])

                if category == "commodity":
                    last = convert_commodity(symbol, last, usd_inr)
                    prev = convert_commodity(symbol, prev, usd_inr)

                chg_pct = round((last - prev) / prev * 100, 2) if prev else 0.0

                if len(df) >= 22:
                    p30 = float(df["Close"].iloc[-22].values[0])
                    p30_c = convert_commodity(symbol, p30, usd_inr) if category == "commodity" else p30
                    chg_30d = round((last - p30_c) / p30_c * 100, 2) if p30_c else 0.0
                else:
                    chg_30d = 0.0

                if len(df) >= 252:
                    p1y = float(df["Close"].iloc[-252].values[0])
                    p1y_c = convert_commodity(symbol, p1y, usd_inr) if category == "commodity" else p1y
                    chg_1y = round((last - p1y_c) / p1y_c * 100, 2) if p1y_c else 0.0
                else:
                    chg_1y = 0.0

                _log(f"  [OK] {name}: {last:.2f} (yfinance)")

            if history_closes:
                cursor.execute(
                    "UPDATE indices SET last_price=?, updated_at=? WHERE symbol=?",
                    (round(last, 2), now, symbol),
                )
            else:
                cursor.execute(
                    "UPDATE indices SET last_price=?, change_pct=?, updated_at=? WHERE symbol=?",
                    (round(last, 2), round(chg_pct or 0, 2), now, symbol),
                )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT OR IGNORE INTO indices (symbol, name, category, last_price, change_pct, change_30d, change_1y, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (symbol, name, category, round(last, 2), round(chg_pct or 0, 2), 0.0, 0.0, now),
                )

        except Exception as e:
            _log(f"  [X] {name}: {e}")

    conn.commit()
    _log("[OK] Live prices updated")


def ensure_equity_index_rows(conn) -> int:
    """
    Insert chartable equity indices from INDICES that are missing in `indices`.
    Live level from Upstox when configured, else Yahoo (no NSE mix).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM indices")
    existing = {r[0] for r in cursor.fetchall()}
    missing = [
        (symbol, name, category)
        for symbol, name, category in INDICES
        if category == "equity" and symbol not in existing
    ]
    if not missing:
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quotes: dict[str, dict] = {}
    try:
        import sys

        pkg = BASE_DIR / "packages"
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        from server import upstox_config, upstox_client, upstox_instruments

        if upstox_config.market_data_enabled():
            data_dir = BASE_DIR / "data"
            upstox_instruments.configure_paths(data_dir=data_dir)
            syms = [s for s, _n, _c in missing]
            rows, _err = upstox_client.fetch_quotes(syms, index_names=dict(NSE_NAME_MAP))
            for r in rows or []:
                sym = str((r or {}).get("symbol") or "").strip().upper()
                if sym:
                    quotes[sym] = r
    except Exception:
        pass

    added = 0
    for symbol, name, category in missing:
        snap = quotes.get(symbol) or {}
        last = float(snap.get("price") or 0)
        chg_pct = float(snap.get("change_pct") or 0) if snap.get("change_pct") is not None else 0.0
        if last <= 0:
            try:
                df = yf.download(symbol, period="5d", progress=False, auto_adjust=True)
                if df is not None and not df.empty:
                    last = float(df["Close"].iloc[-1].values[0])
                    if len(df) >= 2:
                        prev = float(df["Close"].iloc[-2].values[0])
                        chg_pct = round((last - prev) / prev * 100, 2) if prev else 0.0
            except Exception:
                last = 0.0
                chg_pct = 0.0
        cursor.execute(
            "INSERT OR IGNORE INTO indices (symbol, name, category, last_price, change_pct, change_30d, change_1y, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, name, category, round(last, 2), round(chg_pct, 2), 0.0, 0.0, now),
        )
        if cursor.rowcount:
            added += 1
    if added:
        conn.commit()
    return added


def _nse_history_symbols_to_refresh(
    conn,
    *,
    max_lag_days: int = 5,
    min_rows: int = 2,
) -> list[tuple[str, str]]:
    """Chartable equity indices that need Upstox/Yahoo history deepen (legacy name kept)."""
    from datetime import date as date_cls

    cutoff = (date_cls.today() - timedelta(days=max_lag_days)).strftime("%Y-%m-%d")
    cursor = conn.cursor()
    to_refresh: dict[str, str] = {}

    for symbol, name, category in INDICES:
        if category != "equity":
            continue
        cursor.execute(
            "SELECT COUNT(*), MAX(SUBSTR(Date, 1, 10)) FROM index_history WHERE Symbol = ?",
            (symbol,),
        )
        row = cursor.fetchone() or (0, None)
        count = int(row[0] or 0)
        last = row[1]
        if count < min_rows or not last or str(last)[:10] < cutoff:
            to_refresh[symbol] = name

    return sorted(to_refresh.items())


def sync_nse_index_history(conn, *, max_lag_days: int = 5, min_rows: int = 2) -> int:
    """
    Backfill or extend index_history for chartable equity indices.
    Upstox primary, Yahoo secondary — no NSE indicesHistory mix.
    """
    targets = _nse_history_symbols_to_refresh(
        conn, max_lag_days=max_lag_days, min_rows=min_rows
    )
    if not targets:
        return 0

    usd_inr = get_usd_inr()
    total = 0
    for symbol, name in targets:
        try:
            rows = scrape_history(symbol, name, "equity", usd_inr, conn)
            if rows:
                _log(f"  [OK] {name}: {rows} history row(s) (Upstox/Yahoo)")
                total += rows
        except Exception as exc:
            _log(f"  [X] {name} history: {exc}")

    if total:
        recalculate_index_changes(conn)
    return total


def ensure_missing_index_history(conn, **kwargs) -> int:
    """Backward-compatible alias for sync_nse_index_history."""
    return sync_nse_index_history(conn, **kwargs)


def recalculate_index_changes(conn):
    _log("\nRecalculating index change % from history...")
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM indices WHERE category IN ('equity', 'commodity')")
    symbols = [r[0] for r in cursor.fetchall()]
    updated = 0
    for sym in symbols:
        try:
            cursor.execute("SELECT Close FROM index_history WHERE Symbol=? ORDER BY Date DESC LIMIT 1", (sym,))
            row = cursor.fetchone()
            if not row:
                continue
            last = row[0]
            cursor.execute("SELECT Close FROM index_history WHERE Symbol=? ORDER BY Date DESC LIMIT 1 OFFSET 1", (sym,))
            row_prev = cursor.fetchone()
            cursor.execute("SELECT Close FROM index_history WHERE Symbol=? AND SUBSTR(Date,1,7) < SUBSTR((SELECT MAX(Date) FROM index_history WHERE Symbol=?),1,7) ORDER BY Date DESC LIMIT 1", (sym, sym))
            row_1m = cursor.fetchone()
            cursor.execute("SELECT Close FROM index_history WHERE Symbol=? AND SUBSTR(Date,1,4) < SUBSTR((SELECT MAX(Date) FROM index_history WHERE Symbol=?),1,4) ORDER BY Date DESC LIMIT 1", (sym, sym))
            row_1y = cursor.fetchone()
            chg_pct = round((last - row_prev[0]) / row_prev[0] * 100, 2) if row_prev else None
            chg_1m  = round((last - row_1m[0])  / row_1m[0]  * 100, 2) if row_1m  else None
            chg_1y  = round((last - row_1y[0])  / row_1y[0]  * 100, 2) if row_1y  else None
            fields, vals = [], []
            if chg_pct is not None: fields.append("change_pct = ?");  vals.append(chg_pct)
            if chg_1m  is not None: fields.append("change_30d = ?");  vals.append(chg_1m)
            if chg_1y  is not None: fields.append("change_1y = ?");   vals.append(chg_1y)
            if fields:
                vals.append(sym)
                cursor.execute(f"UPDATE indices SET {', '.join(fields)} WHERE symbol=?", vals)
                updated += 1
        except Exception:
            continue
    conn.commit()
    _log(f"  [OK] Recalculated {updated} indices")


if __name__ == "__main__":
    _log("=" * 50)
    _log("NSE Index Scraper")
    _log(f"Started: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
    _log("=" * 50)

    conn = connect_db()
    setup_db(conn)

    _log("\nFetching USD/INR rate...")
    usd_inr = get_usd_inr()
    _log(f"USD/INR: {usd_inr:.2f}")

    _log("\nScraping historical data...")
    total = 0
    for symbol, name, category in INDICES:
        total += scrape_history(symbol, name, category, usd_inr, conn)

    _log(f"\nTotal rows inserted: {total}")

    update_live_prices(usd_inr, conn)
    fetch_all_nse_indices(conn)
    sync_nse_index_history(conn)
    recalculate_index_changes(conn)

    conn.close()
    _log("\n[OK] Done.")
    _log(f"Finished: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
