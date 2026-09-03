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


class FilterScheduleInstanceTests(unittest.TestCase):
    def test_normalize_adds_empty_filter_schedules(self):
        cfg = ajs._normalize_config(None)
        self.assertEqual(cfg["filterSchedules"], [])

    def test_normalize_filter_schedules_assigns_ids_and_mode(self):
        cfg = ajs._normalize_config({
            "filterSchedules": [
                {"enabled": True, "afterHourIst": 21, "afterMinuteIst": 30, "mode": "incremental"},
                {"id": "custom", "enabled": True, "weekdaysIst": [5], "mode": "full"},
            ]
        })
        instances = cfg["filterSchedules"]
        self.assertEqual(len(instances), 2)
        self.assertTrue(instances[0]["id"])
        self.assertEqual(instances[0]["mode"], "incremental")
        self.assertEqual(instances[0]["preset"]["mode"], "incremental")
        self.assertEqual(instances[1]["id"], "custom")
        self.assertEqual(instances[1]["mode"], "full")
        self.assertEqual(instances[1]["preset"]["mode"], "full")

    def test_filter_schedule_next_run_all_weekdays(self):
        entry = ajs._normalize_filter_schedule_entry(
            {"id": "d1", "enabled": True, "afterHourIst": 22, "afterMinuteIst": 0, "weekdaysIst": list(range(7))},
            0,
        )
        now = datetime(2026, 7, 2, 10, 0, tzinfo=IST)
        nxt = ajs._fs_next_run(entry, {}, now)
        self.assertEqual(nxt, datetime(2026, 7, 2, 22, 0, tzinfo=IST).isoformat())

    def test_filter_schedule_due_gating(self):
        entry = ajs._normalize_filter_schedule_entry(
            {"id": "d2", "enabled": True, "afterHourIst": 9, "afterMinuteIst": 0, "weekdaysIst": list(range(7))},
            0,
        )
        now = datetime(2026, 7, 2, 10, 0, tzinfo=IST)
        self.assertTrue(ajs._fs_is_due_now(entry, {}, now))
        ran = {ajs._fs_state_key("d2", "lastDate"): now.date().isoformat()}
        self.assertFalse(ajs._fs_is_due_now(entry, ran, now))

    def test_filter_schedule_weekday_only_skips_unselected_day(self):
        entry = ajs._normalize_filter_schedule_entry(
            {"id": "w1", "enabled": True, "afterHourIst": 10, "afterMinuteIst": 0, "weekdaysIst": [0, 2, 4]},
            0,
        )
        tue = datetime(2026, 6, 16, 11, 0, tzinfo=IST)
        self.assertFalse(ajs._fs_is_due_now(entry, {}, tue))


