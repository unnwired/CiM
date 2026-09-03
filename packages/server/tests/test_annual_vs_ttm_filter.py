"""Unit tests for Annual vs TTM Screener quarterly comparison."""
from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
import sys

PACKAGES = Path(__file__).resolve().parents[2]
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from annual_vs_ttm_filter import (  # noqa: E402
    compute_annual_and_ttm,
    normalize_annual_vs_ttm_params,
    passes_ttm_vs_annual,
    query_annual_vs_ttm_symbols,
)


def _payload(periods, sales, net_profit):
    return {
        "periods": periods,
        "rows": [
            {"slug": "sales", "label": "Sales", "values": sales, "is_pdf": False},
            {"slug": "net_profit", "label": "Net Profit", "values": net_profit, "is_pdf": False},
        ],
    }


class AnnualVsTtmComputeTest(unittest.TestCase):
    def test_mid_year_revenue_ttm_lt_annual(self):
        # FY Mar-2025 annual = 100+110+120+130 = 460
        # TTM ending Jun-2025 = 110+120+130+90 = 450 → TTM < Annual
        periods = [
            {"period": "Jun 2024", "date_key": "2024-06-30"},
            {"period": "Sep 2024", "date_key": "2024-09-30"},
            {"period": "Dec 2024", "date_key": "2024-12-31"},
            {"period": "Mar 2025", "date_key": "2025-03-31"},
            {"period": "Jun 2025", "date_key": "2025-06-30"},
        ]
        sales = ["100", "110", "120", "130", "90"]
        got = compute_annual_and_ttm(_payload(periods, sales, sales), "total_revenue")
        self.assertIsNotNone(got)
        annual, ttm, meta = got
        self.assertEqual(annual, 460.0)
        self.assertEqual(ttm, 450.0)
        self.assertTrue(passes_ttm_vs_annual(annual, ttm, "ttm_lt_annual"))
        self.assertFalse(passes_ttm_vs_annual(annual, ttm, "ttm_gt_annual"))
        self.assertEqual(meta["annual_end_period"], "Mar 2025")

    def test_just_after_fy_close_equal_no_match(self):
        periods = [
            {"period": "Jun 2024", "date_key": "2024-06-30"},
            {"period": "Sep 2024", "date_key": "2024-09-30"},
            {"period": "Dec 2024", "date_key": "2024-12-31"},
            {"period": "Mar 2025", "date_key": "2025-03-31"},
        ]
        sales = ["100", "110", "120", "130"]
        annual, ttm, _ = compute_annual_and_ttm(_payload(periods, sales, sales), "total_revenue")
        self.assertEqual(annual, ttm)
        self.assertFalse(passes_ttm_vs_annual(annual, ttm, "ttm_gt_annual"))
        self.assertFalse(passes_ttm_vs_annual(annual, ttm, "ttm_lt_annual"))

    def test_net_income_ttm_gt_annual(self):
        periods = [
            {"period": "Jun 2024", "date_key": "2024-06-30"},
            {"period": "Sep 2024", "date_key": "2024-09-30"},
            {"period": "Dec 2024", "date_key": "2024-12-31"},
            {"period": "Mar 2025", "date_key": "2025-03-31"},
            {"period": "Jun 2025", "date_key": "2025-06-30"},
        ]
        # annual FY = 10+10+10+10 = 40; TTM = 10+10+10+50 = 80
        net = ["10", "10", "10", "10", "50"]
        annual, ttm, _ = compute_annual_and_ttm(_payload(periods, net, net), "net_income")
        self.assertEqual(annual, 40.0)
        self.assertEqual(ttm, 80.0)
        self.assertTrue(passes_ttm_vs_annual(annual, ttm, "ttm_gt_annual"))

    def test_legacy_condition_aliases(self):
        p = normalize_annual_vs_ttm_params({"metric": "net_income", "condition": "annual_lt_ttm"})
        self.assertEqual(p["metrics"], ["net_income"])
        self.assertEqual(p["condition"], "ttm_gt_annual")
        p2 = normalize_annual_vs_ttm_params({"metrics": ["total_revenue", "net_income"], "condition": "annual_gt_ttm"})
        self.assertEqual(p2["metrics"], ["total_revenue", "net_income"])
        self.assertEqual(p2["condition"], "ttm_lt_annual")


class AnnualVsTtmQueryTest(unittest.TestCase):
    def test_query_multi_metric_and(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE screener_quarterly (
                symbol TEXT NOT NULL,
                basis TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source_url TEXT,
                PRIMARY KEY (symbol, basis)
            )
            """
        )
        periods = [
            {"period": "Jun 2024", "date_key": "2024-06-30"},
            {"period": "Sep 2024", "date_key": "2024-09-30"},
            {"period": "Dec 2024", "date_key": "2024-12-31"},
            {"period": "Mar 2025", "date_key": "2025-03-31"},
            {"period": "Jun 2025", "date_key": "2025-06-30"},
        ]
        # AAA: rev TTM < annual (450 < 460), net TTM > annual (80 > 40)
        aaa = _payload(
            periods,
            ["100", "110", "120", "130", "90"],
            ["10", "10", "10", "10", "50"],
        )
        # BBB: both TTM > annual
        bbb = _payload(
            periods,
            ["100", "100", "100", "100", "200"],
            ["10", "10", "10", "10", "50"],
        )
        conn.execute(
            "INSERT INTO screener_quarterly VALUES (?,?,?,?,?)",
            ("AAA", "consolidated", json.dumps(aaa), "2026-07-01", None),
        )
        conn.execute(
            "INSERT INTO screener_quarterly VALUES (?,?,?,?,?)",
            ("BBB", "consolidated", json.dumps(bbb), "2026-07-01", None),
        )
        conn.commit()

        rev_lt = query_annual_vs_ttm_symbols(
            conn,
            {"metrics": ["total_revenue"], "condition": "ttm_lt_annual", "basis": "consolidated"},
        )
        both_gt = query_annual_vs_ttm_symbols(
            conn,
            {
                "metrics": ["total_revenue", "net_income"],
                "condition": "ttm_gt_annual",
                "basis": "consolidated",
            },
        )
        self.assertEqual(rev_lt, ["AAA"])
        self.assertEqual(both_gt, ["BBB"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
