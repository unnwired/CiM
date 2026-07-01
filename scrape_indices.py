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

INDICES = [
    ("^NSEI",      "NIFTY 50",                    "equity"),
    ("^NSEBANK",   "NIFTY Bank",                  "equity"),
    ("^CNXIT",     "NIFTY IT",                    "equity"),
    ("^NSMIDCP",   "NIFTY Midcap 100",             "equity"),
    ("^NSEMDCP50", "NIFTY Midcap 50",              "equity"),
    ("^CNXFMCG",   "NIFTY FMCG",                  "equity"),
    ("^CNXPHARMA", "NIFTY Pharma",                "equity"),
    ("NIFTY_HEALTHCARE.NS", "Nifty Healthcare",   "equity"),
    ("^CNXAUTO",   "NIFTY Auto",                  "equity"),
    ("^CNXMETAL",  "NIFTY Metal",                 "equity"),
    ("^CNXREALTY", "NIFTY Realty",                "equity"),
    ("^CNXENERGY", "NIFTY Energy",                "equity"),
    ("^CNXINFRA",  "NIFTY Infra",                 "equity"),
    ("^CNXINDDEF", "Nifty India Defence",         "equity"),
    ("^CNXPSUBANK","NIFTY PSU Bank",              "equity"),
    ("^CNXSC",     "NIFTY Smallcap 100",          "equity"),
    ("^CNXCMDT",   "NIFTY Commodities",           "equity"),
    ("^CNXPSE",    "NIFTY PSE",                   "equity"),
    ("^CNXMNC",    "NIFTY MNC",                   "equity"),
    ("^CNXSERVICE","NIFTY Services Sector",       "equity"),
    ("^CNXMEDIA",  "NIFTY Media",                 "equity"),
    ("^CNXDIVOP",  "NIFTY Dividend Opp 50",       "equity"),
    ("^CNXNXT50",  "Nifty Next 50",               "equity"),
    ("^CNX100",    "Nifty 100",                   "equity"),
    ("^CNX200",    "Nifty 200",                   "equity"),
    ("^CRSLDX",    "Nifty 500",                   "equity"),
    ("^CNXSMLCP50","Nifty Smallcap 50",           "equity"),
    ("GC=F",       "Gold Futures",                "commodity"),
    ("SI=F",       "Silver Futures",              "commodity"),
]

NSE_NAME_MAP = {
    "^NSEI":      "NIFTY 50",
    "^NSEBANK":   "NIFTY BANK",
    "^CNXIT":     "NIFTY IT",
    "^NSMIDCP":   "NIFTY MIDCAP 100",
    "^NSEMDCP50": "NIFTY MIDCAP 50",
    "^CNXFMCG":   "NIFTY FMCG",
    "^CNXPHARMA": "NIFTY PHARMA",
    "NIFTY_HEALTHCARE.NS": "NIFTY HEALTHCARE INDEX",
    "^CNXAUTO":   "NIFTY AUTO",
    "^CNXMETAL":  "NIFTY METAL",
    "^CNXREALTY": "NIFTY REALTY",
    "^CNXENERGY": "NIFTY ENERGY",
    "^CNXINFRA":  "NIFTY INFRA",
    "^CNXINDDEF": "NIFTY INDIA DEFENCE",
    "^CNXPSUBANK":"NIFTY PSU BANK",
    "^CNXSC":     "NIFTY SMALLCAP 100",
    "^CNXCMDT":   "NIFTY COMMODITIES",
    "^CNXPSE":    "NIFTY PSE",
    "^CNXMNC":    "NIFTY MNC",
    "^CNXSERVICE":"NIFTY SERVICES SECTOR",
    "^CNXMEDIA":  "NIFTY MEDIA",
    "^CNXDIVOP":  "NIFTY DIVIDEND OPPORTUNITIES 50",
    "^CNXNXT50":  "NIFTY NEXT 50",
    "^CNX100":    "NIFTY 100",
    "^CNX200":    "NIFTY 200",
    "^CRSLDX":    "NIFTY 500",
    "^CNXSMLCP50":"NIFTY SMLCAP 50",
}

SKIP_KEYWORDS = ["G-SEC", "BOND", "BHARAT BOND", "COMPOSITE G-SEC"]
CHARTABLE_NAMES = set(NSE_NAME_MAP.values())

