"""Reconcile TradingView actual vs surprise % when scanner fields disagree."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from tradingview_earnings import (  # noqa: E402
    _reconcile_actual_vs_tv_surprise,
    _row_reported,
)


class TestReconcileActualVsTvSurprise(unittest.TestCase):
    def test_deepakntr_stale_revenue_actual_fixed_from_surprise(self):
        # Scanner lag: total_revenue_fq stale, surprise matches TV calendar (~25.56B).
        actual, surp = _reconcile_actual_vs_tv_surprise(
            20_519_200_000.0,
            23_522_583_333.0,
            8.66578571810304,
        )
        self.assertAlmostEqual(surp, 8.66578571810304, places=6)
        self.assertAlmostEqual(actual / 1e9, 25.561, places=3)

    def test_consistent_fields_unchanged(self):
        actual, surp = _reconcile_actual_vs_tv_surprise(23.7, 17.2, 37.7906976744186)
        self.assertEqual(actual, 23.7)
        self.assertAlmostEqual(surp, 37.7906976744186, places=6)

    def test_row_reported_applies_reconciliation(self):
        row = {
            "earnings_per_share_fq": 23.7,
            "earnings_per_share_forecast_fq": 17.2,
            "eps_surprise_percent_fq": 37.7906976744186,
            "total_revenue_fq": 20_519_200_000.0,
            "revenue_forecast_fq": 23_522_583_333.0,
            "revenue_surprise_percent_fq": 8.66578571810304,
            "earnings_release_date": 1785846240,
            "market_cap_basic": 1e11,
            "close": 1700.0,
            "change": 1.0,
            "change|1M": 2.0,
            "price_earnings_ttm": 20.0,
        }
        item = _row_reported("NSE:DEEPAKNTR", "DEEPAKNTR", row)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertAlmostEqual(item["revenue_actual"] / 1e9, 25.561, places=3)
        self.assertAlmostEqual(item["revenue_surprise_pct"], 8.66578571810304, places=6)
        self.assertEqual(item["eps_actual"], 23.7)

    def test_eps_stale_surprise_does_not_rewrite_actual(self):
        # Pidilite-style: actual already correct, surprise % still stale miss.
        actual, surp = _reconcile_actual_vs_tv_surprise(
            8.57,
            7.51,
            -1.41,
            allow_rewrite_actual=False,
        )
        self.assertEqual(actual, 8.57)
        self.assertAlmostEqual(surp, ((8.57 - 7.51) / 7.51) * 100.0, places=4)

    def test_row_reported_keeps_eps_when_surprise_stale(self):
        row = {
            "earnings_per_share_fq": 8.57,
            "earnings_per_share_forecast_fq": 7.51,
            "eps_surprise_percent_fq": -1.41,
            "total_revenue_fq": 45_515_250_000.0,
            "revenue_forecast_fq": 44_245_589_000.0,
            "revenue_surprise_percent_fq": 2.87,
            "earnings_release_date": 1785833100,
            "market_cap_basic": 1e12,
            "close": 1665.0,
            "change": 1.0,
            "change|1M": 2.0,
            "price_earnings_ttm": 69.0,
        }
        item = _row_reported("NSE:PIDILITIND", "PIDILITIND", row)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["eps_actual"], 8.57)
        self.assertGreater(item["eps_surprise_pct"], 0)


if __name__ == "__main__":
    unittest.main()
