"""Tests for scheduled filter rebuild task presets."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_PACKAGES = Path(__file__).resolve().parents[2]
_SERVER = Path(__file__).resolve().parents[1]
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))
if str(_SERVER) not in sys.path:
    sys.path.append(str(_SERVER))

import admin_job_scheduler as ajs  # noqa: E402


class FilterRebuildScheduleTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)
        (self.root / "runtime" / "logs").mkdir(parents=True)
        ajs.configure(start_fns={}, job_running_fn=lambda: False, install_root=self.root)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_filter_preset_drops_unknown_keys_and_timeframes(self):
        cfg = ajs._normalize_config({
            "filterSchedules": [{
                "id": "daily1",
                "enabled": True,
                "mode": "incremental",
                "preset": {
                    "keys": ["ema", "unknown", "avg_volume", "ema"],
                    "mode": "full",
                    "days_back": 999,
                    "timeframes": ["1D", "bad", "4H", "1D"],
                },
            }],
        })
        preset = cfg["filterSchedules"][0]["preset"]
        self.assertEqual(cfg["filterSchedules"][0]["mode"], "incremental")
        self.assertEqual(preset["mode"], "incremental")
        self.assertEqual(preset["days_back"], 30)
        self.assertEqual(preset["keys"], ["ema", "avg_volume"])
        self.assertEqual(preset["timeframes"], ["1D", "4H"])

    def test_filter_preset_keeps_30m_not_month_token(self):
        cfg = ajs._normalize_config({
            "filterSchedules": [{
                "id": "daily30",
                "enabled": True,
                "mode": "incremental",
                "preset": {
                    "keys": ["ema"],
                    "timeframes": ["30m", "30M", "1D", "bad"],
                },
            }],
        })
        preset = cfg["filterSchedules"][0]["preset"]
        self.assertEqual(preset["timeframes"], ["30m", "1D"])

    def test_saved_filter_schedule_preset_preserved(self):
        ajs.save_config({
            "filterSchedules": [{
                "id": "weekly1",
                "enabled": True,
                "mode": "full",
                "afterHourIst": 2,
                "afterMinuteIst": 0,
                "preset": {
                    "keys": ["price_ohlc", "range_channel"],
                    "timeframes": ["3D", "1M"],
                },
            }],
        })
        cfg = ajs.load_config()
        preset = cfg["filterSchedules"][0]["preset"]
        self.assertEqual(preset["mode"], "full")
        self.assertEqual(preset["keys"], ["price_ohlc", "range_channel"])
        self.assertEqual(preset["timeframes"], ["3D", "1M"])

    def test_filter_schedule_daily_vs_weekly_type(self):
        cfg = ajs._normalize_config({
            "filterSchedules": [
                {
                    "id": "d1",
                    "enabled": True,
                    "scheduleType": "daily",
                    "afterHourIst": 22,
                    "afterMinuteIst": 30,
                    "weekdaysIst": [],
                    "preset": {"keys": ["ema"], "timeframes": ["1D"]},
                },
                {
                    "id": "w1",
                    "enabled": True,
                    "scheduleType": "weekly",
                    "afterHourIst": 2,
                    "afterMinuteIst": 0,
                    "weekdaysIst": [0, 2],
                    "preset": {"keys": ["macd"], "timeframes": ["1W"]},
                },
            ],
        })
        daily = cfg["filterSchedules"][0]
        weekly = cfg["filterSchedules"][1]
        self.assertEqual(daily["scheduleType"], "daily")
        self.assertEqual(daily["weekdaysIst"], list(range(7)))
        self.assertEqual(weekly["scheduleType"], "weekly")
        self.assertEqual(weekly["weekdaysIst"], [0, 2])

        from datetime import datetime

        IST = ajs.IST
        # Tuesday 2026-07-14 (weekday index 1 in Mon=0 scheme)
        tue = datetime(2026, 7, 14, 23, 0, tzinfo=IST)
        self.assertTrue(ajs._fs_is_due_now(daily, {}, tue))
        self.assertFalse(ajs._fs_is_due_now(weekly, {}, tue))  # Tue=1, selected Mon/Wed
        wed = datetime(2026, 7, 15, 3, 0, tzinfo=IST)
        self.assertTrue(ajs._fs_is_due_now(weekly, {}, wed))

    def test_filter_schedule_infers_daily_from_all_weekdays(self):
        cfg = ajs._normalize_config({
            "filterSchedules": [{
                "id": "legacy_daily",
                "enabled": True,
                "weekdaysIst": list(range(7)),
                "preset": {"keys": ["ema"], "timeframes": ["1D"]},
            }],
        })
        self.assertEqual(cfg["filterSchedules"][0]["scheduleType"], "daily")


if __name__ == "__main__":
    unittest.main()
