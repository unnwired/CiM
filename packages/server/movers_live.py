"""
Live quotes for Market Movers.

Primary: Upstox LTPC WebSocket universe stream (full screener) when LIVE is on.
Fallback: Upstox REST rotate when the stream is down or disabled (no Yahoo).
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time as time_module
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
import requests

# Re-use ranking / universe from movers_data (import after load to avoid circular import at module level).
_movers_data = None
_data_dir: Optional[Path] = None

VALID_POLL_INTERVALS = frozenset({0, 15, 30, 60, 120})
BULK_INDICES = [
    "NIFTY TOTAL MARKET",
    "SECURITIES IN F&O",
    "NIFTY MIDCAP 100",
    "NIFTY SMALLCAP 100",
]
QUOTE_BATCH_SIZE = 25
QUOTE_WORKERS = 3
YAHOO_ROTATE_BATCH_SIZE = 120
NSE_ON_DEMAND_FALLBACK_MAX = 25
ON_DEMAND_QUOTE_MAX = 80
ON_DEMAND_QUOTE_WORKERS = 8
BULK_REFRESH_MIN_SEC = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-equity-market",
    "Origin": "https://www.nseindia.com",
}

IST = timezone(timedelta(hours=5, minutes=30))

_lock = threading.Lock()
_bulk_refresh_lock = threading.Lock()
# Prevent concurrent movers list builds from stacking GB of temporary DataFrames.
_query_sem = threading.Semaphore(1)
_cache: dict[str, dict[str, Any]] = {}
_status: dict[str, Any] = {
    "interval_seconds": 0,
    "worker_running": False,
    "last_nse_refresh_at": None,
    "last_quote_refresh_at": None,
    "quote_source": "upstox",
    "last_nse_error": None,
    "symbols_in_cache": 0,
    "market_open": False,
    "upstox_enabled": False,
    "fallback_active": False,
    "last_upstox_error": None,
    "quote_source_counts": {},
    "universe_subscribed": False,
    "universe_size": 0,
    "universe_connected": False,
    "stream_mode": "ltpc",
    "quotes_fresh_count": 0,
}
_stop = threading.Event()
_worker: Optional[threading.Thread] = None
_rotate_offset = 0
_all_symbols: list[str] = []
_get_db_connection: Optional[Callable[[], sqlite3.Connection]] = None
_last_bulk_refresh_ts = 0.0
_universe_stream_active = False
_universe_df_cache: Optional[Any] = None
_universe_df_cache_ts = 0.0
_UNIVERSE_DF_TTL_SEC = 30.0
_light_query_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_LIGHT_QUERY_TTL_SEC = 3.0
_LEAN_QUOTE_KEYS = (
    "symbol",
    "price",
    "previous_close",
    "change_pct",
    "volume",
    "updated_at",
    "source",
    # Session wick memory for live charts (max high / min low across ticks + REST day OHLC).
    "open",
    "high",
    "low",
)


def _md():
    global _movers_data
    if _movers_data is None:
        raise RuntimeError("movers_live.init() not called")
    return _movers_data


def init(get_db_connection: Callable[[], sqlite3.Connection]) -> None:
    global _get_db_connection
    _get_db_connection = get_db_connection


def configure_paths(*, data_dir: Path) -> None:
    """Encrypted runtime may load this module from app-cache; data stays in install root."""
    global _data_dir
    _data_dir = Path(data_dir)
    if _movers_data is not None and hasattr(_movers_data, "configure_paths"):
        _movers_data.configure_paths(data_dir=_data_dir)


def warm_cache_on_startup() -> None:
    """One-shot quote refresh so dashboard 1D % has live quotes soon after server boot."""
    try:
        _run_live_refresh_once(include_quotes=True)
    except Exception as e:
        with _lock:
            _status["last_nse_error"] = str(e)


def _yahoo_primary_enabled() -> bool:
    try:
        from server.product_config import yahoo_primary_pipeline

        return bool(yahoo_primary_pipeline())
    except Exception:
        return False


def _run_yahoo_refresh_once() -> None:
    """Rotate Upstox quote batches across the screener universe (no Yahoo / NSE mix)."""
    global _rotate_offset, _all_symbols

    from server import live_quote_providers as lqp

    if not _all_symbols:
        _all_symbols = _load_symbol_universe()
    universe = _all_symbols
    if not universe:
        return
    batch: list[str] = []
    n = len(universe)
    size = min(YAHOO_ROTATE_BATCH_SIZE, n)
    for i in range(size):
        batch.append(universe[(_rotate_offset + i) % n])
    _rotate_offset = (_rotate_offset + len(batch)) % max(n, 1)
    entries = lqp.fetch_primary_equity_quotes(batch)
    if entries:
        _merge_cache(entries)
    now = _iso_now()
    src_counts: dict[str, int] = {}
    for e in entries:
        src = str(e.get("source") or "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    primary = "upstox" if src_counts.get("upstox") else ("yfinance" if src_counts.get("yfinance") else "none")
    upstox_err = None
    try:
        from server import upstox_client, upstox_config

        upstox_on = upstox_config.market_data_enabled()
        upstox_err = upstox_client.last_error()
    except Exception:
        upstox_on = False
    with _lock:
        _status["last_nse_refresh_at"] = now
        _status["last_quote_refresh_at"] = now
        _status["quote_source"] = primary
        _status["quote_source_counts"] = src_counts
        _status["upstox_enabled"] = bool(upstox_on)
        _status["fallback_active"] = bool(upstox_on and src_counts.get("yfinance"))
        _status["last_upstox_error"] = upstox_err
        _status["last_nse_error"] = upstox_err if (upstox_on and upstox_err and not entries) else None
        _status["symbols_in_cache"] = len(_cache)
        _status["market_open"] = _market_open()


def _load_movers_data_module():
    global _movers_data
    if _movers_data is not None:
        return _movers_data
    import importlib.util
    from pathlib import Path

    base = Path(__file__).resolve().parent / "movers_data"
    path = base.with_suffix(".py")
    if not path.exists():
        path = base.with_suffix(".pyc")
    spec = importlib.util.spec_from_file_location("nse_pulse_movers_data_live", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load movers_data from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if _data_dir is not None and hasattr(mod, "configure_paths"):
        mod.configure_paths(data_dir=_data_dir)
    _movers_data = mod
    return mod


def _market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)


def _iso_now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _cache_quote_stale(snap: Optional[dict[str, Any]]) -> bool:
    """True when entry is missing, has no price, or was not refreshed today (IST)."""
    if not snap:
        return True
    if _finite_or_none(snap.get("price")) is None:
        return True
    updated = snap.get("updated_at")
    if not updated:
        return True
    try:
        date_part = str(updated).split()[0]
        return date_part != datetime.now(IST).strftime("%Y-%m-%d")
    except Exception:
        return True


def cache_quote_fresh(snap: Optional[dict[str, Any]]) -> bool:
    return not _cache_quote_stale(snap)


def _quote_age_sec(snap: Optional[dict[str, Any]]) -> Optional[float]:
    """Seconds since quote updated_at (IST). None if unparsable."""
    if not snap:
        return None
    updated = snap.get("updated_at")
    if not updated:
        return None
    try:
        s = str(updated).replace(" IST", "").strip()
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
        return max(0.0, (datetime.now(IST) - dt).total_seconds())
    except Exception:
        return None


def _finite_or_none(v: Any) -> Optional[float]:
    """Reject None, NaN, and inf so live overlay never poisons EOD rankings."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def _positive_finite_or_none(v: Any) -> Optional[float]:
    """OHLC / price fields must be > 0 for candle merge."""
    x = _finite_or_none(v)
    if x is None or x <= 0:
        return None
    return x


