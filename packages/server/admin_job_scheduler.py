"""
Unified opt-in admin job scheduler for showcase host (IST).

All tasks default to disabled. Runs inside the uvicorn process while the backend is up.
"""
from __future__ import annotations

import json
import shutil
import threading
import time as time_module
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from filter_rebuild_registry import SNAPSHOT_TIMEFRAME_OPTIONS, registry_by_key
from server.core.install_root import get_install_root

IST = ZoneInfo("Asia/Kolkata")
ALLOWED_OHLCV_INTERVAL_MINUTES = (15, 30, 60, 90)
POLL_SEC = 30
RETRY_SEC = 5 * 60
LOG_TAIL_LINES = 40
FILTER_REBUILD_KEYS = tuple(registry_by_key().keys())
FILTER_REBUILD_LIGHT_TIMEFRAMES = tuple(
    tf for tf in SNAPSHOT_TIMEFRAME_OPTIONS if tf not in ("4W", "1M")
)

TASK_KEYS = (
    "ohlcv",
    "filterRebuildDaily",
    "filterRebuildWeekly",
    "eodReconcile",
    "liveQuotesWarm",
    "splitWatch",
    "earningsPlusWarm",
    "fetchFinancials",
    "fetchScreenerSectors",
    "expandUniverse",
)

# Deprecated — all tasks are schedulable; kept for one release of API compat.
MANUAL_TASK_KEYS: tuple[str, ...] = ()

# Lighter tasks first; weekly full filter rebuild after EOD/OHLCV.
TASK_LOOP_ORDER = (
    "liveQuotesWarm",
    "eodReconcile",
    "ohlcv",
    "filterRebuildDaily",
    "filterRebuildWeekly",
    "earningsPlusWarm",
    "splitWatch",
    "fetchScreenerSectors",
    "expandUniverse",
    "fetchFinancials",
)

_DEFAULT_DAILY = {
    "enabled": False,
    "scheduleType": "daily",
    "afterHourIst": 15,
    "afterMinuteIst": 30,
    "weekdayIst": 4,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "ohlcv": {
        "enabled": False,
        "scheduleType": "interval",
        "intervalMinutes": 30,
        "afterHourIst": 15,
        "afterMinuteIst": 30,
        "weekdayIst": 4,
    },
    "filterRebuildDaily": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 23,
        "afterMinuteIst": 0,
        "weekdayIst": 4,
        "preset": {
            "keys": list(FILTER_REBUILD_KEYS),
            "mode": "incremental",
            "days_back": 1,
            "timeframes": list(FILTER_REBUILD_LIGHT_TIMEFRAMES),
        },
    },
    "filterRebuildWeekly": {
        "enabled": False,
        "scheduleType": "weekly",
        "afterHourIst": 2,
        "afterMinuteIst": 0,
        "weekdayIst": 5,
        "preset": {
            "keys": list(FILTER_REBUILD_KEYS),
            "mode": "full",
            "days_back": 1,
            "timeframes": list(SNAPSHOT_TIMEFRAME_OPTIONS),
        },
    },
    "eodReconcile": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 16,
        "afterMinuteIst": 15,
        "weekdayIst": 4,
    },
    "liveQuotesWarm": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 9,
        "afterMinuteIst": 15,
        "weekdayIst": 4,
    },
    "splitWatch": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 10,
        "afterMinuteIst": 0,
        "weekdayIst": 4,
    },
    "earningsPlusWarm": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 11,
        "afterMinuteIst": 0,
        "weekdayIst": 4,
    },
    "fetchFinancials": {
        "enabled": False,
        "scheduleType": "weekly",
        "afterHourIst": 2,
        "afterMinuteIst": 0,
        "weekdayIst": 5,
    },
    "fetchScreenerSectors": {
        "enabled": False,
        "scheduleType": "weekly",
        "afterHourIst": 3,
        "afterMinuteIst": 0,
        "weekdayIst": 5,
    },
    "expandUniverse": {
        "enabled": False,
        "scheduleType": "weekly",
        "afterHourIst": 4,
        "afterMinuteIst": 0,
        "weekdayIst": 6,
    },
}

