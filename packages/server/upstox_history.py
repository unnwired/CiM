"""Upstox historical candles — daily + minutes with rate control and Yahoo-style row shape."""
from __future__ import annotations

import os
import threading
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from server import upstox_adjust, upstox_client, upstox_config, upstox_instruments

IST = ZoneInfo("Asia/Kolkata")
DAILY_CHUNK_DAYS = 3650  # ~10 years (Upstox daily max window)
MINUTE_CHUNK_DAYS = 28  # ~1 month for 1–15m historical
MIN_REQUEST_INTERVAL_SEC = 0.03  # stay under ~50 req/s
# Parallel history workers (shared rate limiter). Override via CIM_UPSTOX_HISTORY_WORKERS.
HISTORY_WORKERS = max(1, min(32, int(os.getenv("CIM_UPSTOX_HISTORY_WORKERS", "12") or "12")))


_last_request_ts = 0.0
_throttle_lock = threading.Lock()
_data_dir: Optional[Path] = None


def configure_paths(*, data_dir: Path) -> None:
    global _data_dir
    _data_dir = Path(data_dir)


def _throttle() -> None:
    global _last_request_ts
    with _throttle_lock:
        now = time_module.time()
        wait = MIN_REQUEST_INTERVAL_SEC - (now - _last_request_ts)
        if wait > 0:
            time_module.sleep(wait)
        _last_request_ts = time_module.time()


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _candle_ts_to_daily_str(ts: Any) -> Optional[str]:
    s = str(ts or "").strip()
    if len(s) < 10:
        return None
    return s[:10] + " 00:00:00+05:30"


def _candle_ts_to_dt(ts: Any) -> Optional[datetime]:
    s = str(ts or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except ValueError:
        d = _as_date(s)
        return datetime(d.year, d.month, d.day, tzinfo=IST)


def _parse_ohlcv(candle: Sequence[Any]) -> Optional[tuple[Any, float, float, float, float, float]]:
    if not isinstance(candle, (list, tuple)) or len(candle) < 6:
        return None
    try:
        o, h, l, c = float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4])
        v = float(candle[5] or 0)
    except (TypeError, ValueError):
        return None
    if c <= 0:
        return None
    return candle[0], round(o, 2), round(h, 2), round(l, 2), round(c, 2), round(v, 2)


def _date_windows(from_d: date, to_d: date, chunk_days: int) -> list[tuple[date, date]]:
    if from_d > to_d:
        return []
    windows: list[tuple[date, date]] = []
    cur = from_d
    step = timedelta(days=max(1, chunk_days))
    while cur <= to_d:
        end = min(cur + step - timedelta(days=1), to_d)
        windows.append((cur, end))
        cur = end + timedelta(days=1)
    return windows


def _ist_today() -> date:
    return datetime.now(IST).date()


def _is_nse_session_day(d: date) -> bool:
    """True on NSE cash session days (Mon–Fri not holiday, or special weekend session)."""
    try:
        from movers_data import _is_nse_session_day as _md_session

        return bool(_md_session(d))
    except Exception:
        pass
    try:
        from server.movers_data import _is_nse_session_day as _md_session

        return bool(_md_session(d))
    except Exception:
        # Weekday fallback if calendar helpers unavailable.
        return d.weekday() < 5


def _is_after_nse_cash_open(now: Optional[datetime] = None) -> bool:
    """True from 09:15 IST onward (cash open). Pre-open quotes must not become today's bar."""
    dt = now or datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    mins = dt.hour * 60 + dt.minute
    return mins >= (9 * 60 + 15)


def _filter_session_day_bars(rows: list[tuple]) -> list[tuple]:
    """Drop Sat/Sun/holiday bars so weekends never land in daily history."""
    out: list[tuple] = []
    for row in rows or []:
        try:
            day = date.fromisoformat(str(row[0])[:10])
        except ValueError:
            continue
        if _is_nse_session_day(day):
            out.append(row)
    return out


