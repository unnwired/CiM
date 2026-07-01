import sqlite3
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from nse_bhavcopy import fetch_bhavcopy_rows, reconcile_recent_eod_from_nse, sync_screener_from_bhavcopy


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


class TestNseBhavcopy(unittest.TestCase):
    def test_fetch_mm_row_matches_nse_close(self):
        rows = fetch_bhavcopy_rows(date(2026, 6, 10))
        self.assertIn("M&M", rows)
        mm = rows["M&M"]
        self.assertEqual(mm["close"], 2952.5)
        self.assertEqual(mm["trade_date"], "2026-06-10")

    def test_reconcile_does_not_write_historical_data(self):
        conn = _mem_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO historical_data VALUES ('TRENT','2026-06-01 00:00:00+05:30',2800,2800,2800,2816,2816,1000,NULL)"
        )
        cur.execute("INSERT INTO screener VALUES ('TRENT', 0, 0)")
        conn.commit()
        before = cur.execute("SELECT COUNT(*) FROM historical_data").fetchone()[0]

        fake_bhav = {
            "TRENT": {
                "open": 2830.0,
                "high": 2849.0,
                "low": 2751.0,
                "close": 2837.6,
                "volume": 100.0,
                "trade_date": "2026-06-04",
            }
        }

        with patch("nse_bhavcopy.fetch_bhavcopy_rows", return_value=fake_bhav):
            n = reconcile_recent_eod_from_nse(conn, ["TRENT"], lookback_calendar_days=3)

        after = cur.execute("SELECT COUNT(*) FROM historical_data").fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(n, 1)
        row = cur.execute(
            "SELECT price, change_percent FROM screener WHERE symbol='TRENT'"
        ).fetchone()
        self.assertEqual(row[0], 2837.6)

    def test_screener_overlay_computes_change_percent(self):
        conn = _mem_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO historical_data VALUES ('TRENT','2026-06-03 00:00:00+05:30',2800,2800,2800,2806,2806,1000,NULL)"
        )
        cur.execute("INSERT INTO screener VALUES ('TRENT', 0, 0)")
        conn.commit()

        def fake_fetch(d, **kwargs):
            return {
                "TRENT": {
                    "close": 2837.6,
                    "trade_date": "2026-06-04",
                    "open": 2830.0,
                    "high": 2849.0,
                    "low": 2751.0,
                    "volume": 1.0,
                }
            }

        with patch("nse_bhavcopy.fetch_bhavcopy_rows", side_effect=fake_fetch):
            with patch("nse_bhavcopy.time.sleep", return_value=None):
                updated = sync_screener_from_bhavcopy(conn, ["TRENT"], lookback_calendar_days=3)

        self.assertEqual(updated, 1)
        price, chg = cur.execute(
            "SELECT price, change_percent FROM screener WHERE symbol='TRENT'"
        ).fetchone()
        self.assertEqual(price, 2837.6)
        self.assertAlmostEqual(chg, round((2837.6 - 2806.0) / 2806.0 * 100, 2), places=2)


if __name__ == "__main__":
    unittest.main()
