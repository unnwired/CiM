"""Registry of filter data sources and rebuild metadata for Admin selective rebuild."""
from __future__ import annotations

from typing import Any

INDICATOR_FAMILIES = frozenset({"ohlc", "ema", "macd", "stochrsi"})

RANGE_CHANNEL_CANONICAL_PARAMS: dict[str, Any] = {
    "timeframe": "3D",
    "lookback_bars": 18,
    "max_channel_width_pct": 20,
    "macd_allowed_stragglers": 2,
    "hist_flat_stragglers": 2,
    "spike_ratio": 1.8,
    "spike_min_delta": 0.8,
}

VOLUME_STATS_PERIODS = (10, 20, 30)

SNAPSHOT_TIMEFRAME_OPTIONS = (
    "30m", "4H", "1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W", "4W", "1M",
)


def normalize_snapshot_timeframe(raw: Any) -> str:
    """Canonicalize TF tokens. Keep ``30m`` lowercase so it never becomes month ``30M``."""
    tf = str(raw or "").strip()
    if not tf:
        return ""
    if tf.lower() == "30m":
        return "30m"
    return tf.upper()


_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "key": "price_ohlc",
        "label": "Price filter snapshots",
        "filter_types": ["price"],
        "engine": "indicator_snapshots",
        "families": ["ohlc"],
        "supports_timeframes": True,
        "default_timeframes": list(SNAPSHOT_TIMEFRAME_OPTIONS),
    },
    {
        "key": "ema",
        "label": "EMA",
        "filter_types": ["ema"],
        "engine": "indicator_snapshots",
        "families": ["ema"],
        "supports_timeframes": True,
        "default_timeframes": list(SNAPSHOT_TIMEFRAME_OPTIONS),
    },
    {
        "key": "macd",
        "label": "MACD + Histogram",
        "filter_types": ["macd", "macd_hist_chain"],
        "engine": "indicator_snapshots",
        "families": ["macd"],
        "supports_timeframes": True,
        "default_timeframes": list(SNAPSHOT_TIMEFRAME_OPTIONS),
    },
    {
        "key": "stochrsi",
        "label": "StochRSI",
        "filter_types": ["stochrsi"],
        "engine": "indicator_snapshots",
        "families": ["stochrsi"],
        "supports_timeframes": True,
        "default_timeframes": list(SNAPSHOT_TIMEFRAME_OPTIONS),
    },
    {
        "key": "avg_volume",
        "label": "Avg Volume",
        "filter_types": ["avg_volume"],
        "engine": "volume_stats",
        "families": [],
        "supports_timeframes": False,
        "default_timeframes": [],
    },
    {
        "key": "range_channel",
        "label": "Range Channel (3D defaults)",
        "filter_types": ["range_channel"],
        "engine": "range_channel_snapshots",
        "families": [],
        "supports_timeframes": True,
        "default_timeframes": ["3D"],
        "canonical_params": dict(RANGE_CHANNEL_CANONICAL_PARAMS),
    },
)


def list_registry_entries() -> list[dict[str, Any]]:
    return [dict(e) for e in _REGISTRY]


def registry_by_key() -> dict[str, dict[str, Any]]:
    return {str(e["key"]): e for e in _REGISTRY}


def resolve_keys(keys: list[str] | None) -> list[dict[str, Any]]:
    by_key = registry_by_key()
    if not keys:
        return list_registry_entries()
    out = []
    for k in keys:
        key = str(k or "").strip().lower()
        if key in by_key:
            out.append(by_key[key])
    return out


def indicator_families_for_keys(keys: list[str]) -> frozenset[str]:
    fam: set[str] = set()
    by_key = registry_by_key()
    for k in keys:
        entry = by_key.get(str(k).strip().lower())
        if not entry or entry.get("engine") != "indicator_snapshots":
            continue
        for f in entry.get("families") or []:
            if f in INDICATOR_FAMILIES:
                fam.add(f)
    return frozenset(fam)


def keys_for_engine(keys: list[str], engine: str) -> list[str]:
    by_key = registry_by_key()
    return [
        str(k).strip().lower()
        for k in keys
        if by_key.get(str(k).strip().lower(), {}).get("engine") == engine
    ]


def public_options_payload() -> dict[str, Any]:
    items = []
    for e in _REGISTRY:
        items.append({
            "key": e["key"],
            "label": e["label"],
            "filter_types": list(e.get("filter_types") or []),
            "engine": e["engine"],
            "supports_timeframes": bool(e.get("supports_timeframes")),
            "default_timeframes": list(e.get("default_timeframes") or []),
            "canonical_params": dict(e["canonical_params"]) if e.get("canonical_params") else None,
        })
    return {
        "items": items,
        "snapshot_timeframes": list(SNAPSHOT_TIMEFRAME_OPTIONS),
        "volume_stats_periods": list(VOLUME_STATS_PERIODS),
    }