def _daily_bar_from_quote_entry(entry: dict[str, Any]) -> Optional[tuple]:
    """
    Build today's forming daily bar from an Upstox market quote.
    Historical /days candles omit the incomplete session day — quotes fill that gap.
    Only after cash open on an NSE session day (never pre-open / weekend / holiday).
    """
    if not isinstance(entry, dict):
        return None
    today = _ist_today()
    if not _is_nse_session_day(today):
        return None
    if not _is_after_nse_cash_open():
        return None
    px = entry.get("price")
    try:
        close = float(px) if px is not None else 0.0
    except (TypeError, ValueError):
        return None
    if close <= 0:
        return None
    try:
        op = float(entry["open"]) if entry.get("open") is not None else close
        hi = float(entry["high"]) if entry.get("high") is not None else max(op, close)
        lo = float(entry["low"]) if entry.get("low") is not None else min(op, close)
        vol = float(entry.get("volume") or 0)
    except (TypeError, ValueError):
        return None
    if op <= 0:
        op = close
    hi = max(hi, op, close)
    lo = min(lo, op, close) if lo > 0 else min(op, close)
    day = today.isoformat() + " 00:00:00+05:30"
    return (day, round(op, 2), round(hi, 2), round(lo, 2), round(close, 2), round(vol, 2))


def _merge_today_quote_bars(
    result: dict[str, list[tuple]],
    symbols: Sequence[str],
    *,
    stats: dict[str, Any],
) -> None:
    """Batch-quote symbols missing today's bar and merge into result (after cash open only)."""
    if not _is_nse_session_day(_ist_today()):
        return
    if not _is_after_nse_cash_open():
        return
    today_s = _ist_today().isoformat()
    need = []
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        rows = result.get(sym) or []
        if any(str(r[0])[:10] == today_s for r in rows):
            continue
        need.append(sym)
    if not need:
        return
    try:
        entries, qerr = upstox_client.fetch_quotes(need)
    except Exception as e:
        stats.setdefault("errors", []).append(f"today quote batch: {e}")
        return
    if qerr and not entries:
        stats.setdefault("errors", []).append(str(qerr)[:200])
        return
    filled = 0
    got_syms: set[str] = set()
    for ent in entries or []:
        sym = str((ent or {}).get("symbol") or "").strip().upper()
        if not sym:
            continue
        bar = _daily_bar_from_quote_entry(ent)
        if not bar:
            continue
        existing = list(result.get(sym) or [])
        existing = [r for r in existing if str(r[0])[:10] != today_s]
        existing.append(bar)
        existing.sort(key=lambda r: str(r[0])[:10])
        result[sym] = existing
        filled += 1
        got_syms.add(sym)

    # Retry one symbol at a time for keys that batch quote missed.
    for sym in need:
        if sym in got_syms:
            continue
        try:
            retry_entries, _ = upstox_client.fetch_quotes([sym])
        except Exception:
            continue
        for ent in retry_entries or []:
            rsym = str((ent or {}).get("symbol") or "").strip().upper()
            if rsym != sym:
                continue
            bar = _daily_bar_from_quote_entry(ent)
            if not bar:
                continue
            existing = list(result.get(sym) or [])
            existing = [r for r in existing if str(r[0])[:10] != today_s]
            existing.append(bar)
            existing.sort(key=lambda r: str(r[0])[:10])
            result[sym] = existing
            filled += 1
            break
    if filled:
        stats["today_quote"] = int(stats.get("today_quote") or 0) + filled


