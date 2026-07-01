"""
Coordinate full indicator snapshot rebuilds with live watchdog heal and admin scheduler.

- Pauses live watchdog (stop loop) on showcase host before full rebuild.
- Writes a hold file so heal scripts skip restarts if watchdog is still running.
- Blocks admin scheduler tasks while hold is active.
"""
from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from server.core.install_root import get_install_root

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_IMMINENT_MINUTES = 20
_HOLD_FILENAME = "snapshot-rebuild-hold.json"
_PAUSE_FILENAME = "live-watchdog-pause.json"

_active = threading.Lock()
_hold_count = 0


def _root() -> Path:
    return get_install_root()


def hold_path() -> Path:
    return _root() / "runtime" / "logs" / _HOLD_FILENAME


def watchdog_pause_path() -> Path:
    return _root() / "runtime" / "logs" / _PAUSE_FILENAME


def is_showcase_install() -> bool:
    try:
        from server.product_config import is_showcase_host

        return is_showcase_host(_root())
    except Exception:
        return (_root() / "config" / ".cim-showcase-host").is_file()


def is_hold_active() -> bool:
    path = hold_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        until_raw = data.get("until")
        if until_raw:
            until = datetime.fromisoformat(str(until_raw))
            if until.tzinfo is None:
                until = until.replace(tzinfo=IST)
            if datetime.now(IST) > until.astimezone(IST):
                return False
        return bool(data.get("active"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return path.is_file()


def _write_hold(*, reason: str, hours: int = 6) -> None:
    log_dir = hold_path().parent
    log_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(IST)
    payload = {
        "active": True,
        "reason": reason,
        "startedAt": now.isoformat(),
        "until": (now + timedelta(hours=hours)).isoformat(),
        "watchdogPaused": True,
    }
    hold_path().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _clear_hold_files() -> None:
    for path in (hold_path(), watchdog_pause_path()):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_watchdog_pause(*, reason: str, hours: int = 6) -> None:
    log_dir = watchdog_pause_path().parent
    log_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(IST)
    payload = {
        "reason": reason,
        "pausedAt": now.isoformat(),
        "until": (now + timedelta(hours=hours)).isoformat(),
    }
    watchdog_pause_path().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_powershell(script: Path, web_root: Path) -> bool:
    if not script.is_file():
        return False
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-WebRoot",
                str(web_root),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def pause_live_watchdog() -> bool:
    """Stop background live watchdog loop (live install only)."""
    if not is_showcase_install():
        return False
    root = _root()
    _write_watchdog_pause(reason="full_indicator_snapshot_rebuild")
    script = root / "scripts" / "Stop-CiMLiveWatchdog.ps1"
    if not script.is_file():
        script = Path(__file__).resolve().parents[2] / "scripts" / "Stop-CiMLiveWatchdog.ps1"
    return _run_powershell(script, root)


def resume_live_watchdog() -> bool:
    """Restart live watchdog loop after rebuild completes."""
    if not is_showcase_install():
        return False
    root = _root()
    try:
        watchdog_pause_path().unlink(missing_ok=True)
    except OSError:
        pass
    script = root / "scripts" / "Start-CiMLiveWatchdog.ps1"
    if not script.is_file():
        script = Path(__file__).resolve().parents[2] / "scripts" / "Start-CiMLiveWatchdog.ps1"
    return _run_powershell(script, root)


def acquire_full_rebuild_hold(*, reason: str = "full_indicator_snapshot_rebuild") -> None:
    global _hold_count
    with _active:
        _hold_count += 1
        if _hold_count > 1:
            return
        _write_hold(reason=reason)
        pause_live_watchdog()


def release_full_rebuild_hold() -> None:
    global _hold_count
    with _active:
        if _hold_count <= 0:
            _hold_count = 0
            _clear_hold_files()
            return
        _hold_count -= 1
        if _hold_count > 0:
            return
        _clear_hold_files()
        resume_live_watchdog()


def scheduler_is_frozen() -> bool:
    return _hold_count > 0 or is_hold_active()


def collect_scheduler_conflicts(
    *,
    job_running_fn: Callable[[], bool],
    imminent_minutes: int = DEFAULT_IMMINENT_MINUTES,
) -> list[dict[str, Any]]:
    """Tasks due now, job already running, or daily/weekly run within imminent window."""
    import admin_job_scheduler as ajs

    issues: list[dict[str, Any]] = []
    if job_running_fn():
        issues.append({"type": "job_running", "message": "An admin job is already running."})

    cfg = ajs.load_config()
    state = ajs.load_state()
    now = datetime.now(IST)
    horizon = now + timedelta(minutes=max(1, int(imminent_minutes)))

    for task_key in ajs.TASK_KEYS:
        task_cfg = cfg.get(task_key) or {}
        if not task_cfg.get("enabled"):
            continue
        if ajs.task_is_due_now(task_key, cfg, state, now):
            issues.append({
                "type": "due_now",
                "task": task_key,
                "message": f"Scheduled task '{task_key}' is due now.",
            })
            continue
        nxt_raw = ajs.compute_next_run(task_key, cfg, state, now)
        if not nxt_raw:
            continue
        try:
            nxt = datetime.fromisoformat(str(nxt_raw))
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=IST)
            nxt = nxt.astimezone(IST)
        except (TypeError, ValueError):
            continue
        if nxt > horizon:
            continue
        if task_key == "ohlcv" and str(task_cfg.get("scheduleType", "interval")).lower() == "interval":
            continue
        issues.append({
            "type": "imminent",
            "task": task_key,
            "at": nxt.isoformat(),
            "minutes": max(0, int((nxt - now).total_seconds() // 60)),
            "message": f"Scheduled task '{task_key}' is due within {imminent_minutes} minutes.",
        })
    return issues