# Yahoo has no usable daily OHLC — use NSE indicesHistory for 1D+ only (not 4H).
# 4H intraday uses Yahoo 5m first, then NSE charting 5m fallback (see bars_4h.py).
NSE_ONLY_INDEX_SYMBOLS = frozenset({
    "^CNXINDDEF",
    "NIFTY_HEALTHCARE.NS",
})

# Earliest calendar date to request from NSE (index may list later).
NSE_INDEX_HISTORY_START = {
    "^CNXINDDEF": "2024-11-11",
    "NIFTY_HEALTHCARE.NS": "2020-11-18",
}


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


def scrape_history(symbol, name, category, usd_inr, conn):
    _log(f"  Scraping {name} ({symbol})...")
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(Date) FROM index_history WHERE Symbol = ?", (symbol,))
    last_date = cursor.fetchone()[0]

    if last_date:
        start = (datetime.strptime(last_date[:10], "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        start = "2010-01-01"

    end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    nse_name = NSE_NAME_MAP.get(symbol)

    if symbol in NSE_ONLY_INDEX_SYMBOLS and nse_name and category == "equity":
        try:
            from nse_index_history import scrape_history_from_nse

            history_start = NSE_INDEX_HISTORY_START.get(symbol, "2010-01-01")
            rows = scrape_history_from_nse(
                conn,
                symbol,
                nse_name,
                history_start=history_start,
            )
            if rows:
                _log(f"    [OK] {rows} rows from NSE history API")
                return rows
        except Exception as exc:
            _log(f"    NSE history failed: {exc}")
        _log("    No data returned")
        return 0

    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)

    if df.empty:
        if nse_name and category == "equity":
            try:
                from nse_index_history import scrape_history_from_nse

                rows = scrape_history_from_nse(
                    conn,
                    symbol,
                    nse_name,
                    history_start=start,
                )
                if rows:
                    _log(f"    [OK] {rows} rows from NSE history API (Yahoo fallback)")
                    return rows
            except Exception as exc:
                _log(f"    NSE history fallback failed: {exc}")
        _log("    No data returned")
        return 0

    df = df.reset_index()
    df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]

    rows = 0
    for _, row in df.iterrows():
        try:
            date_str = row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"])[:10]
            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            v = float(row.get("Volume", 0) or 0)

            if category == "commodity":
                o = convert_commodity(symbol, o, usd_inr)
                h = convert_commodity(symbol, h, usd_inr)
                l = convert_commodity(symbol, l, usd_inr)
                c = convert_commodity(symbol, c, usd_inr)

            cursor.execute(
                "INSERT OR REPLACE INTO index_history (Symbol, Date, Open, High, Low, Close, Volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (symbol, date_str, round(o,2), round(h,2), round(l,2), round(c,2), round(v,2))
            )
            rows += 1
        except Exception:
            continue

    conn.commit()
    _log(f"    [OK] {rows} rows inserted/updated")
    return rows


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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept":     "application/json",
        "Referer":    "https://www.nseindia.com/",
    }
    session = requests.Session()
    session.headers.update(headers)

    nse_data = {}
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
        if r.status_code == 200:
            for d in r.json().get("data", []):
                key = d.get("index", "").upper().strip()
                nse_data[key] = d
            _log(f"  NSE returned {len(nse_data)} indices")
    except Exception as e:
        _log(f"  NSE fetch failed: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _has_index_history_closes(sym):
        cursor.execute(
            "SELECT COUNT(*) FROM index_history WHERE Symbol = ? AND Close IS NOT NULL",
            (sym,),
        )
        return (cursor.fetchone() or [0])[0] >= 2

    for symbol, name, category in INDICES:
        try:
            last = chg_pct = chg_30d = chg_1y = None
            history_closes = _has_index_history_closes(symbol)

            if category == "equity" and nse_data:
                nse_key = NSE_NAME_MAP.get(symbol, "").upper()
                matched = nse_data.get(nse_key)
                if matched:
                    last    = float(matched.get("last", 0) or 0)
                    # NSE percentChange is session vs prev close; 1D % for charts/list
                    # comes from index_history via recalculate_index_changes().
                    if not history_closes:
                        chg_pct = float(matched.get("percentChange", 0) or 0)
                    chg_30d = None
                    chg_1y  = None
                    _log(f"  [OK] {name}: {last}")

            if last is None:
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
                    p30   = float(df["Close"].iloc[-22].values[0])
                    p30_c = convert_commodity(symbol, p30, usd_inr) if category == "commodity" else p30
                    chg_30d = round((last - p30_c) / p30_c * 100, 2) if p30_c else 0.0
                else:
                    chg_30d = 0.0

                if len(df) >= 252:
                    p1y   = float(df["Close"].iloc[-252].values[0])
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
                    (round(last, 2), round(chg_pct, 2), now, symbol),
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
    Uses NSE allIndices for live level and session % when Yahoo has no history yet.
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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    }
    session = requests.Session()
    session.headers.update(headers)
    nse_data: dict[str, dict] = {}
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
        if r.status_code == 200:
            for d in r.json().get("data", []):
                key = str(d.get("index", "")).upper().strip()
                if key:
                    nse_data[key] = d
    except Exception:
        pass

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    added = 0
    for symbol, name, category in missing:
        nse_key = NSE_NAME_MAP.get(symbol, "").upper()
        matched = nse_data.get(nse_key)
        if not matched:
            continue
        last = float(matched.get("last", 0) or 0)
        chg_pct = float(matched.get("percentChange", 0) or 0)
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
    """Symbols that need NSE index_history backfill or extension."""
    from datetime import date as date_cls

    from nse_index_history import find_index_history_gaps

    cutoff = (date_cls.today() - timedelta(days=max_lag_days)).strftime("%Y-%m-%d")
    cursor = conn.cursor()
    to_refresh: dict[str, str] = {}

    for symbol in NSE_ONLY_INDEX_SYMBOLS:
        nse_name = NSE_NAME_MAP.get(symbol)
        if not nse_name:
            continue
        cursor.execute("SELECT name FROM indices WHERE symbol = ?", (symbol,))
        row = cursor.fetchone()
        name = (row[0] if row else None) or symbol
        if find_index_history_gaps(conn, symbol):
            to_refresh[symbol] = name
            continue
        cursor.execute(
            "SELECT MAX(SUBSTR(Date, 1, 10)) FROM index_history WHERE Symbol = ?",
            (symbol,),
        )
        last = cursor.fetchone()[0]
        if not last or str(last)[:10] < cutoff:
            to_refresh[symbol] = name

    cursor.execute(
        """
        SELECT i.symbol, i.name
        FROM indices i
        WHERE i.category = 'equity'
          AND (SELECT COUNT(*) FROM index_history h WHERE h.Symbol = i.symbol) < ?
        """,
        (min_rows,),
    )
    for symbol, name in cursor.fetchall():
        if NSE_NAME_MAP.get(symbol):
            to_refresh[str(symbol)] = str(name or symbol)

    return sorted(to_refresh.items())


