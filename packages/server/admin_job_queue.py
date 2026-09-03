"""
FIFO admin job queue — one heavy job at a time; extras wait then run.

Coalesces by job key (second ohlcv while one is queued does not duplicate).
Cancel running is separate (admin_job_control); this module only manages the backlog.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

Source = Literal["manual", "scheduled"]

_lock = threading.RLock()
_queue: list["QueuedJob"] = []
_pumping = False
_reserved = False  # slot claimed between submit/on_job_idle and set_job
_is_running_fn: Optional[Callable[[], bool]] = None


@dataclass
class QueuedJob:
    id: str
    key: str
    label: str
    source: Source
    starter: Callable[[], None]
    coalesce_key: str = ""

    def __post_init__(self) -> None:
        if not self.coalesce_key:
            self.coalesce_key = self.key


def configure(*, is_running_fn: Callable[[], bool]) -> None:
    global _is_running_fn
    with _lock:
        _is_running_fn = is_running_fn


def reset_for_tests() -> None:
    """Clear queue state (unit tests only)."""
    global _pumping, _reserved
    with _lock:
        _queue.clear()
        _pumping = False
        _reserved = False


def _job_running() -> bool:
    if _is_running_fn is None:
        return False
    try:
        return bool(_is_running_fn())
    except Exception:
        return False


def _slot_busy() -> bool:
    return _job_running() or _reserved


def note_job_started() -> None:
    """Call from set_job once running=True owns the slot."""
    global _reserved
    with _lock:
        _reserved = False


def snapshot() -> list[dict[str, Any]]:
    with _lock:
        return [
            {
                "id": j.id,
                "key": j.key,
                "label": j.label,
                "source": j.source,
                "position": i + 1,
            }
            for i, j in enumerate(_queue)
        ]


def slot_busy() -> bool:
    """True if a job is running or a start is reserved."""
    with _lock:
        return _slot_busy()


def submit(
    key: str,
    starter: Callable[[], None],
    *,
    label: str = "",
    source: Source = "manual",
    coalesce_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Start immediately if the slot is free; otherwise enqueue (coalesce by key).

    starter must start the background work (typically spawn a daemon thread)
    and must not block until the job finishes.
    """
    global _reserved
    key = str(key or "").strip() or "job"
    label = str(label or key).strip() or key
    ck = str(coalesce_key or key).strip() or key

    with _lock:
        if _slot_busy():
            for existing in _queue:
                if existing.coalesce_key == ck:
                    existing.label = label
                    existing.source = source
                    existing.starter = starter
                    existing.key = key
                    pos = _queue.index(existing) + 1
                    return {
                        "status": "queued",
                        "job": key,
                        "label": label,
                        "source": source,
                        "id": existing.id,
                        "position": pos,
                        "coalesced": True,
                        "queue": snapshot(),
                    }

            job = QueuedJob(
                id=uuid.uuid4().hex[:12],
                key=key,
                label=label,
                source=source,
                starter=starter,
                coalesce_key=ck,
            )
            _queue.append(job)
            return {
                "status": "queued",
                "job": key,
                "label": label,
                "source": source,
                "id": job.id,
                "position": len(_queue),
                "coalesced": False,
                "queue": snapshot(),
            }

        _reserved = True

    try:
        starter()
    except Exception:
        with _lock:
            _reserved = False
        raise

    return {
        "status": "started",
        "job": key,
        "label": label,
        "source": source,
        "position": 0,
        "queue": snapshot(),
    }


def cancel_queued(entry_id: str) -> bool:
    """Remove one waiting entry. Does not touch the running job."""
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    with _lock:
        for i, j in enumerate(_queue):
            if j.id == eid:
                _queue.pop(i)
                return True
    return False


def clear_queue() -> int:
    """Drop all waiting entries. Returns count removed."""
    with _lock:
        n = len(_queue)
        _queue.clear()
        return n


def on_job_idle() -> None:
    """
    Called after finish_job / fail_job / cancel_job sets running=False.
    Starts the next queued job if the slot is still free.
    """
    global _pumping, _reserved
    with _lock:
        if _pumping:
            return
        _reserved = False
        if _job_running():
            return
        if not _queue:
            return
        _pumping = True
        nxt = _queue.pop(0)
        _reserved = True

    try:
        nxt.starter()
    except Exception:
        with _lock:
            _pumping = False
            _reserved = False
        on_job_idle()
        return
    finally:
        with _lock:
            _pumping = False