def fetch_daily_for_symbol(
    symbol: str,
    start_date: date | datetime,
    end_date: date | datetime,
    *,
    adjust: bool = True,
) -> tuple[list[tuple], Optional[str]]:
    """
    Daily OHLCV as (date_str, o, h, l, c, v) matching scrape_daily.write_rows.
    Equities and NSE indices (via resolve_index_key). Returns (rows, error_or_None).
    """
    if not upstox_config.market_data_enabled():
        return [], "Upstox market data is not configured"

    sym = str(symbol or "").strip().upper()
    raw = str(symbol or "").strip()
    is_index = False
    try:
        from server.cim_index_catalog import is_cim_index_symbol

        is_index = is_cim_index_symbol(raw) or is_cim_index_symbol(sym)
    except Exception:
        is_index = (
            sym.startswith("^")
            or sym.startswith("NSE:")
            or sym.startswith("NIFTY_")
            or sym == "INDIA_VIX"
            or (sym.endswith(".NS") and "NIFTY" in sym)
        )

    key = None
    if is_index:
        key = upstox_instruments.resolve_index_key(raw) or upstox_instruments.resolve_index_key(sym)
    else:
        key = upstox_instruments.resolve_equity_key(sym)
    if not key:
        return [], f"No Upstox instrument key for {sym}"

    from_d = _as_date(start_date)
    to_d = _as_date(end_date)
    today = _ist_today()
    # Historical daily endpoint has no incomplete session candle — stop at yesterday.
    hist_to = min(to_d, today - timedelta(days=1))
    raw_rows: list[tuple] = []
    try:
        if from_d <= hist_to:
            for win_from, win_to in _date_windows(from_d, hist_to, DAILY_CHUNK_DAYS):
                _throttle()
                candles = upstox_client.fetch_historical_daily(key, win_from, win_to)
                for candle in candles:
                    parsed = _parse_ohlcv(candle)
                    if not parsed:
                        continue
                    ts, o, h, l, c, v = parsed
                    date_str = _candle_ts_to_daily_str(ts)
                    if not date_str:
                        continue
                    raw_rows.append((date_str, o, h, l, c, v))
    except Exception as e:
        return [], str(e)

    by_day: dict[str, tuple] = {}
    for row in raw_rows:
        by_day[str(row[0])[:10]] = row
    rows = [by_day[k] for k in sorted(by_day.keys())]

    # Corporate-action adjust applies to equities only (completed days).
    if adjust and not is_index and rows:
        rows = upstox_adjust.adjust_ohlcv_rows(sym, rows, data_dir=_data_dir)
        rows = [tuple(r) if not isinstance(r, tuple) else r for r in rows]

    # Session day only: append/replace today from live Upstox quote (not Yahoo).
    # Weekends/holidays must not get a cloned Friday bar stamped as "today".
    if to_d >= today and from_d <= today and _is_nse_session_day(today):
        today_s = today.isoformat()
        if not any(str(r[0])[:10] == today_s for r in rows):
            try:
                entries, _qerr = upstox_client.fetch_quotes([sym])
            except Exception as e:
                if not rows:
                    return [], str(e)
                return _filter_session_day_bars(rows), None
            for ent in entries or []:
                if str((ent or {}).get("symbol") or "").strip().upper() != sym:
                    continue
                bar = _daily_bar_from_quote_entry(ent)
                if bar:
                    rows = [r for r in rows if str(r[0])[:10] != today_s]
                    rows.append(bar)
                    rows.sort(key=lambda r: str(r[0])[:10])
                break

    rows = _filter_session_day_bars(rows)
    if not rows:
        return [], None
    return rows, None


