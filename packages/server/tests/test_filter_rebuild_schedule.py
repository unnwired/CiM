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
            "filterRebuildDaily": {
                "enabled": True,
                "preset": {
                    "keys": ["ema", "unknown", "avg_volume", "ema"],
                    "mode": "full",
                    "days_back": 999,
                    "timeframes": ["1D", "bad", "4H", "1D"],
                },
            },
        })
        preset = cfg["filterRebuildDaily"]["preset"]
        self.assertEqual(preset["mode"], "incremental")
        self.assertEqual(preset["days_back"], 30)
        self.assertEqual(preset["keys"], ["ema", "avg_volume"])
        self.assertEqual(preset["timeframes"], ["1D", "4H"])

    def test_saved_filter_preset_can_be_read_for_runner(self):
        ajs.save_config({
            "filterRebuildWeekly": {
                "enabled": True,
                "afterHourIst": 2,
                "afterMinuteIst": 0,
                "preset": {
                    "keys": ["price_ohlc", "range_channel"],
                    "timeframes": ["3D", "1M"],
                },
            },
        })
        preset = ajs.filter_rebuild_preset_for_task("filterRebuildWeekly")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["mode"], "full")
        self.assertEqual(preset["keys"], ["price_ohlc", "range_channel"])
        self.assertEqual(preset["timeframes"], ["3D", "1M"])


if __name__ == "__main__":
    unittest.main()
