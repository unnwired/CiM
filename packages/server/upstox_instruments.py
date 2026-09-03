"""Upstox BOD instrument map — trading_symbol / index name → instrument_key."""
from __future__ import annotations

import gzip
import json
import threading
import time as time_module
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

IST = timezone(timedelta(hours=5, minutes=30))

BOD_GZ_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
MAP_FILENAME = "upstox_instrument_map.json"
DOWNLOAD_TIMEOUT_SEC = 180.0

# NSE cash equities we chart/scrape. EQ-only maps miss Trade-for-Trade (BE/BZ) and SME (SM/ST/SZ).
_NSE_EQ_CASH_TYPES = frozenset({"EQ", "BE", "BZ", "SM", "ST", "SZ"})
# Prefer rolling EQ over surveillance/T2T duplicates of the same trading symbol.
_NSE_EQ_TYPE_PRIORITY = {"EQ": 0, "BE": 1, "BZ": 2, "SM": 3, "ST": 4, "SZ": 5}

def _cim_index_to_upstox_name() -> dict[str, str]:
    try:
        from server.cim_index_catalog import upstox_name_map

        return upstox_name_map()
    except Exception:
        return {}


# Lazily refreshed from cim_index_catalog (all chartable NSE indices).
_CIM_INDEX_TO_UPSTOX_NAME: dict[str, str] = {}

_lock = threading.Lock()
_data_dir: Optional[Path] = None
_memory_cache: dict[str, Any] = {"loaded_at": 0.0, "map": None}


def configure_paths(*, data_dir: Path) -> None:
    global _data_dir
    _data_dir = Path(data_dir)


def _map_path() -> Path:
    root = _data_dir or Path(__file__).resolve().parents[2] / "data"
    return root / MAP_FILENAME


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _normalize_index_name(name: str) -> str:
    return " ".join(str(name or "").strip().split()).title()


def _session_day_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _map_stale(meta: dict[str, Any]) -> bool:
    built_for = str(meta.get("session_day") or "").strip()
    return built_for != _session_day_ist()


def _build_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    symbols: dict[str, str] = {}
    symbol_types: dict[str, str] = {}
    index_names: dict[str, str] = {}
    type_counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        segment = str(row.get("segment") or "").strip()
        key = str(row.get("instrument_key") or "").strip()
        if not key:
            continue
        if segment == "NSE_EQ":
            itype = str(row.get("instrument_type") or "").strip().upper()
            if itype not in _NSE_EQ_CASH_TYPES:
                continue
            sym = _normalize_symbol(row.get("trading_symbol"))
            if not sym:
                continue
            type_counts[itype] = type_counts.get(itype, 0) + 1
            prev_t = symbol_types.get(sym)
            if prev_t is not None:
                if _NSE_EQ_TYPE_PRIORITY.get(itype, 99) >= _NSE_EQ_TYPE_PRIORITY.get(prev_t, 99):
                    continue
            symbols[sym] = key
            symbol_types[sym] = itype
        elif segment == "NSE_INDEX":
            name = str(row.get("name") or "").strip()
            if name:
                index_names[_normalize_index_name(name)] = key
                trading = _normalize_symbol(row.get("trading_symbol"))
                if trading and trading not in symbols:
                    symbols[trading] = key
    return {
        "session_day": _session_day_ist(),
        "built_at": datetime.now(IST).isoformat(),
        "symbols": symbols,
        "index_names": index_names,
        "equity_count": len(symbols),
        "index_count": len(index_names),
        "included_equity_types": sorted(_NSE_EQ_CASH_TYPES),
        "equity_type_counts": type_counts,
    }


def _download_bod_rows() -> list[dict[str, Any]]:
    r = requests.get(BOD_GZ_URL, timeout=DOWNLOAD_TIMEOUT_SEC)
    r.raise_for_status()
    raw = gzip.decompress(r.content)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Upstox BOD JSON root is not a list")
    return data


def _save_map(meta: dict[str, Any]) -> None:
    path = _map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    tmp.replace(path)


def _load_map_file() -> Optional[dict[str, Any]]:
    path = _map_path()
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else None
    except Exception:
        return None


def refresh_instrument_map(*, force: bool = False) -> dict[str, Any]:
    """Download BOD instruments when missing or stale (once per IST session day)."""
    with _lock:
        if not force:
            cached = _memory_cache.get("map")
            if isinstance(cached, dict) and not _map_stale(cached) and _map_has_cash_series(cached):
                return cached
            file_map = _load_map_file()
            if isinstance(file_map, dict) and not _map_stale(file_map) and _map_has_cash_series(file_map):
                _memory_cache["map"] = file_map
                _memory_cache["loaded_at"] = time_module.time()
                return file_map

        rows = _download_bod_rows()
        meta = _build_map_from_rows(rows)
        _save_map(meta)
        _memory_cache["map"] = meta
        _memory_cache["loaded_at"] = time_module.time()
        return meta


