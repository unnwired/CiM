import unittest
from unittest.mock import patch

from earnings_beat_lookup import (
    _latest_reported_row_by_symbol,
    attach_earnings_beat_flags,
    is_dual_beat_report_row,
    read_dual_beat_symbols,
)


class TestIsDualBeatReportRow(unittest.TestCase):
    def test_both_positive_with_actuals(self):
        self.assertTrue(
            is_dual_beat_report_row(
                {
                    "eps_surprise_pct": 5.0,
                    "revenue_surprise_pct": 2.0,
                    "eps_actual": 10,
                    "revenue_actual": 100,
                }
            )
        )

    def test_rejects_negative_surprise(self):
        self.assertFalse(
            is_dual_beat_report_row(
                {"eps_surprise_pct": 5.0, "revenue_surprise_pct": -1.0}
            )
        )

    def test_rejects_zero_without_actuals(self):
        self.assertFalse(
            is_dual_beat_report_row(
                {"eps_surprise_pct": 0, "revenue_surprise_pct": 0}
            )
        )

    def test_partial_beat_revenue_only_when_eps_actual_present(self):
        # GMDC-style: no EPS estimate, revenue beat, reported EPS exists.
        self.assertTrue(
            is_dual_beat_report_row(
                {
                    "eps_surprise_pct": None,
                    "revenue_surprise_pct": 3.5,
                    "eps_actual": 1.2,
                    "revenue_actual": 500,
                }
            )
        )

    def test_partial_beat_eps_only_when_revenue_actual_present(self):
        self.assertTrue(
            is_dual_beat_report_row(
                {
                    "eps_surprise_pct": 2.0,
                    "revenue_surprise_pct": None,
                    "eps_actual": 10,
                    "revenue_actual": 100,
                }
            )
        )

    def test_partial_beat_rejects_missing_sibling_actual(self):
        self.assertFalse(
            is_dual_beat_report_row(
                {
                    "eps_surprise_pct": None,
                    "revenue_surprise_pct": 3.5,
                    "eps_actual": None,
                    "revenue_actual": 500,
                }
            )
        )
        self.assertFalse(
            is_dual_beat_report_row(
                {
                    "eps_surprise_pct": 2.0,
                    "revenue_surprise_pct": None,
                    "eps_actual": 10,
                    "revenue_actual": None,
                }
            )
        )

    def test_partial_beat_rejects_negative_measurable_surprise(self):
        self.assertFalse(
            is_dual_beat_report_row(
                {
                    "eps_surprise_pct": None,
                    "revenue_surprise_pct": -1.0,
                    "eps_actual": 1.2,
                    "revenue_actual": 500,
                }
            )
        )


class TestLatestReportedRowBySymbol(unittest.TestCase):
    def test_keeps_newest_date(self):
        latest = _latest_reported_row_by_symbol(
            [
                {
                    "symbol": "HEROMOTOCO",
                    "earnings_release_date": "2026-01-01",
                    "eps_surprise_pct": -1,
                    "revenue_surprise_pct": 1,
                },
                {
                    "symbol": "HEROMOTOCO",
                    "earnings_release_date": "2026-05-05",
                    "eps_surprise_pct": 1,
                    "revenue_surprise_pct": 1,
                },
            ]
        )
        self.assertEqual(latest["HEROMOTOCO"]["earnings_release_date"], "2026-05-05")


class TestAttachEarningsBeatFlags(unittest.TestCase):
    @patch("tradingview_earnings._fetch_reported_rows_for_symbols")
    def test_attach_flags_uses_latest_quarter(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "symbol": "RELIANCE",
                "earnings_release_date": "2026-04-24",
                "eps_surprise_pct": 3.0,
                "revenue_surprise_pct": 1.0,
                "eps_actual": 1,
                "revenue_actual": 2,
            },
            {
                "symbol": "FAILCO",
                "earnings_release_date": "2026-05-01",
                "eps_surprise_pct": 3.0,
                "revenue_surprise_pct": -2.0,
                "eps_actual": 1,
                "revenue_actual": 2,
            },
        ]
        rows = [{"symbol": "RELIANCE"}, {"symbol": "FAILCO"}]
        attach_earnings_beat_flags(rows)
        self.assertTrue(rows[0]["earnings_beat"])
        self.assertFalse(rows[1]["earnings_beat"])

    def test_read_dual_beat_symbols_empty(self):
        self.assertEqual(read_dual_beat_symbols([]), set())


if __name__ == "__main__":
    unittest.main()
