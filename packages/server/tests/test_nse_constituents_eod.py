import sqlite3
import unittest
from unittest.mock import patch

from nse_constituents import enrich_archive_rows


class TestNseConstituentsEod(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE historical_data (
                Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE screener (
                symbol TEXT, market_cap REAL, change_percent REAL, price REAL,
                nse_sector TEXT, issued_shares REAL
            )
            """
        )
        cur.executemany(
            "INSERT INTO historical_data VALUES (?,?,?,?,?,?)",
            [
                ("MM", "2026-06-03 00:00:00+05:30", 100, 101, 99, 100.0),
                ("MM", "2026-06-04 00:00:00+05:30", 100, 102, 98, 95.0),
            ],
        )
        cur.execute(
            "INSERT INTO screener VALUES (?,?,?,?,?,?)",
            ("MM", None, 5.0, 105.0, "Auto", 1_000_000),
        )
        self.conn.commit()

    @patch("nse_constituents._session_day_intraday_active", return_value=False)
    def test_enrich_prefers_historical_over_stale_screener(self, _intraday):
        rows = enrich_archive_rows([{"symbol": "MM", "company_name": "M&M"}], self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["change_pct"], -5.0)
        self.assertEqual(rows[0]["last_price"], 95.0)

    @patch("nse_constituents._session_day_intraday_active", return_value=False)
    @patch("nse_constituents._live_snap_for_symbol")
    def test_enrich_ignores_stale_live_cache_after_close(self, live_snap, _intraday):
        live_snap.return_value = {"price": 110.0, "change_pct": 10.0}
        rows = enrich_archive_rows([{"symbol": "MM", "company_name": "M&M"}], self.conn)
        self.assertEqual(rows[0]["change_pct"], -5.0)
        self.assertEqual(rows[0]["last_price"], 95.0)


if __name__ == "__main__":
    unittest.main()
