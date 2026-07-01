"""
Compare Nifty 50 EOD closes and 1D % in local DB vs NSE bhavcopy (official).
Run: python scripts/verify_nifty50_eod.py
"""
from __future__ import annotations

import csv
import io
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from nse_constituents import INDEX_ARCHIVE_CSV, parse_archive_constituents, _fetch_archive_text  # noqa: E402

DB_PATH = ROOT / "data" / "nse_data.db"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TRADING_DAYS = 7
TOLERANCE_PCT = 0.15  # allow minor rounding / yfinance vs NSE drift


def load_nifty50_symbols() -> list[str]:
    text = _fetch_archive_text(INDEX_ARCHIVE_CSV["^NSEI"])
    rows = parse_archive_constituents(text)
    return [r["symbol"] for r in rows]


def fetch_bhavcopy(d: date) -> dict[str, dict]:
    """symbol -> {close, prev_close, chg_pct, date} for EQ series."""
    ddmmyyyy = d.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"__error__": str(e)}

    out: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        series = (row.get("SERIES") or row.get(" SERIES") or "").strip()
        if series != "EQ":
            continue
        sym = (row.get("SYMBOL") or row.get(" SYMBOL") or "").strip().upper()
        if not sym:
            continue
        try:
            close = float(row.get("CLOSE_PRICE") or row.get(" CLOSE_PRICE") or 0)
            prev = float(row.get("PREV_CLOSE") or row.get(" PREV_CLOSE") or 0)
        except (TypeError, ValueError):
            continue
        if prev <= 0 or close <= 0:
            continue
        chg = round((close - prev) / prev * 100, 2)
        out[sym] = {
            "close": round(close, 2),
            "prev_close": round(prev, 2),
            "chg_pct": chg,
            "date": d.strftime("%Y-%m-%d"),
        }
    return out


def db_last_bars(conn: sqlite3.Connection, symbol: str, n: int = 8) -> list[tuple]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT substr(Date,1,10) as d, Close
        FROM historical_data
        WHERE Symbol = ?
        ORDER BY Date DESC
        LIMIT ?
        """,
        (symbol, n),
    )
    return cur.fetchall()


def db_screener_chg(conn: sqlite3.Connection, symbol: str) -> float | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT change_percent FROM screener WHERE UPPER(TRIM(symbol)) = ?",
        (symbol.upper(),),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def main() -> int:
    if not DB_PATH.is_file():
        print(f"DB not found: {DB_PATH}")
        return 1

    symbols = load_nifty50_symbols()
    print(f"Nifty 50 constituents: {len(symbols)}")

    # Collect NSE bhavcopy for last ~14 calendar days (need 7 trading days)
    nse_by_date: dict[str, dict[str, dict]] = {}
    today = date.today()
    for offset in range(1, 15):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        bhav = fetch_bhavcopy(d)
        if "__error__" in bhav:
            continue
        if not bhav:
            continue
        nse_by_date[d.strftime("%Y-%m-%d")] = bhav

    if not nse_by_date:
        print("Could not fetch any NSE bhavcopy files.")
        return 1

    nse_dates = sorted(nse_by_date.keys(), reverse=True)[:TRADING_DAYS]
    latest_nse_date = nse_dates[0]
    print(f"NSE bhavcopy dates used: {nse_dates}")
    print(f"Latest NSE session: {latest_nse_date}\n")

    conn = sqlite3.connect(DB_PATH)
    mismatches_latest: list[str] = []
    week_mismatches: list[str] = []
    missing_db: list[str] = []

    for sym in sorted(symbols):
        bars = db_last_bars(conn, sym, TRADING_DAYS + 2)
        if len(bars) < 2:
            missing_db.append(sym)
            continue

        db_latest_date, db_latest_close = bars[0]
        _, db_prev_close = bars[1]
        db_chg = round((float(db_latest_close) - float(db_prev_close)) / float(db_prev_close) * 100, 2)

        nse_row = nse_by_date.get(latest_nse_date, {}).get(sym)
        screener_chg = db_screener_chg(conn, sym)

        if nse_row:
            nse_chg = nse_row["chg_pct"]
            diff = abs(db_chg - nse_chg)
            if diff > TOLERANCE_PCT or db_latest_date != latest_nse_date:
                mismatches_latest.append(
                    f"{sym}: DB {db_latest_date} {db_chg:+.2f}% (close {db_latest_close}) "
                    f"vs NSE {latest_nse_date} {nse_chg:+.2f}% (close {nse_row['close']}) "
                    f"screener={screener_chg}"
                )

        # Week: compare each NSE date to DB bar on that date vs prior
        for ds in nse_dates:
            nse = nse_by_date[ds].get(sym)
            if not nse:
                continue
            db_close_on = next((float(c) for d, c in bars if d == ds), None)
            if db_close_on is None:
                week_mismatches.append(f"{sym} {ds}: no DB bar on NSE date")
                continue
            if abs(db_close_on - nse["close"]) > 0.05:
                week_mismatches.append(
                    f"{sym} {ds}: DB close {db_close_on} vs NSE {nse['close']}"
                )

    conn.close()

    print("=== Latest session 1D % (DB last-two-bars vs NSE bhavcopy) ===")
    if mismatches_latest:
        for line in mismatches_latest:
            print(line)
        print(f"\nMISMATCH count: {len(mismatches_latest)} / {len(symbols)}")
    else:
        print(f"All {len(symbols)} symbols within {TOLERANCE_PCT}% on latest session.")

    if missing_db:
        print(f"\nMissing historical_data (<2 bars): {', '.join(missing_db)}")

    print("\n=== Week close-level mismatches (DB vs NSE) ===")
    if week_mismatches:
        for line in week_mismatches[:80]:
            print(line)
        if len(week_mismatches) > 80:
            print(f"... and {len(week_mismatches) - 80} more")
        print(f"\nWeek mismatch count: {len(week_mismatches)}")
    else:
        print("No close-level mismatches in checked window.")

    return 0 if not mismatches_latest else 2


if __name__ == "__main__":
    raise SystemExit(main())