# Legacy state / config key mapping (indicatorIncremental/snapshotsLight -> filterRebuildDaily)
_LEGACY_CONFIG_ALIASES = {"indicatorIncremental": "filterRebuildDaily"}
_LEGACY_STATE_PREFIX = {
    "filterRebuildDaily": "FilterRebuildDaily",
    "filterRebuildWeekly": "FilterRebuildWeekly",
    "eodReconcile": "EodReconcile",
    "liveQuotesWarm": "LiveQuotesWarm",
    "splitWatch": "SplitWatch",
    "earningsPlusWarm": "EarningsPlusWarm",
    "fetchFinancials": "FetchFinancials",
    "fetchScreenerSectors": "FetchScreenerSectors",
    "expandUniverse": "ExpandUniverse",
}

_start_fns: dict[str, Callable[[], bool]] = {}
_job_running_fn: Optional[Callable[[], bool]] = None
_scheduler_blocked_fn: Optional[Callable[[], bool]] = None
_install_root: Optional[Path] = None
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_file_lock = threading.Lock()
_config_cache: dict[str, Any] = dict(DEFAULT_CONFIG)
_waiting_task: Optional[str] = None
_waiting_reason: Optional[str] = None


def _root() -> Path:
    return _install_root or get_install_root()


def _config_path() -> Path:
    return _root() / "config" / "admin_schedules.json"


def _legacy_config_path() -> Path:
    return _root() / "config" / "showcase_admin_schedules.json"


def _state_path() -> Path:
    return _root() / "data" / "admin_scheduler_state.json"


def _legacy_state_path() -> Path:
    return _root() / "data" / "showcase_admin_scheduler_state.json"


def _log_path() -> Path:
    log_dir = _root() / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "admin-scheduler.log"


def append_log(message: str) -> None:
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    line = f"[{stamp}] {message}"
    print(f"[admin_job_scheduler] {message}", flush=True)
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def read_log_tail(max_lines: int = LOG_TAIL_LINES) -> list[str]:
    path = _log_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-max_lines:]
    except OSError:
        return []


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    with _file_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        tmp.replace(path)


def _normalize_weekdays(raw: dict[str, Any], defaults: dict[str, Any]) -> list[int]:
    days: list[int] = []
    raw_list = raw.get("weekdaysIst")
    if isinstance(raw_list, list):
        for item in raw_list:
            try:
                days.append(max(0, min(6, int(item))))
            except (TypeError, ValueError):
                continue
    if not days:
        try:
            days = [max(0, min(6, int(raw.get("weekdayIst", defaults.get("weekdayIst", 4)))))]
        except (TypeError, ValueError):
            days = [max(0, min(6, int(defaults.get("weekdayIst", 4))))]
    return sorted(set(days))


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _weekdays_from_task(task_cfg: dict[str, Any]) -> list[int]:
    raw = task_cfg.get("weekdaysIst")
    if isinstance(raw, list) and raw:
        days = sorted({max(0, min(6, _safe_int(d, 4))) for d in raw})
        if days:
            return days
    return [max(0, min(6, _safe_int(task_cfg.get("weekdayIst", 4), 4)))]