def fetch_daily_batch(
    symbols: Sequence[str],
    start_date: date | datetime,
    end_date: date | datetime,
    *,
    adjust: bool = True,
) -> tuple[dict[str, list[tuple]], dict[str, Any]]:
    """
    Fetch daily candles for many symbols.
    Completed days: Upstox historical daily. Session day: Upstox market quotes
    (historical /days omits the incomplete candle — that was causing Yahoo fallback).
    """
    result: dict[str, list[tuple]] = {}
    stats: dict[str, Any] = {
        "upstox": 0,
        "failed": 0,
        "unresolved": 0,
        "today_quote": 0,
        "errors": [],
        "source": "upstox",
    }
    if not upstox_config.market_data_enabled():
        stats["errors"].append("Upstox market data is not configured")
        return {}, stats

    try:
        upstox_instruments.instrument_map()
    except Exception as e:
        stats["errors"].append(f"instrument map: {e}")
        return {}, stats

    from_d = _as_date(start_date)
    to_d = _as_date(end_date)
    today = _ist_today()
    today_only = from_d == today and to_d == today
    wanted = [str(s or "").strip().upper() for s in symbols if str(s or "").strip()]

    if not today_only:
        hist_to = min(to_d, today - timedelta(days=1))
        if from_d <= hist_to:
            workers = min(HISTORY_WORKERS, max(1, len(wanted)))

            def _one(sym: str) -> tuple[str, list[tuple], Optional[str]]:
                rows, err = fetch_daily_for_symbol(sym, from_d, hist_to, adjust=adjust)
                return sym, rows or [], err

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [pool.submit(_one, sym) for sym in wanted]
                for fut in as_completed(futs):
                    try:
                        sym, rows, err = fut.result()
                    except Exception as e:
                        stats["errors"].append(str(e))
                        continue
                    if rows:
                        result[sym] = rows
                    elif err and "instrument key" in err.lower():
                        stats["unresolved"] += 1
                        stats["errors"].append(f"{sym}: {err}")
                    elif err:
                        stats["errors"].append(f"{sym}: {err}")

    if to_d >= today and from_d <= today:
        _merge_today_quote_bars(result, wanted, stats=stats)

    for sym in list(result.keys()):
        result[sym] = _filter_session_day_bars(result.get(sym) or [])
        if not result[sym]:
            result.pop(sym, None)

    stats["upstox"] = sum(1 for s in wanted if result.get(s))
    stats["failed"] = sum(1 for s in wanted if not result.get(s))
    if stats["errors"]:
        stats["errors"] = list(stats["errors"])[:20]
    return result, stats


def fetch_minutes_for_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    interval: str = "5",
    adjust: bool = True,
) -> tuple[list[tuple], Optional[str]]:
    """
    5m (or other minute) bars as (dt, o, h, l, c, v) in IST — matches bars_4h row shape.
    Uses historical minutes for past windows and intraday endpoint when window includes today.
    """
    if not upstox_config.market_data_enabled():
        return [], "Upstox market data is not configured"

    sym = str(symbol or "").strip().upper()
    key = upstox_instruments.resolve_equity_key(sym)
    if not key:
        # Indices
        key = upstox_instruments.resolve_index_key(sym)
    if not key:
        return [], f"No Upstox instrument key for {sym}"

    start_ist = start.astimezone(IST) if start.tzinfo else start.replace(tzinfo=IST)
    end_ist = end.astimezone(IST) if end.tzinfo else end.replace(tzinfo=IST)
    today = datetime.now(IST).date()
    raw: list[tuple] = []

    try:
        # Historical portion (exclude today — use intraday for session)
        hist_end = min(end_ist.date(), today - timedelta(days=1)) if end_ist.date() >= today else end_ist.date()
        hist_start = start_ist.date()
        if hist_start <= hist_end:
            for win_from, win_to in _date_windows(hist_start, hist_end, MINUTE_CHUNK_DAYS):
                _throttle()
                candles = upstox_client.fetch_historical_minutes(key, interval, win_from, win_to)
                for candle in candles:
                    parsed = _parse_ohlcv(candle)
                    if not parsed:
                        continue
                    ts, o, h, l, c, v = parsed
                    dt = _candle_ts_to_dt(ts)
                    if not dt or dt < start_ist or dt > end_ist:
                        continue
                    raw.append((dt, o, h, l, c, v))

        if end_ist.date() >= today and start_ist.date() <= today:
            _throttle()
            candles = upstox_client.fetch_intraday_minutes(key, interval=interval)
            for candle in candles:
                parsed = _parse_ohlcv(candle)
                if not parsed:
                    continue
                ts, o, h, l, c, v = parsed
                dt = _candle_ts_to_dt(ts)
                if not dt or dt < start_ist or dt > end_ist:
                    continue
                raw.append((dt, o, h, l, c, v))
    except Exception as e:
        return [], str(e)

    if not raw:
        return [], None

    by_ts: dict[str, tuple] = {}
    for row in raw:
        by_ts[row[0].isoformat()] = row
    rows = [by_ts[k] for k in sorted(by_ts.keys())]

    if adjust:
        # Convert to list rows with date string for adjust helper, then restore dt
        tmp = [(r[0].date().isoformat(), r[1], r[2], r[3], r[4], r[5]) for r in rows]
        adjusted = upstox_adjust.adjust_ohlcv_rows(sym, tmp, data_dir=_data_dir)
        restored: list[tuple] = []
        for orig, adj in zip(rows, adjusted):
            if isinstance(adj, (list, tuple)) and len(adj) >= 6:
                restored.append((orig[0], adj[1], adj[2], adj[3], adj[4], adj[5]))
            else:
                restored.append(orig)
        rows = restored
    return rows, None


