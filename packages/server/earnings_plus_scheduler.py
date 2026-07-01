"""
Work-hours background Earnings+ cache warm (08:00–20:00 IST).

Runs incremental refresh while the backend is up; persists last-run status for UI.
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
WARM_WINDOW_START = dtime(8, 0)
WARM_WINDOW_END = dtime(20, 0)
STARTUP_DELAY_SEC_MIN = 120
STARTUP_DELAY_SEC_MAX = 300
INTERVAL_SEC_MIN = 45 * 60
INTERVAL_SEC_MAX = 90 * 60
MIN_GAP_BETWEEN_RUNS_SEC = 30 * 60

_run_refresh: Optional[Callable[..., None]] = None
_job_running: Optional[Callable[[], bool]] = None
_data_dir: Optional[Path] = None
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_last_attempt_at: Optional[datetime] = None


def _warm_log_path() -> Path:
    base = _data_dir or get_data_dir()
    return base / "earnings_plus_warm.json"


def read_warm_log() -> dict[str, Any]:
    path = _warm_log_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_warm_log(record: dict[str, Any]) -> None:
    path = _warm_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)


def _in_warm_window(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(IST)
    t = now.timetz().replace(tzinfo=None) if hasattr(now, "timetz") else now.time()
    return WARM_WINDOW_START <= t < WARM_WINDOW_END


def _seconds_until_window_opens(now: datetime) -> float:
    if _in_warm_window(now):
        return 0.0
    today_open = datetime.combine(now.date(), WARM_WINDOW_START, tzinfo=IST)
    if now.time() >= WARM_WINDOW_END:
        today_open += timedelta(days=1)
    return max(60.0, (today_open - now).total_seconds())


def _next_interval_sec() -> float:
    return float(random.randint(INTERVAL_SEC_MIN, INTERVAL_SEC_MAX))


def _startup_delay_sec() -> float:
    return float(random.randint(STARTUP_DELAY_SEC_MIN, STARTUP_DELAY_SEC_MAX))


def configure(
    *,
    run_refresh_fn: Callable[..., None],
    job_running_fn: Callable[[], bool],
    data_dir: Path,
) -> None:
    global _run_refresh, _job_running, _data_dir
    _run_refresh = run_refresh_fn
    _job_running = job_running_fn
    _data_dir = data_dir


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_scheduler_loop, name="earnings-plus-warm", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def _maybe_run(trigger: str) -> None:
    global _last_attempt_at
    if _run_refresh is None or _job_running is None:
        return
    now = datetime.now(IST)
    if not _in_warm_window(now):
        return
    with _lock:
        if _job_running():
            return
        if _last_attempt_at is not None:
            elapsed = (now - _last_attempt_at).total_seconds()
            if elapsed < MIN_GAP_BETWEEN_RUNS_SEC:
                return
        _last_attempt_at = now

    y, m = now.year, now.month
    try:
        _run_refresh(y, m, force=False, only_incomplete=False, quiet=True, trigger=trigger)
    except Exception:
        pass


def _scheduler_loop() -> None:
    delay = _startup_delay_sec()
    while not _stop.wait(delay):
        delay = _next_interval_sec()
        now = datetime.now(IST)
        if not _in_warm_window(now):
            delay = max(delay, _seconds_until_window_opens(now))
            continue
        _maybe_run("scheduled")


def run_startup_warm_once() -> None:
    """First warm after backend boot (jittered), only inside work-hours window."""

    def _go() -> None:
        time_module.sleep(_startup_delay_sec())
        if _stop.is_set():
            return
        _maybe_run("startup")

    threading.Thread(target=_go, name="earnings-plus-warm-startup", daemon=True).start()
