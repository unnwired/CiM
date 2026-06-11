#!/usr/bin/env python3
"""
One-shot development database seeder for Charts In Motion.

Creates data/nse_data.db with screener rows, indices, and ~2 years of synthetic OHLCV
so charts and the screener work offline without running scrapers.

Usage:
  python scripts/dev_setup.py          # skip if DB already has stocks + OHLCV
  python scripts/dev_setup.py --force  # recreate from scratch
"""
from __future__ import annotations

import argparse
import math
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "nse_data.db"

DEV_STOCKS = [
    ("RELIANCE", "Reliance Industries", 1800000, 2850.0, 24.5, "Energy"),
    ("TCS", "Tata Consultancy Services", 1400000, 3890.0, 32.0, "IT"),
    ("INFY", "Infosys", 750000, 1820.0, 28.5, "IT"),
    ("HDFCBANK", "HDFC Bank", 1200000, 1680.0, 18.2, "Financial Services"),
    ("ICICIBANK", "ICICI Bank", 850000, 1120.0, 16.8, "Financial Services"),
    ("HINDUNILVR", "Hindustan Unilever", 620000, 2380.0, 55.0, "FMCG"),
    ("ITC", "ITC", 580000, 465.0, 28.0, "FMCG"),
    ("SBIN", "State Bank of India", 720000, 780.0, 9.5, "Financial Services"),
    ("BHARTIARTL", "Bharti Airtel", 680000, 1580.0, 42.0, "Telecom"),
    ("KOTAKBANK", "Kotak Mahindra Bank", 420000, 1780.0, 20.5, "Financial Services"),
    ("LT", "Larsen & Toubro", 480000, 3450.0, 35.0, "Capital Goods"),
    ("AXISBANK", "Axis Bank", 380000, 1120.0, 14.2, "Financial Services"),
    ("ASIANPAINT", "Asian Paints", 320000, 2850.0, 58.0, "Consumer Durables"),
    ("MARUTI", "Maruti Suzuki", 350000, 11800.0, 28.0, "Automobile"),
    ("TITAN", "Titan Company", 310000, 3450.0, 85.0, "Consumer Durables"),
    ("SUNPHARMA", "Sun Pharmaceutical", 340000, 1680.0, 38.0, "Healthcare"),
    ("WIPRO", "Wipro", 280000, 520.0, 22.0, "IT"),
    ("ULTRACEMCO", "UltraTech Cement", 290000, 11200.0, 45.0, "Construction"),
    ("NESTLEIND", "Nestle India", 260000, 2280.0, 72.0, "FMCG"),
    ("BAJFINANCE", "Bajaj Finance", 520000, 7200.0, 32.0, "Financial Services"),
]

DEV_INDICES = [
    ("NIFTY 50", "Nifty 50", "Broad", 24500.0),
    ("NIFTY BANK", "Nifty Bank", "Sector", 52000.0),
    ("NIFTY IT", "Nifty IT", "Sector", 38500.0),
]

SCREENER_DDL = """
CREATE TABLE IF NOT EXISTS screener (
    symbol TEXT PRIMARY KEY,
    market_cap REAL,
    price REAL,
    change_percent REAL,
    change_percent_monthly REAL,
    pe REAL,
    revenue_growth_ttm REAL,
    revenue_growth_qoq REAL,
    net_income_ttm REAL,
    net_income_qoq REAL,
    ebitda_growth_qoq REAL,
    recent_earnings REAL,
    upcoming_earnings REAL,
    ema9 REAL, ema21 REAL, ema50 REAL, ema100 REAL, ema200 REAL,
    ema9_prev REAL, ema21_prev REAL, ema50_prev REAL, ema100_prev REAL, ema200_prev REAL,
    nse_sector TEXT,
    nse_industry TEXT,
    isin TEXT,
    upcoming_result_date TEXT,
    next_expected_date TEXT,
    earnings_verification_status TEXT,
    earnings_verification_meta TEXT,
    issued_shares INTEGER
)
"""

HISTORICAL_DDL = """
CREATE TABLE IF NOT EXISTS historical_data (
    Symbol TEXT,
    Date TEXT,
    Open REAL,
    High REAL,
    Low REAL,
    Close REAL,
    AdjClose REAL,
    Volume REAL,
    MarketCap REAL,
    PRIMARY KEY (Symbol, Date)
)
"""

INDICES_DDL = """
CREATE TABLE IF NOT EXISTS indices (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    last_price REAL,
    change_pct REAL,
    change_30d REAL,
    change_1y REAL,
    updated_at TEXT
)
"""