def fetch_minutes_for_symbols(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    *,
    interval: str = "5",
) -> dict[str, list[tuple]]:
    wanted = [str(raw or "").strip().upper() for raw in symbols if str(raw or "").strip()]
    if not wanted:
        return {}
    out: dict[str, list[tuple]] = {}
    workers = min(HISTORY_WORKERS, max(1, len(wanted)))

    def _one(sym: str) -> tuple[str, list[tuple]]:
        rows, _err = fetch_minutes_for_symbol(sym, start, end, interval=interval)
        return sym, rows or []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, sym) for sym in wanted]
        for fut in as_completed(futs):
            try:
                sym, rows = fut.result()
            except Exception:
                continue
            if rows:
                out[sym] = rows
    return out


def repull_symbol_history(
    symbol: str,
    *,
    db_path: Path | str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict[str, Any]:
    """
    Re-fetch + re-adjust full daily history for one symbol after a split/bonus.
    Writes via scrape_daily.write_rows when available.
    """
    sym = str(symbol or "").strip().upper()
    start = from_date or date(2000, 1, 1)
    end = to_date or datetime.now(IST).date()
    rows, err = fetch_daily_for_symbol(sym, start, end, adjust=True)
    if err and not rows:
        return {"symbol": sym, "ok": False, "error": err, "rows": 0}
    if not rows:
        return {"symbol": sym, "ok": False, "error": "no rows", "rows": 0}

    try:
        import importlib.util
        import sqlite3
        from pathlib import Path as P

        # Prefer repo scrape_daily next to packages/
        repo = P(__file__).resolve().parents[2]
        scrape_path = repo / "scrape_daily.py"
        if not scrape_path.is_file():
            return {"symbol": sym, "ok": False, "error": "scrape_daily.py missing", "rows": len(rows)}
        spec = importlib.util.spec_from_file_location("scrape_daily_upstox_repull", scrape_path)
        if spec is None or spec.loader is None:
            return {"symbol": sym, "ok": False, "error": "cannot load scrape_daily", "rows": len(rows)}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        conn = sqlite3.connect(str(db_path), timeout=60.0)
        try:
            if hasattr(mod, "write_rows"):
                mod.write_rows(conn, sym, rows, overwrite=True)
            else:
                return {"symbol": sym, "ok": False, "error": "write_rows missing", "rows": len(rows)}
        finally:
            conn.close()
        return {"symbol": sym, "ok": True, "rows": len(rows), "source": "upstox"}
    except Exception as e:
        return {"symbol": sym, "ok": False, "error": str(e), "rows": len(rows)}
