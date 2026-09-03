"""Strict TV EPS + revenue beat helper."""
from __future__ import annotations

import unittest

from tradingview_earnings import is_tv_eps_rev_beat_row


class TestIsTvEpsRevBeatRow(unittest.TestCase):
    def test_both_beat(self):
        self.assertTrue(
            is_tv_eps_rev_beat_row(
                {
                    "eps_actual": 10,
                    "eps_estimate": 8,
                    "revenue_actual": 100,
                    "revenue_estimate": 90,
                }
            )
        )

    def test_rejects_meet(self):
        self.assertFalse(
            is_tv_eps_rev_beat_row(
                {
                    "eps_actual": 8,
                    "eps_estimate": 8,
                    "revenue_actual": 90,
                    "revenue_estimate": 90,
                }
            )
        )

    def test_rejects_partial_or_missing(self):
        self.assertFalse(
            is_tv_eps_rev_beat_row(
                {
                    "eps_actual": 10,
                    "eps_estimate": 8,
                    "revenue_actual": 80,
                    "revenue_estimate": 90,
                }
            )
        )
        self.assertFalse(
            is_tv_eps_rev_beat_row(
                {
                    "eps_actual": 10,
                    "eps_estimate": None,
                    "revenue_actual": 100,
                    "revenue_estimate": 90,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
