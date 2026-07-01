"""Tests for full-universe NSE price refresh and fresh screener quote handling."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from server import movers_data as md
from server.universe_price_refresh import (
    ensure_screener_price_columns,
    recalculate_screener_change_from_bars,
    should_skip_live_nse_quote_refresh,
)


class UniversePriceRefreshTests(unittest.TestCase):
    def test_ensure_screener_price_columns_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "CREATE TABLE screener (symbol TEXT PRIMARY KEY, price REAL, change_percent REAL)"
                )
                ensure_screener_price_columns(conn)
                ensure_screener_price_columns(conn)
                cols = {r[1] for r in conn.execute("PRAGMA table_info(screener)")}
                self.assertIn("previous_close", cols)
                self.assertIn("price_updated_at", cols)
            finally:
                conn.close()

    def test_recalculate_skips_during_live_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "CREATE TABLE screener (symbol TEXT PRIMARY KEY, change_percent REAL, change_percent_monthly REAL)"
                )
                conn.execute(
                    "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Close REAL)"
                )
                conn.execute("INSERT INTO screener VALUES ('AAA', 5.0, 10.0)")
                conn.execute("INSERT INTO historical_data VALUES ('AAA', '2026-06-09', 100.0)")
                conn.execute("INSERT INTO historical_data VALUES ('AAA', '2026-06-10', 110.0)")
                conn.commit()
                with patch("server.universe_price_refresh._session_intraday_active", return_value=True):
                    result = recalculate_screener_change_from_bars(conn, include_monthly=True)
                self.assertTrue(result.get("skipped"))
                row = conn.execute("SELECT change_percent FROM screener WHERE symbol='AAA'").fetchone()
                self.assertEqual(row[0], 5.0)
            finally:
                conn.close()

    def test_recalculate_runs_during_session_on_yahoo_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "CREATE TABLE screener (symbol TEXT PRIMARY KEY, change_percent REAL, change_percent_monthly REAL)"
                )
                conn.execute(
                    "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Close REAL)"
                )
                conn.execute("INSERT INTO screener VALUES ('AAA', 0.0, 0.0)")
                conn.execute("INSERT INTO historical_data VALUES ('AAA', '2026-06-09', 100.0)")
                conn.execute("INSERT INTO historical_data VALUES ('AAA', '2026-06-10', 110.0)")
                conn.commit()
                with patch("server.universe_price_refresh._session_intraday_active", return_value=True):
                    with patch("server.product_config.yahoo_primary_pipeline", return_value=True):
                        result = recalculate_screener_change_from_bars(conn, include_monthly=False)
                self.assertFalse(result.get("skipped"))
                row = conn.execute("SELECT change_percent FROM screener WHERE symbol='AAA'").fetchone()
                self.assertAlmostEqual(row[0], 10.0, places=2)
            finally:
                conn.close()

    def test_recalculate_updates_when_not_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "CREATE TABLE screener (symbol TEXT PRIMARY KEY, change_percent REAL, change_percent_monthly REAL)"
                )
                conn.execute(
                    "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Close REAL)"
                )
                conn.execute("INSERT INTO screener VALUES ('AAA', 0.0, 0.0)")
                conn.execute("INSERT INTO historical_data VALUES ('AAA', '2026-06-09', 100.0)")
                conn.execute("INSERT INTO historical_data VALUES ('AAA', '2026-06-10', 110.0)")
                conn.commit()
                with patch("server.universe_price_refresh._session_intraday_active", return_value=False):
                    result = recalculate_screener_change_from_bars(conn, include_monthly=False)
                self.assertFalse(result.get("skipped"))
                row = conn.execute("SELECT change_percent FROM screener WHERE symbol='AAA'").fetchone()
                self.assertAlmostEqual(row[0], 10.0, places=2)
            finally:
                conn.close()

    def test_should_skip_live_nse_after_close(self):
        with patch("server.universe_price_refresh._session_intraday_active", return_value=False):
            skip, msg = should_skip_live_nse_quote_refresh(bhav_screener_written=2014)
        self.assertTrue(skip)
        self.assertIn("bhavcopy", msg)

    def test_should_not_skip_live_nse_during_session(self):
        with patch("server.universe_price_refresh._session_intraday_active", return_value=True):
            skip, msg = should_skip_live_nse_quote_refresh(bhav_screener_written=2014)
        self.assertFalse(skip)
        self.assertEqual(msg, "")

    def test_apply_fresh_screener_quotes_uses_today_rows(self):
        today_s = datetime.now(md.IST).strftime("%Y-%m-%d")
        df = pd.DataFrame([
            {
                "symbol": "FRESH",
                "price": 100.0,
                "change_pct": 0.0,
                "screener_price": 105.0,
                "screener_change_pct": 5.0,
                "price_updated_at": f"{today_s} 10:00:00",
            },
            {
                "symbol": "STALE",
                "price": 100.0,
                "change_pct": 0.0,
                "screener_price": 120.0,
                "screener_change_pct": 20.0,
                "price_updated_at": "2020-01-01 10:00:00",
            },
        ])
        out = md.apply_fresh_screener_quotes(df)
        fresh = out.loc[out["symbol"] == "FRESH"].iloc[0]
        stale = out.loc[out["symbol"] == "STALE"].iloc[0]
        self.assertAlmostEqual(float(fresh["price"]), 105.0, places=2)
        self.assertAlmostEqual(float(fresh["change_pct"]), 5.0, places=2)
        self.assertAlmostEqual(float(stale["price"]), 100.0, places=2)
        self.assertAlmostEqual(float(stale["change_pct"]), 0.0, places=2)

    def test_session_adjustment_skips_fresh_screener_rows(self):
        today_s = datetime.now(md.IST).strftime("%Y-%m-%d")
        df = pd.DataFrame([
            {
                "symbol": "FRESH",
                "change_pct": 5.0,
                "eod_close": 100.0,
                "eod_prev_close": 95.0,
                "screener_price": 105.0,
                "screener_change_pct": 5.0,
                "price_updated_at": f"{today_s} 10:00:00",
                "as_of_date": "2026-06-01",
                "market_cap": 1e9,
            },
        ])
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            out = md.apply_session_day_adjustment(df)
        self.assertAlmostEqual(float(out.loc[0, "change_pct"]), 5.0, places=2)


if __name__ == "__main__":
    unittest.main()
