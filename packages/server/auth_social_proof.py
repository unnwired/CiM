"""Simulated global 'users online' counter for web host auth shell (showcase only).

IST day curve — simulated base (band-capped) + live login overlay (uncapped):
  Overnight       00:00–07:59  →  2–4
  Morning ramp    08:00–09:59  → 12–25
  Peak            10:00–15:29  → 30–45
  Late session    15:30–15:59  → 25–38
  After close     16:00–18:29  → 18–30
  Evening churn   18:30–20:59  →  8–16  (faster / wider drift)
  Night           21:00–23:59  →  2–4

Displayed count = simulated_users + live_users.
Drift and phase bands apply to simulated_users only.
Each successful web login adds +1 to live_users; sign-out subtracts 1 (min 0).
"""
from __future__ import annotations

import json
import random
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_MIN_SIMULATED = 2

# (band_min, band_max) — drift biases simulated count toward these ranges per phase
_PHASE_BANDS: dict[str, tuple[int, int]] = {
    "overnight": (2, 4),
    "morning_ramp": (12, 25),
    "peak": (30, 45),
    "late_session": (25, 38),
    "after_close": (18, 30),
    "evening_churn": (8, 16),
    "night": (2, 4),
}

_DRIFT_DELAYS_SEC: dict[str, tuple[int, int]] = {
    "overnight": (45 * 60, 90 * 60),
    "morning_ramp": (20 * 60, 40 * 60),
    "peak": (30 * 60, 60 * 60),
    "late_session": (15 * 60, 25 * 60),
    "after_close": (20 * 60, 40 * 60),
    "evening_churn": (10 * 60, 20 * 60),
    "night": (15 * 60, 30 * 60),
}

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class _Phase(str, Enum):
    OVERNIGHT = "overnight"
    MORNING_RAMP = "morning_ramp"
    PEAK = "peak"
    LATE_SESSION = "late_session"
    AFTER_CLOSE = "after_close"
    EVENING_CHURN = "evening_churn"
    NIGHT = "night"


def _state_path(base_dir: Path) -> Path:
    return Path(base_dir) / "data" / "cim_social_proof.json"


def _lock_for(base_dir: Path) -> threading.Lock:
    key = str(Path(base_dir).resolve())
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ist_minutes(now: datetime) -> int:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ist = now.astimezone(IST)
    return ist.hour * 60 + ist.minute


def _phase_for_time(now: datetime) -> _Phase:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    m = _ist_minutes(now)
    if m < 8 * 60:
        return _Phase.OVERNIGHT
    if m < 10 * 60:
        return _Phase.MORNING_RAMP
    if m < 15 * 60 + 30:
        return _Phase.PEAK
    if m < 16 * 60:
        return _Phase.LATE_SESSION
    if m < 18 * 60 + 30:
        return _Phase.AFTER_CLOSE
    if m < 21 * 60:
        return _Phase.EVENING_CHURN
    return _Phase.NIGHT


def _band_for_phase(phase: _Phase) -> tuple[int, int]:
    return _PHASE_BANDS[phase.value]


def _floor_for_phase(phase: _Phase) -> int:
    lo, _ = _band_for_phase(phase)
    return max(_MIN_SIMULATED, lo)


def _ceil_for_phase(phase: _Phase) -> int:
    _, hi = _band_for_phase(phase)
    return hi


def _clamp_simulated(value: int, phase: _Phase) -> int:
    lo, hi = _band_for_phase(phase)
    return max(lo, min(hi, value))


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _random_drift_delay(phase: _Phase) -> timedelta:
    lo, hi = _DRIFT_DELAYS_SEC[phase.value]
    return timedelta(seconds=random.randint(lo, hi))


def _weighted_choice(options: list[int], weights: list[int]) -> int:
    return random.choices(options, weights=weights, k=1)[0]


def _pick_drift_delta(current: int, phase: _Phase) -> int:
    lo, hi = _band_for_phase(phase)
    floor = _floor_for_phase(phase)
    center = (lo + hi) // 2

    if phase is _Phase.EVENING_CHURN:
        if current <= floor:
            return random.choice([1, 2, 3])
        if current >= hi:
            return random.choice([-4, -3, -2])
        return random.choice([-4, -3, -2, -1, 1, 2, 3, 4])

    if phase is _Phase.MORNING_RAMP and current < center:
        return _weighted_choice([-1, 1, 2, 3], [1, 2, 3, 3])

    if phase is _Phase.NIGHT and current > hi:
        return _weighted_choice([-4, -3, -2, -1], [3, 4, 3, 1])

    if current <= floor:
        return random.choice([1, 2])

    if current > hi:
        return _weighted_choice([-3, -2, -1, 1], [3, 4, 3, 1])

    if current < lo:
        return _weighted_choice([-1, 1, 2, 3], [2, 3, 2, 1])

    if current > center:
        return _weighted_choice([-3, -2, -1, 1, 2], [2, 3, 3, 2, 1])

    if current < center:
        return _weighted_choice([-2, -1, 1, 2, 3], [1, 2, 2, 3, 2])

    return random.choice([-2, -1, 1, 2])


