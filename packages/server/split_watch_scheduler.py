"""
Background stock-split scan (08:00–20:00 IST) and auto-apply of pending events.
"""

from __future__ import annotations

import json
import random
import threading
import time as time_module
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from server.core.install_root import get_data_dir

IST = ZoneInfo("Asia/Kolkata")
WATCH_WINDOW_START = dtime(8, 0)
WATCH_WINDOW_END = dtime(20, 0)
STARTUP_DELAY_SEC_MIN = 120
STARTUP_DELAY_SEC_MAX = 300
INTERVAL_SEC_MIN = 45 * 60
INTERVAL_SEC_MAX = 90 * 60
MIN_GAP_BETWEEN_SCANS_SEC = 30 * 60

_scan_fn: Optional[Callable[..., dict[str, Any]]] = None
_apply_fn: Optional[Callable[..., None]] = None
_job_running_fn: Optional[Callable[[], bool]] = None
_scan_busy_fn: Optional[Callable[[], bool]] = None
_data_dir: Optional[Path] = None
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_last_scan_at: Optional[datetime] = None


def _watch_log_path() -> Path:
    base = _data_dir or get_data_dir()
    return base / "split_watch.json"


def read_watch_log() -> dict[str, Any]:
    path = _watch_log_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_watch_log(record: dict[str, Any]) -> None:
    path = _watch_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**read_watch_log(), **record}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def _in_watch_window(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(IST)
    t = now.timetz().replace(tzinfo=None) if hasattr(now, "timetz") else now.time()
    return WATCH_WINDOW_START <= t < WATCH_WINDOW_END


def _seconds_until_window_opens(now: datetime) -> float:
    if _in_watch_window(now):
        return 0.0
    today_open = datetime.combine(now.date(), WATCH_WINDOW_START, tzinfo=IST)
    if now.time() >= WATCH_WINDOW_END:
        today_open += timedelta(days=1)
    return max(60.0, (today_open - now).total_seconds())


def _next_interval_sec() -> float:
    return float(random.randint(INTERVAL_SEC_MIN, INTERVAL_SEC_MAX))


def _startup_delay_sec() -> float:
    return float(random.randint(STARTUP_DELAY_SEC_MIN, STARTUP_DELAY_SEC_MAX))


def configure(
    *,
    scan_fn: Callable[..., dict[str, Any]],
    apply_fn: Callable[..., None],
    job_running_fn: Callable[[], bool],
    scan_busy_fn: Callable[[], bool],
    data_dir: Path,
) -> None:
    global _scan_fn, _apply_fn, _job_running_fn, _scan_busy_fn, _data_dir
    _scan_fn = scan_fn
    _apply_fn = apply_fn
    _job_running_fn = job_running_fn
    _scan_busy_fn = scan_busy_fn
    _data_dir = data_dir


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_scheduler_loop, name="split-watch", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def _maybe_run_cycle(trigger: str) -> None:
    global _last_scan_at
    if _scan_fn is None or _apply_fn is None or _job_running_fn is None:
        return
    now = datetime.now(IST)
    if not _in_watch_window(now):
        return
    if _scan_busy_fn and _scan_busy_fn():
        return
    with _lock:
        if _job_running_fn():
            write_watch_log(
                {
                    "last_skip_at": now.isoformat(),
                    "last_skip_reason": "admin_job_running",
                    "trigger": trigger,
                }
            )
            return
        if _last_scan_at is not None:
            elapsed = (now - _last_scan_at).total_seconds()
            if elapsed < MIN_GAP_BETWEEN_SCANS_SEC:
                return
        _last_scan_at = now

    summary: dict[str, Any] = {"trigger": trigger, "last_scan_at": now.isoformat()}
    try:
        summary.update(_scan_fn(trigger=trigger, quiet=True))
    except Exception as e:
        summary["scan_error"] = str(e)
        write_watch_log(summary)
        return

    write_watch_log(summary)
    pending_new = int(summary.get("pending_new") or 0)
    pending_total = int(summary.get("pending_count") or 0)
    if pending_new <= 0 and pending_total <= 0:
        return
    if _job_running_fn():
        write_watch_log(
            {
                "last_apply_deferred_at": datetime.now(IST).isoformat(),
                "pending_count": pending_total,
            }
        )
        return
    try:
        _apply_fn(trigger=trigger, quiet=True, auto=True)
    except Exception as e:
        write_watch_log({"last_apply_error": str(e), "trigger": trigger})


def _scheduler_loop() -> None:
    delay = _startup_delay_sec()
    while not _stop.wait(delay):
        delay = _next_interval_sec()
        now = datetime.now(IST)
        if not _in_watch_window(now):
            delay = max(delay, _seconds_until_window_opens(now))
            continue
        _maybe_run_cycle("scheduled")


def run_startup_scan_once() -> None:
    def _go() -> None:
        time_module.sleep(_startup_delay_sec())
        if _stop.is_set():
            return
        _maybe_run_cycle("startup")

    threading.Thread(target=_go, name="split-watch-startup", daemon=True).start()