def _pct_change(price: float, reference_close: float) -> Optional[float]:
    ref = _finite_or_none(reference_close)
    px = _finite_or_none(price)
    if ref is None or px is None or ref <= 0:
        return None
    return round((px - ref) / ref * 100.0, 2)


def _reference_close_from_row(row) -> Optional[float]:
    """Previous session close to anchor today's intraday % (not Thu-vs-Wed when today is Fri)."""
    eod_close = _finite_or_none(row.get("eod_close"))
    eod_prev = _finite_or_none(row.get("eod_prev_close"))
    if eod_close is None:
        return None
    as_of = row.get("as_of_date")
    today = datetime.now(IST).date()
    as_of_date = None
    if as_of is not None:
        try:
            as_of_date = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    if as_of_date == today and eod_prev is not None and eod_prev > 0:
        return eod_prev
    if as_of_date is not None and as_of_date < today:
        return eod_close
    return eod_close


def stream_universe_symbols() -> list[str]:
    """Screener symbols for the Upstox LTPC movers subscription."""
    global _all_symbols
    if not _all_symbols:
        _all_symbols = _load_symbol_universe()
    return list(_all_symbols)


# Coalesce high-rate LTPC ticks — per-tick merge + full-cache scans starved the API.
_pending_stream_quotes: dict[str, dict[str, Any]] = {}
_ingest_flush_stop = threading.Event()
_ingest_flush_thread: Optional[threading.Thread] = None
_INGEST_FLUSH_SEC = 0.35


def _flush_pending_stream_quotes() -> None:
    with _lock:
        pending = list(_pending_stream_quotes.values())
        _pending_stream_quotes.clear()
    if not pending:
        return
    _merge_cache(pending)
    with _lock:
        _status["last_quote_refresh_at"] = _iso_now()
        _status["quote_source"] = "upstox_stream"
        _status["symbols_in_cache"] = len(_cache)
        # Incremental: pending symbols are stream-sourced; avoid O(universe) recount each flush.
        counts = dict(_status.get("quote_source_counts") or {})
        prev = int(counts.get("upstox_stream") or _status.get("quotes_fresh_count") or 0)
        counts["upstox_stream"] = max(prev, len(_cache))
        _status["quote_source_counts"] = counts
        _status["quotes_fresh_count"] = counts["upstox_stream"]


def _ensure_ingest_flusher() -> None:
    global _ingest_flush_thread
    if _ingest_flush_thread and _ingest_flush_thread.is_alive():
        return

    def _loop() -> None:
        while not _ingest_flush_stop.wait(_INGEST_FLUSH_SEC):
            try:
                _flush_pending_stream_quotes()
            except Exception:
                pass
        try:
            _flush_pending_stream_quotes()
        except Exception:
            pass

    _ingest_flush_stop.clear()
    _ingest_flush_thread = threading.Thread(target=_loop, name="movers-ingest-flush", daemon=True)
    _ingest_flush_thread.start()


def ingest_stream_quotes(entries: list[dict[str, Any]]) -> None:
    """Queue LTPC ticks for batched merge (keeps uvicorn responsive under full-universe feed)."""
    if not entries:
        return
    _ensure_ingest_flusher()
    with _lock:
        for e in entries:
            if not isinstance(e, dict):
                continue
            sym = str(e.get("symbol") or "").strip().upper()
            if not sym:
                continue
            _pending_stream_quotes[sym] = e


def set_universe_stream_active(
    active: bool,
    *,
    universe_size: int = 0,
    stream_status: Optional[dict[str, Any]] = None,
) -> None:
    """Called when floating LIVE starts/stops the movers LTPC universe."""
    global _universe_stream_active
    _universe_stream_active = bool(active)
    connected = bool((stream_status or {}).get("connected"))
    with _lock:
        _status["universe_subscribed"] = bool(active)
        _status["universe_size"] = int(universe_size or 0)
        _status["universe_connected"] = connected if active else False
        _status["stream_mode"] = "ltpc"
        if active:
            _status["quote_source"] = "upstox_stream"
            _status["interval_seconds"] = 0
            # Stop legacy HTTP poll worker — WS is primary.
        else:
            if str(_status.get("quote_source") or "") == "upstox_stream":
                _status["quote_source"] = "idle"
    if active:
        _stop_worker()
    else:
        _stop_worker()


def universe_stream_active() -> bool:
    return bool(_universe_stream_active)


def get_status() -> dict[str, Any]:
    upstox_on = False
    upstox_err = None
    universe_connected = False
    universe_size = 0
    try:
        from server import upstox_client, upstox_config

        upstox_on = upstox_config.market_data_enabled()
        upstox_err = upstox_client.last_error()
    except Exception:
        pass
    try:
        from server.upstox_stream_worker import movers_manager

        st = movers_manager.status()
        universe_connected = bool(st.get("connected"))
        universe_size = int(st.get("subscription_count") or 0)
    except Exception:
        pass
    with _lock:
        counts = dict(_status.get("quote_source_counts") or {})
        if not counts and _cache:
            for snap in _cache.values():
                src = str((snap or {}).get("source") or "unknown")
                counts[src] = counts.get(src, 0) + 1
        stream_n = int(counts.get("upstox_stream") or 0)
        fallback = bool(
            upstox_on
            and not (_universe_stream_active and universe_connected)
            and (counts.get("yfinance") or counts.get("nse") or counts.get("nse_all_indices") or counts.get("upstox"))
        )
        return {
            **_status,
            "symbols_in_cache": len(_cache),
            "market_open": _market_open(),
            "upstox_enabled": upstox_on,
            "fallback_active": fallback or bool(_status.get("fallback_active")),
            "last_upstox_error": upstox_err or _status.get("last_upstox_error"),
            "quote_source_counts": counts,
            # Never advertise NSE as the live product source when Upstox is configured.
            "quote_source": (
                "upstox_stream"
                if (_universe_stream_active or stream_n)
                else ("upstox" if upstox_on else str(_status.get("quote_source") or "idle"))
            ),
            "universe_subscribed": bool(_universe_stream_active),
            "universe_size": universe_size or int(_status.get("universe_size") or 0),
            "universe_connected": universe_connected if _universe_stream_active else False,
            "quotes_fresh_count": stream_n or int(_status.get("quotes_fresh_count") or 0),
            "stream_mode": "ltpc",
        }