def instrument_map(*, allow_refresh: bool = True) -> dict[str, Any]:
    with _lock:
        cached = _memory_cache.get("map")
        if isinstance(cached, dict) and not _map_stale(cached) and _map_has_cash_series(cached):
            return cached
    file_map = _load_map_file()
    if isinstance(file_map, dict) and not _map_stale(file_map) and _map_has_cash_series(file_map):
        with _lock:
            _memory_cache["map"] = file_map
        return file_map
    if allow_refresh:
        # Force rebuild when on-disk map is EQ-only (pre-BE fix) even on same session day.
        force = isinstance(file_map, dict) and not _map_has_cash_series(file_map)
        return refresh_instrument_map(force=force)
    return {"symbols": {}, "index_names": {}}


def _map_has_cash_series(meta: dict[str, Any]) -> bool:
    """True when map metadata includes Trade-for-Trade / SME cash series (not EQ-only)."""
    included = meta.get("included_equity_types")
    if isinstance(included, list) and included:
        return "BE" in {str(x).upper() for x in included}
    # Legacy maps omit the field — treat as incomplete so we rebuild once.
    return False


def resolve_equity_key(symbol: str) -> Optional[str]:
    sym = _normalize_symbol(symbol)
    if not sym or sym.startswith("^") or sym.startswith("NSE:"):
        return None
    try:
        from server.cim_index_catalog import is_cim_index_symbol

        if is_cim_index_symbol(sym):
            return None
    except Exception:
        if sym.startswith("NIFTY_") or sym == "INDIA_VIX":
            return None
    if sym.endswith(".NS"):
        sym = sym[:-3]
    meta = instrument_map()
    return (meta.get("symbols") or {}).get(sym)


def resolve_index_key(
    symbol: str,
    *,
    display_name: Optional[str] = None,
) -> Optional[str]:
    global _CIM_INDEX_TO_UPSTOX_NAME
    if not _CIM_INDEX_TO_UPSTOX_NAME:
        _CIM_INDEX_TO_UPSTOX_NAME = _cim_index_to_upstox_name()

    sym = _normalize_symbol(symbol)
    raw_sym = str(symbol or "").strip()
    upstox_name = (
        _CIM_INDEX_TO_UPSTOX_NAME.get(sym)
        or _CIM_INDEX_TO_UPSTOX_NAME.get(raw_sym)
        or _CIM_INDEX_TO_UPSTOX_NAME.get(raw_sym.upper())
    )
    if not upstox_name and display_name:
        upstox_name = str(display_name).strip()
        if upstox_name.startswith("NSE:"):
            upstox_name = upstox_name[4:].replace("_", " ")
    if not upstox_name:
        return None
    meta = instrument_map()
    index_names = meta.get("index_names") or {}
    key = index_names.get(_normalize_index_name(upstox_name))
    if key:
        return key
    # Some DB names are already title-cased NSE labels.
    for candidate in (upstox_name, upstox_name.upper(), upstox_name.title()):
        key = index_names.get(_normalize_index_name(candidate))
        if key:
            return key
    return None


def resolve_instrument_keys(
    symbols: list[str],
    *,
    index_names: Optional[dict[str, str]] = None,
) -> tuple[dict[str, str], list[str]]:
    """
    Map CiM symbols → Upstox instrument_key.
    Returns (symbol_to_key, unresolved_symbols).
    """
    index_names = index_names or {}
    out: dict[str, str] = {}
    unresolved: list[str] = []
    seen: set[str] = set()

    def _is_index_symbol(sym: str) -> bool:
        try:
            from server.cim_index_catalog import is_cim_index_symbol

            return is_cim_index_symbol(sym)
        except Exception:
            if sym.startswith("^") or sym.startswith("NSE:"):
                return True
            if sym.endswith(".NS") and "NIFTY" in sym:
                return True
            if sym.startswith("NIFTY_") or sym == "INDIA_VIX":
                return True
            return False

    for raw in symbols or []:
        sym = _normalize_symbol(raw)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        if _is_index_symbol(sym):
            key = resolve_index_key(sym, display_name=index_names.get(sym))
        else:
            key = resolve_equity_key(sym)
        if key:
            out[sym] = key
        else:
            unresolved.append(sym)
    return out, unresolved
