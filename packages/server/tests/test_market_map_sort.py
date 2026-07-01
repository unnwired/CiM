"""Market Map constituent sort and magnitude filters."""

import unittest

from market_map import filter_constituents_by_magnitude, sort_constituents_by_pct_desc


def _row(sym: str, chg) -> dict:
    return {"symbol": sym, "change_pct": chg}


class TestMarketMapSort(unittest.TestCase):
    def test_sort_pct_desc_signed(self):
        rows = [_row("A", -5.0), _row("B", 2.0), _row("C", 10.0), _row("D", None)]
        sort_constituents_by_pct_desc(rows)
        self.assertEqual([r["symbol"] for r in rows], ["C", "B", "A", "D"])

    def test_magnitude_gainers_only(self):
        rows = [_row("A", 6.0), _row("B", -6.0), _row("C", 4.0)]
        out = filter_constituents_by_magnitude(rows, 5)
        self.assertEqual([r["symbol"] for r in out], ["A"])

    def test_magnitude_losers_only(self):
        rows = [_row("A", 6.0), _row("B", -6.0), _row("C", -4.0)]
        out = filter_constituents_by_magnitude(rows, -5)
        self.assertEqual([r["symbol"] for r in out], ["B"])

    def test_magnitude_plus_three_excludes_negative(self):
        rows = [_row("A", 3.5), _row("B", -3.5)]
        out = filter_constituents_by_magnitude(rows, 3)
        self.assertEqual([r["symbol"] for r in out], ["A"])


if __name__ == "__main__":
    unittest.main()