def configure_poll_interval(seconds: int) -> dict[str, Any]:
    """Deprecated: floating LIVE + LTPC universe replaced poll intervals.

    Kept for API compatibility. Non-zero starts REST fallback worker only when
    the universe stream is not active.
    """
    sec = int(seconds)
    if sec not in VALID_POLL_INTERVALS:
        sec = 0
    with _lock:
        _status["interval_seconds"] = sec
    if _universe_stream_active:
        _stop_worker()
        return get_status()
    if sec == 0:
        _stop_worker()
    else:
        _ensure_worker()
        threading.Thread(target=_run_live_refresh_once, name="movers-live-initial", daemon=True).start()
    return get_status()


def _stop_worker() -> None:
    global _worker
    _stop.set()
    if _worker and _worker.is_alive():
        _worker.join(timeout=2.0)
    _worker = None
    with _lock:
        _status["worker_running"] = False


def _ensure_worker() -> None:
    global _worker
    _load_movers_data_module()
    if _worker and _worker.is_alive():
        _stop.clear()
        return
    _stop.clear()
    _worker = threading.Thread(target=_worker_loop, name="movers-live-nse", daemon=True)
    _worker.start()
    with _lock:
        _status["worker_running"] = True


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=15)
        time_module.sleep(1.5)
        s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
        time_module.sleep(1.5)
    except Exception:
        pass
    return s


def _fetch_bulk(session: requests.Session, index_name: str) -> list[dict]:
    encoded = index_name.replace(" ", "%20").replace("&", "%26")
    url = f"https://www.nseindia.com/api/equity-stockIndices?index={encoded}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.json().get("data", []) or []
    except Exception:
        pass
    return []


def _parse_quote_row(symbol: str, item: dict) -> Optional[dict[str, Any]]:
    sym = str(item.get("symbol") or symbol or "").strip().upper()
    if not sym:
        return None
    pi = item.get("priceInfo") if isinstance(item.get("priceInfo"), dict) else {}
    pch = item.get("pChange")
    if pch is None:
        pch = pi.get("pChange")
    price = item.get("lastPrice")
    if price is None:
        price = pi.get("lastPrice")
    prev_close = item.get("previousClose")
    if prev_close is None:
        prev_close = pi.get("previousClose")
    vol = item.get("totalTradedVolume")
    if vol is None:
        vol = pi.get("totalTradedVolume")
    op = item.get("open")
    if op is None:
        op = pi.get("open")
    hi = item.get("dayHigh")
    lo = item.get("dayLow")
    ild = pi.get("intraDayHighLow")
    if isinstance(ild, dict):
        if hi is None:
            hi = ild.get("max")
        if lo is None:
            lo = ild.get("min")
    price_f = _finite_or_none(price)
    if price_f is not None:
        price_f = round(price_f, 2)
    prev_f = _finite_or_none(prev_close)
    if prev_f is not None:
        prev_f = round(prev_f, 2)
    pch_f = _pct_change(price_f, prev_f) if price_f is not None and prev_f is not None else None
    if pch_f is None:
        pch_f = _finite_or_none(pch)
        if pch_f is not None:
            pch_f = round(pch_f, 2)
    vol_f = _finite_or_none(vol)
    op_f = _finite_or_none(op)
    hi_f = _finite_or_none(hi)
    lo_f = _finite_or_none(lo)
    if price_f is None and pch_f is None and vol_f is None:
        return None
    out: dict[str, Any] = {
        "symbol": sym,
        "price": price_f,
        "change_pct": pch_f,
        "volume": vol_f,
        "updated_at": _iso_now(),
        "source": item.get("_source", "bulk"),
    }
    if prev_f is not None:
        out["previous_close"] = prev_f
    if op_f is not None:
        out["open"] = round(op_f, 2)
    if hi_f is not None:
        out["high"] = round(hi_f, 2)
    if lo_f is not None:
        out["low"] = round(lo_f, 2)
    return out


def _fetch_quote_equity(session: requests.Session, symbol: str) -> Optional[dict[str, Any]]:
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        pi = data.get("priceInfo") or {}
        row = {
            "symbol": symbol,
            "lastPrice": pi.get("lastPrice"),
            "previousClose": pi.get("previousClose"),
            "pChange": pi.get("pChange"),
            "totalTradedVolume": pi.get("totalTradedVolume"),
            "priceInfo": pi,
            "_source": "quote",
        }
        return _parse_quote_row(symbol, row)
    except Exception:
        return None


def _sanitize_cache_entry(e: dict[str, Any]) -> Optional[dict[str, Any]]:
    sym = str(e.get("symbol") or "").strip().upper()
    if not sym:
        return None
    price = _finite_or_none(e.get("price"))
    if price is not None:
        price = round(price, 2)
    prev_close = _finite_or_none(e.get("previous_close"))
    if prev_close is not None:
        prev_close = round(prev_close, 2)
    change_pct = _pct_change(price, prev_close) if price is not None and prev_close is not None else None
    if change_pct is None:
        change_pct = _finite_or_none(e.get("change_pct"))
        if change_pct is not None:
            change_pct = round(change_pct, 2)
    volume = _finite_or_none(e.get("volume"))
    if price is None and change_pct is None and volume is None:
        return None
    out: dict[str, Any] = {"symbol": sym}
    if price is not None:
        out["price"] = price
    if change_pct is not None:
        out["change_pct"] = change_pct
    if prev_close is not None:
        out["previous_close"] = prev_close
    if volume is not None:
        out["volume"] = volume
    op = _positive_finite_or_none(e.get("open"))
    hi = _positive_finite_or_none(e.get("high"))
    lo = _positive_finite_or_none(e.get("low"))
    if op is not None:
        out["open"] = round(op, 2)
    if hi is not None:
        out["high"] = round(hi, 2)
    if lo is not None:
        out["low"] = round(lo, 2)
    src = e.get("source")
    if src:
        out["source"] = str(src)
    updated = e.get("updated_at")
    if updated:
        out["updated_at"] = updated
    return out


