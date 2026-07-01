"""Cooperative cancel for long-running admin background jobs."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

_cancel_event = threading.Event()


class JobCancelled(Exception):
    """Raised when the operator requests job cancellation."""


def clear_cancel() -> None:
    _cancel_event.clear()


def request_cancel() -> bool:
    """Signal cancellation. Returns False if no cancel was pending."""
    _cancel_event.set()
    return True


def is_cancel_requested() -> bool:
    return _cancel_event.is_set()


def raise_if_cancelled() -> None:
    if is_cancel_requested():
        raise JobCancelled()


def sleep_interruptible(
    seconds: float,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> None:
    """Sleep in 1s slices so cancellation can interrupt long NSE backoffs."""
    check = cancel_check or is_cancel_requested
    end = time.time() + max(0.0, float(seconds))
    while time.time() < end:
        if check():
            raise JobCancelled()
        time.sleep(min(1.0, end - time.time()))