class AdminJobSchedulerTests(unittest.TestCase):
    def test_normalize_defaults_all_tasks_disabled(self):
        cfg = ajs._normalize_config(None)
        self.assertEqual(len(cfg), len(ajs.TASK_KEYS) + 2)  # + filterSchedules + taskSchedules
        self.assertEqual(cfg["taskSchedules"], [])
        self.assertFalse(cfg["ohlcv"]["enabled"])
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertNotIn("intervalMinutes", cfg["ohlcv"])
        self.assertNotIn("filterRebuildDaily", cfg)
        self.assertNotIn("filterRebuildWeekly", cfg)
        self.assertFalse(cfg["eodReconcile"]["enabled"])
        self.assertFalse(cfg["fetchFinancials"]["enabled"])
        self.assertEqual(cfg["fetchFinancials"]["scheduleType"], "weekly")

    def test_normalize_twelve_task_keys(self):
        cfg = ajs._normalize_config(None)
        self.assertEqual(len(ajs.TASK_KEYS), 12)
        for key in ajs.TASK_KEYS:
            self.assertIn(key, cfg)
        self.assertIn("earningsTvResync", cfg)
        self.assertIn("sectorIndexCores", cfg)
        self.assertIn("exchangeClassification", cfg)
        self.assertEqual(cfg["sectorIndexCores"]["scheduleType"], "weekly")
        self.assertEqual(cfg["exchangeClassification"]["scheduleType"], "weekly")

    def test_migrate_singleton_into_task_schedules(self):
        cfg = ajs._normalize_config({
            "ohlcv": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 15,
                "afterMinuteIst": 35,
            },
            "eodReconcile": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 16,
                "afterMinuteIst": 20,
            },
        })
        self.assertFalse(cfg["ohlcv"]["enabled"])
        self.assertFalse(cfg["eodReconcile"]["enabled"])
        by_task = {s["taskKey"]: s for s in cfg["taskSchedules"]}
        self.assertIn("ohlcv", by_task)
        self.assertIn("eodReconcile", by_task)
        self.assertEqual(by_task["ohlcv"]["afterMinuteIst"], 35)
        self.assertEqual(by_task["eodReconcile"]["afterHourIst"], 16)

    def test_multiple_schedules_same_task(self):
        cfg = ajs._normalize_config({
            "taskSchedules": [
                {
                    "id": "ohlcv_a",
                    "taskKey": "ohlcv",
                    "enabled": True,
                    "scheduleType": "daily",
                    "afterHourIst": 15,
                    "afterMinuteIst": 35,
                },
                {
                    "id": "ohlcv_b",
                    "taskKey": "ohlcv",
                    "enabled": True,
                    "scheduleType": "daily",
                    "afterHourIst": 16,
                    "afterMinuteIst": 20,
                },
            ],
        })
        self.assertEqual(len(cfg["taskSchedules"]), 2)
        self.assertEqual({s["id"] for s in cfg["taskSchedules"]}, {"ohlcv_a", "ohlcv_b"})

    def test_two_ohlcv_instances_both_due_independently(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"ohlcv": start_fn},
            job_running_fn=lambda: False,
        )
        a = ajs._normalize_task_schedule_entry({
            "id": "a",
            "taskKey": "ohlcv",
            "enabled": True,
            "scheduleType": "daily",
            "afterHourIst": 15,
            "afterMinuteIst": 35,
        }, 0)
        b = ajs._normalize_task_schedule_entry({
            "id": "b",
            "taskKey": "ohlcv",
            "enabled": True,
            "scheduleType": "daily",
            "afterHourIst": 16,
            "afterMinuteIst": 20,
        }, 1)
        at_a = datetime(2026, 8, 4, 15, 40, tzinfo=IST)
        state = ajs._maybe_run_task_schedule(a, {}, at_a)
        self.assertEqual(calls, [1])
        self.assertEqual(state[ajs._ts_state_key("a", "lastDate")], "2026-08-04")
        # Second instance still due at 16:20 even though first already ran today.
        at_b = datetime(2026, 8, 4, 16, 25, tzinfo=IST)
        state = ajs._maybe_run_task_schedule(b, state, at_b)
        self.assertEqual(calls, [1, 1])
        self.assertEqual(state[ajs._ts_state_key("b", "lastDate")], "2026-08-04")
        # First instance does not re-fire same day.
        state = ajs._maybe_run_task_schedule(a, state, at_b)
        self.assertEqual(calls, [1, 1])

    def test_weekly_next_run(self):
        cfg = ajs._normalize_config({
            "taskSchedules": [{
                "id": "ff1",
                "taskKey": "fetchFinancials",
                "enabled": True,
                "scheduleType": "weekly",
                "weekdayIst": 4,
                "afterHourIst": 15,
                "afterMinuteIst": 30,
            }],
        })
        entry = cfg["taskSchedules"][0]
        now = datetime(2026, 6, 18, 10, 0, tzinfo=IST)  # Thursday
        nxt = ajs._ts_next_run(entry, {}, now)
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
        # Singleton stub keeps normalized weekdays; live schedule is in taskSchedules.
        self.assertEqual(cfg["fetchFinancials"]["weekdaysIst"], [0, 2, 4, 6])
        self.assertEqual(cfg["fetchFinancials"]["weekdayIst"], 0)
        self.assertEqual(cfg["taskSchedules"][0]["weekdaysIst"], [0, 2, 4, 6])

    def test_weekly_runs_on_each_selected_day(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"fetchFinancials": start_fn},
            job_running_fn=lambda: False,
        )
        entry = ajs._normalize_task_schedule_entry({
            "id": "ff_w",
            "taskKey": "fetchFinancials",
            "enabled": True,
            "scheduleType": "weekly",
            "weekdaysIst": [0, 2, 4],
            "afterHourIst": 10,
            "afterMinuteIst": 0,
        }, 0)
        mon = datetime(2026, 6, 15, 10, 30, tzinfo=IST)
        state = ajs._maybe_run_task_schedule(entry, {}, mon)
        self.assertEqual(calls, [1])
        state = ajs._maybe_run_task_schedule(entry, state, mon)
        self.assertEqual(calls, [1])
        wed = datetime(2026, 6, 17, 10, 30, tzinfo=IST)
        state = ajs._maybe_run_task_schedule(entry, state, wed)
        self.assertEqual(calls, [1, 1])
        tue = datetime(2026, 6, 16, 10, 30, tzinfo=IST)
        state = ajs._maybe_run_task_schedule(entry, state, tue)
        self.assertEqual(calls, [1, 1])

    def test_weekly_next_run_multi_day(self):
        entry = ajs._normalize_task_schedule_entry({
            "id": "ff_w2",
            "taskKey": "fetchFinancials",
            "enabled": True,
            "scheduleType": "weekly",
            "weekdaysIst": [0, 2, 4],
            "afterHourIst": 10,
            "afterMinuteIst": 0,
        }, 0)
        thu = datetime(2026, 6, 18, 11, 0, tzinfo=IST)
        nxt = ajs._ts_next_run(entry, {}, thu)
        parsed = datetime.fromisoformat(nxt)
        self.assertEqual(parsed.weekday(), 4)

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

    def test_migrate_legacy_indicator_incremental_to_filter_schedules(self):
        cfg = ajs._normalize_config({
            "indicatorIncremental": {"enabled": True, "afterHourIst": 16, "afterMinuteIst": 0},
        })
        migrated = [s for s in cfg["filterSchedules"] if s.get("id") == "indicatorIncremental"]
        self.assertEqual(len(migrated), 1)
        self.assertTrue(migrated[0]["enabled"])
        self.assertEqual(migrated[0]["afterHourIst"], 16)
        self.assertEqual(migrated[0]["preset"]["mode"], "incremental")
        self.assertEqual(migrated[0]["weekdaysIst"], list(range(7)))

    def test_migrate_legacy_filter_rebuild_daily_and_weekly(self):
        cfg = ajs._normalize_config({
            "filterRebuildDaily": {
                "enabled": True,
                "afterHourIst": 23,
                "afterMinuteIst": 0,
            },
            "filterRebuildWeekly": {
                "enabled": True,
                "weekdayIst": 5,
                "afterHourIst": 2,
                "afterMinuteIst": 0,
            },
        })
        ids = {s["id"] for s in cfg["filterSchedules"]}
        self.assertIn("filterRebuildDaily", ids)
        self.assertIn("filterRebuildWeekly", ids)
        daily = next(s for s in cfg["filterSchedules"] if s["id"] == "filterRebuildDaily")
        weekly = next(s for s in cfg["filterSchedules"] if s["id"] == "filterRebuildWeekly")
        self.assertEqual(daily["preset"]["mode"], "incremental")
        self.assertEqual(daily["weekdaysIst"], list(range(7)))
        self.assertEqual(daily["scheduleType"], "daily")
        self.assertEqual(weekly["preset"]["mode"], "full")
        self.assertEqual(weekly["scheduleType"], "weekly")

    def test_migrate_snapshots_heavy_to_weekly_filter_schedule(self):
        cfg = ajs._normalize_config({
            "snapshotsHeavy": {
                "enabled": True,
                "weekdayIst": 6,
                "afterHourIst": 21,
                "afterMinuteIst": 15,
            },
        })
        migrated = [s for s in cfg["filterSchedules"] if s.get("id") == "snapshotsHeavy"]
        self.assertEqual(len(migrated), 1)
        self.assertTrue(migrated[0]["enabled"])
        self.assertEqual(migrated[0]["weekdayIst"], 6)
        self.assertEqual(migrated[0]["afterHourIst"], 21)
        self.assertEqual(migrated[0]["afterMinuteIst"], 15)
        self.assertEqual(migrated[0]["preset"]["mode"], "full")

    def test_normalize_clamps_time_and_migrates_legacy_interval(self):
        cfg = ajs._normalize_config({
            "ohlcv": {"enabled": True, "scheduleType": "interval", "intervalMinutes": 999},
            "filterSchedules": [{"id": "x", "enabled": True, "afterHourIst": 25, "afterMinuteIst": 99}],
        })
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertNotIn("intervalMinutes", cfg["ohlcv"])
        self.assertEqual(cfg["filterSchedules"][0]["afterHourIst"], 23)

    def test_normalize_uses_defaults_for_malformed_time_values(self):
        cfg = ajs._normalize_config({
            "ohlcv": {"enabled": True, "scheduleType": "bad"},
            "filterSchedules": [{
                "id": "bad",
                "enabled": True,
                "afterHourIst": "bad",
                "afterMinuteIst": None,
                "weekdaysIst": ["bad"],
            }],
        })
        self.assertEqual(cfg["ohlcv"]["scheduleType"], "daily")
        self.assertEqual(cfg["filterSchedules"][0]["afterHourIst"], 23)
        self.assertEqual(cfg["filterSchedules"][0]["afterMinuteIst"], 0)
        self.assertEqual(cfg["filterSchedules"][0]["weekdaysIst"], [0])

    def test_monthly_first_weekday_due_and_next(self):
        # July 2026: first Monday is July 6.
        entry = ajs._normalize_task_schedule_entry({
            "id": "ff_m",
            "taskKey": "fetchFinancials",
            "enabled": True,
            "scheduleType": "monthly",
            "weekdaysIst": [0],
            "afterHourIst": 2,
            "afterMinuteIst": 0,
        }, 0)
        self.assertEqual(entry["scheduleType"], "monthly")
        self.assertEqual(entry["weekdaysIst"], [0])
        mon = datetime(2026, 7, 6, 3, 0, tzinfo=IST)
        self.assertTrue(ajs._ts_is_due_now(entry, {}, mon))
        tue = datetime(2026, 7, 7, 3, 0, tzinfo=IST)
        self.assertFalse(ajs._ts_is_due_now(entry, {}, tue))
        before = datetime(2026, 7, 1, 10, 0, tzinfo=IST)
        nxt = ajs._ts_next_run(entry, {}, before)
        self.assertIsNotNone(nxt)
        parsed = datetime.fromisoformat(nxt)
        self.assertEqual(parsed.date().isoformat(), "2026-07-06")
        self.assertEqual(parsed.hour, 2)

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
        entry = cfg["taskSchedules"][0]
        now = datetime(2026, 6, 16, 10, 0, tzinfo=IST)
        nxt = ajs._ts_next_run(entry, {}, now)
        self.assertIsNotNone(nxt)
        parsed = datetime.fromisoformat(nxt)
        self.assertEqual(parsed.hour, 16)
        self.assertEqual(parsed.minute, 0)

    def test_ohlcv_daily_skips_after_scheduled_run_today(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"ohlcv": start_fn},
            job_running_fn=lambda: False,
        )
        entry = ajs._normalize_task_schedule_entry({
            "id": "ohlcv1",
            "taskKey": "ohlcv",
            "enabled": True,
            "scheduleType": "daily",
            "afterHourIst": 15,
            "afterMinuteIst": 30,
        }, 0)
        now = datetime(2026, 6, 16, 16, 0, tzinfo=IST)
        state = {
            ajs._ts_state_key("ohlcv1", "lastDate"): "2026-06-16",
            ajs._ts_state_key("ohlcv1", "trigger"): "scheduled",
        }
        state = ajs._maybe_run_task_schedule(entry, state, now)
        self.assertEqual(calls, [])

    def test_manual_ohlcv_does_not_block_scheduled_slot(self):
        """Legacy singleton behavior: manual Update must not cancel scheduled.

        With multi-instance schedules, each instance uses its own lastDate; this
        test keeps the legacy singleton path covered for Update-menu recording.
        """
        calls = []

        def start_fn():
            calls.append(1)
            return True

        root = Path(self._temp_dir())
        ajs.configure(
            start_fns={"ohlcv": start_fn},
            job_running_fn=lambda: False,
            install_root=root,
        )
        # Force-enable singleton in cfg for legacy path (bypass normalize disable).
        cfg = {
            "ohlcv": {
                "enabled": True,
                "scheduleType": "daily",
                "afterHourIst": 15,
                "afterMinuteIst": 45,
                "weekdaysIst": list(range(7)),
                "weekdayIst": 0,
            },
        }
        now = datetime(2026, 7, 24, 15, 46, tzinfo=IST)
        state = {
            "lastOhlcvDate": "2026-07-24",
            "lastOhlcvAt": "2026-07-24T13:29:26+05:30",
            "lastOhlcvTrigger": "manual",
        }
        self.assertTrue(ajs.task_is_due_now("ohlcv", cfg, state, now))
        state = ajs._maybe_run_task("ohlcv", cfg, state, now)
        self.assertEqual(calls, [1])
        self.assertEqual(state.get("lastOhlcvTrigger"), "scheduled")
        self.assertEqual(state.get("lastOhlcvScheduledDate"), "2026-07-24")

    def test_maybe_run_skips_when_disabled(self):
        calls = []

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"fetchFinancials": start_fn},
            job_running_fn=lambda: False,
        )
        cfg = ajs._normalize_config(None)
        now = datetime.now(IST)
        state = ajs._maybe_run_task("fetchFinancials", cfg, {}, now)
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

    def test_run_task_now_filter_schedule(self):
        started = []

        def filter_start(preset):
            started.append(preset.get("mode"))
            return True

        root = Path(self._temp_dir())
        ajs.configure(
            filter_instance_start_fn=filter_start,
            job_running_fn=lambda: False,
            install_root=root,
        )
        cfg = ajs._normalize_config({
            "filterSchedules": [{"id": "fs1", "enabled": True, "mode": "full", "preset": {"mode": "full", "keys": ["ema"]}}],
        })
        ajs.save_config(cfg)
        result = ajs.run_task_now("filter:fs1")
        self.assertTrue(result["ok"])
        self.assertEqual(started, ["full"])

    def test_scheduler_loop_does_not_run_disabled_tasks(self):
        calls = []
        root = Path(self._temp_dir())
        cfg_path = root / "config" / "admin_schedules.json"
        cfg_path.write_text(
            '{"fetchFinancials": {"enabled": false, "afterHourIst": 20, "afterMinuteIst": 0}}',
            encoding="utf-8",
        )

        def start_fn():
            calls.append(1)
            return True

        ajs.configure(
            start_fns={"fetchFinancials": start_fn},
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