def _nudge_simulated_on_phase_change(simulated: int, new_phase: _Phase) -> int:
    """Pull simulated count toward the new phase band when the IST phase changes."""
    lo, hi = _band_for_phase(new_phase)
    if simulated > hi:
        return max(hi, simulated - random.randint(4, 10))
    if simulated < lo:
        return min(lo, simulated + random.randint(3, 8))
    return simulated


def _total_users(state: dict[str, Any]) -> int:
    sim = int(state.get("simulated_users") or _MIN_SIMULATED)
    live = max(0, int(state.get("live_users") or 0))
    return sim + live


def _apply_drift_if_due(state: dict[str, Any], now: datetime) -> bool:
    next_at = _parse_iso(str(state.get("next_drift_at") or ""))
    if next_at is not None and now < next_at:
        return False
    phase = _phase_for_time(now)
    current = int(state.get("simulated_users") or _MIN_SIMULATED)
    delta = _pick_drift_delta(current, phase)
    floor = _floor_for_phase(phase)
    ceiling = _ceil_for_phase(phase)
    state["simulated_users"] = max(floor, min(ceiling, current + delta))
    state["next_drift_at"] = (now + _random_drift_delay(phase)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return True


def _seed_simulated_for_phase(phase: _Phase) -> int:
    lo, hi = _band_for_phase(phase)
    return random.randint(lo, hi)


def _fresh_state(phase: _Phase, now: datetime) -> dict[str, Any]:
    return {
        "simulated_users": _seed_simulated_for_phase(phase),
        "live_users": 0,
        "next_drift_at": (now + _random_drift_delay(phase)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_phase": phase.value,
    }


def _migrate_legacy_payload(data: dict[str, Any], phase: _Phase) -> dict[str, Any]:
    """Upgrade single-field users_online JSON to simulated + live split."""
    live = max(0, int(data.get("live_users") or 0))
    if "simulated_users" in data:
        sim = int(data.get("simulated_users") or _MIN_SIMULATED)
    else:
        combined = int(data.get("users_online") or 0)
        sim = max(0, combined - live)
    sim = _clamp_simulated(sim, phase)
    return {
        "simulated_users": sim,
        "live_users": live,
        "next_drift_at": str(data.get("next_drift_at") or ""),
        "last_phase": str(data.get("last_phase") or phase.value),
    }


def _load_state(base_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    phase = _phase_for_time(now)
    path = _state_path(base_dir)
    if not path.is_file():
        return _fresh_state(phase, now)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("invalid social proof state")
        state = _migrate_legacy_payload(raw, phase)
        state["simulated_users"] = _clamp_simulated(int(state["simulated_users"]), phase)
        state["live_users"] = max(0, int(state.get("live_users") or 0))
        if not state.get("next_drift_at"):
            state["next_drift_at"] = (now + _random_drift_delay(phase)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        return state
    except (OSError, ValueError, TypeError):
        return _fresh_state(phase, now)


def _apply_phase_transition(state: dict[str, Any], now: datetime) -> bool:
    phase = _phase_for_time(now)
    prev = str(state.get("last_phase") or "").strip()
    changed = bool(prev and prev != phase.value)
    if changed:
        simulated = int(state.get("simulated_users") or _MIN_SIMULATED)
        state["simulated_users"] = _clamp_simulated(
            _nudge_simulated_on_phase_change(simulated, phase),
            phase,
        )
    state["last_phase"] = phase.value
    return changed


def _save_state(base_dir: Path, state: dict[str, Any], phase: _Phase | None = None) -> None:
    path = _state_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    phase = phase or _phase_for_time(_utcnow())
    sim = _clamp_simulated(int(state.get("simulated_users") or _MIN_SIMULATED), phase)
    live = max(0, int(state.get("live_users") or 0))
    payload = {
        "simulated_users": sim,
        "live_users": live,
        "next_drift_at": str(state.get("next_drift_at") or ""),
        "last_phase": str(state.get("last_phase") or phase.value),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _refresh_state(base_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    path = _state_path(base_dir)
    existed = path.is_file()
    state = _load_state(base_dir, now)
    phase_changed = _apply_phase_transition(state, now)
    drifted = _apply_drift_if_due(state, now)
    if not existed or phase_changed or drifted:
        _save_state(base_dir, state, _phase_for_time(now))
    return state


def get_users_online(base_dir: Path) -> int:
    with _lock_for(base_dir):
        state = _refresh_state(base_dir)
        return _total_users(state)


def record_successful_login(base_dir: Path) -> int:
    with _lock_for(base_dir):
        now = _utcnow()
        phase = _phase_for_time(now)
        state = _load_state(base_dir, now)
        _apply_phase_transition(state, now)
        _apply_drift_if_due(state, now)
        state["live_users"] = max(0, int(state.get("live_users") or 0)) + 1
        _save_state(base_dir, state, phase)
        return _total_users(state)


def record_sign_out(base_dir: Path) -> int:
    with _lock_for(base_dir):
        now = _utcnow()
        phase = _phase_for_time(now)
        state = _load_state(base_dir, now)
        _apply_phase_transition(state, now)
        _apply_drift_if_due(state, now)
        state["live_users"] = max(0, int(state.get("live_users") or 0) - 1)
        _save_state(base_dir, state, phase)
        return _total_users(state)
