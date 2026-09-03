"""
Unified opt-in admin job scheduler for showcase host (IST).

All tasks default to disabled. Runs inside the uvicorn process while the backend is up.
"""
from __future__ import annotations

import json
import shutil
import threading
import time as time_module
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from filter_rebuild_registry import SNAPSHOT_TIMEFRAME_OPTIONS, normalize_snapshot_timeframe, registry_by_key
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
    "eodReconcile",
    "liveQuotesWarm",
    "splitWatch",
    "earningsPlusWarm",
    "earningsTvResync",
    "fetchFinancials",
    "fetchScreenerSectors",
    "expandUniverse",
    "mfNav",
    "sectorIndexCores",
    "exchangeClassification",
)

FILTER_DEFAULT_PRESET = {
    "keys": list(FILTER_REBUILD_KEYS),
    "mode": "incremental",
    "days_back": 1,
    "timeframes": list(FILTER_REBUILD_LIGHT_TIMEFRAMES),
}

FILTER_DEFAULT_TIMED = {
    "enabled": False,
    "afterHourIst": 23,
    "afterMinuteIst": 0,
    "weekdayIst": 0,
    "weekdaysIst": list(range(7)),
}

# Deprecated — all tasks are schedulable; kept for one release of API compat.
MANUAL_TASK_KEYS: tuple[str, ...] = ()

# Lighter tasks first; weekly full filter rebuild after EOD/OHLCV.
TASK_LOOP_ORDER = (
    "liveQuotesWarm",
    "eodReconcile",
    "ohlcv",
    "earningsTvResync",
    "earningsPlusWarm",
    "splitWatch",
    "fetchScreenerSectors",
    "expandUniverse",
    "fetchFinancials",
    "mfNav",
    "sectorIndexCores",
    "exchangeClassification",
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
        "scheduleType": "daily",
        "afterHourIst": 15,
        "afterMinuteIst": 30,
        "weekdayIst": 4,
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
    "earningsTvResync": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 12,
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
    "mfNav": {
        "enabled": False,
        "scheduleType": "daily",
        "afterHourIst": 21,
        "afterMinuteIst": 30,
        "weekdayIst": 4,
    },
    "sectorIndexCores": {
        "enabled": False,
        "scheduleType": "weekly",
        "afterHourIst": 5,
        "afterMinuteIst": 0,
        "weekdayIst": 6,
    },
    "exchangeClassification": {
        "enabled": False,
        "scheduleType": "weekly",
        "afterHourIst": 5,
        "afterMinuteIst": 30,
        "weekdayIst": 6,
    },
}

# Legacy config keys migrated into filterSchedules on load.
_LEGACY_CONFIG_ALIASES: dict[str, str] = {}
_LEGACY_STATE_PREFIX = {
    "eodReconcile": "EodReconcile",
    "liveQuotesWarm": "LiveQuotesWarm",
    "splitWatch": "SplitWatch",
    "earningsPlusWarm": "EarningsPlusWarm",
    "earningsTvResync": "EarningsTvResync",
    "fetchFinancials": "FetchFinancials",
    "fetchScreenerSectors": "FetchScreenerSectors",
    "expandUniverse": "ExpandUniverse",
    "mfNav": "MfNav",
    "sectorIndexCores": "SectorIndexCores",
    "exchangeClassification": "ExchangeClassification",
}

_start_fns: dict[str, Callable[[], bool]] = {}
_filter_instance_start_fn: Optional[Callable[[dict[str, Any]], bool]] = None
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
    # Legacy interval → daily.
    if schedule_type == "interval":
        schedule_type = "daily"
    if schedule_type not in ("daily", "weekly", "monthly"):
        schedule_type = "daily"
    if schedule_type == "daily":
        weekdays = list(range(7))
    elif schedule_type == "monthly":
        weekdays = [weekdays[0]] if weekdays else [_safe_int(defaults.get("weekdayIst", 4), 4)]
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
    # OHLCV uses daily/weekly/monthly. Legacy "interval" migrates to daily.
    return _normalize_timed_task(raw, defaults)


def _normalize_filter_preset(
    raw: dict[str, Any] | None,
    defaults: dict[str, Any],
    *,
    mode: str,
    allow_empty_keys: bool = False,
    allow_empty_timeframes: bool = False,
) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    default_preset = defaults.get("preset") if isinstance(defaults.get("preset"), dict) else {}
    by_key = registry_by_key()

    # When the caller explicitly supplies a keys list (even empty), honor it as-is
    # so "no data sources selected" is preserved. Only fall back to defaults when
    # keys were omitted entirely.
    keys_provided = isinstance(raw.get("keys"), list)
    keys_raw = raw.get("keys") if keys_provided else default_preset.get("keys", [])
    keys = []
    for item in keys_raw:
        key = str(item or "").strip().lower()
        if key in by_key and key not in keys:
            keys.append(key)
    if not keys and not (allow_empty_keys and keys_provided):
        keys = list(FILTER_REBUILD_KEYS)

    # When the caller explicitly supplies a timeframes list (even empty), honor it
    # as-is so "no timeframes selected" is preserved. Only fall back to defaults
    # when timeframes were omitted entirely.
    tf_provided = isinstance(raw.get("timeframes"), list)
    valid_tfs = set(SNAPSHOT_TIMEFRAME_OPTIONS)
    tf_raw = raw.get("timeframes") if tf_provided else default_preset.get("timeframes", [])
    timeframes = []
    for item in tf_raw:
        tf = normalize_snapshot_timeframe(item)
        if tf in valid_tfs and tf not in timeframes:
            timeframes.append(tf)
    if not timeframes and not (allow_empty_timeframes and tf_provided):
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