def _merge_cache(entries: list[dict[str, Any]]) -> None:
    with _lock:
        for e in entries:
            if not e:
                continue
            clean = _sanitize_cache_entry(e)
            if not clean:
                continue
            sym = clean["symbol"]
            prev = _cache.get(sym) or {}
            merged = {k: prev[k] for k in _LEAN_QUOTE_KEYS if k in prev}
            merged.update(clean)
            for key in ("price", "change_pct", "volume", "previous_close", "open", "high", "low"):
                if key in merged and _finite_or_none(merged[key]) is None:
                    merged.pop(key, None)
            px = _finite_or_none(merged.get("price"))
            pc = _finite_or_none(merged.get("previous_close"))
            if px is not None and pc is not None:
                chg = _pct_change(px, pc)
                if chg is not None:
                    merged["change_pct"] = chg
            # Running session wick: keep earliest open, max high, min low across ticks.
            prev_open = _positive_finite_or_none(prev.get("open"))
            prev_high = _positive_finite_or_none(prev.get("high"))
            prev_low = _positive_finite_or_none(prev.get("low"))
            next_open = _positive_finite_or_none(merged.get("open"))
            next_high = _positive_finite_or_none(merged.get("high"))
            next_low = _positive_finite_or_none(merged.get("low"))
            if next_open is None and prev_open is not None:
                merged["open"] = prev_open
            elif next_open is None:
                merged.pop("open", None)
            hi_candidates = [v for v in (prev_high, next_high, px) if v is not None]
            if hi_candidates:
                merged["high"] = round(max(hi_candidates), 2)
            lo_candidates = [v for v in (prev_low, next_low, px) if v is not None]
            if lo_candidates:
                merged["low"] = round(min(lo_candidates), 2)
            _cache[sym] = merged

def clear_stream_quote_cache() -> None:
    """Drop ranking quote cache when movers LIVE turns off (free RAM)."""
    global _universe_df_cache, _universe_df_cache_ts
    with _lock:
        _pending_stream_quotes.clear()
        _cache.clear()
        _status["symbols_in_cache"] = 0
        _status["quotes_fresh_count"] = 0
        counts = dict(_status.get("quote_source_counts") or {})
        counts["upstox_stream"] = 0
        _status["quote_source_counts"] = counts
        _light_query_cache.clear()
        _universe_df_cache = None
        _universe_df_cache_ts = 0.0


def _load_symbol_universe() -> list[str]:
    if _get_db_connection is None:
        return []
    try:
        conn = _get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
                FROM screener
                WHERE symbol IS NOT NULL AND TRIM(symbol) != ''
                ORDER BY symbol
                """
            )
            return [str(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def _nse_refresh_cycle(session: requests.Session, *, include_quotes: bool = True) -> None:
    global _rotate_offset, _all_symbols
    entries: list[dict] = []
    for idx_name in BULK_INDICES:
        for item in _fetch_bulk(session, idx_name):
            if str(item.get("symbol", "")).upper() == idx_name.upper():
                continue
            parsed = _parse_quote_row("", {**item, "_source": "bulk"})
            if parsed:
                entries.append(parsed)
    if not _all_symbols:
        _all_symbols = _load_symbol_universe()
    universe = _all_symbols
    if universe and include_quotes:
        batch: list[str] = []
        n = len(universe)
        for i in range(QUOTE_BATCH_SIZE):
            batch.append(universe[(_rotate_offset + i) % n])
        _rotate_offset = (_rotate_offset + len(batch)) % n
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=QUOTE_WORKERS) as pool:
            futures = {pool.submit(_fetch_quote_equity, session, sym): sym for sym in batch}
            for fut in as_completed(futures):
                row = fut.result()
                if row:
                    entries.append(row)
    _merge_cache(entries)
    with _lock:
        _status["last_nse_refresh_at"] = _iso_now()
        _status["last_nse_error"] = None
        _status["symbols_in_cache"] = len(_cache)
        _status["market_open"] = _market_open()


def _run_nse_refresh_once(*, include_quotes: Optional[bool] = None) -> None:
    global _last_bulk_refresh_ts
    try:
        session = _make_session()
        if include_quotes is None:
            include_quotes = _market_open()
        _nse_refresh_cycle(session, include_quotes=include_quotes)
        _last_bulk_refresh_ts = time_module.time()
        now = _iso_now()
        with _lock:
            _status["last_nse_refresh_at"] = now
            _status["last_quote_refresh_at"] = now
            _status["quote_source"] = "nse"
    except Exception as e:
        with _lock:
            _status["last_nse_error"] = str(e)


def _run_live_refresh_once(*, include_quotes: Optional[bool] = None) -> None:
    """Upstox-only live quotes. No Yahoo / NSE bulk mix."""
    global _last_bulk_refresh_ts
    if include_quotes is None:
        include_quotes = _market_open()
    if include_quotes:
        _run_yahoo_refresh_once()
    _last_bulk_refresh_ts = time_module.time()


def refresh_after_data_update(*, include_quotes: bool = True) -> None:
    """After OHLCV / universal update: warm live quote cache so movers show today's session."""
    global _all_symbols

    def _go() -> None:
        try:
            _all_symbols = []
            _run_live_refresh_once(include_quotes=include_quotes)
        except Exception as e:
            with _lock:
                _status["last_nse_error"] = str(e)

    threading.Thread(target=_go, name="movers-post-data-quotes", daemon=True).start()


def refresh_after_data_update_sync(*, include_quotes: bool = True) -> None:
    """Blocking quote cache warm — use after admin update so movers see fresh quotes."""
    global _all_symbols

    try:
        _all_symbols = []
        _run_live_refresh_once(include_quotes=include_quotes)
    except Exception as e:
        with _lock:
            _status["last_nse_error"] = str(e)


def _ensure_bulk_cache_fresh() -> None:
    """Refresh live quote cache when empty or stale — skip if LTPC universe is feeding."""
    global _last_bulk_refresh_ts
    if _universe_stream_active:
        try:
            from server.upstox_stream_worker import movers_manager

            st = movers_manager.status()
            if st.get("connected") and int(st.get("cached_quotes") or 0) >= 100:
                return
        except Exception:
            pass
    with _lock:
        cache_len = len(_cache)
        age = time_module.time() - _last_bulk_refresh_ts
        stream_n = int(_status.get("quotes_fresh_count") or 0)
    if _universe_stream_active and stream_n >= 400:
        return
    if cache_len >= 400 and age < BULK_REFRESH_MIN_SEC:
        return
    # One refresher at a time — concurrent light polls used to stampede Yahoo/Upstox.
    if not _bulk_refresh_lock.acquire(blocking=False):
        return
    try:
        with _lock:
            cache_len = len(_cache)
            age = time_module.time() - _last_bulk_refresh_ts
        if cache_len >= 400 and age < BULK_REFRESH_MIN_SEC:
            return
        _run_live_refresh_once()
    finally:
        _bulk_refresh_lock.release()


def _symbol_needs_live_quote(sym: str, *, force: bool = False) -> bool:
    s = str(sym or "").strip().upper()
    if not s:
        return True
    if force:
        return True
    with _lock:
        snap = _cache.get(s)
    return _cache_quote_stale(snap)


