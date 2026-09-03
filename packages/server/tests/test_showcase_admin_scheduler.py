"""Backward-compatible imports from admin_job_scheduler."""
import sys
import unittest
from pathlib import Path

_PACKAGES = Path(__file__).resolve().parents[2]
_SERVER = Path(__file__).resolve().parents[1]
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))
if str(_SERVER) not in sys.path:
    sys.path.append(str(_SERVER))

from admin_job_scheduler import _normalize_config  # noqa: E402


class ShowcaseAdminSchedulerCompatTests(unittest.TestCase):
    def test_normalize_defaults(self):
        cfg = _normalize_config(None)
        self.assertFalse(cfg["ohlcv"]["enabled"])
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertEqual(cfg["filterSchedules"], [])

    def test_normalize_clamps_filter_schedule_time(self):
        cfg = _normalize_config({
            "ohlcv": {"enabled": True, "scheduleType": "daily"},
            "filterSchedules": [{"id": "x", "enabled": True, "afterHourIst": 25, "afterMinuteIst": 99}],
        })
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertEqual(cfg["filterSchedules"][0]["afterHourIst"], 23)

    def test_legacy_interval_migrates_to_daily(self):
        cfg = _normalize_config({"ohlcv": {"scheduleType": "interval", "intervalMinutes": 60}})
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertNotIn("intervalMinutes", cfg["ohlcv"])


if __name__ == "__main__":
    unittest.main()
