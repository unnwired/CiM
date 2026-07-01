"""Tests for incremental-safe indicator snapshot rebuild helpers."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scrape_daily import (  # noqa: E402
    SNAPSHOT_INCREMENTAL_MAX_DAILY_BARS,
    _is_incremental_snapshot_run,
    _load_candles_batch,
)


class TestSnapshotIncrementalSafe(unittest.TestCase):
    def test_incremental_run_detection(self):
        self.assertTrue(_is_incremental_snapshot_run(["RELIANCE"], False))
        self.assertFalse(_is_incremental_snapshot_run(["RELIANCE"], True))
        self.assertFalse(_is_incremental_snapshot_run(None, False))
        self.assertFalse(_is_incremental_snapshot_run(None, True))

    def test_load_candles_batch_caps_trailing_bars(self):
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL)"
        )
        for i in range(10):
            cur.execute(
                "INSERT INTO historical_data VALUES (?, ?, 1, 2, 0.5, 1.5)",
                ("AAA", f"2024-01-{i + 1:02d}"),
            )
        for i in range(10):
            cur.execute(
                "INSERT INTO historical_data VALUES (?, ?, 1, 2, 0.5, 1.5)",
                ("BBB", f"2024-02-{i + 1:02d}"),
            )
        conn.commit()

        all_rows = _load_candles_batch(cur, ["AAA", "BBB"], max_daily_bars=None)
        self.assertEqual(len(all_rows["AAA"]), 10)
        self.assertEqual(len(all_rows["BBB"]), 10)

        capped = _load_candles_batch(cur, ["AAA", "BBB"], max_daily_bars=3)
        self.assertEqual(len(capped["AAA"]), 3)
        self.assertEqual(capped["AAA"][0][0], "2024-01-08")
        self.assertEqual(capped["AAA"][-1][0], "2024-01-10")
        self.assertEqual(len(capped["BBB"]), 3)

        conn.close()

    def test_default_incremental_bar_cap_sane(self):
        self.assertGreaterEqual(SNAPSHOT_INCREMENTAL_MAX_DAILY_BARS, 260)


if __name__ == "__main__":
    unittest.main()
