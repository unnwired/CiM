"""Tests for 4H bar integrity scanning, daily rescale repair, and host repair queue."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


def _mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE bars_4h (
            Symbol TEXT NOT NULL,
            BarStart TEXT NOT NULL,
            SessionDate TEXT NOT NULL,
            Bucket INTEGER NOT NULL,
            Open REAL, High REAL, Low REAL, Close REAL, Volume REAL,
            PRIMARY KEY (Symbol, BarStart)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE historical_data (
            Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL,
            AdjClose REAL, Volume REAL, MarketCap REAL,
            PRIMARY KEY (Symbol, Date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE screener (symbol TEXT PRIMARY KEY, price REAL, change_percent REAL)
        """
    )
    cur.execute(
        """
        CREATE TABLE updater_meta (key TEXT PRIMARY KEY, value TEXT)
        """
    )
    conn.commit()
    return conn


def _insert_4h(conn, sym, sd, bucket, close):
    bar_start = f"{sd}T{'09:15:00' if bucket == 1 else '13:15:00'}+05:30"
    conn.execute(
        "INSERT INTO bars_4h VALUES (?,?,?,?,?,?,?,?,?)",
        (sym, bar_start, sd, bucket, close, close, close, close, 1000.0),
    )


class TestBars4hIntegrityScanner(unittest.TestCase):
    def test_detects_trent_like_cliff(self):
        from server.bars_4h_integrity import scan_bars_4h_anomalies

        conn = _mem_conn()
        conn.execute("INSERT INTO screener VALUES ('TRENT', 2840, 0)")
        days = [
            ("2026-05-27", 1828.0),
            ("2026-05-28", 1828.0),
            ("2026-05-29", 1828.0),
            ("2026-06-02", 1828.0),
            ("2026-06-03", 2840.0),
            ("2026-06-04", 2835.0),
        ]
        for sd, close in days:
            _insert_4h(conn, "TRENT", sd, 2, close)
            conn.execute(
                "INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?,?)",
                ("TRENT", f"{sd} 00:00:00+05:30", close, close, close, close, close, 1000.0, None),
            )
        conn.commit()

        hits = scan_bars_4h_anomalies(conn, lookback_calendar_days=60, symbols=["TRENT"])
        kinds = {h["kind"] for h in hits}
        self.assertIn("TRENT", {h["symbol"] for h in hits})
        self.assertTrue("discontinuity" in kinds or "daily_anchor" in kinds or "flatline" in kinds)

    def test_flatline_vs_daily(self):
        from server.bars_4h_integrity import scan_bars_4h_anomalies

        conn = _mem_conn()
        conn.execute("INSERT INTO screener VALUES ('TRENT', 2840, 0)")
        flat_days = ["2026-05-22", "2026-05-23", "2026-05-26", "2026-05-27", "2026-05-28"]
        daily_closes = [2700.0, 2720.0, 2750.0, 2780.0, 2840.0]
        for sd, d_close in zip(flat_days, daily_closes):
            _insert_4h(conn, "TRENT", sd, 2, 1828.0)
            conn.execute(
                "INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?,?)",
                ("TRENT", f"{sd} 00:00:00+05:30", d_close, d_close, d_close, d_close, d_close, 1000.0, None),
            )
        conn.commit()

        hits = scan_bars_4h_anomalies(conn, lookback_calendar_days=60, symbols=["TRENT"])
        self.assertTrue(any(h["kind"] == "flatline" for h in hits))


class TestDailyRescale(unittest.TestCase):
    def test_rescale_fixes_trent_flatline(self):
        from server.bars_4h_integrity import (
            rescale_bars_4h_from_daily_anchor,
            scan_bars_4h_anomalies,
        )

        conn = _mem_conn()
        flat_days = ["2026-05-22", "2026-05-23", "2026-05-26", "2026-05-27", "2026-05-28"]
        daily_closes = [2700.0, 2720.0, 2750.0, 2780.0, 2840.0]
        for sd, d_close in zip(flat_days, daily_closes):
            _insert_4h(conn, "TRENT", sd, 2, 1828.0)
            conn.execute(
                "INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?,?)",
                ("TRENT", f"{sd} 00:00:00+05:30", d_close, d_close, d_close, d_close, d_close, 1000.0, None),
            )
        conn.commit()

        before = scan_bars_4h_anomalies(conn, lookback_calendar_days=60, symbols=["TRENT"])
        self.assertTrue(before)

        result = rescale_bars_4h_from_daily_anchor(conn, "TRENT", lookback_calendar_days=60)
        self.assertEqual(result["scaled_sessions"], 5)

        after = scan_bars_4h_anomalies(conn, lookback_calendar_days=60, symbols=["TRENT"])
        self.assertFalse(any(h["kind"] == "flatline" for h in after))
        self.assertFalse(any(h["kind"] == "daily_anchor" for h in after))

        row = conn.execute(
            "SELECT Close FROM bars_4h WHERE Symbol='TRENT' AND SessionDate='2026-05-28'"
        ).fetchone()
        self.assertAlmostEqual(float(row[0]), 2840.0, places=1)


class TestRepairOrchestration(unittest.TestCase):
    @patch("server.bars_4h.build_bars_4h_for_symbols")
    def test_repair_uses_rescale_without_yahoo_when_clean(self, mock_build):
        from server.bars_4h_integrity import repair_bars_4h_symbol

        mock_build.return_value = {"updated": 0, "failed": 0, "skipped": 0}
        conn = _mem_conn()
        flat_days = ["2026-05-22", "2026-05-23", "2026-05-26", "2026-05-27", "2026-05-28"]
        daily_closes = [2700.0, 2720.0, 2750.0, 2780.0, 2840.0]
        for sd, d_close in zip(flat_days, daily_closes):
            _insert_4h(conn, "TRENT", sd, 2, 1828.0)
            conn.execute(
                "INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?,?)",
                ("TRENT", f"{sd} 00:00:00+05:30", d_close, d_close, d_close, d_close, d_close, 1000.0, None),
            )
        conn.commit()

        outcome = repair_bars_4h_symbol(conn, ROOT, "TRENT", lookback_calendar_days=60)
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["steps"], ["daily_rescale"])
        mock_build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
