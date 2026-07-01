"""Tests for range_channel_snapshots canonical fast path."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[1]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from filter_rebuild_registry import RANGE_CHANNEL_CANONICAL_PARAMS  # noqa: E402
from range_channel_snapshots_rebuild import (  # noqa: E402
    filter_params_match_canonical,
    query_range_channel_from_snapshots,
    rebuild_range_channel_snapshots,
)


class TestRangeChannelSnapshots(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TABLE screener (symbol TEXT PRIMARY KEY)"
        )
        cur.execute("INSERT INTO screener VALUES ('AAA')")
        cur.execute(
            "CREATE TABLE range_channel_snapshots ("
            "symbol TEXT, timeframe TEXT, params_hash TEXT, passes INTEGER, "
            "channel_width_pct REAL, updated_at TEXT, "
            "PRIMARY KEY (symbol, timeframe, params_hash))"
        )
        from range_channel_snapshots_rebuild import canonical_params_hash

        p_hash = canonical_params_hash()
        cur.execute(
            "INSERT INTO range_channel_snapshots VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ("AAA", "3D", p_hash, 1, 12.5),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_canonical_params_match(self):
        body = dict(RANGE_CHANNEL_CANONICAL_PARAMS)
        self.assertTrue(filter_params_match_canonical(body))

    def test_custom_params_do_not_match(self):
        body = {**RANGE_CHANNEL_CANONICAL_PARAMS, "lookback_bars": 24}
        self.assertFalse(filter_params_match_canonical(body))

    def test_snapshot_query_returns_passing_symbols(self):
        body = dict(RANGE_CHANNEL_CANONICAL_PARAMS)
        results = query_range_channel_from_snapshots(self.conn, body)
        self.assertEqual(results, ["AAA"])

    def test_mismatch_returns_none(self):
        body = {**RANGE_CHANNEL_CANONICAL_PARAMS, "max_channel_width_pct": 10}
        results = query_range_channel_from_snapshots(self.conn, body)
        self.assertIsNone(results)


if __name__ == "__main__":
    unittest.main()
