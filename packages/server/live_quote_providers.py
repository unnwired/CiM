"""Live quote providers — NSE JSON where available, yfinance fallback (in-memory only)."""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

IST = timezone(timedelta(hours=5, minutes=30))

YFINANCE_WORKERS = 8
YFINANCE_SYMBOL_TIMEOUT_SEC = 4.0
PATCH_WALL_CLOCK_SEC = 18.0

_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-equity-market",
    "Origin": "https://www.nseindia.com",
}

_INDEX_YAHOO_TICKER = {
    "^NSEI": "^NSEI",
    "^NSEBANK": "^NSEBANK",
    "^CNXIT": "^CNXIT",
    "^CNXAUTO": "^CNXAUTO",
    "^CNXFMCG": "^CNXFMCG",
    "^CNXMETAL": "^CNXMETAL",
    "^CNXPHARMA": "^CNXPHARMA",
    "NIFTY_HEALTHCARE.NS": "NIFTY_HEALTHCARE.NS",
    "^CNXENERGY": "^CNXENERGY",
    "^CRSLDX": "^CRSLDX",
}

# Cached NSE allIndices map (session day) — avoid refetching every patch chunk.
_nse_indices_cache: dict[str, Any] = {"at": 0.0, "data": {}}
_NSE_INDICES_TTL_SEC = 45.0


