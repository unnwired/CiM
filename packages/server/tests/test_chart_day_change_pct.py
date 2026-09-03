"""Chart day_change_pct must match list (DB), not stale live quotes."""

from __future__ import annotations

import unittest

from server import movers_data as md


class ChartDayChangePctTests(unittest.TestCase):
    def test_prefers_db_over_stale_live(self):
        self.assertEqual(md.resolve_chart_day_change_pct(1.6, -0.7), 1.6)
        self.assertEqual(md.resolve_chart_day_change_pct(2.69, -0.8), 2.69)

    def test_falls_back_to_live_when_db_missing(self):
        self.assertEqual(md.resolve_chart_day_change_pct(None, -0.7), -0.7)

    def test_none_when_both_missing(self):
        self.assertIsNone(md.resolve_chart_day_change_pct(None, None))


if __name__ == "__main__":
    unittest.main()