def _normalize_filter_schedule_entry(raw: dict[str, Any] | None, index: int) -> dict[str, Any]:
    """Normalize one filter schedule instance (daily/weekly + free mode)."""
    raw = raw if isinstance(raw, dict) else {}
    defaults = FILTER_DEFAULT_TIMED
    hour = _safe_int(raw.get("afterHourIst", defaults["afterHourIst"]), defaults["afterHourIst"])
    minute = _safe_int(raw.get("afterMinuteIst", defaults["afterMinuteIst"]), defaults["afterMinuteIst"])
    # Honor an explicit (possibly empty) weekday list so "no days selected" is
    # preserved. Only fall back to a legacy single weekday when weekdaysIst was
    # never provided as a list.
    raw_weekdays = raw.get("weekdaysIst")
    if isinstance(raw_weekdays, list):
        parsed: list[int] = []
        for item in raw_weekdays:
            try:
                parsed.append(max(0, min(6, int(item))))
            except (TypeError, ValueError):
                continue
        weekdays = sorted(set(parsed))
        # An explicit empty list means "no days selected" and is preserved.
        # A non-empty but fully invalid list is malformed → fall back to default.
        if not weekdays and len(raw_weekdays) > 0:
            weekdays = _normalize_weekdays(raw, defaults)
    else:
        weekdays = _normalize_weekdays(raw, defaults)

    schedule_raw = str(raw.get("scheduleType") or "").strip().lower()
    if schedule_raw in ("daily", "weekly", "monthly"):
        schedule_type = schedule_raw
    else:
        # Legacy: all seven weekdays meant every-day / "daily".
        schedule_type = "daily" if weekdays == list(range(7)) else "weekly"

    if schedule_type == "daily":
        weekdays = list(range(7))
    elif schedule_type == "monthly":
        # Single weekday only — first that weekday of each month.
        weekdays = [weekdays[0]] if weekdays else []

    mode_raw = str(raw.get("mode") or (raw.get("preset") or {}).get("mode") or "incremental").strip().lower()
    mode = "full" if mode_raw == "full" else "incremental"
    preset_defaults = {"preset": FILTER_DEFAULT_PRESET}
    entry_id = str(raw.get("id") or "").strip() or f"fs_{index}_{int(time_module.time() * 1000)}"
    preset = _normalize_filter_preset(
        raw.get("preset") if isinstance(raw.get("preset"), dict) else None,
        preset_defaults,
        mode=mode,
        allow_empty_keys=True,
        allow_empty_timeframes=True,
    )
    return {
        "id": entry_id,
        "enabled": bool(raw.get("enabled", False)),
        "mode": mode,
        "scheduleType": schedule_type,
        "afterHourIst": max(0, min(23, hour)),
        "afterMinuteIst": max(0, min(59, minute)),
        "weekdaysIst": weekdays,
        "weekdayIst": weekdays[0] if weekdays else 0,
        "preset": preset,
    }


