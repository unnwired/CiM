"""Tests for snapshot rebuild guard and scheduler freeze."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

_PACKAGES = Path(__file__).resolve().parents[2]
_SERVER = Path(__file__).resolve().parents[1]
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))
if str(_SERVER) not in sys.path:
    sys.path.append(str(_SERVER))

import admin_job_scheduler as ajs  # noqa: E402
from server import snapshot_rebuild_guard as srg  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


class SnapshotRebuildGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "runtime" / "logs").mkdir(parents=True)
        (self.root / "config").mkdir(parents=True)
        ajs.configure(
            start_fns={"ohlcv": lambda: True},
            job_running_fn=lambda: False,
            scheduler_blocked_fn=srg.scheduler_is_frozen,
            install_root=self.root,
        )
        srg._hold_count = 0

    def tearDown(self):
        srg._hold_count = 0
        srg._clear_hold_files()
        ajs.set_scheduler_blocked_fn(None)
        self._tmpdir.cleanup()

    def test_interval_ohlcv_not_imminent_only_due_now_blocks(self):
        now = datetime(2026, 6, 26, 10, 0, tzinfo=IST)
        cfg = ajs._normalize_config({
            "ohlcv": {"enabled": True, "scheduleType": "interval", "intervalMinutes": 60},
        })
        state = {"lastOhlcvAt": now.isoformat()}
        conflicts = srg.collect_scheduler_conflicts(job_running_fn=lambda: False)
        self.assertFalse(any(c.get("task") == "ohlcv" for c in conflicts))

    def test_daily_filter_rebuild_imminent_within_window(self):
        now = datetime(2026, 6, 26, 15, 20, tzinfo=IST)
        cfg = ajs._normalize_config({
            "filterRebuildDaily": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 15,
                "afterMinuteIst": 30,
            },
        })
        with mock.patch.object(ajs, "load_config", return_value=cfg), mock.patch.object(
            ajs, "load_state", return_value={}
        ), mock.patch("server.snapshot_rebuild_guard.datetime") as dt_cls:
            dt_cls.now.return_value = now
            dt_cls.fromisoformat = datetime.fromisoformat
            dt_cls.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            conflicts = srg.collect_scheduler_conflicts(job_running_fn=lambda: False)
        self.assertTrue(any(c.get("type") == "imminent" and c.get("task") == "filterRebuildDaily" for c in conflicts))

    def test_scheduler_frozen_skips_run_task_now(self):
        srg.acquire_full_rebuild_hold()
        try:
            self.assertTrue(ajs.scheduler_is_blocked())
            result = ajs.run_task_now("ohlcv")
            self.assertFalse(result["ok"])
            self.assertIn("snapshot rebuild", result["error"].lower())
        finally:
            srg.release_full_rebuild_hold()

    def test_hold_file_written_and_cleared(self):
        with mock.patch.object(srg, "pause_live_watchdog", return_value=True), mock.patch.object(
            srg, "resume_live_watchdog", return_value=True
        ):
            srg.acquire_full_rebuild_hold()
            self.assertTrue(srg.hold_path().is_file())
            data = json.loads(srg.hold_path().read_text(encoding="utf-8"))
            self.assertTrue(data.get("active"))
            srg.release_full_rebuild_hold()
        self.assertFalse(srg.hold_path().is_file())

    def test_task_is_due_now_daily_after_target(self):
        now = datetime(2026, 6, 26, 16, 0, tzinfo=IST)
        cfg = ajs._normalize_config({
            "filterRebuildDaily": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 15,
                "afterMinuteIst": 30,
            },
        })
        self.assertTrue(ajs.task_is_due_now("filterRebuildDaily", cfg, {}, now))


if __name__ == "__main__":
    unittest.main()
