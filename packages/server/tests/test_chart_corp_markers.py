"""Tests for chart corp markers and DB split-gap detection."""
import sqlite3
import unittest

from server.chart_corp_markers import detect_unapplied_splits_from_history


class ChartCorpMarkersTests(unittest.TestCase):
    def test_detect_unapplied_splits_from_history(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Close REAL)")
        conn.executemany(
            "INSERT INTO historical_data (Symbol, Date, Close) VALUES (?, ?, ?)",
            [
                ("AAA", "2026-08-21 00:00:00+05:30", 1000.0),
                ("AAA", "2026-08-24 00:00:00+05:30", 500.0),
            ],
        )
        hits = detect_unapplied_splits_from_history(conn, lookback_days=90)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["symbol"], "AAA")
        self.assertEqual(hits[0]["split_date"], "2026-08-24")
        self.assertEqual(hits[0]["ratio"], 2.0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
