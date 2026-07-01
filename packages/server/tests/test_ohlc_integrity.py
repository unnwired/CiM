"""Tests for OHLC scale discontinuity detection and repair orchestration."""

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
        CREATE TABLE historical_data (
            Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL,
            AdjClose REAL, Volume REAL, MarketCap REAL,
            PRIMARY KEY (Symbol, Date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE screener (
            symbol TEXT PRIMARY KEY, price REAL, change_percent REAL
        )
        """
    )
    conn.commit()
    return conn


class TestOhlcIntegrityScanner(unittest.TestCase):
    def test_detects_trent_like_cliff(self):
        from ohlc_integrity import scan_ohlc_discontinuities

        conn = _mem_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO screener VALUES ('TRENT', 0, 0)")
        rows = [
            ("TRENT", "2026-05-27 00:00:00+05:30", 2832.4),
            ("TRENT", "2026-05-28 00:00:00+05:30", 2832.4),
            ("TRENT", "2026-05-29 00:00:00+05:30", 4224.0),
            ("TRENT", "2026-06-03 00:00:00+05:30", 4257.6),
            ("TRENT", "2026-06-04 00:00:00+05:30", 2837.6),
            ("TRENT", "2026-06-05 00:00:00+05:30", 2774.2),
        ]
        for sym, ds, close in rows:
            cur.execute(
                "INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?,?)",
                (sym, ds, close, close, close, close, close, 1000.0, None),
            )
        conn.commit()

        hits = scan_ohlc_discontinuities(conn, lookback_calendar_days=60, symbols=["TRENT"])
        symbols = {h["symbol"] for h in hits}
        self.assertIn("TRENT", symbols)
        self.assertTrue(any(abs(h["pct"]) > 25 for h in hits))


class TestRepairOrchestration(unittest.TestCase):
    @patch("split_utils.apply_symbol_history_refresh")
    def test_repair_calls_yahoo_refresh(self, mock_refresh):
        from ohlc_integrity import repair_ohlc_anomalies

        mock_refresh.return_value = (True, "")
        conn = _mem_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO screener VALUES ('TRENT', 0, 0)")
        for ds, close in [
            ("2026-05-28 00:00:00+05:30", 2832.4),
            ("2026-05-29 00:00:00+05:30", 4224.0),
            ("2026-06-04 00:00:00+05:30", 2837.6),
            ("2026-06-05 00:00:00+05:30", 2774.2),
            ("2026-06-06 00:00:00+05:30", 2770.0),
        ]:
            cur.execute(
                "INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?,?)",
                ("TRENT", ds, close, close, close, close, close, 1000.0, None),
            )
        conn.commit()

        with patch("nse_bhavcopy.sync_screener_from_bhavcopy", return_value=0):
            result = repair_ohlc_anomalies(
                conn,
                symbols=["TRENT"],
                apply_bhav_screener_overlay=True,
            )
        self.assertEqual(result["repaired_count"], 1)
        mock_refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