INDEX_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS index_history (
    Symbol TEXT,
    Date TEXT,
    Open REAL,
    High REAL,
    Low REAL,
    Close REAL,
    Volume REAL,
    PRIMARY KEY (Symbol, Date)
)
"""


def _db_ready(conn: sqlite3.Connection) -> bool:
    try:
        n_stocks = conn.execute("SELECT COUNT(*) FROM screener").fetchone()[0]
        n_bars = conn.execute("SELECT COUNT(*) FROM historical_data").fetchone()[0]
        return n_stocks >= 5 and n_bars >= 100
    except sqlite3.OperationalError:
        return False


def _trading_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _seed_ohlcv(conn: sqlite3.Connection, symbol: str, base_price: float, mcap: float) -> None:
    end = date.today()
    start = end - timedelta(days=730)
    price = base_price
    rows = []
    for d in _trading_days(start, end):
        drift = random.uniform(-0.025, 0.025)
        open_p = price
        close_p = max(1.0, price * (1.0 + drift))
        high_p = max(open_p, close_p) * (1.0 + random.uniform(0, 0.012))
        low_p = min(open_p, close_p) * (1.0 - random.uniform(0, 0.012))
        vol = random.randint(500_000, 5_000_000)
        ds = d.isoformat()
        rows.append((symbol, ds, open_p, high_p, low_p, close_p, close_p, float(vol), mcap))
        price = close_p
    conn.executemany(
        """
        INSERT OR REPLACE INTO historical_data
        (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _sync_change_percent(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE screener SET
            price = (
                SELECT Close FROM historical_data h1
                WHERE h1.Symbol = screener.symbol
                ORDER BY h1.Date DESC LIMIT 1
            ),
            change_percent = (
                SELECT ROUND(
                    (
                        (SELECT Close FROM historical_data h1
                         WHERE h1.Symbol = screener.symbol ORDER BY h1.Date DESC LIMIT 1)
                        - (SELECT Close FROM historical_data h2
                           WHERE h2.Symbol = screener.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
                    )
                    / (SELECT Close FROM historical_data h3
                       WHERE h3.Symbol = screener.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1)
                    * 100, 2)
            )
        WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = screener.symbol)
        """
    )


def _seed_indices(conn: sqlite3.Connection) -> None:
    today = date.today().isoformat()
    for sym, name, cat, px in DEV_INDICES:
        conn.execute(
            """
            INSERT OR REPLACE INTO indices
            (symbol, name, category, last_price, change_pct, change_30d, change_1y, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sym, name, cat, px, round(random.uniform(-1.5, 1.5), 2), round(random.uniform(-5, 8), 2), round(random.uniform(-10, 25), 2), today),
        )
        base = px
        for d in _trading_days(date.today() - timedelta(days=365), date.today()):
            drift = random.uniform(-0.015, 0.015)
            o = base
            c = max(1.0, base * (1.0 + drift))
            h = max(o, c) * 1.005
            l = min(o, c) * 0.995
            conn.execute(
                """
                INSERT OR REPLACE INTO index_history (Symbol, Date, Open, High, Low, Close, Volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sym, d.isoformat(), o, h, l, c, float(random.randint(1_000_000, 10_000_000))),
            )
            base = c


def run_setup(*, force: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and not force:
        conn = sqlite3.connect(DB_PATH)
        try:
            if _db_ready(conn):
                _sync_change_percent(conn)
                conn.commit()
                print(f"[dev_setup] Database already seeded: {DB_PATH}")
                print("[dev_setup] Refreshed change_percent from latest OHLCV bars.")
                return
        finally:
            conn.close()

    if force and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"[dev_setup] Removed existing {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(
            SCREENER_DDL + HISTORICAL_DDL + INDICES_DDL + INDEX_HISTORY_DDL
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hist_symbol_date ON historical_data(Symbol, Date)"
        )

        for symbol, _name, mcap, price, pe, sector in DEV_STOCKS:
            conn.execute(
                """
                INSERT OR REPLACE INTO screener
                (symbol, market_cap, price, change_percent, pe, nse_sector, issued_shares)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
                """,
                (symbol, mcap, price, pe, sector, int(mcap * 1e7 / max(price, 1))),
            )
            _seed_ohlcv(conn, symbol, price, mcap)

        _sync_change_percent(conn)
        _seed_indices(conn)
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM screener").fetchone()[0]
        bars = conn.execute("SELECT COUNT(*) FROM historical_data").fetchone()[0]
        print(f"[dev_setup] Created {DB_PATH}")
        print(f"[dev_setup] Seeded {n} stocks, {bars} OHLCV bars, {len(DEV_INDICES)} indices.")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Charts In Motion dev database")
    parser.add_argument("--force", action="store_true", help="Recreate database from scratch")
    args = parser.parse_args()
    run_setup(force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