def _normalize_timed_task(raw: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    hour = _safe_int(raw.get("afterHourIst", defaults.get("afterHourIst", 15)), defaults.get("afterHourIst", 15))
    minute = _safe_int(raw.get("afterMinuteIst", defaults.get("afterMinuteIst", 30)), defaults.get("afterMinuteIst", 30))
    weekdays = _normalize_weekdays(raw, defaults)
    schedule_type = str(raw.get("scheduleType", defaults.get("scheduleType", "daily"))).strip().lower()
    if schedule_type not in ("daily", "weekly"):
        schedule_type = "daily"
    return {
        "enabled": bool(raw.get("enabled", False)),
        "scheduleType": schedule_type,
        "afterHourIst": max(0, min(23, hour)),
        "afterMinuteIst": max(0, min(59, minute)),
        "weekdaysIst": weekdays,
        "weekdayIst": weekdays[0],
    }


def _normalize_daily_task(raw: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    return _normalize_timed_task(raw, defaults)


def _normalize_ohlcv(raw: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    schedule_type = str(raw.get("scheduleType", defaults.get("scheduleType", "interval"))).strip().lower()
    if schedule_type not in ("interval", "daily", "weekly"):
        schedule_type = "interval"
    interval = _safe_int(raw.get("intervalMinutes", defaults.get("intervalMinutes", 30)), defaults.get("intervalMinutes", 30))
    if interval not in ALLOWED_OHLCV_INTERVAL_MINUTES:
        interval = int(defaults.get("intervalMinutes", 30))
    timed = _normalize_timed_task(raw, defaults)
    return {
        "enabled": bool(raw.get("enabled", False)),
        "scheduleType": schedule_type,
        "intervalMinutes": interval,
        "afterHourIst": timed["afterHourIst"],
        "afterMinuteIst": timed["afterMinuteIst"],
        "weekdaysIst": timed["weekdaysIst"],
        "weekdayIst": timed["weekdayIst"],
    }


def _normalize_filter_preset(
    raw: dict[str, Any] | None,
    defaults: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    default_preset = defaults.get("preset") if isinstance(defaults.get("preset"), dict) else {}
    by_key = registry_by_key()

    keys_raw = raw.get("keys") if isinstance(raw.get("keys"), list) else default_preset.get("keys", [])
    keys = []
    for item in keys_raw:
        key = str(item or "").strip().lower()
        if key in by_key and key not in keys:
            keys.append(key)
    if not keys:
        keys = list(FILTER_REBUILD_KEYS)

    valid_tfs = set(SNAPSHOT_TIMEFRAME_OPTIONS)
    tf_raw = raw.get("timeframes") if isinstance(raw.get("timeframes"), list) else default_preset.get("timeframes", [])
    timeframes = []
    for item in tf_raw:
        tf = str(item or "").strip().upper()
        if tf in valid_tfs and tf not in timeframes:
            timeframes.append(tf)
    if not timeframes:
        default_tfs = FILTER_REBUILD_LIGHT_TIMEFRAMES if mode == "incremental" else SNAPSHOT_TIMEFRAME_OPTIONS
        timeframes = list(default_tfs)

    try:
        days_back = max(0, min(30, int(raw.get("days_back", default_preset.get("days_back", 1)))))
    except (TypeError, ValueError):
        days_back = 1

    return {
        "keys": keys,
        "mode": mode,
        "days_back": days_back,
        "timeframes": timeframes,
    }


def _normalize_filter_rebuild_task(
    raw: dict[str, Any] | None,
    defaults: dict[str, Any],
    *,
    task_key: str,
) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    timed = _normalize_timed_task(raw, defaults)
    if task_key == "filterRebuildDaily":
        timed["scheduleType"] = "daily"
        mode = "incremental"
    else:
        timed["scheduleType"] = "weekly"
        mode = "full"
    timed["preset"] = _normalize_filter_preset(
        raw.get("preset") if isinstance(raw.get("preset"), dict) else None,
        defaults,
        mode=mode,
    )
    return timed


def filter_rebuild_preset_for_task(task_key: str) -> dict[str, Any] | None:
    cfg = load_config()
    task = cfg.get(str(task_key or "").strip())
    if not isinstance(task, dict):
        return None
    preset = task.get("preset")
    return dict(preset) if isinstance(preset, dict) else None


def _copy_legacy_snapshot_schedule(
    raw: dict[str, Any],
    legacy_key: str,
    new_key: str,
) -> None:
    if new_key in raw or legacy_key not in raw or not isinstance(raw.get(legacy_key), dict):
        return
    legacy = dict(raw[legacy_key])
    defaults = DEFAULT_CONFIG[new_key]
    preset = dict(defaults.get("preset") or {})
    raw[new_key] = {
        "enabled": bool(legacy.get("enabled", False)),
        "scheduleType": defaults.get("scheduleType", "daily"),
        "afterHourIst": legacy.get("afterHourIst", defaults.get("afterHourIst")),
        "afterMinuteIst": legacy.get("afterMinuteIst", defaults.get("afterMinuteIst")),
        "weekdayIst": legacy.get("weekdayIst", defaults.get("weekdayIst")),
        "weekdaysIst": legacy.get("weekdaysIst", [legacy.get("weekdayIst", defaults.get("weekdayIst"))]),
        "preset": preset,
    }


def _normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(raw) if isinstance(raw, dict) else {}
    _copy_legacy_snapshot_schedule(raw, "snapshotsLight", "filterRebuildDaily")
    _copy_legacy_snapshot_schedule(raw, "indicatorIncremental", "filterRebuildDaily")
    _copy_legacy_snapshot_schedule(raw, "snapshotsHeavy", "filterRebuildWeekly")
    for legacy, new in _LEGACY_CONFIG_ALIASES.items():
        if legacy in raw and new not in raw:
            raw[new] = raw[legacy]

    ohlcv_raw = raw.get("ohlcv") if isinstance(raw.get("ohlcv"), dict) else {}

    out: dict[str, Any] = {
        "ohlcv": _normalize_ohlcv(ohlcv_raw, DEFAULT_CONFIG["ohlcv"]),
    }
    for key in TASK_KEYS:
        if key == "ohlcv":
            continue
        raw_task = raw.get(key) if isinstance(raw.get(key), dict) else None
        if key in ("filterRebuildDaily", "filterRebuildWeekly"):
            out[key] = _normalize_filter_rebuild_task(
                raw_task,
                DEFAULT_CONFIG[key],
                task_key=key,
            )
        else:
            out[key] = _normalize_timed_task(
                raw_task,
                DEFAULT_CONFIG[key],
            )
    return out


def _migrate_legacy_files() -> None:
    cfg = _config_path()
    legacy_cfg = _legacy_config_path()
    if not cfg.is_file() and legacy_cfg.is_file():
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_cfg, cfg)
            append_log(f"Migrated config from {legacy_cfg.name}")
        except OSError as e:
            append_log(f"Config migration warning: {e}")

    st = _state_path()
    legacy_st = _legacy_state_path()
    if not st.is_file() and legacy_st.is_file():
        try:
            st.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_st, st)
            append_log(f"Migrated state from {legacy_st.name}")
        except OSError as e:
            append_log(f"State migration warning: {e}")


def load_config() -> dict[str, Any]:
    _migrate_legacy_files()
    path = _config_path()
    if not path.is_file():
        return _normalize_config(None)
    try:
        with open(path, encoding="utf-8-sig") as f:
            return _normalize_config(json.load(f))
    except (OSError, json.JSONDecodeError):
        return _normalize_config(None)


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    global _config_cache
    normalized = _normalize_config(config)
    path = _config_path()
    _write_json_atomic(path, normalized)
    with _lock:
        _config_cache = normalized
    enabled = [k for k in TASK_KEYS if (normalized.get(k) or {}).get("enabled")]
    append_log(f"Config saved; enabled tasks: {enabled or '(none)'}")
    return normalized


def reload_config() -> dict[str, Any]:
    global _config_cache
    with _lock:
        _config_cache = load_config()
        return dict(_config_cache)


def load_state() -> dict[str, Any]:
    _migrate_legacy_files()
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    _write_json_atomic(path, state)


def _parse_iso_ist(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except (TypeError, ValueError):
        return None


def _task_state_prefix(task_key: str) -> str:
    if task_key == "ohlcv":
        return "Ohlcv"
    return _LEGACY_STATE_PREFIX.get(task_key, task_key[:1].upper() + task_key[1:])


def _state_last_at_key(task_key: str) -> str:
    if task_key == "ohlcv":
        return "lastOhlcvAt"
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}At"


def _state_last_date_key(task_key: str) -> str:
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}Date"


def _state_last_week_key(task_key: str) -> str:
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}Week"


