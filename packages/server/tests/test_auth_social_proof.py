"""Tests for simulated users-online counter (simulated + live split)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

import auth_social_proof as asp  # noqa: F401 — patch target namespace
from auth_social_proof import (
    _MIN_SIMULATED,
    _Phase,
    _apply_drift_if_due,
    _band_for_phase,
    _phase_for_time,
    _pick_drift_delta,
    _total_users,
    get_users_online,
    record_sign_out,
    record_successful_login,
)

# IST = UTC+5:30
_OVERNIGHT_UTC = datetime(2026, 6, 14, 22, 0, tzinfo=timezone.utc)       # 03:30 IST
_MORNING_UTC = datetime(2026, 6, 15, 3, 30, tzinfo=timezone.utc)         # 09:00 IST
_PEAK_UTC = datetime(2026, 6, 15, 6, 30, tzinfo=timezone.utc)            # 12:00 IST
_LATE_SESSION_UTC = datetime(2026, 6, 15, 10, 15, tzinfo=timezone.utc) # 15:45 IST
_AFTER_CLOSE_UTC = datetime(2026, 6, 15, 11, 30, tzinfo=timezone.utc)    # 17:00 IST
_CHURN_UTC = datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc)         # 19:00 IST
_NIGHT_UTC = datetime(2026, 6, 15, 16, 30, tzinfo=timezone.utc)        # 22:00 IST


class TestAuthSocialProof(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cim_social_proof_"))
        self.base = self.tmp / "install"
        self.base.mkdir(exist_ok=True)

    def tearDown(self):
        import shutil

        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_state(self, payload: dict) -> None:
        path = self.base / "data" / "cim_social_proof.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_phase_boundaries(self):
        self.assertEqual(_phase_for_time(_OVERNIGHT_UTC), _Phase.OVERNIGHT)
        self.assertEqual(_phase_for_time(_MORNING_UTC), _Phase.MORNING_RAMP)
        self.assertEqual(_phase_for_time(_PEAK_UTC), _Phase.PEAK)
        self.assertEqual(_phase_for_time(_LATE_SESSION_UTC), _Phase.LATE_SESSION)
        self.assertEqual(_phase_for_time(_AFTER_CLOSE_UTC), _Phase.AFTER_CLOSE)
        self.assertEqual(_phase_for_time(_CHURN_UTC), _Phase.EVENING_CHURN)
        self.assertEqual(_phase_for_time(_NIGHT_UTC), _Phase.NIGHT)

    def test_bands_match_schedule(self):
        self.assertEqual(_band_for_phase(_Phase.OVERNIGHT), (2, 4))
        self.assertEqual(_band_for_phase(_Phase.MORNING_RAMP), (12, 25))
        self.assertEqual(_band_for_phase(_Phase.PEAK), (30, 45))
        self.assertEqual(_band_for_phase(_Phase.LATE_SESSION), (25, 38))
        self.assertEqual(_band_for_phase(_Phase.AFTER_CLOSE), (18, 30))
        self.assertEqual(_band_for_phase(_Phase.EVENING_CHURN), (8, 16))
        self.assertEqual(_band_for_phase(_Phase.NIGHT), (2, 4))

    def test_seed_in_peak_band_on_first_read(self):
        with mock.patch("auth_social_proof.random.randint", return_value=40):
            with mock.patch("auth_social_proof._utcnow", return_value=_PEAK_UTC):
                count = get_users_online(self.base)
        self.assertEqual(count, 40)
        path = self.base / "data" / "cim_social_proof.json"
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["simulated_users"], 40)
        self.assertEqual(data["live_users"], 0)

    def test_seed_in_night_band(self):
        with mock.patch("auth_social_proof.random.randint", return_value=3):
            with mock.patch("auth_social_proof._utcnow", return_value=_NIGHT_UTC):
                count = get_users_online(self.base)
        self.assertEqual(count, 3)

    def test_persistence_without_drift(self):
        future = (_PEAK_UTC + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state({
            "simulated_users": 38,
            "live_users": 2,
            "next_drift_at": future,
            "last_phase": "peak",
        })
        with mock.patch("auth_social_proof._utcnow", return_value=_PEAK_UTC):
            self.assertEqual(get_users_online(self.base), 40)
            self.assertEqual(get_users_online(self.base), 40)

    def test_live_login_adds_on_top_of_peak_cap(self):
        future = (_PEAK_UTC + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state({
            "simulated_users": 45,
            "live_users": 0,
            "next_drift_at": future,
            "last_phase": "peak",
        })
        with mock.patch("auth_social_proof._utcnow", return_value=_PEAK_UTC):
            self.assertEqual(record_successful_login(self.base), 46)
            self.assertEqual(record_successful_login(self.base), 47)
            self.assertEqual(record_successful_login(self.base), 48)
            self.assertEqual(record_successful_login(self.base), 49)
            self.assertEqual(record_successful_login(self.base), 50)

    def test_thirty_live_logins_at_peak_cap(self):
        future = (_PEAK_UTC + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state({
            "simulated_users": 45,
            "live_users": 0,
            "next_drift_at": future,
            "last_phase": "peak",
        })
        with mock.patch("auth_social_proof._utcnow", return_value=_PEAK_UTC):
            total = 45
            for _ in range(30):
                total = record_successful_login(self.base)
            self.assertEqual(total, 75)

    def test_sign_out_only_reduces_live_not_simulated_floor(self):
        future = (_NIGHT_UTC + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state({
            "simulated_users": 3,
            "live_users": 2,
            "next_drift_at": future,
            "last_phase": "night",
        })
        with mock.patch("auth_social_proof._utcnow", return_value=_NIGHT_UTC):
            self.assertEqual(record_sign_out(self.base), 4)
            self.assertEqual(record_sign_out(self.base), 3)
            self.assertEqual(record_sign_out(self.base), 3)

    def test_drift_only_changes_simulated(self):
        state = {
            "simulated_users": 35,
            "live_users": 7,
            "next_drift_at": "2020-01-01T00:00:00Z",
            "last_phase": "peak",
        }
        with mock.patch("auth_social_proof._pick_drift_delta", return_value=2):
            changed = _apply_drift_if_due(state, _PEAK_UTC)
        self.assertTrue(changed)
        self.assertEqual(state["simulated_users"], 37)
        self.assertEqual(state["live_users"], 7)
        self.assertEqual(_total_users(state), 44)

    def test_drift_biased_down_when_above_after_close_band(self):
        delta = _pick_drift_delta(45, _Phase.AFTER_CLOSE)
        self.assertLessEqual(delta, 1)

    def test_drift_from_high_simulated_steps_down_not_cliff(self):
        state = {
            "simulated_users": 52,
            "live_users": 0,
            "next_drift_at": "2020-01-01T00:00:00Z",
            "last_phase": "peak",
        }
        with mock.patch("auth_social_proof._pick_drift_delta", return_value=-3):
            _apply_drift_if_due(state, _PEAK_UTC)
        self.assertEqual(state["simulated_users"], 45)

    def test_drift_respects_simulated_floor(self):
        state = {
            "simulated_users": _MIN_SIMULATED,
            "live_users": 0,
            "next_drift_at": "2020-01-01T00:00:00Z",
            "last_phase": "overnight",
        }
        with mock.patch("auth_social_proof.random.choice", return_value=1):
            _apply_drift_if_due(state, _OVERNIGHT_UTC)
        self.assertGreaterEqual(state["simulated_users"], 2)

    def test_legacy_users_online_migrates_to_simulated(self):
        future = (_PEAK_UTC + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_state({"users_online": 41, "next_drift_at": future})
        with mock.patch("auth_social_proof._utcnow", return_value=_PEAK_UTC):
            self.assertEqual(get_users_online(self.base), 41)


if __name__ == "__main__":
    unittest.main()
