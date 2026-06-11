"""Thread-safe TTL caches for chart and filter endpoints."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

from cachetools import TTLCache

CHART_CACHE_SCHEMA = 3

CACHE_PROFILE_NORMAL = {
    "chart_ttl": 300,
    "chart_max_entries": 300,
    "filter_ttl": 120,
    "filter_max_entries": 500,
}
CACHE_PROFILE_AGGRESSIVE = {
    "chart_ttl": 1800,
    "chart_max_entries": 1200,
    "filter_ttl": 600,
    "filter_max_entries": 2000,
}


class AppCaches:
    def __init__(self) -> None:
        self._chart_lock = threading.Lock()
        self._filter_lock = threading.Lock()
        self._snapshot_lock = threading.Lock()
        self.aggressive = False
        self.chart_ttl = CACHE_PROFILE_NORMAL["chart_ttl"]
        self.chart_max_entries = CACHE_PROFILE_NORMAL["chart_max_entries"]
        self.filter_ttl = CACHE_PROFILE_NORMAL["filter_ttl"]
        self.filter_max_entries = CACHE_PROFILE_NORMAL["filter_max_entries"]
        self._chart_cache: TTLCache = self._new_chart_cache()
        self._filter_cache: TTLCache = self._new_filter_cache()
        self._snapshot_filter_coverage_cache: dict = {}

    def _new_chart_cache(self) -> TTLCache:
        return TTLCache(maxsize=max(1, self.chart_max_entries), ttl=max(1, self.chart_ttl))

    def _new_filter_cache(self) -> TTLCache:
        return TTLCache(maxsize=max(1, self.filter_max_entries), ttl=max(1, self.filter_ttl))

    def set_mode(self, aggressive: bool) -> None:
        profile = CACHE_PROFILE_AGGRESSIVE if aggressive else CACHE_PROFILE_NORMAL
        self.aggressive = bool(aggressive)
        self.chart_ttl = int(profile["chart_ttl"])
        self.chart_max_entries = int(profile["chart_max_entries"])
        self.filter_ttl = int(profile["filter_ttl"])
        self.filter_max_entries = int(profile["filter_max_entries"])
        with self._chart_lock:
            self._chart_cache = self._new_chart_cache()
        with self._filter_lock:
            self._filter_cache = self._new_filter_cache()
        with self._snapshot_lock:
            self._snapshot_filter_coverage_cache = {}

    def chart_key(self, symbol: str, timeframe: str, ema_periods: list) -> tuple:
        return (symbol.upper(), timeframe, tuple(sorted(ema_periods)), CHART_CACHE_SCHEMA)

    def get_chart(self, symbol: str, timeframe: str, ema_periods: list) -> Optional[Any]:
        key = self.chart_key(symbol, timeframe, ema_periods)
        with self._chart_lock:
            return self._chart_cache.get(key)

    def set_chart(self, symbol: str, timeframe: str, ema_periods: list, data: Any) -> None:
        key = self.chart_key(symbol, timeframe, ema_periods)
        with self._chart_lock:
            self._chart_cache[key] = data

    def invalidate_chart(self, symbol: Optional[str] = None) -> None:
        with self._chart_lock:
            if symbol is None:
                self._chart_cache.clear()
            else:
                sym_u = symbol.upper()
                for key in list(self._chart_cache.keys()):
                    if isinstance(key, tuple) and key and key[0] == sym_u:
                        self._chart_cache.pop(key, None)

    def filter_key(self, endpoint: str, body: dict) -> tuple:
        normalized = _normalize_filter_body(body)
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return (endpoint, payload)

    def get_filter(self, endpoint: str, body: dict) -> Optional[Any]:
        key = self.filter_key(endpoint, body)
        with self._filter_lock:
            return self._filter_cache.get(key)

    def set_filter(self, endpoint: str, body: dict, data: Any) -> None:
        key = self.filter_key(endpoint, body)
        with self._filter_lock:
            self._filter_cache[key] = data

    def invalidate_filters(self) -> None:
        with self._filter_lock:
            self._filter_cache.clear()
        with self._snapshot_lock:
            self._snapshot_filter_coverage_cache = {}

    def get_snapshot_coverage(self, timeframe: str) -> Optional[dict]:
        with self._snapshot_lock:
            return self._snapshot_filter_coverage_cache.get(timeframe)

    def set_snapshot_coverage(self, timeframe: str, ok: bool) -> None:
        with self._snapshot_lock:
            self._snapshot_filter_coverage_cache[timeframe] = {"ts": time.time(), "ok": ok}

    @property
    def chart_entries(self) -> int:
        with self._chart_lock:
            return len(self._chart_cache)

    @property
    def filter_entries(self) -> int:
        with self._filter_lock:
            return len(self._filter_cache)


def _normalize_filter_body(body: dict) -> dict:
    if not isinstance(body, dict):
        return {}
    b = dict(body)
    if isinstance(b.get("market_sectors"), list):
        b["market_sectors"] = sorted([str(x).strip() for x in b["market_sectors"] if str(x).strip()])
    return b


caches = AppCaches()
