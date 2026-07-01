"""Tests for aggregate_ohlcv chart engine."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

from repo_paths import REPO_ROOT as ROOT

_PKG = ROOT / "packages"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from server.server import aggregate_ohlcv  # noqa: E402


def _make_daily_df(rows):
    return pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])


class ChartAggregationTests(unittest.TestCase):
    def test_1d_passthrough(self):
        df = _make_daily_df([
            ("2025-01-06", 100, 110, 95, 105, 1_000_000),
            ("2025-01-07", 105, 115, 100, 108, 900_000),
        ])
        bars = aggregate_ohlcv(df, "1D")
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]["open"], 100)
        self.assertEqual(bars[0]["close"], 105)
        self.assertEqual(bars[1]["close"], 108)

    def test_1w_aggregation(self):
        df = _make_daily_df([
            ("2025-01-06", 100, 115, 98, 110, 500_000),
            ("2025-01-07", 110, 120, 105, 118, 600_000),
            ("2025-01-08", 118, 125, 112, 115, 550_000),
            ("2025-01-09", 115, 116, 108, 109, 480_000),
            ("2025-01-10", 109, 112, 100, 102, 520_000),
        ])
        bars = aggregate_ohlcv(df, "1W")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["open"], 100)
        self.assertEqual(bars[0]["high"], 125)
        self.assertEqual(bars[0]["low"], 98)
        self.assertEqual(bars[0]["close"], 102)
        self.assertEqual(bars[0]["volume"], 2_650_000)

    def test_empty_df(self):
        df = _make_daily_df([])
        bars = aggregate_ohlcv(df, "1D")
        self.assertEqual(bars, [])


if __name__ == "__main__":
    unittest.main()
