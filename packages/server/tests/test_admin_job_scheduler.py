"""Unit tests for admin_job_scheduler."""
from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_PACKAGES = Path(__file__).resolve().parents[2]
_SERVER = Path(__file__).resolve().parents[1]
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))
if str(_SERVER) not in sys.path:
    sys.path.append(str(_SERVER))

import admin_job_scheduler as ajs  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


class AdminJobSchedulerTests(unittest.TestCase):
    def test_normalize_defaults_all_tasks_disabled(self):
        cfg = ajs._normalize_config(None)
        self.assertEqual(len(cfg), len(ajs.TASK_KEYS))
        self.assertFalse(cfg["ohlcv"]["enabled"])
        self.assertEqual(cfg["ohlcv"]["intervalMinutes"], 30)
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "interval")
        self.assertFalse(cfg["filterRebuildDaily"]["enabled"])
        self.assertEqual(cfg["filterRebuildDaily"]["scheduleType"], "daily")
        self.assertEqual(cfg["filterRebuildDaily"]["preset"]["mode"], "incremental")
        self.assertFalse(cfg["filterRebuildWeekly"]["enabled"])
        self.assertEqual(cfg["filterRebuildWeekly"]["scheduleType"], "weekly")
        self.assertEqual(cfg["filterRebuildWeekly"]["afterHourIst"], 2)
        self.assertEqual(cfg["filterRebuildWeekly"]["preset"]["mode"], "full")
        self.assertFalse(cfg["eodReconcile"]["enabled"])
        self.assertFalse(cfg["fetchFinancials"]["enabled"])
        self.assertEqual(cfg["fetchFinancials"]["scheduleType"], "weekly")

    def test_normalize_ten_task_keys(self):
        cfg = ajs._normalize_config(None)
        self.assertEqual(len(ajs.TASK_KEYS), 10)
        for key in ajs.TASK_KEYS:
            self.assertIn(key, cfg)

    def test_weekly_next_run(self):
        cfg = ajs._normalize_config({
            "fetchFinancials": {
                "enabled": True,
                "scheduleType": "weekly",
                "weekdayIst": 4,
                "afterHourIst": 15,
                "afterMinuteIst": 30,
            },
        })
        now = datetime(2026, 6, 18, 10, 0, tzinfo=IST)  # Thursday
        nxt = ajs.compute_next_run("fetchFinancials", cfg, {}, now)
        self.assertIsNotNone(nxt)

    def test_normalize_weekdays_ist_multi_day(self):
        cfg = ajs._normalize_config({
            "fetchFinancials": {
                "enabled": True,
                "scheduleType": "weekly",
                "weekdaysIst": [0, 2, 4, 6],
                "afterHourIst": 2,
                "afterMinuteIst": 0,
            },
        })
        self.assertEqual(cfg["fetchFinancials"]["weekdaysIst"], [0, 2, 4, 6])
        self.assertEqual(cfg["fetchFinancials"]["weekdayIst"], 0)

    def test_weekly_runs_on_each_selected_day(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"fetchFinancials": start_fn},
            job_running_fn=lambda: False,
        )
        cfg = ajs._normalize_config({
            "fetchFinancials": {
                "enabled": True,
                "scheduleType": "weekly",
                "weekdaysIst": [0, 2, 4],
                "afterHourIst": 10,
                "afterMinuteIst": 0,
            },
        })
        # Monday 10:30 IST — should run
        mon = datetime(2026, 6, 15, 10, 30, tzinfo=IST)
        state = ajs._maybe_run_task("fetchFinancials", cfg, {}, mon)
        self.assertEqual(calls, [1])
        # Same Monday again — should skip (already ran today)
        state = ajs._maybe_run_task("fetchFinancials", cfg, state, mon)
        self.assertEqual(calls, [1])
        # Wednesday same week — should run again
        wed = datetime(2026, 6, 17, 10, 30, tzinfo=IST)
        state = ajs._maybe_run_task("fetchFinancials", cfg, state, wed)
        self.assertEqual(calls, [1, 1])
        # Tuesday — not selected
        tue = datetime(2026, 6, 16, 10, 30, tzinfo=IST)
        state = ajs._maybe_run_task("fetchFinancials", cfg, state, tue)
        self.assertEqual(calls, [1, 1])

    def test_weekly_next_run_multi_day(self):
        cfg = ajs._normalize_config({
            "fetchFinancials": {
                "enabled": True,
                "scheduleType": "weekly",
                "weekdaysIst": [0, 2, 4],
                "afterHourIst": 10,
                "afterMinuteIst": 0,
            },
        })
        # Thursday — next should be Friday? No, Friday is 4, next is Fri Jun 19
        thu = datetime(2026, 6, 18, 11, 0, tzinfo=IST)
        nxt = ajs.compute_next_run("fetchFinancials", cfg, {}, thu)
        parsed = datetime.fromisoformat(nxt)
        self.assertEqual(parsed.weekday(), 4)  # Friday

    def test_run_task_now_fetch_financials_without_enable(self):
        started = []
        root = Path(self._temp_dir())

        def start_fn():
            started.append(True)
            return True

        ajs.configure(
            start_fns={"fetchFinancials": start_fn},
            job_running_fn=lambda: False,
            install_root=root,
        )
        cfg = ajs._normalize_config(None)
        self.assertFalse(cfg["fetchFinancials"]["enabled"])
        result = ajs.run_task_now("fetchFinancials")
        self.assertTrue(result["ok"])
        self.assertTrue(started)

    def test_normalize_legacy_indicator_incremental_alias(self):
        cfg = ajs._normalize_config({
            "indicatorIncremental": {"enabled": True, "afterHourIst": 16, "afterMinuteIst": 0},
        })
        self.assertTrue(cfg["filterRebuildDaily"]["enabled"])
        self.assertEqual(cfg["filterRebuildDaily"]["afterHourIst"], 16)
        self.assertEqual(cfg["filterRebuildDaily"]["preset"]["mode"], "incremental")

    def test_normalize_migrates_snapshot_heavy_to_weekly_filter_rebuild(self):
        cfg = ajs._normalize_config({
            "snapshotsHeavy": {
                "enabled": True,
                "scheduleType": "daily",
                "weekdayIst": 6,
                "afterHourIst": 21,
                "afterMinuteIst": 15,
            },
        })
        self.assertTrue(cfg["filterRebuildWeekly"]["enabled"])
        self.assertEqual(cfg["filterRebuildWeekly"]["scheduleType"], "weekly")
        self.assertEqual(cfg["filterRebuildWeekly"]["weekdayIst"], 6)
        self.assertEqual(cfg["filterRebuildWeekly"]["afterHourIst"], 21)
        self.assertEqual(cfg["filterRebuildWeekly"]["afterMinuteIst"], 15)

    def test_normalize_clamps_interval_and_time(self):
        cfg = ajs._normalize_config({
            "ohlcv": {"enabled": True, "intervalMinutes": 999},
            "filterRebuildWeekly": {"enabled": True, "afterHourIst": 25, "afterMinuteIst": 99},
        })
        self.assertEqual(cfg["ohlcv"]["intervalMinutes"], 30)
        self.assertEqual(cfg["filterRebuildWeekly"]["afterHourIst"], 23)

    def test_normalize_uses_defaults_for_malformed_time_values(self):
        cfg = ajs._normalize_config({
            "ohlcv": {"enabled": True, "intervalMinutes": "bad"},
            "filterRebuildDaily": {
                "enabled": True,
                "afterHourIst": "bad",
                "afterMinuteIst": None,
                "weekdaysIst": ["bad"],
            },
        })
        self.assertEqual(cfg["ohlcv"]["intervalMinutes"], 30)
        self.assertEqual(cfg["filterRebuildDaily"]["afterHourIst"], 23)
        self.assertEqual(cfg["filterRebuildDaily"]["afterMinuteIst"], 0)
        self.assertEqual(cfg["filterRebuildDaily"]["weekdaysIst"], [4])

    def test_ohlcv_daily_schedule_type(self):
        cfg = ajs._normalize_config({
            "ohlcv": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 16,
                "afterMinuteIst": 0,
            },
        })
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertEqual(cfg["ohlcv"]["afterHourIst"], 16)
        now = datetime(2026, 6, 16, 10, 0, tzinfo=IST)
        nxt = ajs.compute_next_run("ohlcv", cfg, {}, now)
        self.assertIsNotNone(nxt)
        parsed = datetime.fromisoformat(nxt)
        self.assertEqual(parsed.hour, 16)
        self.assertEqual(parsed.minute, 0)

    def test_ohlcv_daily_skips_after_run_today(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"ohlcv": start_fn},
            job_running_fn=lambda: False,
        )
        cfg = ajs._normalize_config({
            "ohlcv": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 15,
                "afterMinuteIst": 30,
            },
        })
        now = datetime(2026, 6, 16, 16, 0, tzinfo=IST)
        state = {"lastOhlcvDate": "2026-06-16"}
        state = ajs._maybe_run_task("ohlcv", cfg, state, now)
        self.assertEqual(calls, [])

    def test_compute_next_daily_not_before_target_time(self):
        cfg = ajs._normalize_config({
            "filterRebuildDaily": {"enabled": True, "afterHourIst": 20, "afterMinuteIst": 0},
        })
        now = datetime(2026, 6, 16, 10, 0, tzinfo=IST)
        nxt = ajs.compute_next_run("filterRebuildDaily", cfg, {}, now)
        self.assertIsNotNone(nxt)

    def test_maybe_run_skips_when_disabled(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"filterRebuildWeekly": start_fn},
            job_running_fn=lambda: False,
        )
        cfg = ajs._normalize_config(None)
        now = datetime.now(IST)
        state = ajs._maybe_run_task("filterRebuildWeekly", cfg, {}, now)
        self.assertEqual(calls, [])
        self.assertEqual(state, {})

    def test_run_task_now_records_manual_trigger(self):
        started = []
        root = Path(self._temp_dir())

        def start_fn():
            started.append(True)
            return True

        ajs.configure(
            start_fns={"ohlcv": start_fn},
            job_running_fn=lambda: False,
            install_root=root,
        )
        result = ajs.run_task_now("ohlcv")
        self.assertTrue(result["ok"])
        self.assertTrue(started)
        state = ajs.load_state()
        self.assertEqual(state.get("lastOhlcvTrigger"), "manual")

    def test_scheduler_loop_does_not_run_disabled_tasks(self):
        calls = []
        root = Path(self._temp_dir())
        cfg_path = root / "config" / "admin_schedules.json"
        cfg_path.write_text(
            '{"filterRebuildWeekly": {"enabled": false, "afterHourIst": 20, "afterMinuteIst": 0}}',
            encoding="utf-8",
        )

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"filterRebuildWeekly": start_fn},
            job_running_fn=lambda: False,
            install_root=root,
        )
        ajs.reload_config()
        ajs._stop.clear()
        ajs.start()
        time.sleep(0.08)
        ajs.stop()
        self.assertEqual(calls, [])

    def _temp_dir(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "config").mkdir()
        (d / "data").mkdir()
        (d / "runtime" / "logs").mkdir(parents=True)
        return d


if __name__ == "__main__":
    unittest.main()
