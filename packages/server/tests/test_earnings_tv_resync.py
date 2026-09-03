"""Recent-window TradingView earnings re-sync helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

import tradingview_earnings as te  # noqa: E402


class TestEarningsTvResync(unittest.TestCase):
    def test_parse_rolling_past_days(self):
        self.assertEqual(te._parse_rolling_past_days("rolling_4_days"), 4)
        self.assertEqual(te._parse_rolling_past_days("rolling_10_days"), 10)
        self.assertIsNone(te._parse_rolling_past_days("this_week"))
        self.assertIsNone(te._parse_rolling_past_days("rolling_0_days"))

    def test_resolve_rolling_4_days_window(self):
        rng, key = te.resolve_reported_date_range(report_window="rolling_4_days")
        self.assertEqual(key, "rw:4")
        self.assertEqual(len(rng), 2)
        self.assertLess(rng[0], rng[1])
        # Roughly 4 days of seconds (+ a day buffer for DST / end-of-day).
        self.assertGreater(rng[1] - rng[0], 3.5 * 86400)
        self.assertLess(rng[1] - rng[0], 5.5 * 86400)

    def test_fetch_recent_reported_clears_cache_and_uses_window(self):
        te._cache["dummy"] = ([], 0.0)
        fake = {
            "rows": [{"symbol": "PIDILITIND", "eps_actual": 8.57}],
            "fetched_at": 1,
        }
        with mock.patch.object(te, "fetch_earnings_calendar", return_value=fake) as mocked:
            out = te.fetch_recent_reported_for_resync(lookback_days=4, limit=500)
        self.assertNotIn("dummy", te._cache)
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs.get("mode"), "reported")
        self.assertEqual(kwargs.get("report_window"), "rolling_4_days")
        self.assertFalse(kwargs.get("use_cache"))
        self.assertEqual(out.get("resync_lookback_days"), 4)
        self.assertEqual(out["rows"][0]["symbol"], "PIDILITIND")


if __name__ == "__main__":
    unittest.main()