def _iso_now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _finite(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if not math.isfinite(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _pct_change(px: Optional[float], prev: Optional[float]) -> Optional[float]:
    if px is None or prev is None or prev <= 0:
        return None
    return round((px - prev) / prev * 100.0, 2)


def _positive_finite(v: Any) -> Optional[float]:
    n = _finite(v)
    if n is None or n <= 0:
        return None
    return n


def _entry(
    symbol: str,
    *,
    price: Optional[float],
    previous_close: Optional[float] = None,
    change_pct: Optional[float] = None,
    source: str,
    volume: Optional[float] = None,
    open: Optional[float] = None,
    high: Optional[float] = None,
    low: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    px = _finite(price)
    if px is None:
        return None
    px = round(px, 2)
    prev = _finite(previous_close)
    if prev is not None:
        prev = round(prev, 2)
    chg = _finite(change_pct)
    if chg is None:
        chg = _pct_change(px, prev)
    out: dict[str, Any] = {
        "symbol": sym,
        "price": px,
        "change_pct": chg,
        "updated_at": _iso_now(),
        "source": source,
    }
    if prev is not None:
        out["previous_close"] = prev
    vol = _finite(volume)
    if vol is not None:
        out["volume"] = vol
    op = _positive_finite(open)
    if op is not None:
        out["open"] = round(op, 2)
    hi = _positive_finite(high)
    if hi is not None:
        out["high"] = round(hi, 2)
    lo = _positive_finite(low)
    if lo is not None:
        out["low"] = round(lo, 2)
    return out


def _warm_nse_session(session: requests.Session) -> None:
    try:
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=8)
    except Exception:
        pass


def _is_patchable_equity_symbol(symbol: str) -> bool:
    sym = str(symbol or "").strip().upper()
    if not sym or sym.startswith("^") or sym.startswith("NSE:"):
        return False
    # Skip commodities/FX mistaken for NSE tickers (e.g. GC=F).
    if "=" in sym or sym.endswith(".NS") and "=" in sym[:-3]:
        return False
    return True


def _equity_yahoo_ticker(symbol: str) -> Optional[str]:
    sym = str(symbol or "").strip().upper()
    if not _is_patchable_equity_symbol(sym) and not sym.startswith("^") and not sym.startswith("NSE:"):
        return None
    if sym.startswith("^") or sym.startswith("NSE:"):
        return _INDEX_YAHOO_TICKER.get(sym, sym)
    if sym.endswith(".NS"):
        return sym
    return f"{sym}.NS"


def _is_likely_index_symbol(symbol: str) -> bool:
    sym = str(symbol or "").strip().upper()
    return sym.startswith("^") or sym.startswith("NSE:")


def _fast_info_value(fi: Any, *keys: str) -> Optional[float]:
    for key in keys:
        try:
            if hasattr(fi, key):
                v = getattr(fi, key)
            elif isinstance(fi, dict):
                v = fi.get(key)
            else:
                v = None
            n = _finite(v)
            if n is not None:
                return n
        except Exception:
            continue
    return None


def _fetch_one_yfinance(symbol: str) -> Optional[dict[str, Any]]:
    ticker = _equity_yahoo_ticker(symbol)
    if not ticker:
        return None
    try:
        import yfinance as yf

        fi = yf.Ticker(ticker).fast_info
        px = _fast_info_value(fi, "last_price", "lastPrice")
        prev = _fast_info_value(fi, "previous_close", "previousClose")
        op = _fast_info_value(fi, "open", "regularMarketOpen")
        hi = _fast_info_value(fi, "day_high", "dayHigh")
        lo = _fast_info_value(fi, "day_low", "dayLow")
        vol = _fast_info_value(fi, "last_volume", "lastVolume")
        return _entry(
            symbol,
            price=px,
            previous_close=prev,
            open=op,
            high=hi,
            low=lo,
            volume=vol,
            source="yfinance",
        )
    except Exception:
        return None


def fetch_yfinance_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    """Batch download (one Yahoo round-trip) — stays under reverse-proxy timeouts."""
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ordered.append(sym)
    if not ordered:
        return []

    try:
        import yfinance as yf
    except ImportError:
        return []

    pairs: list[tuple[str, str]] = []
    for sym in ordered:
        ticker = _equity_yahoo_ticker(sym)
        if ticker:
            pairs.append((sym, ticker))
    if not pairs:
        return []

    entries_by_sym: dict[str, dict[str, Any]] = {}

    # Prefer fast_info — includes session open/high/low + LTP (daily download lacks intraday OHLC).
    workers = min(YFINANCE_WORKERS, max(1, len(pairs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one_yfinance, sym): sym for sym, _t in pairs}
        try:
            for fut in as_completed(futures, timeout=PATCH_WALL_CLOCK_SEC):
                try:
                    row = fut.result(timeout=YFINANCE_SYMBOL_TIMEOUT_SEC)
                    if row:
                        entries_by_sym[row["symbol"]] = row
                except Exception:
                    continue
        except Exception:
            pass

    if len(entries_by_sym) == len(pairs):
        return list(entries_by_sym.values())

    missing_pairs = [(sym, ticker) for sym, ticker in pairs if sym not in entries_by_sym]
    tickers = [t for _, t in missing_pairs]
    try:
        if len(tickers) == 1:
            frames = {tickers[0]: yf.download(tickers[0], period="5d", interval="1d", progress=False, threads=False)}
        elif tickers:
            frames = yf.download(
                tickers,
                period="5d",
                interval="1d",
                progress=False,
                threads=True,
                group_by="ticker",
            )
        else:
            frames = None
    except Exception:
        frames = None

    if frames is not None and not getattr(frames, "empty", True):
        for sym, ticker in missing_pairs:
            try:
                if len(tickers) == 1:
                    sub = frames
                else:
                    sub = frames[ticker] if ticker in frames.columns.get_level_values(0) else None
                if sub is None or getattr(sub, "empty", True):
                    continue
                closes = sub["Close"].dropna()
                if closes.empty:
                    continue
                px = _finite(closes.iloc[-1])
                prev = _finite(closes.iloc[-2]) if len(closes) > 1 else None
                ent = _entry(sym, price=px, previous_close=prev, source="yfinance")
                if ent:
                    entries_by_sym[sym] = ent
            except Exception:
                continue

    return list(entries_by_sym.values())


def fetch_upstox_quotes(
    symbols: list[str],
    *,
    index_names: Optional[dict[str, str]] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Upstox full quotes when Analytics Token is configured."""
    try:
        from server import upstox_client

        return upstox_client.fetch_quotes(symbols, index_names=index_names)
    except Exception as e:
        return [], str(e)


def fetch_primary_equity_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    """Equity live quotes — Upstox only (no Yahoo on regular path)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        if not _is_patchable_equity_symbol(sym):
            continue
        seen.add(sym)
        ordered.append(sym)
    if not ordered:
        return []

    try:
        from server import upstox_config

        if upstox_config.market_data_enabled():
            rows, _err = fetch_upstox_quotes(ordered)
            return rows or []
    except Exception:
        pass
    return []


def fetch_nse_all_indices() -> dict[str, dict[str, Any]]:
    """NSE /api/allIndices — cached briefly to keep patch requests fast."""
    import time as time_module

    now = time_module.time()
    if now - float(_nse_indices_cache.get("at") or 0) < _NSE_INDICES_TTL_SEC:
        cached = _nse_indices_cache.get("data")
        if isinstance(cached, dict) and cached:
            return cached

    session = requests.Session()
    session.headers.update(_SESSION_HEADERS)
    _warm_nse_session(session)
    try:
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=10)
        if r.status_code != 200:
            return {}
        rows = r.json().get("data") or []
    except Exception:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("index") or row.get("indexSymbol") or "").strip().upper()
        if not name:
            continue
        px = _finite(row.get("last"))
        prev = _finite(row.get("previousClose"))
        chg = _finite(row.get("percentChange"))
        if chg is None:
            chg = _finite(row.get("variation"))
        ent = _entry(name, price=px, previous_close=prev, change_pct=chg, source="nse_all_indices")
        if ent:
            out[name] = ent
            sym_key = str(row.get("indexSymbol") or "").strip().upper()
            if sym_key and sym_key != name:
                out[sym_key] = {**ent, "symbol": sym_key}
    _nse_indices_cache["at"] = now
    _nse_indices_cache["data"] = out
    return out


def fetch_live_quotes(
    symbols: list[str],
    *,
    index_names: Optional[dict[str, str]] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    index_names = index_names or {}
    equity: list[str] = []
    indices: list[str] = []
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        if _is_likely_index_symbol(sym):
            indices.append(sym)
        elif _is_patchable_equity_symbol(sym):
            equity.append(sym)

    entries: list[dict[str, Any]] = []
    errors: list[str] = []

    upstox_enabled = False
    try:
        from server import upstox_config

        upstox_enabled = upstox_config.market_data_enabled()
    except Exception:
        upstox_enabled = False

    if indices:
        idx_entries: list[dict[str, Any]] = []
        if upstox_enabled:
            ux_rows, ux_err = fetch_upstox_quotes(indices, index_names=index_names)
            if ux_rows:
                idx_entries.extend(ux_rows)
            if ux_err and not ux_rows:
                errors.append(ux_err)
        elif indices:
            errors.append("Upstox market data is not configured for indices.")
        entries.extend(idx_entries)

    if equity:
        if upstox_enabled:
            ux_rows, ux_err = fetch_upstox_quotes(equity)
            got = {r["symbol"] for r in ux_rows}
            entries.extend(ux_rows)
            if ux_err and len(got) < len(equity):
                errors.append(ux_err)
            if len(got) < len(equity):
                errors.append(f"Upstox miss for {len(equity) - len(got)} equity symbol(s).")
        else:
            errors.append("Upstox market data is not configured.")

    if not entries and symbols:
        errors.append("Live quote providers returned no data.")

    err = "; ".join(errors) if errors else None
    return entries, err