def _fetch_missing_quote_symbols(
    symbols: list[str],
    *,
    max_n: int = ON_DEMAND_QUOTE_MAX,
    force: bool = False,
) -> int:
    """Live quotes for symbols missing or stale (top movers often outside bulk indices)."""
    seen: set[str] = set()
    missing: list[str] = []
    for sym in symbols:
        s = str(sym or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        if _symbol_needs_live_quote(s, force=force):
            missing.append(s)
        if len(missing) >= max_n:
            break
    if not missing:
        return 0
    entries: list[dict] = []

    # Upstox only. No NSE quote-equity mix for on-demand fills.
    try:
        from server import live_quote_providers as lqp

        primary_rows = lqp.fetch_primary_equity_quotes(missing)
        if primary_rows:
            _merge_cache(primary_rows)
            entries.extend(primary_rows)
    except Exception as e:
        with _lock:
            _status["last_nse_error"] = str(e)
    return len(entries)


def _has_live_quote(sym: str, live: dict[str, dict[str, Any]]) -> bool:
    snap = live.get(str(sym or "").strip().upper())
    return bool(snap and _finite_or_none(snap.get("price")) is not None)


def _worker_loop() -> None:
    while not _stop.is_set():
        with _lock:
            interval = int(_status.get("interval_seconds") or 0)
        if interval <= 0:
            time_module.sleep(1.0)
            continue
        with _lock:
            _status["market_open"] = _market_open()
        _run_live_refresh_once()
        for _ in range(interval):
            if _stop.is_set():
                break
            time_module.sleep(1.0)


def live_cache_snapshot() -> dict[str, dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _cache.items()}


def apply_live_overlay(df: pd.DataFrame, live: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Overlay live prices; day % uses quote previous_close (matches chart), not DB EOD prior."""
    if df.empty or not live:
        return df
    md = _load_movers_data_module()
    out = df.copy()
    price_map: dict[str, float] = {}
    prev_map: dict[str, float] = {}
    chg_map: dict[str, float] = {}
    vol_map: dict[str, float] = {}
    for sym, snap in live.items():
        if not snap or not cache_quote_fresh(snap):
            continue
        key = str(sym).upper()
        live_price = _finite_or_none(snap.get("price"))
        ref_close = _finite_or_none(snap.get("previous_close"))
        if live_price is not None:
            price_map[key] = round(live_price, 2)
        if ref_close is not None and ref_close > 0:
            prev_map[key] = round(ref_close, 4)
        live_chg = _finite_or_none(snap.get("change_pct"))
        if live_price is not None and ref_close is not None and ref_close > 0:
            live_chg = _pct_change(live_price, ref_close)
        elif live_chg is not None and (ref_close is None or ref_close <= 0):
            # Unverified vendor change_pct without previous_close — ignore for day rank.
            live_chg = None
        if live_chg is not None:
            chg_map[key] = round(live_chg, 2)
        live_vol = _finite_or_none(snap.get("volume"))
        if live_vol is not None:
            vol_map[key] = live_vol

    if not price_map and not chg_map and not vol_map:
        return out

    today_s = datetime.now(IST).strftime("%Y-%m-%d")
    syms = out["symbol"].astype(str).str.strip().str.upper()
    if price_map:
        mapped = syms.map(price_map)
        out["price"] = mapped.where(mapped.notna(), out["price"])
        if "issued_shares" in out.columns:
            shares = pd.to_numeric(out["issued_shares"], errors="coerce")
            px = pd.to_numeric(out["price"], errors="coerce")
            mcap = shares * px
            out["market_cap"] = mcap.where(shares.gt(0) & px.gt(0), out.get("market_cap"))

        # Prefer live quote previous_close so list % matches the chart day move
        # (DB eod_close prior can inflate day % vs the live feed).
        px = pd.to_numeric(out["price"], errors="coerce")
        quote_prev = syms.map(prev_map)
        from_quote = (px - quote_prev) / quote_prev * 100.0
        use_quote = mapped.notna() & quote_prev.gt(0) & px.gt(0)
        out.loc[use_quote, "change_pct"] = from_quote.loc[use_quote].round(2)
        out.loc[use_quote, "as_of_date"] = today_s

        still = mapped.notna() & ~use_quote
        if still.any():
            out.loc[still, "change_pct"] = float("nan")
        for sym, live_chg in chg_map.items():
            idxs = out.index[syms == sym]
            if len(idxs) == 0:
                continue
            idx = idxs[0]
            if sym in prev_map and idx in use_quote.index and bool(use_quote.loc[idx]):
                continue
            out.at[idx, "change_pct"] = live_chg
            out.at[idx, "as_of_date"] = today_s
        if still.any():
            today = datetime.now(IST).date()
            eod = pd.to_numeric(out.get("eod_close"), errors="coerce")
            eod_prev = pd.to_numeric(out.get("eod_prev_close"), errors="coerce")
            as_of = out.get("as_of_date")
            if as_of is not None:
                as_of_d = pd.to_datetime(as_of, errors="coerce").dt.date
                prior = eod_prev.where(as_of_d >= today, eod)
            else:
                prior = eod
            from_db = (px - prior) / prior * 100.0
            need = still & out["change_pct"].isna() & prior.gt(0) & px.gt(0)
            out.loc[need, "change_pct"] = from_db.loc[need].round(2)
            out.loc[need, "as_of_date"] = today_s
    elif chg_map:
        for i, sym in enumerate(syms.tolist()):
            live_chg = chg_map.get(sym)
            if live_chg is None:
                continue
            existing_chg = _finite_or_none(out.iloc[i].get("change_pct"))
            if md.should_apply_live_day_change(existing_chg, live_chg):
                out.iat[i, out.columns.get_loc("change_pct")] = live_chg
                if "as_of_date" in out.columns:
                    out.iat[i, out.columns.get_loc("as_of_date")] = today_s
    if vol_map:
        mapped_v = syms.map(vol_map)
        out["volume_today"] = mapped_v.where(mapped_v.notna(), out["volume_today"])
        if "volume_prior" in out.columns:
            vp = pd.to_numeric(out["volume_prior"], errors="coerce")
            vt = pd.to_numeric(out["volume_today"], errors="coerce")
            vchg = (vt - vp) / vp * 100.0
            out["volume_change_pct"] = vchg.where(vp.gt(0) & mapped_v.notna(), out.get("volume_change_pct"))
        if "avg_volume_20d" in out.columns:
            avg = pd.to_numeric(out["avg_volume_20d"], errors="coerce")
            vt = pd.to_numeric(out["volume_today"], errors="coerce")
            rvol = vt / avg
            out["rvol_20d"] = rvol.where(avg.gt(0) & mapped_v.notna(), out.get("rvol_20d"))
    return out



def rebuild_movers_universe_with_live(conn, mcap_sql: str) -> pd.DataFrame:
    """Reload movers universe and apply session + live overlays."""
    md = _load_movers_data_module()
    df = md.load_movers_universe(conn, mcap_sql)
    df = md.apply_session_day_adjustment(df)
    live = live_cache_snapshot()
    if live:
        df = apply_live_overlay(df, live)
    return df


def enrich_session_day_change(
    conn,
    mcap_sql: str,
    df: pd.DataFrame,
    side: str,
    limit: int,
    *,
    refresh_quotes: bool = True,
) -> tuple[pd.DataFrame, int]:
    """
    On session days, fetch NSE quotes for top day-change candidates missing from cache
    (EOD and live endpoints — fixes small caps like COFFEEDAY outside bulk indices).
    """
    if df.empty:
        return df, 0
    md = _load_movers_data_module()
    if not md._session_day_intraday_active():
        return df, 0
    side_n = (side or "gainers").strip().lower()
    ascending = side_n == "losers"
    work = df[df["change_pct"].apply(lambda v: _finite_or_none(v) is not None)].copy()
    work = md.filter_day_change_by_side(work, side_n)
    work = work.sort_values("change_pct", ascending=ascending, na_position="last")
    candidates = [str(s).upper() for s in work.head(max(limit * 5, 150))["symbol"]]
    fetched = 0
    if refresh_quotes and candidates:
        fetched = _fetch_missing_quote_symbols(candidates)
    return rebuild_movers_universe_with_live(conn, mcap_sql), fetched


def _cached_movers_universe_df(conn, mcap_sql: str):
    """Reuse EOD universe frame briefly; live overlay is applied by the caller."""
    global _universe_df_cache, _universe_df_cache_ts
    md = _load_movers_data_module()
    now = time_module.time()
    with _lock:
        cached = _universe_df_cache
        ts = _universe_df_cache_ts
    if cached is not None and (now - ts) < _UNIVERSE_DF_TTL_SEC:
        return cached.copy()
    df = md.load_movers_universe(conn, mcap_sql)
    df = md.apply_session_day_adjustment(df)
    with _lock:
        _universe_df_cache = df
        _universe_df_cache_ts = now
    return df.copy()


def _light_query_cache_key(
    *,
    mode: str,
    side: Optional[str],
    volume_mode: Optional[str],
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
) -> str:
    return "|".join(
        [
            str(mode),
            str(side or ""),
            str(volume_mode or ""),
            str(int(limit)),
            str(min_mcap if min_mcap is not None else ""),
            str(max_mcap if max_mcap is not None else ""),
        ]
    )


def _query_live(
    conn,
    *,
    mcap_sql: str,
    mode: str,
    side: Optional[str],
    volume_mode: Optional[str],
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
    allowed_symbols: Optional[set],
    refresh_quotes: bool = True,
) -> dict[str, Any]:
    # Serialize list builds — overlapping polls were measured at ~10GB RSS.
    acquired = _query_sem.acquire(timeout=90)
    if not acquired:
        raise TimeoutError("Movers list query busy — retry shortly")
    try:
        return _query_live_unlocked(
            conn,
            mcap_sql=mcap_sql,
            mode=mode,
            side=side,
            volume_mode=volume_mode,
            limit=limit,
            min_mcap=min_mcap,
            max_mcap=max_mcap,
            allowed_symbols=allowed_symbols,
            refresh_quotes=refresh_quotes,
        )
    finally:
        _query_sem.release()


def _query_live_unlocked(
    conn,
    *,
    mcap_sql: str,
    mode: str,
    side: Optional[str],
    volume_mode: Optional[str],
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
    allowed_symbols: Optional[set],
    refresh_quotes: bool = True,
) -> dict[str, Any]:
    md = _load_movers_data_module()
    light = not refresh_quotes
    cache_key = None
    if light and allowed_symbols is None and mode != "day_change":
        cache_key = _light_query_cache_key(
            mode=mode,
            side=side,
            volume_mode=volume_mode,
            limit=limit,
            min_mcap=min_mcap,
            max_mcap=max_mcap,
        )
        with _lock:
            hit = _light_query_cache.get(cache_key)
        if hit:
            ts, payload = hit
            if (time_module.time() - ts) <= _LIGHT_QUERY_TTL_SEC:
                return payload

    if refresh_quotes:
        _ensure_bulk_cache_fresh()
    else:
        with _lock:
            cache_len = len(_cache)
            age = time_module.time() - _last_bulk_refresh_ts
            stream_on = _universe_stream_active
        # Day-change light polls must refresh often — otherwise the ranked list freezes
        # on the first Yahoo batch.
        refresh_age = 20 if mode == "day_change" else 120
        if not stream_on and (cache_len < 100 or age > refresh_age):
            _ensure_bulk_cache_fresh()

    # Always reuse base universe briefly; overlay applies live quotes.
    df = _cached_movers_universe_df(conn, mcap_sql)
    live = live_cache_snapshot()
    if live:
        df = apply_live_overlay(df, live)

    st = get_status()
    as_of = st.get("last_nse_refresh_at")
    on_demand_fetched = 0

    if mode == "day_change":
        # Session-day LIVE: rank only names with a fresh live quote so yesterday's
        # EOD bar-to-bar % cannot dominate the top list.
        side_n = (side or "gainers").strip().lower()
        ascending = side_n == "losers"
        session = md._session_day_intraday_active()
        quote_refresh_age_sec = 45.0

        def _fresh_live_syms(snap: dict) -> set[str]:
            # Require previous_close so day %% is (price-prev)/prev — Yahoo rows with
            # only a stale change_pct (e.g. GUJGASLTD) must not enter the rank set.
            out: set[str] = set()
            for k, v in (snap or {}).items():
                if not v or not cache_quote_fresh(v):
                    continue
                if _finite_or_none(v.get("price")) is None:
                    continue
                if _finite_or_none(v.get("previous_close")) is None:
                    continue
                out.add(str(k).upper())
            return out

        def _provisional_top_syms(frame) -> list[str]:
            work = frame.copy()
            work = md._apply_mcap_filter(work, min_mcap, max_mcap)
            work = md._apply_sector_filter(work, allowed_symbols)
            if session and live:
                fresh = _fresh_live_syms(live)
                if fresh:
                    su = work["symbol"].astype(str).str.strip().str.upper()
                    work.loc[~su.isin(fresh), "change_pct"] = float("nan")
            work = work[work["change_pct"].apply(lambda v: _finite_or_none(v) is not None)]
            work = md.filter_day_change_by_side(work, side_n)
            work = work.sort_values("change_pct", ascending=ascending, na_position="last")
            return [str(s).upper() for s in work.head(max(limit, 25))["symbol"].tolist()]

        if session:
            top_need = _provisional_top_syms(df)
            stale_or_missing: list[str] = []
            fresh = _fresh_live_syms(live)
            if refresh_quotes:
                work = df.copy()
                work = md._apply_mcap_filter(work, min_mcap, max_mcap)
                work = md._apply_sector_filter(work, allowed_symbols)
                work = work[work["change_pct"].apply(lambda v: _finite_or_none(v) is not None)]
                work = work.reindex(work["change_pct"].abs().sort_values(ascending=False).index)
                for s in work["symbol"].tolist():
                    u = str(s).upper()
                    if u not in fresh:
                        stale_or_missing.append(u)
                    if len(stale_or_missing) >= max(limit * 4, 80):
                        break
            for u in top_need:
                snap = (live or {}).get(u)
                age = _quote_age_sec(snap) if snap else None
                if u not in fresh or age is None or age > quote_refresh_age_sec:
                    stale_or_missing.append(u)
            seen: set[str] = set()
            need: list[str] = []
            for u in stale_or_missing:
                if u in seen:
                    continue
                seen.add(u)
                need.append(u)
            if need:
                max_n = min(len(need), max(limit * 2, 50) if light else max(limit * 4, 80))
                on_demand_fetched = _fetch_missing_quote_symbols(need, max_n=max_n, force=True)
                live = live_cache_snapshot()
                if live:
                    df = apply_live_overlay(df, live)

        df = md._apply_mcap_filter(df, min_mcap, max_mcap)
        df = md._apply_sector_filter(df, allowed_symbols)
        if session and live:
            fresh = _fresh_live_syms(live)
            if fresh:
                sym_u = df["symbol"].astype(str).str.strip().str.upper()
                df.loc[~sym_u.isin(fresh), "change_pct"] = float("nan")
        df = df[df["change_pct"].apply(lambda v: _finite_or_none(v) is not None)]
        df = md.filter_day_change_by_side(df, side_n)
        if df.empty and live and not session:
            df = md.load_movers_universe(conn, mcap_sql)
            df = md.apply_session_day_adjustment(df)
            df = md._apply_mcap_filter(df, min_mcap, max_mcap)
            df = md._apply_sector_filter(df, allowed_symbols)
            df = df[df["change_pct"].apply(lambda v: _finite_or_none(v) is not None)]
            df = md.filter_day_change_by_side(df, side_n)
            live = {}
            as_of = None
        df = df.sort_values("change_pct", ascending=ascending, na_position="last")
        top = df.head(limit)
        rows = [md._row_to_dict(top.iloc[i], i + 1) for i in range(len(top))]
        if min_mcap is not None:
            floor = float(min_mcap)
            rows = [
                r for r in rows
                if r.get("market_cap") is not None and float(r["market_cap"]) >= floor
            ]
            for i, r in enumerate(rows):
                r["rank"] = i + 1
        live_count = 0
        for r in rows:
            sym = r.get("symbol")
            if sym and _has_live_quote(sym, live):
                live_count += 1
                r["live"] = True
                r["quote_updated_at"] = live[str(sym).upper()].get("updated_at")
        st = {**st, "on_demand_quotes_fetched": on_demand_fetched, "rows_with_live_quote": live_count}
        result = {
            "mode": "day_change",
            "side": side_n,
            "limit": limit,
            "data_source": "live",
            "as_of_date": as_of if not session else datetime.now(IST).strftime("%Y-%m-%d"),
            "live_status": st,
            "count": len(rows),
            "data": rows,
        }
        # Do not freeze day-change rankings in light cache — overlay must reshuffle.
        return result

    df = md._apply_mcap_filter(df, min_mcap, max_mcap)
    df = md._apply_sector_filter(df, allowed_symbols)

    vm = (volume_mode or "absolute").strip().lower()
    pre_sort_col = "volume_today"
    if vm == "surge":
        pre_sort_col = "volume_change_pct"
    elif vm == "rvol":
        pre_sort_col = "rvol_20d"
    pre = df[df[pre_sort_col].apply(lambda v: _finite_or_none(v) is not None)]
    pre = pre.sort_values(pre_sort_col, ascending=False, na_position="last")
    candidates = [str(s).upper() for s in pre.head(max(limit * 5, 150))["symbol"]]
    on_demand_fetched = 0
    if refresh_quotes and not _universe_stream_active:
        on_demand_fetched = _fetch_missing_quote_symbols(candidates)
    if on_demand_fetched:
        live = live_cache_snapshot()
        df = md.load_movers_universe(conn, mcap_sql)
        df = md.apply_session_day_adjustment(df)
        df = apply_live_overlay(df, live)
        df = md._apply_mcap_filter(df, min_mcap, max_mcap)
        df = md._apply_sector_filter(df, allowed_symbols)

    if vm == "surge":
        df = df[df["volume_change_pct"].notna()]
        sort_col = "volume_change_pct"
    elif vm == "rvol":
        df = df[df["rvol_20d"].notna()]
        sort_col = "rvol_20d"
    else:
        df = df[df["volume_today"].notna()]
        sort_col = "volume_today"
        vm = "absolute"
    df = df.sort_values(sort_col, ascending=False, na_position="last")
    top = df.head(limit)
    rows = [md._row_to_dict(top.iloc[i], i + 1) for i in range(len(top))]
    if min_mcap is not None:
        floor = float(min_mcap)
        rows = [
            r for r in rows
            if r.get("market_cap") is not None and float(r["market_cap"]) >= floor
        ]
        for i, r in enumerate(rows):
            r["rank"] = i + 1
    live_count = 0
    for r in rows:
        sym = r.get("symbol")
        if sym and _has_live_quote(sym, live):
            live_count += 1
            r["live"] = True
            r["quote_updated_at"] = live[str(sym).upper()].get("updated_at")
    st = {**st, "on_demand_quotes_fetched": on_demand_fetched, "rows_with_live_quote": live_count}
    result = {
        "mode": "volume",
        "volume_mode": vm,
        "limit": limit,
        "data_source": "live",
        "as_of_date": as_of,
        "live_status": st,
        "count": len(rows),
        "data": rows,
    }
    if cache_key:
        with _lock:
            _light_query_cache[cache_key] = (time_module.time(), result)
    return result


def query_day_change_live(
    conn,
    *,
    mcap_sql: str,
    side: str,
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
    allowed_symbols: Optional[set],
    refresh_quotes: bool = True,
) -> dict[str, Any]:
    return _query_live(
        conn,
        mcap_sql=mcap_sql,
        mode="day_change",
        side=side,
        volume_mode=None,
        limit=limit,
        min_mcap=min_mcap,
        max_mcap=max_mcap,
        allowed_symbols=allowed_symbols,
        refresh_quotes=refresh_quotes,
    )


def query_volume_live(
    conn,
    *,
    mcap_sql: str,
    volume_mode: str,
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
    allowed_symbols: Optional[set],
    refresh_quotes: bool = True,
) -> dict[str, Any]:
    return _query_live(
        conn,
        mcap_sql=mcap_sql,
        mode="volume",
        side=None,
        volume_mode=volume_mode,
        limit=limit,
        min_mcap=min_mcap,
        max_mcap=max_mcap,
        allowed_symbols=allowed_symbols,
        refresh_quotes=refresh_quotes,
    )


def get_symbol_live_snapshot(symbol: str, *, allow_fetch: bool = False) -> Optional[dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    snap = live_cache_snapshot().get(sym)
    if snap and cache_quote_fresh(snap):
        return snap
    if allow_fetch:
        _fetch_missing_quote_symbols([sym], max_n=1, force=True)
        snap = live_cache_snapshot().get(sym)
        if snap and cache_quote_fresh(snap):
            return snap
    return None


def merge_live_touch_last_bar(
    symbol: str,
    bars: list[dict[str, Any]],
    *,
    allow_fetch: bool = False,
) -> tuple[list[dict[str, Any]], Optional[float]]:
    """Update only the latest bar's OHLC from cache (weekly/monthly/etc.) — no new intraday bars."""
    if not bars:
        return bars, None
    snap = get_symbol_live_snapshot(symbol, allow_fetch=False)
    if allow_fetch and (not snap or _session_high_looks_stub(snap)):
        snap = get_symbol_live_snapshot(symbol, allow_fetch=True) or snap
    if not snap:
        return bars, None
    px = _finite_or_none(snap.get("price"))
    if px is None:
        return bars, None
    px = round(px, 2)
    prev = _finite_or_none(snap.get("previous_close"))
    hi = _finite_or_none(snap.get("high")) or px
    lo = _finite_or_none(snap.get("low")) or px
    out = [dict(b) for b in bars]
    last = out[-1]
    last["close"] = px
    last["high"] = round(max(float(last.get("high", px)), hi, px), 2)
    last["low"] = round(min(float(last.get("low", px)), lo, px), 2)
    last["live"] = True
    day_chg = _pct_change(px, prev) if prev else _finite_or_none(snap.get("change_pct"))
    return out, day_chg


def _session_high_looks_stub(snap: dict[str, Any]) -> bool:
    """True when cached high is missing or collapsed to LTP (pre-HOD / LTPC-only)."""
    hi = _positive_finite_or_none(snap.get("high"))
    px = _positive_finite_or_none(snap.get("price"))
    if hi is None:
        return True
    if px is not None and abs(hi - px) < 0.015:
        return True
    return False


def merge_live_into_chart_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str,
    *,
    allow_fetch: bool = False,
) -> tuple[list[dict[str, Any]], Optional[float]]:
    tf = str(timeframe or "1D").strip().upper()
    if tf == "1D":
        return merge_live_into_daily_bars(symbol, bars, timeframe, allow_fetch=allow_fetch)
    return merge_live_touch_last_bar(symbol, bars, allow_fetch=allow_fetch)


def _is_after_nse_cash_open(now: Optional[datetime] = None) -> bool:
    """True from 09:15 IST onward. Pre-open quotes must not become today's daily bar."""
    dt = now or datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return (dt.hour * 60 + dt.minute) >= (9 * 60 + 15)


def merge_live_into_daily_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str,
    *,
    allow_fetch: bool = False,
) -> tuple[list[dict[str, Any]], Optional[float]]:
    """Append or update today's 1D candle from the live quote in movers cache."""
    tf = str(timeframe or "1D").strip().upper()
    if tf != "1D" or not bars:
        return bars, None
    # Upstox/NSE pre-open quotes often carry prior-session OHLC/volume labeled as today.
    if not _is_after_nse_cash_open():
        return bars, None
    snap = get_symbol_live_snapshot(symbol, allow_fetch=False)
    if allow_fetch and (not snap or _session_high_looks_stub(snap)):
        snap = get_symbol_live_snapshot(symbol, allow_fetch=True) or snap
    if not snap:
        return bars, None

    today = datetime.now(IST).strftime("%Y-%m-%d")
    px = _positive_finite_or_none(snap.get("price"))
    if px is None:
        return bars, None
    px = round(px, 2)
    prev = _positive_finite_or_none(snap.get("previous_close"))
    vol = _finite_or_none(snap.get("volume")) or 0.0

    snap_open = _positive_finite_or_none(snap.get("open"))
    hi = _positive_finite_or_none(snap.get("high"))
    lo = _positive_finite_or_none(snap.get("low"))

    out = [dict(b) for b in bars]
    last = out[-1]
    last_day = str(last.get("time", ""))[:10]

    if last_day > today:
        return bars, None

    last_open = _positive_finite_or_none(last.get("open"))
    last_high = _positive_finite_or_none(last.get("high"))
    last_low = _positive_finite_or_none(last.get("low"))

    # Never use previous_close as today's open — that inverts candle color vs session.
    op = snap_open
    if op is None and last_day == today and last_open is not None:
        op = last_open
    if op is None:
        if last_day == today and last_open is not None:
            last["close"] = px
            hi_touch = hi if hi is not None else px
            lo_touch = lo if lo is not None else px
            last["high"] = round(max(last_high if last_high is not None else px, hi_touch, px), 2)
            last["low"] = round(min(last_low if last_low is not None else px, lo_touch, px), 2)
            if vol > 0:
                last["volume"] = round(vol, 2)
            last["live"] = True
            day_chg = _pct_change(px, prev) if prev else _finite_or_none(snap.get("change_pct"))
            return out, day_chg
        return bars, _pct_change(px, prev) if prev else _finite_or_none(snap.get("change_pct"))
    if hi is None:
        hi = px
    if lo is None:
        lo = px
    hi = max(hi, px, op)
    lo = min(lo, px, op)

    if last_day == today:
        last["close"] = px
        # Prefer session open from quote (9:15) over incomplete DB stub when available.
        last["open"] = round(op if snap_open is not None else (last_open if last_open is not None else op), 2)
        last["high"] = round(max(last_high if last_high is not None else px, hi, px, op), 2)
        last["low"] = round(min(last_low if last_low is not None else px, lo, px, op), 2)
        if vol > 0:
            last["volume"] = round(vol, 2)
        last["live"] = True
    else:
        out.append(
            {
                "time": today,
                "open": round(op, 2),
                "high": round(hi, 2),
                "low": round(lo, 2),
                "close": px,
                "volume": round(vol, 2),
                "live": True,
            }
        )

    day_chg = _pct_change(px, prev) if prev else _finite_or_none(snap.get("change_pct"))
    return out, day_chg


def movers_meta_live(conn, mcap_sql: str) -> dict[str, Any]:
    md = _load_movers_data_module()
    base = md.movers_meta(conn, mcap_sql)
    st = get_status()
    base["data_source"] = "live" if st.get("interval_seconds") else "eod"
    base["live_status"] = st
    base["note"] = (
        "Live: NSE snapshot + rotating quotes (15s–2m). "
        "RVOL/surge use intraday volume vs EOD history where available."
    )
    return base
