"""Tests for family-scoped indicator snapshot rebuild merge."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scrape_daily import (  # noqa: E402
    SNAPSHOT_ALL_FAMILIES,
    _merge_snapshot_rows_with_existing,
    _normalize_snapshot_families,
    _snapshot_merge_needed,
    build_snapshot_payload,
    ensure_indicator_snapshot_table,
)


def _sample_candles(n=30):
    out = []
    for i in range(n):
        c = 100 + i * 0.5
        out.append((f"2024-01-{i + 1:02d}", c, c + 1, c - 1, c))
    return out


class TestSnapshotFamilyRebuild(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_indicator_snapshot_table(self.conn)
        cur = self.conn.cursor()
        full = build_snapshot_payload("AAA", "1D", _sample_candles(), families=SNAPSHOT_ALL_FAMILIES)
        cur.execute(
            """
            INSERT INTO indicator_snapshots (
                symbol, timeframe, close_curr, close_prev, open_curr, open_prev,
                high_curr, high_prev, low_curr, low_prev,
                ema9, ema9_prev, ema21, ema21_prev, ema50, ema50_prev,
                ema100, ema100_prev, ema200, ema200_prev,
                macd, macd_prev, macd_signal, macd_signal_prev, macd_hist_chain,
                stoch_k, stoch_k_prev, stoch_d, stoch_d_prev
            ) VALUES (
                :symbol, :timeframe, :close_curr, :close_prev, :open_curr, :open_prev,
                :high_curr, :high_prev, :low_curr, :low_prev,
                :ema9, :ema9_prev, :ema21, :ema21_prev, :ema50, :ema50_prev,
                :ema100, :ema100_prev, :ema200, :ema200_prev,
                :macd, :macd_prev, :macd_signal, :macd_signal_prev, :macd_hist_chain,
                :stoch_k, :stoch_k_prev, :stoch_d, :stoch_d_prev
            )
            """,
            full,
        )
        self.conn.commit()
        self.original_macd = full["macd"]

    def tearDown(self):
        self.conn.close()

    def test_ema_only_payload_preserves_macd_on_merge(self):
        ema_only = build_snapshot_payload("AAA", "1D", _sample_candles(), families={"ema"})
        self.assertNotIn("macd", ema_only)
        cur = self.conn.cursor()
        merged = _merge_snapshot_rows_with_existing(cur, [ema_only], {"ema"})
        self.assertEqual(len(merged), 1)
        self.assertIsNotNone(merged[0]["ema9"])
        self.assertEqual(merged[0]["macd"], self.original_macd)

    def test_full_families_skip_merge(self):
        self.assertFalse(_snapshot_merge_needed(SNAPSHOT_ALL_FAMILIES))
        self.assertTrue(_snapshot_merge_needed({"ema"}))
        self.assertEqual(_normalize_snapshot_families(["ema", "bad"]), frozenset({"ema"}))


if __name__ == "__main__":
    unittest.main()
