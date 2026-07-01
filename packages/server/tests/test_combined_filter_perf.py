"""Tests for combined filter hybrid path and combined cache."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_paths import REPO_ROOT as ROOT

PKG = ROOT / "packages"
SERVER_PKG = ROOT / "packages" / "server"
TESTS_PKG = SERVER_PKG / "tests"
for p in (str(PKG), str(TESTS_PKG), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import server.server as srv  # noqa: E402


class CombinedFilterPerfTests(unittest.TestCase):
    def test_combined_histogram_uses_native_evaluator(self):
        filt = {
            "filter_type": "macd_hist_chain",
            "timeframe": "2W",
            "histogram_side": "negative",
            "chain_mode": "increasing",
            "bars_to_compare": 4,
            "allowed_stragglers": 0,
            "allow_cross_zero": False,
        }
        with patch.object(srv, "filter_macd_hist_chain", return_value={"symbols": ["AAA"], "count": 1}) as mock_hist:
            srv.invalidate_filter_cache()
            result = srv._combined_filter_symbols([filt], [])
            self.assertEqual(result, {"AAA"})
            mock_hist.assert_called_once()

    def test_combined_filter_cache_hit(self):
        filt = {
            "filter_type": "macd_hist_chain",
            "timeframe": "2W",
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allowed_stragglers": 0,
            "allow_cross_zero": False,
        }
        with patch.object(srv, "filter_macd_hist_chain", return_value={"symbols": ["AAA"], "count": 1}) as mock_hist:
            srv.invalidate_filter_cache()
            first = srv._combined_filter_symbols([filt], [])
            second = srv._combined_filter_symbols([filt], [])
            self.assertEqual(first, {"AAA"})
            self.assertEqual(second, {"AAA"})
            self.assertEqual(mock_hist.call_count, 1)

    def test_earnings_filter_uses_slow_path_not_snapshot_fast(self):
        earnings_body = {
            "filter_type": "earnings",
            "report_window": "month_range",
            "from_year": 2026,
            "from_month": 4,
            "to_year": 2026,
            "to_month": 6,
            "eps_surprise_min": 0.0,
            "revenue_surprise_min": 0.0,
        }
        with patch.object(srv, "filter_earnings", return_value={"symbols": ["RELIANCE", "TCS"], "count": 2}) as mock_fe, patch.object(
            srv, "_load_filter_snapshots"
        ) as mock_load_snaps:
            mock_load_snaps.side_effect = AssertionError("snapshot fast path must not run for earnings")
            srv.invalidate_filter_cache()
            result = srv._combined_filter_symbols([earnings_body], [])
            self.assertEqual(result, {"RELIANCE", "TCS"})
            mock_fe.assert_called_once()
            call_body = mock_fe.call_args[0][0]
            self.assertEqual(call_body.get("filter_type"), "earnings")
            self.assertEqual(call_body.get("from_month"), 4)
            self.assertEqual(call_body.get("eps_surprise_min"), 0.0)


if __name__ == "__main__":
    unittest.main()
