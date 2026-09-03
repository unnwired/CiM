"""Inclusive EPS/revenue surprise % bounds for the Earnings tab."""
from __future__ import annotations

import unittest

from tradingview_earnings import _passes_surprise_bound, row_passes_surprise_filters


class TestPassesSurpriseBound(unittest.TestCase):
    def test_min_includes_exact_value(self):
        self.assertTrue(_passes_surprise_bound(1.0, min_val=1.0, max_val=None))
        self.assertTrue(_passes_surprise_bound(0.0, min_val=0.0, max_val=None))

    def test_max_includes_exact_value(self):
        self.assertTrue(_passes_surprise_bound(1.0, min_val=None, max_val=1.0))
        self.assertTrue(_passes_surprise_bound(0.0, min_val=None, max_val=0.0))

    def test_min_rejects_strictly_below(self):
        self.assertFalse(_passes_surprise_bound(0.99, min_val=1.0, max_val=None))

    def test_max_rejects_strictly_above(self):
        self.assertFalse(_passes_surprise_bound(1.01, min_val=None, max_val=1.0))

    def test_display_rounding_includes_near_boundary(self):
        # Table shows +1.00% for 0.995; min=1 must include it (not strict >).
        self.assertTrue(_passes_surprise_bound(0.995, min_val=1.0, max_val=None))
        self.assertTrue(_passes_surprise_bound(0.994, min_val=None, max_val=0.99))

    def test_none_value_fails_when_bound_set(self):
        self.assertFalse(_passes_surprise_bound(None, min_val=0.0, max_val=None))
        self.assertFalse(_passes_surprise_bound(None, min_val=None, max_val=1.0))

    def test_no_bounds_always_pass(self):
        self.assertTrue(_passes_surprise_bound(None, min_val=None, max_val=None))
        self.assertTrue(_passes_surprise_bound(-50.0, min_val=None, max_val=None))


class TestRowPassesSurpriseFilters(unittest.TestCase):
    def _check(self, row, **kwargs):
        return row_passes_surprise_filters(
            row,
            eps_surprise_min=kwargs.get("eps_surprise_min"),
            eps_surprise_max=kwargs.get("eps_surprise_max"),
            revenue_surprise_min=kwargs.get("revenue_surprise_min"),
            revenue_surprise_max=kwargs.get("revenue_surprise_max"),
            legacy_both_positive=kwargs.get("legacy_both_positive", False),
        )

    def test_min_one_includes_exact_one(self):
        row = {"eps_surprise_pct": 1.0, "revenue_surprise_pct": 1.0}
        self.assertTrue(
            self._check(row, eps_surprise_min=1.0, revenue_surprise_min=1.0)
        )

    def test_min_zero_includes_exact_zero(self):
        row = {"eps_surprise_pct": 0.0, "revenue_surprise_pct": 0.0}
        self.assertTrue(
            self._check(row, eps_surprise_min=0.0, revenue_surprise_min=0.0)
        )

    def test_null_eps_kept_when_revenue_present_and_eps_min_set(self):
        # HAVELLS-style: no EPS vs estimate, but revenue surprise released.
        row = {"eps_surprise_pct": None, "revenue_surprise_pct": 0.09}
        self.assertTrue(self._check(row, eps_surprise_min=0.0))

    def test_null_rev_kept_when_eps_present_and_rev_min_set(self):
        row = {"eps_surprise_pct": 2.0, "revenue_surprise_pct": None}
        self.assertTrue(self._check(row, revenue_surprise_min=0.0))

    def test_both_null_excluded_when_bound_set(self):
        row = {"eps_surprise_pct": None, "revenue_surprise_pct": None}
        self.assertFalse(self._check(row, eps_surprise_min=0.0))
        self.assertFalse(self._check(row, revenue_surprise_min=0.0))

    def test_null_eps_still_requires_sibling_rev_to_meet_rev_bound(self):
        row = {"eps_surprise_pct": None, "revenue_surprise_pct": -1.0}
        self.assertFalse(
            self._check(row, eps_surprise_min=0.0, revenue_surprise_min=0.0)
        )
        self.assertTrue(
            self._check(row, eps_surprise_min=0.0, revenue_surprise_min=None)
        )

    def test_known_eps_below_min_still_excluded(self):
        row = {"eps_surprise_pct": -1.0, "revenue_surprise_pct": 5.0}
        self.assertFalse(self._check(row, eps_surprise_min=0.0))


if __name__ == "__main__":
    unittest.main()