def sync_nse_index_history(conn, *, max_lag_days: int = 5, min_rows: int = 2) -> int:
    """
    Backfill or extend index_history for NSE-only / Yahoo-missing indices.
    Runs on startup and after index updates so charts do not freeze on an old bar.
    """
    from nse_index_history import (
        find_index_history_gaps,
        make_nse_history_session,
        scrape_history_from_nse,
    )

    targets = _nse_history_symbols_to_refresh(
        conn, max_lag_days=max_lag_days, min_rows=min_rows
    )
    if not targets:
        return 0

    session = make_nse_history_session()
    total = 0
    try:
        for symbol, name in targets:
            nse_name = NSE_NAME_MAP.get(symbol)
            if not nse_name:
                continue
            history_start = NSE_INDEX_HISTORY_START.get(symbol, "2010-01-01")
            force_full = bool(find_index_history_gaps(conn, symbol))
            try:
                rows = scrape_history_from_nse(
                    conn,
                    symbol,
                    nse_name,
                    history_start=history_start,
                    session=session,
                    force_full=force_full,
                )
                if rows:
                    _log(f"  [OK] {name}: {rows} NSE history row(s)")
                    total += rows
            except Exception as exc:
                _log(f"  [X] {name} NSE history: {exc}")
    finally:
        session.close()

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