def _iso_week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _ist_weekday(dt: datetime) -> int:
    """Monday=0 … Sunday=6."""
    return dt.weekday()


def _next_weekday_datetime(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """Next occurrence of weekday at hour:minute (includes today if still ahead)."""
    days_ahead = (weekday - _ist_weekday(now)) % 7
    candidate = now + timedelta(days=days_ahead)
    target = datetime.combine(candidate.date(), dtime(hour, minute), tzinfo=IST)
    if days_ahead == 0 and now >= target:
        target = target + timedelta(days=7)
    return target


def _state_last_trigger_key(task_key: str) -> str:
    if task_key == "ohlcv":
        return "lastOhlcvTrigger"
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}Trigger"


def _state_last_attempt_key(task_key: str) -> str:
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}AttemptAt"


def _daily_target(now: datetime, hour: int, minute: int) -> datetime:
    return datetime.combine(now.date(), dtime(hour, minute), tzinfo=IST)


def _compute_next_daily(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return None
    if str(task_cfg.get("scheduleType", "daily")).lower() == "weekly":
        return _compute_next_weekly(task_key, cfg, state, now)
    hour = int(task_cfg.get("afterHourIst", 15))
    minute = int(task_cfg.get("afterMinuteIst", 30))
    target = _daily_target(now, hour, minute)
    today = now.date().isoformat()
    if state.get(_state_last_date_key(task_key)) == today:
        tomorrow = now.date() + timedelta(days=1)
        nxt = datetime.combine(tomorrow, dtime(hour, minute), tzinfo=IST)
        return nxt.isoformat()
    if now >= target:
        return now.isoformat()
    return target.isoformat()


def _compute_next_weekly(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return None
    hour = int(task_cfg.get("afterHourIst", 15))
    minute = int(task_cfg.get("afterMinuteIst", 30))
    weekdays = _weekdays_from_task(task_cfg)
    weekday_set = set(weekdays)
    today_iso = now.date().isoformat()
    ran_today = state.get(_state_last_date_key(task_key)) == today_iso
    target_today = _daily_target(now, hour, minute)

    if _ist_weekday(now) in weekday_set and not ran_today:
        if now >= target_today:
            return now.isoformat()
        return target_today.isoformat()

    search_from = now + timedelta(days=1)
    for offset in range(14):
        day = search_from + timedelta(days=offset)
        if _ist_weekday(day) not in weekday_set:
            continue
        return datetime.combine(day.date(), dtime(hour, minute), tzinfo=IST).isoformat()
    return None


def _compute_next_ohlcv(cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    ohlcv = cfg.get("ohlcv") or {}
    if not ohlcv.get("enabled"):
        return None
    interval = int(ohlcv.get("intervalMinutes") or 0)
    if interval <= 0:
        return None
    last = _parse_iso_ist(state.get("lastOhlcvAt"))
    if last is None:
        return now.isoformat()
    nxt = last + timedelta(minutes=interval)
    if nxt <= now:
        return now.isoformat()
    return nxt.isoformat()


def compute_next_run(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    if task_key == "ohlcv":
        ohlcv = cfg.get("ohlcv") or {}
        schedule_type = str(ohlcv.get("scheduleType", "interval")).lower()
        if schedule_type == "interval":
            return _compute_next_ohlcv(cfg, state, now)
        if schedule_type == "weekly":
            return _compute_next_weekly(task_key, cfg, state, now)
        return _compute_next_daily(task_key, cfg, state, now)
    return _compute_next_daily(task_key, cfg, state, now)


def _set_waiting(task_key: str | None, reason: str | None) -> None:
    global _waiting_task, _waiting_reason
    _waiting_task = task_key
    _waiting_reason = reason


def _record_task_started(state: dict[str, Any], task_key: str, now: datetime, trigger: str) -> dict[str, Any]:
    state = dict(state)
    at_key = _state_last_at_key(task_key)
    state[at_key] = now.isoformat()
    state[_state_last_trigger_key(task_key)] = trigger
    state[_state_last_date_key(task_key)] = now.date().isoformat()
    state[_state_last_week_key(task_key)] = _iso_week_key(now)
    return state


def scheduler_is_blocked() -> bool:
    return bool(_scheduler_blocked_fn()) if _scheduler_blocked_fn else False


def set_scheduler_blocked_fn(fn: Optional[Callable[[], bool]]) -> None:
    global _scheduler_blocked_fn
    _scheduler_blocked_fn = fn


def task_is_due_now(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> bool:
    """True if the scheduler would start this task on the next eligible poll."""
    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return False

    if task_key == "ohlcv":
        schedule_type = str(task_cfg.get("scheduleType", "interval")).lower()
        if schedule_type == "interval":
            interval = int(task_cfg.get("intervalMinutes") or 0)
            if interval <= 0:
                return False
            last = _parse_iso_ist(state.get("lastOhlcvAt"))
            return last is None or (now - last).total_seconds() >= interval * 60
        return _timed_task_is_due_now(task_key, task_cfg, state, now, schedule_type)

    schedule_type = str(task_cfg.get("scheduleType", "daily")).lower()
    return _timed_task_is_due_now(task_key, task_cfg, state, now, schedule_type)


def _timed_task_is_due_now(
    task_key: str,
    task_cfg: dict[str, Any],
    state: dict[str, Any],
    now: datetime,
    schedule_type: str,
) -> bool:
    hour = int(task_cfg.get("afterHourIst", 15))
    minute = int(task_cfg.get("afterMinuteIst", 30))
    target = _daily_target(now, hour, minute)
    if schedule_type == "weekly":
        weekdays = _weekdays_from_task(task_cfg)
        if _ist_weekday(now) not in weekdays:
            return False
        today = now.date().isoformat()
        if state.get(_state_last_date_key(task_key)) == today:
            return False
        return now >= target
    today = now.date().isoformat()
    if state.get(_state_last_date_key(task_key)) == today:
        return False
    return now >= target


def _maybe_run_task(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> dict[str, Any]:
    global _waiting_task, _waiting_reason
    start_fn = _start_fns.get(task_key)
    if not start_fn:
        return state

    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return state

    if scheduler_is_blocked():
        _set_waiting(task_key, "snapshot_rebuild_hold")
        return state

    if not task_is_due_now(task_key, cfg, state, now):
        return state

    if _job_running_fn and _job_running_fn():
        last_try = _parse_iso_ist(state.get(_state_last_attempt_key(task_key)))
        if last_try and (now - last_try).total_seconds() < RETRY_SEC:
            _set_waiting(task_key, "job_slot_busy")
            return state
        state = {**state, _state_last_attempt_key(task_key): now.isoformat()}
        save_state(state)
        append_log(f"{task_key}: waiting — another job is running; will retry")
        _set_waiting(task_key, "job_slot_busy")
        return state

    _set_waiting(None, None)
    append_log(f"Starting scheduled task: {task_key}")
    started = start_fn()
    state = {**state, _state_last_attempt_key(task_key): now.isoformat()}
    if started:
        state = _record_task_started(state, task_key, now, "scheduled")
        append_log(f"Scheduled task started: {task_key}")
    else:
        append_log(f"Skipped {task_key} — job already running")
        _set_waiting(task_key, "start_rejected")
    save_state(state)
    return state


def get_status() -> dict[str, Any]:
    with _lock:
        cfg = dict(_config_cache)
    state = load_state()
    now = datetime.now(IST)
    running = bool(_job_running_fn()) if _job_running_fn else False
    next_runs = {key: compute_next_run(key, cfg, state, now) for key in TASK_KEYS}
    return {
        "config": cfg,
        "state": state,
        "schedulerRunning": _thread is not None and _thread.is_alive(),
        "jobRunning": running,
        "activeTask": None,
        "waitingTask": _waiting_task,
        "waitingReason": _waiting_reason,
        "istNow": now.isoformat(),
        "nextRuns": next_runs,
        # Backward-compatible keys
        "nextOhlcvAt": next_runs.get("ohlcv"),
        "nextIndicatorAt": next_runs.get("filterRebuildDaily"),
        "logPath": str(_log_path()),
        "logTail": read_log_tail(),
        "allowedOhlcvIntervalMinutes": list(ALLOWED_OHLCV_INTERVAL_MINUTES),
        "taskKeys": list(TASK_KEYS),
        "manualTaskKeys": list(MANUAL_TASK_KEYS),
    }


def configure(
    *,
    start_fns: dict[str, Callable[[], bool]] | None = None,
    start_ohlcv_fn: Callable[[], bool] | None = None,
    start_indicator_fn: Callable[[], bool] | None = None,
    job_running_fn: Callable[[], bool] | None = None,
    scheduler_blocked_fn: Callable[[], bool] | None = None,
    install_root: Path | None = None,
) -> None:
    global _start_fns, _job_running_fn, _install_root
    if start_fns:
        _start_fns = dict(start_fns)
    else:
        _start_fns = {}
        if start_ohlcv_fn:
            _start_fns["ohlcv"] = start_ohlcv_fn
        if start_indicator_fn:
            _start_fns["filterRebuildDaily"] = start_indicator_fn
    if job_running_fn is not None:
        _job_running_fn = job_running_fn
    if scheduler_blocked_fn is not None:
        set_scheduler_blocked_fn(scheduler_blocked_fn)
    if install_root is not None:
        _install_root = Path(install_root).resolve()
    reload_config()


def run_task_now(task_key: str) -> dict[str, Any]:
    """Manual Run now from Scheduler UI or API."""
    task_key = str(task_key or "").strip()
    if task_key not in TASK_KEYS and task_key not in _start_fns:
        return {"ok": False, "error": f"Unknown task: {task_key}"}
    start_fn = _start_fns.get(task_key)
    if not start_fn:
        return {"ok": False, "error": f"Task not configured: {task_key}"}
    if scheduler_is_blocked():
        return {"ok": False, "error": "Scheduler paused for full indicator snapshot rebuild."}
    if _job_running_fn and _job_running_fn():
        return {"ok": False, "error": "A job is already running."}
    now = datetime.now(IST)
    append_log(f"Manual run: {task_key}")
    started = start_fn()
    state = load_state()
    state = {**state, _state_last_attempt_key(task_key): now.isoformat()}
    if started:
        state = _record_task_started(state, task_key, now, "manual")
        append_log(f"Manual task started: {task_key}")
    else:
        append_log(f"Manual run rejected for {task_key} — job already running")
    save_state(state)
    return {"ok": bool(started), "task": task_key, "started": bool(started)}


def record_external_manual_run(task_key: str) -> None:
    """When Update menu starts a job outside run_task_now."""
    if task_key not in TASK_KEYS:
        return
    now = datetime.now(IST)
    state = load_state()
    state = _record_task_started(state, task_key, now, "manual")
    save_state(state)


def _scheduler_loop() -> None:
    append_log("Scheduler thread started (all tasks opt-in; none enabled by default)")
    while not _stop.wait(POLL_SEC):
        try:
            if scheduler_is_blocked():
                _set_waiting(None, "snapshot_rebuild_hold")
                continue
            with _lock:
                cfg = dict(_config_cache)
            now = datetime.now(IST)
            state = load_state()
            _set_waiting(None, None)
            for task_key in TASK_LOOP_ORDER:
                if _job_running_fn and _job_running_fn():
                    break
                state = _maybe_run_task(task_key, cfg, state, now)
        except Exception as e:
            append_log(f"Scheduler loop error: {e}")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_scheduler_loop, name="admin-job-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def mark_indicator_completed(success: bool = True) -> None:
    """Backward-compatible hook when light snapshot job finishes."""
    if not success:
        return
    state = load_state()
    today = datetime.now(IST).date().isoformat()
    state["lastIndicatorDate"] = today
    state["lastFilterRebuildDailyDate"] = today
    save_state(state)
