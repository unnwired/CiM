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

from admin_job_scheduler import _normalize_config, ALLOWED_OHLCV_INTERVAL_MINUTES  # noqa: E402


class ShowcaseAdminSchedulerCompatTests(unittest.TestCase):
    def test_normalize_defaults(self):
        cfg = _normalize_config(None)
        self.assertFalse(cfg["ohlcv"]["enabled"])
        self.assertEqual(cfg["ohlcv"]["intervalMinutes"], 30)
        self.assertEqual(cfg["filterRebuildDaily"]["afterHourIst"], 23)
        self.assertEqual(cfg["filterRebuildWeekly"]["scheduleType"], "weekly")

    def test_normalize_clamps_interval_and_time(self):
        cfg = _normalize_config({
            "ohlcv": {"enabled": True, "intervalMinutes": 999},
            "filterRebuildDaily": {"enabled": True, "afterHourIst": 25, "afterMinuteIst": 99},
        })
        self.assertEqual(cfg["ohlcv"]["intervalMinutes"], 30)
        self.assertEqual(cfg["filterRebuildDaily"]["afterHourIst"], 23)

    def test_normalize_accepts_allowed_intervals(self):
        for minutes in ALLOWED_OHLCV_INTERVAL_MINUTES:
            cfg = _normalize_config({"ohlcv": {"intervalMinutes": minutes}})
            self.assertEqual(cfg["ohlcv"]["intervalMinutes"], minutes)


if __name__ == "__main__":
    unittest.main()
