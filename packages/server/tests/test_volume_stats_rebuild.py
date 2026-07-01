"""Tests for symbol_volume_stats rebuild and avg_volume fast path."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[1]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from volume_stats_rebuild import (  # noqa: E402
    ensure_symbol_volume_stats_table,
    query_avg_volume_from_stats,
    rebuild_volume_stats_universe,
)


class TestVolumeStatsRebuild(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Volume REAL)"
        )
        for i in range(1, 31):
            cur.execute(
                "INSERT INTO historical_data VALUES (?, ?, ?)",
                ("AAA", f"2024-01-{i:02d}", float(i * 1000)),
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_rebuild_populates_stats(self):
        n = rebuild_volume_stats_universe(self.conn)
        self.assertEqual(n, 1)
        cur = self.conn.cursor()
        cur.execute("SELECT avg_volume_10, avg_volume_20, avg_volume_30 FROM symbol_volume_stats WHERE symbol='AAA'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row[0], sum(i * 1000 for i in range(21, 31)) / 10, places=2)

    def test_fast_path_period_20(self):
        rebuild_volume_stats_universe(self.conn)
        results = query_avg_volume_from_stats(
            self.conn,
            {"period": 20, "min_volume": 15000, "condition": "above"},
        )
        self.assertIsNotNone(results)
        self.assertIn("AAA", results)

    def test_fast_path_skips_odd_period(self):
        rebuild_volume_stats_universe(self.conn)
        results = query_avg_volume_from_stats(
            self.conn,
            {"period": 15, "min_volume": 1, "condition": "above"},
        )
        self.assertIsNone(results)


if __name__ == "__main__":
    unittest.main()
