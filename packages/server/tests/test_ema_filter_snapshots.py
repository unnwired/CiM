"""Tests for EMA filter snapshot usability helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from server.server import (  # noqa: E402
    SNAPSHOT_FILTER_MIN_COVERAGE,
    _snapshot_ema_column_coverage,
    _snapshots_usable_for_ema_filter,
)


class TestEmaFilterSnapshots(unittest.TestCase):
    def test_rejects_weekly_rows_missing_ema200(self):
        rows = [
            {"symbol": "AAA", "ema100": 10.0, "ema200": None},
            {"symbol": "BBB", "ema100": 12.0, "ema200": None},
        ]
        self.assertLess(_snapshot_ema_column_coverage(rows, 200), SNAPSHOT_FILTER_MIN_COVERAGE)
        self.assertFalse(
            _snapshots_usable_for_ema_filter(rows, 100, "ema", 200),
        )

    def test_accepts_when_both_emas_populated(self):
        rows = [
            {"symbol": "AAA", "ema100": 10.0, "ema200": 9.0},
            {"symbol": "BBB", "ema100": 12.0, "ema200": 11.0},
        ]
        self.assertTrue(
            _snapshots_usable_for_ema_filter(rows, 100, "ema", 200),
        )


if __name__ == "__main__":
    unittest.main()
