"""
Live quotes for Market Movers.

- Yahoo-primary (testbed): rotating yfinance batches + on-demand Yahoo first.
- Legacy: NSE bulk equity-stockIndices + rotating quote-equity batches.
- Client poll interval: 15 / 30 / 60 / 120 seconds only (configure via API).
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
_cache: dict[str, dict[str, Any]] = {}
_status: dict[str, Any] = {
    "interval_seconds": 0,
    "worker_running": False,
    "last_nse_refresh_at": None,
    "last_quote_refresh_at": None,
    "quote_source": "nse",
    "last_nse_error": None,
    "symbols_in_cache": 0,
    "market_open": False,
}
_stop = threading.Event()
_worker: Optional[threading.Thread] = None
_rotate_offset = 0
_all_symbols: list[str] = []
_get_db_connection: Optional[Callable[[], sqlite3.Connection]] = None
_last_bulk_refresh_ts = 0.0


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
    """Rotate Yahoo fast_info batches across the screener universe (no per-symbol NSE)."""
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
    entries = lqp.fetch_yfinance_quotes(batch)
    if entries:
        _merge_cache(entries)
    now = _iso_now()
    with _lock:
        _status["last_nse_refresh_at"] = now
        _status["last_quote_refresh_at"] = now
        _status["quote_source"] = "yfinance"
        _status["last_nse_error"] = None
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


def get_status() -> dict[str, Any]:
    with _lock:
        return {
            **_status,
            "symbols_in_cache": len(_cache),
            "market_open": _market_open(),
        }


def configure_poll_interval(seconds: int) -> dict[str, Any]:
    sec = int(seconds)
    if sec not in VALID_POLL_INTERVALS:
        sec = 0
    with _lock:
        _status["interval_seconds"] = sec
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
    out = {**e, "symbol": sym}
    if price is not None:
        out["price"] = price
    elif "price" in out:
        out.pop("price", None)
    if change_pct is not None:
        out["change_pct"] = change_pct
    elif "change_pct" in out:
        out.pop("change_pct", None)
    if prev_close is not None:
        out["previous_close"] = prev_close
    elif "previous_close" in out:
        out.pop("previous_close", None)
    if volume is not None:
        out["volume"] = volume
    elif "volume" in out:
        out.pop("volume", None)
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
            merged = {**prev, **clean}
            # Drop stale NaN keys left from older cache entries.
            for key in ("price", "change_pct", "volume", "previous_close"):
                if key in merged and _finite_or_none(merged[key]) is None:
                    merged.pop(key, None)
            px = _finite_or_none(merged.get("price"))
            pc = _finite_or_none(merged.get("previous_close"))
            if px is not None and pc is not None:
                chg = _pct_change(px, pc)
                if chg is not None:
                    merged["change_pct"] = chg
            _cache[sym] = merged


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
    """Yahoo-primary on testbed; legacy NSE bulk + quote-equity elsewhere."""
    global _last_bulk_refresh_ts
    if include_quotes is None:
        include_quotes = _market_open()
    if _yahoo_primary_enabled():
        if include_quotes:
            _run_yahoo_refresh_once()
        _last_bulk_refresh_ts = time_module.time()
        return
    _run_nse_refresh_once(include_quotes=include_quotes)


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
    """Refresh live quote cache when empty or older than BULK_REFRESH_MIN_SEC."""
    global _last_bulk_refresh_ts
    with _lock:
        cache_len = len(_cache)
        age = time_module.time() - _last_bulk_refresh_ts
    if cache_len >= 400 and age < BULK_REFRESH_MIN_SEC:
        return
    _run_live_refresh_once()


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

    if _yahoo_primary_enabled():
        try:
            from server import live_quote_providers as lqp

            yahoo_rows = lqp.fetch_yfinance_quotes(missing)
            if yahoo_rows:
                _merge_cache(yahoo_rows)
                entries.extend(yahoo_rows)
        except Exception as e:
            with _lock:
                _status["last_nse_error"] = str(e)
        fetched_syms = {str(e.get("symbol", "")).upper() for e in entries if e}
        still = [s for s in missing if s not in fetched_syms]
        if still:
            nse_cap = min(len(still), NSE_ON_DEMAND_FALLBACK_MAX)
            try:
                session = _make_session()
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=ON_DEMAND_QUOTE_WORKERS) as pool:
                    futures = {
                        pool.submit(_fetch_quote_equity, session, sym): sym
                        for sym in still[:nse_cap]
                    }
                    for fut in as_completed(futures):
                        row = fut.result()
                        if row:
                            entries.append(row)
                if entries:
                    _merge_cache(entries)
            except Exception as e:
                with _lock:
                    if not _status.get("last_nse_error"):
                        _status["last_nse_error"] = str(e)
        return len(entries)

    try:
        session = _make_session()
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=ON_DEMAND_QUOTE_WORKERS) as pool:
            futures = {pool.submit(_fetch_quote_equity, session, sym): sym for sym in missing}
            for fut in as_completed(futures):
                row = fut.result()
                if row:
                    entries.append(row)
        if entries:
            _merge_cache(entries)
    except Exception as e:
        with _lock:
            _status["last_nse_error"] = str(e)

    fetched_syms = {str(e.get("symbol", "")).upper() for e in entries if e}
    still = [s for s in missing if s not in fetched_syms]
    if still:
        try:
            from server import live_quote_providers as lqp

            fb, _err = lqp.fetch_live_quotes(still)
            if fb:
                _merge_cache(fb)
                entries.extend(fb)
                with _lock:
                    _status["last_nse_error"] = None
        except Exception as e:
            with _lock:
                if not _status.get("last_nse_error"):
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
    if df.empty or not live:
        return df
    md = _load_movers_data_module()
    out = df.copy()
    for idx, row in out.iterrows():
        sym = str(row.get("symbol", "")).upper()
        snap = live.get(sym)
        if not snap or not cache_quote_fresh(snap):
            continue
        live_price = _finite_or_none(snap.get("price"))
        if live_price is not None:
            out.at[idx, "price"] = round(live_price, 2)
        ref_close = _finite_or_none(snap.get("previous_close"))
        if ref_close is None:
            ref_close = _reference_close_from_row(row)
        live_chg = None
        if live_price is not None and ref_close is not None:
            live_chg = _pct_change(live_price, ref_close)
        if live_chg is None:
            live_chg = _finite_or_none(snap.get("change_pct"))
        existing_chg = _finite_or_none(row.get("change_pct"))
        if live_chg is not None and md.should_apply_live_day_change(existing_chg, live_chg):
            out.at[idx, "change_pct"] = round(live_chg, 2)
        live_vol = _finite_or_none(snap.get("volume"))
        if live_vol is not None:
            out.at[idx, "volume_today"] = live_vol
            vp = row.get("volume_prior")
            if vp is not None and not (isinstance(vp, float) and math.isnan(vp)) and float(vp) > 0:
                out.at[idx, "volume_change_pct"] = round(
                    (live_vol - float(vp)) / float(vp) * 100.0, 2
                )
            avg = row.get("avg_volume_20d")
            if avg is not None and not (isinstance(avg, float) and math.isnan(avg)) and float(avg) > 0:
                out.at[idx, "rvol_20d"] = round(live_vol / float(avg), 2)
        shares = row.get("issued_shares")
        price = _finite_or_none(out.at[idx, "price"])
        if shares is not None and price is not None and price > 0:
            try:
                sh = float(shares)
                if sh > 0:
                    out.at[idx, "market_cap"] = sh * price
            except (TypeError, ValueError):
                pass
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
    md = _load_movers_data_module()
    if refresh_quotes:
        _ensure_bulk_cache_fresh()
    else:
        with _lock:
            cache_len = len(_cache)
            age = time_module.time() - _last_bulk_refresh_ts
        if cache_len < 100 or age > 60:
            _ensure_bulk_cache_fresh()
    df = md.load_movers_universe(conn, mcap_sql)
    df = md.apply_session_day_adjustment(df)
    live = live_cache_snapshot()
    if live:
        df = apply_live_overlay(df, live)

    st = get_status()
    as_of = st.get("last_nse_refresh_at")
    on_demand_fetched = 0

    if mode == "day_change":
        df, on_demand_fetched = enrich_session_day_change(
            conn,
            mcap_sql,
            df,
            side or "gainers",
            limit,
            refresh_quotes=refresh_quotes,
        )
        live = live_cache_snapshot()
    df = md._apply_mcap_filter(df, min_mcap, max_mcap)
    df = md._apply_sector_filter(df, allowed_symbols)

    if mode == "day_change":
        side_n = (side or "gainers").strip().lower()
        df = df[df["change_pct"].apply(lambda v: _finite_or_none(v) is not None)]
        df = md.filter_day_change_by_side(df, side_n)
        ascending = side_n == "losers"
        if df.empty and live:
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
        return {
            "mode": "day_change",
            "side": side_n,
            "limit": limit,
            "data_source": "live",
            "as_of_date": as_of,
            "live_status": st,
            "count": len(rows),
            "data": rows,
        }

    vm = (volume_mode or "absolute").strip().lower()
    pre_sort_col = "volume_today"
    if vm == "surge":
        pre_sort_col = "volume_change_pct"
    elif vm == "rvol":
        pre_sort_col = "rvol_20d"
    pre = df[df[pre_sort_col].apply(lambda v: _finite_or_none(v) is not None)]
    pre = pre.sort_values(pre_sort_col, ascending=False, na_position="last")
    candidates = [str(s).upper() for s in pre.head(max(limit * 5, 150))["symbol"]]
    on_demand_fetched = _fetch_missing_quote_symbols(candidates) if refresh_quotes else 0
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
    return {
        "mode": "volume",
        "volume_mode": vm,
        "limit": limit,
        "data_source": "live",
        "as_of_date": as_of,
        "live_status": st,
        "count": len(rows),
        "data": rows,
    }


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
) -> tuple[list[dict[str, Any]], Optional[float]]:
    """Update only the latest bar's OHLC from cache (weekly/monthly/etc.) — no new intraday bars."""
    if not bars:
        return bars, None
    snap = get_symbol_live_snapshot(symbol, allow_fetch=False)
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


def merge_live_into_chart_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str,
) -> tuple[list[dict[str, Any]], Optional[float]]:
    tf = str(timeframe or "1D").strip().upper()
    if tf == "1D":
        return merge_live_into_daily_bars(symbol, bars, timeframe)
    return merge_live_touch_last_bar(symbol, bars)


def merge_live_into_daily_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str,
) -> tuple[list[dict[str, Any]], Optional[float]]:
    """Append or update today's 1D candle from the NSE live quote in movers cache."""
    tf = str(timeframe or "1D").strip().upper()
    if tf != "1D" or not bars:
        return bars, None
    snap = get_symbol_live_snapshot(symbol, allow_fetch=False)
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
        op = px
    if hi is None:
        hi = px
    if lo is None:
        lo = px
    hi = max(hi, px, op)
    lo = min(lo, px, op)

    if last_day == today:
        last["close"] = px
        last["open"] = round(last_open if last_open is not None else op, 2)
        last["high"] = round(max(last_high if last_high is not None else px, hi, px), 2)
        last["low"] = round(min(last_low if last_low is not None else px, lo, px), 2)
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