def _normalize_filter_schedules(raw_list: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(raw_list, list):
        for i, item in enumerate(raw_list):
            entry = _normalize_filter_schedule_entry(item, i)
            if entry["id"] in seen:
                entry["id"] = f"{entry['id']}_{i}"
            seen.add(entry["id"])
            out.append(entry)
    return out


def _normalize_task_schedule_entry(raw: dict[str, Any] | None, index: int) -> dict[str, Any] | None:
    """One multi-instance schedule for any TASK_KEYS job (ohlcv, eod, …)."""
    raw = raw if isinstance(raw, dict) else {}
    task_key = str(raw.get("taskKey") or raw.get("task") or "").strip()
    if task_key not in TASK_KEYS:
        return None
    defaults = DEFAULT_CONFIG.get(task_key) or _DEFAULT_DAILY
    timed = _normalize_timed_task(raw, defaults)
    entry_id = str(raw.get("id") or "").strip() or f"ts_{task_key}_{index}_{int(time_module.time() * 1000)}"
    name = str(raw.get("name") or "").strip()
    return {
        "id": entry_id,
        "taskKey": task_key,
        "name": name,
        **timed,
    }


def _normalize_task_schedules(raw_list: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(raw_list, list):
        for i, item in enumerate(raw_list):
            entry = _normalize_task_schedule_entry(item if isinstance(item, dict) else None, i)
            if not entry:
                continue
            if entry["id"] in seen:
                entry["id"] = f"{entry['id']}_{i}"
            seen.add(entry["id"])
            out.append(entry)
    return out


def _migrate_singletons_into_task_schedules(
    raw: dict[str, Any],
    schedules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Promote legacy one-object-per-task configs into taskSchedules instances."""
    by_task: dict[str, list[dict[str, Any]]] = {}
    for entry in schedules:
        by_task.setdefault(str(entry.get("taskKey")), []).append(entry)
    out = list(schedules)
    for task_key in TASK_KEYS:
        if by_task.get(task_key):
            continue
        singleton = raw.get(task_key) if isinstance(raw.get(task_key), dict) else None
        if not singleton:
            continue
        # Only migrate when the singleton was actually enabled or had a custom stamp.
        if not singleton.get("enabled"):
            continue
        entry = _normalize_task_schedule_entry(
            {**singleton, "id": f"legacy_{task_key}", "taskKey": task_key},
            0,
        )
        if entry:
            out.append(entry)
            by_task.setdefault(task_key, []).append(entry)
    return out


def _legacy_filter_task_to_schedule(
    raw: dict[str, Any] | None,
    *,
    entry_id: str,
    default_weekdays: list[int],
    default_mode: str,
    default_timeframes: tuple[str, ...],
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    preset_raw = raw.get("preset") if isinstance(raw.get("preset"), dict) else {}
    weekdays_raw = raw.get("weekdaysIst")
    if isinstance(weekdays_raw, list) and weekdays_raw:
        weekdays = _normalize_weekdays(raw, {"weekdayIst": default_weekdays[0]})
    elif raw.get("weekdayIst") is not None:
        weekdays = _normalize_weekdays(raw, {"weekdayIst": default_weekdays[0]})
    else:
        weekdays = list(default_weekdays)
    mode_raw = str(raw.get("mode") or preset_raw.get("mode") or default_mode).strip().lower()
    mode = "full" if mode_raw == "full" else "incremental"
    return {
        "id": entry_id,
        "enabled": bool(raw.get("enabled", False)),
        "mode": mode,
        "scheduleType": "weekly" if len(weekdays) < 7 else "daily",
        "afterHourIst": _safe_int(raw.get("afterHourIst", FILTER_DEFAULT_TIMED["afterHourIst"]), 23),
        "afterMinuteIst": _safe_int(raw.get("afterMinuteIst", FILTER_DEFAULT_TIMED["afterMinuteIst"]), 0),
        "weekdaysIst": weekdays,
        "weekdayIst": weekdays[0],
        "preset": _normalize_filter_preset(
            preset_raw,
            {"preset": {**FILTER_DEFAULT_PRESET, "mode": mode, "timeframes": list(default_timeframes)}},
            mode=mode,
        ),
    }


def _migrate_legacy_filter_tasks_into_schedules(raw: dict[str, Any], schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Move legacy filterRebuildDaily/Weekly (and aliases) into filterSchedules once."""
    existing_ids = {str(s.get("id")) for s in schedules if isinstance(s, dict) and s.get("id")}
    out = list(schedules)
    migrations: list[tuple[str, dict[str, Any] | None, list[int], str, tuple[str, ...]]] = [
        ("filterRebuildDaily", raw.get("filterRebuildDaily"), list(range(7)), "incremental", FILTER_REBUILD_LIGHT_TIMEFRAMES),
        ("filterRebuildWeekly", raw.get("filterRebuildWeekly"), [5], "full", SNAPSHOT_TIMEFRAME_OPTIONS),
        ("indicatorIncremental", raw.get("indicatorIncremental"), list(range(7)), "incremental", FILTER_REBUILD_LIGHT_TIMEFRAMES),
        ("snapshotsLight", raw.get("snapshotsLight"), list(range(7)), "incremental", FILTER_REBUILD_LIGHT_TIMEFRAMES),
        ("snapshotsHeavy", raw.get("snapshotsHeavy"), [5], "full", SNAPSHOT_TIMEFRAME_OPTIONS),
    ]
    for entry_id, task_raw, weekdays, mode, tfs in migrations:
        if entry_id in existing_ids:
            continue
        entry = _legacy_filter_task_to_schedule(
            task_raw,
            entry_id=entry_id,
            default_weekdays=weekdays,
            default_mode=mode,
            default_timeframes=tfs,
        )
        if entry and task_raw:
            out.append(entry)
            existing_ids.add(entry_id)
    return out


def _normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(raw) if isinstance(raw, dict) else {}
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
        out[key] = _normalize_timed_task(
            raw_task,
            DEFAULT_CONFIG[key],
        )
    schedules = _normalize_filter_schedules(raw.get("filterSchedules"))
    out["filterSchedules"] = _migrate_legacy_filter_tasks_into_schedules(raw, schedules)

    task_schedules = _normalize_task_schedules(raw.get("taskSchedules"))
    out["taskSchedules"] = _migrate_singletons_into_task_schedules(raw, task_schedules)

    # Singletons are legacy display stubs only — execution uses taskSchedules.
    # Keep shape for older clients, but never leave them enabled (avoids double-fire).
    for key in TASK_KEYS:
        stub = dict(out.get(key) or DEFAULT_CONFIG.get(key) or _DEFAULT_DAILY)
        stub["enabled"] = False
        out[key] = stub
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


def _timed_task_sig(cfg_entry: dict[str, Any]) -> tuple:
    return (
        int(_safe_int(cfg_entry.get("afterHourIst", -1), -1)),
        int(_safe_int(cfg_entry.get("afterMinuteIst", -1), -1)),
        tuple(sorted(cfg_entry.get("weekdaysIst") or [])),
        str(cfg_entry.get("scheduleType") or ""),
    )


def _fs_sig(entry: dict[str, Any]) -> tuple:
    return (
        int(_safe_int(entry.get("afterHourIst", -1), -1)),
        int(_safe_int(entry.get("afterMinuteIst", -1), -1)),
        tuple(sorted(entry.get("weekdaysIst") or [])),
        str(entry.get("scheduleType") or ""),
    )


def _apply_forward_scheduling(prev_cfg: dict[str, Any] | None, new_cfg: dict[str, Any], now: datetime) -> None:
    """When a schedule is newly enabled or its time/days change, don't fire it
    retroactively for a target time that already passed *today*.

    Stamps ``lastDate`` = today so the next run is the next future occurrence
    (matching operator expectation: "run at the time I set, going forward").
    Schedules that were already enabled keep their normal same-day catch-up.
    """
    try:
        state = load_state()
    except Exception:
        return
    today = now.date().isoformat()
    changed = False

    def _arm(key: str, target_passed: bool) -> None:
        nonlocal changed
        if target_passed:
            if state.get(key) != today:
                state[key] = today
                changed = True
        elif key in state:
            # Reconfigured to a still-upcoming time today → allow today's run.
            state.pop(key, None)
            changed = True

    for task_key in TASK_KEYS:
        new_t = new_cfg.get(task_key) or {}
        if not new_t.get("enabled"):
            continue
        schedule_type = str(new_t.get("scheduleType", "daily")).lower()
        prev_t = (prev_cfg or {}).get(task_key) or {}
        if prev_t.get("enabled") and _timed_task_sig(prev_t) == _timed_task_sig(new_t):
            continue
        if schedule_type == "weekly" and _ist_weekday(now) not in set(_weekdays_from_task(new_t)):
            continue
        if schedule_type == "monthly":
            wd = (_weekdays_from_task(new_t) or [None])[0]
            if wd is None or now.date() != _first_weekday_of_month(now.year, now.month, wd):
                continue
        hour = _safe_int(new_t.get("afterHourIst", 15), 15)
        minute = _safe_int(new_t.get("afterMinuteIst", 30), 30)
        # Suppress today's *scheduled* slot only (not manual lastDate display).
        _arm(_state_last_scheduled_date_key(task_key), now >= _daily_target(now, hour, minute))
        _arm(_state_last_date_key(task_key), now >= _daily_target(now, hour, minute))
        if now >= _daily_target(now, hour, minute):
            # Mark as scheduled fulfillment so due-check stays consistent.
            trig = _state_last_trigger_key(task_key)
            if state.get(trig) != "scheduled":
                state[trig] = "scheduled"
                changed = True

    prev_ts_by_id = {
        s.get("id"): s
        for s in ((prev_cfg or {}).get("taskSchedules") or [])
        if isinstance(s, dict)
    }
    for entry in new_cfg.get("taskSchedules") or []:
        if not isinstance(entry, dict) or not entry.get("enabled"):
            continue
        prev = prev_ts_by_id.get(entry.get("id"))
        if prev and prev.get("enabled") and _fs_sig(prev) == _fs_sig(entry):
            continue
        schedule_type = str(entry.get("scheduleType") or "daily").lower()
        if schedule_type == "weekly" and _ist_weekday(now) not in set(_weekdays_from_task(entry)):
            continue
        if schedule_type == "monthly":
            wd = (_weekdays_from_task(entry) or [None])[0]
            if wd is None or now.date() != _first_weekday_of_month(now.year, now.month, wd):
                continue
        hour = _safe_int(entry.get("afterHourIst", 15), 15)
        minute = _safe_int(entry.get("afterMinuteIst", 30), 30)
        _arm(_ts_state_key(str(entry.get("id") or ""), "lastDate"), now >= _daily_target(now, hour, minute))

    prev_by_id = {
        s.get("id"): s
        for s in ((prev_cfg or {}).get("filterSchedules") or [])
        if isinstance(s, dict)
    }
    for entry in new_cfg.get("filterSchedules") or []:
        if not isinstance(entry, dict) or not entry.get("enabled") or _fs_incomplete(entry):
            continue
        prev = prev_by_id.get(entry.get("id"))
        if prev and prev.get("enabled") and _fs_sig(prev) == _fs_sig(entry):
            continue
        schedule_type = str(entry.get("scheduleType") or "weekly").lower()
        if schedule_type == "weekly" and _ist_weekday(now) not in set(_weekdays_from_task(entry)):
            continue
        if schedule_type == "monthly":
            wd = (_weekdays_from_task(entry) or [None])[0]
            if wd is None or now.date() != _first_weekday_of_month(now.year, now.month, wd):
                continue
        hour = _safe_int(entry.get("afterHourIst", 23), 23)
        minute = _safe_int(entry.get("afterMinuteIst", 0), 0)
        _arm(_fs_state_key(str(entry.get("id") or ""), "lastDate"), now >= _daily_target(now, hour, minute))

    if changed:
        try:
            save_state(state)
        except Exception:
            pass


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    global _config_cache
    normalized = _normalize_config(config)
    with _lock:
        prev_cfg = dict(_config_cache)
    path = _config_path()
    _write_json_atomic(path, normalized)
    try:
        _apply_forward_scheduling(prev_cfg, normalized, datetime.now(IST))
    except Exception as exc:
        append_log(f"Forward-scheduling stamp warning: {exc}")
    with _lock:
        _config_cache = normalized
    enabled = [
        f"{s.get('taskKey')}:{s.get('id')}"
        for s in (normalized.get("taskSchedules") or [])
        if isinstance(s, dict) and s.get("enabled")
    ]
    filter_enabled = [s.get("id") for s in (normalized.get("filterSchedules") or []) if isinstance(s, dict) and s.get("enabled")]
    append_log(f"Config saved; enabled task schedules: {enabled or '(none)'}; filter schedules: {filter_enabled or '(none)'}")
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


def _state_last_scheduled_date_key(task_key: str) -> str:
    """Date of the last *scheduled* run — used for once-per-day due gating."""
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}ScheduledDate"


def _state_last_week_key(task_key: str) -> str:
    prefix = _task_state_prefix(task_key)
    return f"last{prefix}Week"


def _scheduled_fulfilled_today(task_key: str, state: dict[str, Any], today: str) -> bool:
    """True when today's scheduled slot is already satisfied.

    Manual Update-menu / Run-now must NOT cancel the scheduled slot for the day.
    Legacy state (pre-split) treated lastDate+trigger==scheduled as fulfillment.
    """
    if state.get(_state_last_scheduled_date_key(task_key)) == today:
        return True
    if state.get(_state_last_date_key(task_key)) != today:
        return False
    # Legacy: only a prior *scheduled* stamp blocks; manual leaves the slot open.
    return str(state.get(_state_last_trigger_key(task_key)) or "").lower() == "scheduled"



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


def _first_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """First calendar date in year/month whose weekday is Mon=0..Sun=6."""
    first = date(year, month, 1)
    delta = (int(weekday) - first.weekday()) % 7
    return first + timedelta(days=delta)


def _add_calendar_months(year: int, month: int, delta: int = 1) -> tuple[int, int]:
    month += delta
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    return year, month


def _next_monthly_target(
    now: datetime,
    weekday: int,
    hour: int,
    minute: int,
    last_date_iso: str | None,
) -> datetime | None:
    """Next first-weekday-of-month occurrence at hour:minute, skipping last_date."""
    y, m = now.year, now.month
    for _ in range(16):
        day = _first_weekday_of_month(y, m, weekday)
        day_iso = day.isoformat()
        target = datetime.combine(day, dtime(hour, minute), tzinfo=IST)
        if last_date_iso == day_iso:
            y, m = _add_calendar_months(y, m, 1)
            continue
        if day > now.date():
            return target
        if day == now.date():
            return now if now >= target else target
        y, m = _add_calendar_months(y, m, 1)
    return None


def _daily_target(now: datetime, hour: int, minute: int) -> datetime:
    return datetime.combine(now.date(), dtime(hour, minute), tzinfo=IST)


def _compute_next_daily(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return None
    schedule_type = str(task_cfg.get("scheduleType", "daily")).lower()
    if schedule_type == "weekly":
        return _compute_next_weekly(task_key, cfg, state, now)
    if schedule_type == "monthly":
        return _compute_next_monthly(task_key, cfg, state, now)
    hour = int(task_cfg.get("afterHourIst", 15))
    minute = int(task_cfg.get("afterMinuteIst", 30))
    target = _daily_target(now, hour, minute)
    today = now.date().isoformat()
    if _scheduled_fulfilled_today(task_key, state, today):
        tomorrow = now.date() + timedelta(days=1)
        nxt = datetime.combine(tomorrow, dtime(hour, minute), tzinfo=IST)
        return nxt.isoformat()
    if now >= target:
        return now.isoformat()
    return target.isoformat()


def _compute_next_monthly(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return None
    weekdays = _weekdays_from_task(task_cfg)
    if not weekdays:
        return None
    hour = int(task_cfg.get("afterHourIst", 15))
    minute = int(task_cfg.get("afterMinuteIst", 30))
    last = state.get(_state_last_date_key(task_key))
    nxt = _next_monthly_target(now, weekdays[0], hour, minute, last if isinstance(last, str) else None)
    return nxt.isoformat() if nxt else None


def _compute_next_weekly(task_key: str, cfg: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    task_cfg = cfg.get(task_key) or {}
    if not task_cfg.get("enabled"):
        return None
    hour = int(task_cfg.get("afterHourIst", 15))
    minute = int(task_cfg.get("afterMinuteIst", 30))
    weekdays = _weekdays_from_task(task_cfg)
    weekday_set = set(weekdays)
    today_iso = now.date().isoformat()
    ran_today = _scheduled_fulfilled_today(task_key, state, today_iso)
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
    # Only scheduled runs consume the once-per-day schedule slot.
    if str(trigger or "").lower() == "scheduled":
        state[_state_last_scheduled_date_key(task_key)] = now.date().isoformat()
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
    today = now.date().isoformat()
    if _scheduled_fulfilled_today(task_key, state, today):
        return False
    if schedule_type == "weekly":
        weekdays = _weekdays_from_task(task_cfg)
        if _ist_weekday(now) not in weekdays:
            return False
        return now >= target
    if schedule_type == "monthly":
        weekdays = _weekdays_from_task(task_cfg)
        if not weekdays:
            return False
        if now.date() != _first_weekday_of_month(now.year, now.month, weekdays[0]):
            return False
        return now >= target
    return now >= target


def _fs_state_key(entry_id: str, field: str) -> str:
    return f"filterSchedule:{entry_id}:{field}"


def _ts_state_key(entry_id: str, field: str) -> str:
    return f"taskSchedule:{entry_id}:{field}"


def _fs_incomplete(entry: dict[str, Any]) -> bool:
    """A schedule with no days (weekly/monthly), no data sources, or no timeframes must never run."""
    preset = entry.get("preset") if isinstance(entry.get("preset"), dict) else {}
    schedule_type = str(entry.get("scheduleType") or "weekly").lower()
    if schedule_type in ("weekly", "monthly") and not (entry.get("weekdaysIst") or []):
        return True
    if not (preset.get("keys") or []):
        return True
    if not (preset.get("timeframes") or []):
        return True
    return False


def _fs_is_due_now(entry: dict[str, Any], state: dict[str, Any], now: datetime) -> bool:
    if not entry.get("enabled"):
        return False
    if _fs_incomplete(entry):
        return False
    hour = int(entry.get("afterHourIst", 23))
    minute = int(entry.get("afterMinuteIst", 0))
    if state.get(_fs_state_key(str(entry.get("id")), "lastDate")) == now.date().isoformat():
        return False
    schedule_type = str(entry.get("scheduleType") or "weekly").lower()
    if schedule_type == "weekly" and _ist_weekday(now) not in set(_weekdays_from_task(entry)):
        return False
    if schedule_type == "monthly":
        weekdays = _weekdays_from_task(entry)
        if not weekdays:
            return False
        if now.date() != _first_weekday_of_month(now.year, now.month, weekdays[0]):
            return False
    return now >= _daily_target(now, hour, minute)


def _fs_next_run(entry: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    if not entry.get("enabled"):
        return None
    if _fs_incomplete(entry):
        return None
    hour = int(entry.get("afterHourIst", 23))
    minute = int(entry.get("afterMinuteIst", 0))
    last_date = state.get(_fs_state_key(str(entry.get("id")), "lastDate"))
    today = now.date().isoformat()
    schedule_type = str(entry.get("scheduleType") or "weekly").lower()
    target_today = _daily_target(now, hour, minute)

    if schedule_type == "monthly":
        weekdays = _weekdays_from_task(entry)
        if not weekdays:
            return None
        nxt = _next_monthly_target(
            now, weekdays[0], hour, minute, last_date if isinstance(last_date, str) else None
        )
        return nxt.isoformat() if nxt else None

    if schedule_type == "daily":
        if last_date != today:
            return (now if now >= target_today else target_today).isoformat()
        tomorrow = (now + timedelta(days=1)).date()
        return datetime.combine(tomorrow, dtime(hour, minute), tzinfo=IST).isoformat()

    weekday_set = set(_weekdays_from_task(entry))
    if _ist_weekday(now) in weekday_set and last_date != today:
        return (now if now >= target_today else target_today).isoformat()
    search_from = now + timedelta(days=1)
    for offset in range(14):
        day = search_from + timedelta(days=offset)
        if _ist_weekday(day) in weekday_set:
            return datetime.combine(day.date(), dtime(hour, minute), tzinfo=IST).isoformat()
    return None


def _start_filter_instance(entry: dict[str, Any]) -> bool:
    if not _filter_instance_start_fn:
        return False
    preset = dict(entry.get("preset") or {})
    preset["schedule_id"] = str(entry.get("id") or "").strip()
    return bool(_filter_instance_start_fn(preset))


def _maybe_run_filter_schedule(entry: dict[str, Any], state: dict[str, Any], now: datetime) -> dict[str, Any]:
    entry_id = str(entry.get("id") or "").strip()
    if not entry_id or not entry.get("enabled") or not _filter_instance_start_fn:
        return state
    waiting_key = f"filter:{entry_id}"

    if scheduler_is_blocked():
        _set_waiting(waiting_key, "snapshot_rebuild_hold")
        return state
    if not _fs_is_due_now(entry, state, now):
        return state

    _set_waiting(None, None)
    append_log(f"Starting scheduled filter schedule: {entry_id}")
    try:
        from server import admin_job_queue as ajq

        was_busy = ajq.slot_busy()
    except Exception:
        was_busy = bool(_job_running_fn and _job_running_fn())
    started = _start_filter_instance(entry)
    state = {**state, _fs_state_key(entry_id, "attemptAt"): now.isoformat()}
    if started:
        state[_fs_state_key(entry_id, "lastAt")] = now.isoformat()
        state[_fs_state_key(entry_id, "lastDate")] = now.date().isoformat()
        state[_fs_state_key(entry_id, "trigger")] = "scheduled"
        if was_busy:
            append_log(f"Scheduled filter schedule queued: {entry_id}")
            _set_waiting(waiting_key, "queued")
        else:
            append_log(f"Scheduled filter schedule started: {entry_id}")
    else:
        append_log(f"Skipped filter schedule {entry_id} — could not start")
        _set_waiting(waiting_key, "start_rejected")
    save_state(state)
    return state


def _ts_is_due_now(entry: dict[str, Any], state: dict[str, Any], now: datetime) -> bool:
    if not entry.get("enabled"):
        return False
    task_key = str(entry.get("taskKey") or "").strip()
    if task_key not in TASK_KEYS:
        return False
    hour = int(entry.get("afterHourIst", 15))
    minute = int(entry.get("afterMinuteIst", 30))
    entry_id = str(entry.get("id") or "").strip()
    if not entry_id:
        return False
    if state.get(_ts_state_key(entry_id, "lastDate")) == now.date().isoformat():
        return False
    schedule_type = str(entry.get("scheduleType") or "daily").lower()
    if schedule_type == "weekly" and _ist_weekday(now) not in set(_weekdays_from_task(entry)):
        return False
    if schedule_type == "monthly":
        weekdays = _weekdays_from_task(entry)
        if not weekdays:
            return False
        if now.date() != _first_weekday_of_month(now.year, now.month, weekdays[0]):
            return False
    return now >= _daily_target(now, hour, minute)


def _ts_next_run(entry: dict[str, Any], state: dict[str, Any], now: datetime) -> str | None:
    if not entry.get("enabled"):
        return None
    task_key = str(entry.get("taskKey") or "").strip()
    if task_key not in TASK_KEYS:
        return None
    hour = int(entry.get("afterHourIst", 15))
    minute = int(entry.get("afterMinuteIst", 30))
    entry_id = str(entry.get("id") or "").strip()
    if not entry_id:
        return None
    last_date = state.get(_ts_state_key(entry_id, "lastDate"))
    today = now.date().isoformat()
    schedule_type = str(entry.get("scheduleType") or "daily").lower()
    target_today = _daily_target(now, hour, minute)

    if schedule_type == "monthly":
        weekdays = _weekdays_from_task(entry)
        if not weekdays:
            return None
        nxt = _next_monthly_target(
            now, weekdays[0], hour, minute, last_date if isinstance(last_date, str) else None
        )
        return nxt.isoformat() if nxt else None

    if schedule_type == "daily":
        if last_date != today:
            return (now if now >= target_today else target_today).isoformat()
        tomorrow = (now + timedelta(days=1)).date()
        return datetime.combine(tomorrow, dtime(hour, minute), tzinfo=IST).isoformat()

    weekday_set = set(_weekdays_from_task(entry))
    if _ist_weekday(now) in weekday_set and last_date != today:
        return (now if now >= target_today else target_today).isoformat()
    search_from = now + timedelta(days=1)
    for offset in range(14):
        day = search_from + timedelta(days=offset)
        if _ist_weekday(day) in weekday_set:
            return datetime.combine(day.date(), dtime(hour, minute), tzinfo=IST).isoformat()
    return None


def _maybe_run_task_schedule(entry: dict[str, Any], state: dict[str, Any], now: datetime) -> dict[str, Any]:
    entry_id = str(entry.get("id") or "").strip()
    task_key = str(entry.get("taskKey") or "").strip()
    start_fn = _start_fns.get(task_key)
    if not entry_id or not entry.get("enabled") or not start_fn:
        return state
    waiting_key = f"task:{entry_id}"

    if scheduler_is_blocked():
        _set_waiting(waiting_key, "snapshot_rebuild_hold")
        return state
    if not _ts_is_due_now(entry, state, now):
        return state

    _set_waiting(None, None)
    append_log(f"Starting scheduled task schedule: {task_key} ({entry_id})")
    try:
        from server import admin_job_queue as ajq

        was_busy = ajq.slot_busy()
    except Exception:
        was_busy = bool(_job_running_fn and _job_running_fn())
    started = start_fn()
    state = {**state, _ts_state_key(entry_id, "attemptAt"): now.isoformat()}
    if started:
        state[_ts_state_key(entry_id, "lastAt")] = now.isoformat()
        state[_ts_state_key(entry_id, "lastDate")] = now.date().isoformat()
        state[_ts_state_key(entry_id, "trigger")] = "scheduled"
        # Mirror onto legacy singleton keys for Update-menu / older status readers.
        state = _record_task_started(state, task_key, now, "scheduled")
        if was_busy:
            append_log(f"Scheduled task schedule queued: {task_key} ({entry_id})")
            _set_waiting(waiting_key, "queued")
        else:
            append_log(f"Scheduled task schedule started: {task_key} ({entry_id})")
    else:
        append_log(f"Skipped task schedule {task_key} ({entry_id}) — could not start")
        _set_waiting(waiting_key, "start_rejected")
    save_state(state)
    return state


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

    _set_waiting(None, None)
    append_log(f"Starting scheduled task: {task_key}")
    try:
        from server import admin_job_queue as ajq

        was_busy = ajq.slot_busy()
    except Exception:
        was_busy = bool(_job_running_fn and _job_running_fn())
    started = start_fn()
    state = {**state, _state_last_attempt_key(task_key): now.isoformat()}
    if started:
        state = _record_task_started(state, task_key, now, "scheduled")
        if was_busy:
            append_log(f"Scheduled task queued: {task_key}")
            _set_waiting(task_key, "queued")
        else:
            append_log(f"Scheduled task started: {task_key}")
    else:
        append_log(f"Skipped {task_key} — could not start")
        _set_waiting(task_key, "start_rejected")
    save_state(state)
    return state


def get_status() -> dict[str, Any]:
    with _lock:
        cfg = dict(_config_cache)
    state = load_state()
    now = datetime.now(IST)
    running = bool(_job_running_fn()) if _job_running_fn else False
    next_runs: dict[str, str | None] = {}
    earliest_by_task: dict[str, str] = {}
    for entry in cfg.get("taskSchedules") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        entry_id = str(entry["id"])
        nxt = _ts_next_run(entry, state, now)
        next_runs[f"task:{entry_id}"] = nxt
        task_key = str(entry.get("taskKey") or "")
        if nxt and task_key:
            prev = earliest_by_task.get(task_key)
            if prev is None or nxt < prev:
                earliest_by_task[task_key] = nxt
    for key in TASK_KEYS:
        next_runs[key] = earliest_by_task.get(key)
    for entry in cfg.get("filterSchedules") or []:
        if isinstance(entry, dict) and entry.get("id"):
            next_runs[f"filter:{entry['id']}"] = _fs_next_run(entry, state, now)
    first_filter_key = next(
        (
            f"filter:{e['id']}"
            for e in (cfg.get("filterSchedules") or [])
            if isinstance(e, dict) and e.get("enabled")
        ),
        None,
    )
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
        "nextIndicatorAt": next_runs.get(first_filter_key) if first_filter_key else None,
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
    filter_instance_start_fn: Callable[[dict[str, Any]], bool] | None = None,
    job_running_fn: Callable[[], bool] | None = None,
    scheduler_blocked_fn: Callable[[], bool] | None = None,
    install_root: Path | None = None,
) -> None:
    global _start_fns, _filter_instance_start_fn, _job_running_fn, _install_root
    if filter_instance_start_fn is not None:
        _filter_instance_start_fn = filter_instance_start_fn
    if start_fns:
        _start_fns = dict(start_fns)
    else:
        _start_fns = {}
        if start_ohlcv_fn:
            _start_fns["ohlcv"] = start_ohlcv_fn
    if job_running_fn is not None:
        _job_running_fn = job_running_fn
    if scheduler_blocked_fn is not None:
        set_scheduler_blocked_fn(scheduler_blocked_fn)
    if install_root is not None:
        _install_root = Path(install_root).resolve()
    reload_config()


def _filter_schedule_by_id(cfg: dict[str, Any], entry_id: str) -> dict[str, Any] | None:
    for entry in cfg.get("filterSchedules") or []:
        if isinstance(entry, dict) and str(entry.get("id")) == str(entry_id):
            return entry
    return None


def _task_schedule_by_id(cfg: dict[str, Any], entry_id: str) -> dict[str, Any] | None:
    for entry in cfg.get("taskSchedules") or []:
        if isinstance(entry, dict) and str(entry.get("id")) == str(entry_id):
            return entry
    return None


def _run_task_instance_now(entry_id: str) -> dict[str, Any]:
    entry_id = str(entry_id or "").strip()
    cfg = reload_config()
    entry = _task_schedule_by_id(cfg, entry_id)
    if not entry:
        return {"ok": False, "error": f"Unknown task schedule: {entry_id}"}
    task_key = str(entry.get("taskKey") or "").strip()
    start_fn = _start_fns.get(task_key)
    if not start_fn:
        return {"ok": False, "error": f"Task not configured: {task_key}"}
    if scheduler_is_blocked():
        return {"ok": False, "error": "Scheduler paused for full indicator snapshot rebuild."}
    now = datetime.now(IST)
    append_log(f"Manual run: task schedule {task_key} ({entry_id})")
    try:
        from server import admin_job_queue as ajq

        was_busy = ajq.slot_busy()
    except Exception:
        was_busy = bool(_job_running_fn and _job_running_fn())
    started = start_fn()
    state = load_state()
    state = {**state, _ts_state_key(entry_id, "attemptAt"): now.isoformat()}
    queued = bool(started and was_busy)
    if started:
        state[_ts_state_key(entry_id, "lastAt")] = now.isoformat()
        state[_ts_state_key(entry_id, "lastDate")] = now.date().isoformat()
        state[_ts_state_key(entry_id, "trigger")] = "manual"
        state = _record_task_started(state, task_key, now, "manual")
        append_log(
            f"Manual task schedule {'queued' if queued else 'started'}: {task_key} ({entry_id})"
        )
        if queued:
            _set_waiting(f"task:{entry_id}", "queued")
    else:
        append_log(f"Manual run rejected for task schedule {task_key} ({entry_id})")
    save_state(state)
    return {
        "ok": bool(started),
        "task": f"task:{entry_id}",
        "started": bool(started),
        "queued": queued,
    }


def _run_filter_instance_now(entry_id: str) -> dict[str, Any]:
    entry_id = str(entry_id or "").strip()
    cfg = reload_config()
    entry = _filter_schedule_by_id(cfg, entry_id)
    if not entry:
        return {"ok": False, "error": f"Unknown filter schedule: {entry_id}"}
    if not _filter_instance_start_fn:
        return {"ok": False, "error": "Filter schedules are not configured."}
    if scheduler_is_blocked():
        return {"ok": False, "error": "Scheduler paused for full indicator snapshot rebuild."}
    now = datetime.now(IST)
    append_log(f"Manual run: filter schedule {entry_id}")
    try:
        from server import admin_job_queue as ajq

        was_busy = ajq.slot_busy()
    except Exception:
        was_busy = bool(_job_running_fn and _job_running_fn())
    started = _start_filter_instance(entry)
    state = load_state()
    state = {**state, _fs_state_key(entry_id, "attemptAt"): now.isoformat()}
    queued = bool(started and was_busy)
    if started:
        state[_fs_state_key(entry_id, "lastAt")] = now.isoformat()
        state[_fs_state_key(entry_id, "lastDate")] = now.date().isoformat()
        state[_fs_state_key(entry_id, "trigger")] = "manual"
        append_log(
            f"Manual filter schedule {'queued' if queued else 'started'}: {entry_id}"
        )
        if queued:
            _set_waiting(f"filter:{entry_id}", "queued")
    else:
        append_log(f"Manual run rejected for filter schedule {entry_id}")
    save_state(state)
    return {
        "ok": bool(started),
        "task": f"filter:{entry_id}",
        "started": bool(started),
        "queued": queued,
    }


def run_task_now(task_key: str) -> dict[str, Any]:
    """Manual Run now from Scheduler UI or API."""
    task_key = str(task_key or "").strip()
    if task_key.startswith("filter:"):
        return _run_filter_instance_now(task_key.split(":", 1)[1])
    if task_key.startswith("task:"):
        return _run_task_instance_now(task_key.split(":", 1)[1])
    if task_key not in TASK_KEYS and task_key not in _start_fns:
        return {"ok": False, "error": f"Unknown task: {task_key}"}
    start_fn = _start_fns.get(task_key)
    if not start_fn:
        return {"ok": False, "error": f"Task not configured: {task_key}"}
    if scheduler_is_blocked():
        return {"ok": False, "error": "Scheduler paused for full indicator snapshot rebuild."}
    now = datetime.now(IST)
    append_log(f"Manual run: {task_key}")
    try:
        from server import admin_job_queue as ajq

        was_busy = ajq.slot_busy()
    except Exception:
        was_busy = bool(_job_running_fn and _job_running_fn())
    started = start_fn()
    state = load_state()
    state = {**state, _state_last_attempt_key(task_key): now.isoformat()}
    queued = bool(started and was_busy)
    if started:
        state = _record_task_started(state, task_key, now, "manual")
        append_log(f"Manual task {'queued' if queued else 'started'}: {task_key}")
        if queued:
            _set_waiting(task_key, "queued")
    else:
        append_log(f"Manual run rejected for {task_key}")
    save_state(state)
    return {"ok": bool(started), "task": task_key, "started": bool(started), "queued": queued}


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
            # Prefer multi-instance taskSchedules; legacy singleton loop kept for
            # any leftover enabled stubs (normalize forces them off).
            for entry in cfg.get("taskSchedules") or []:
                if _job_running_fn and _job_running_fn():
                    break
                if isinstance(entry, dict):
                    state = _maybe_run_task_schedule(entry, state, now)
            for task_key in TASK_LOOP_ORDER:
                if _job_running_fn and _job_running_fn():
                    break
                state = _maybe_run_task(task_key, cfg, state, now)
            for entry in cfg.get("filterSchedules") or []:
                if _job_running_fn and _job_running_fn():
                    break
                if isinstance(entry, dict):
                    state = _maybe_run_filter_schedule(entry, state, now)
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
