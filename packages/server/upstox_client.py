"""Upstox REST client — market quotes and historical candles (Analytics Token)."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

import requests

from server import upstox_config, upstox_instruments

IST = timezone(timedelta(hours=5, minutes=30))
API_BASE = "https://api.upstox.com"
QUOTE_BATCH_SIZE = 500
REQUEST_TIMEOUT_SEC = 30.0

# Shared last-error for movers /admin status (never stores the token).
_last_error: Optional[str] = None


def last_error() -> Optional[str]:
    return _last_error


def _set_last_error(msg: Optional[str]) -> None:
    global _last_error
    _last_error = (str(msg).strip() or None) if msg else None


def _encode_instrument_key(instrument_key: str) -> str:
    return quote(str(instrument_key or "").strip(), safe="")


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


def _auth_headers() -> dict[str, str]:
    token = upstox_config.analytics_token()
    if not token:
        raise RuntimeError("UPSTOX_ANALYTICS_TOKEN is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _iso_now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _quote_entry_from_payload(symbol: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    px = _finite(payload.get("last_price"))
    if px is None:
        px = _finite((payload.get("ohlc") or {}).get("close"))
    if px is None:
        return None
    px = round(px, 2)
    net_chg = _finite(payload.get("net_change"))
    prev = None
    if net_chg is not None:
        prev = round(px - net_chg, 2)
    ohlc = payload.get("ohlc") if isinstance(payload.get("ohlc"), dict) else {}
    op = _finite(ohlc.get("open"))
    hi = _finite(ohlc.get("high"))
    lo = _finite(ohlc.get("low"))
    vol = _finite(payload.get("volume"))
    change_pct = None
    if net_chg is not None and prev is not None and prev > 0:
        change_pct = round(net_chg / prev * 100.0, 2)
    out: dict[str, Any] = {
        "symbol": sym,
        "price": px,
        "change_pct": change_pct,
        "updated_at": _iso_now(),
        "source": "upstox",
    }
    if prev is not None and prev > 0:
        out["previous_close"] = prev
    if op is not None and op > 0:
        out["open"] = round(op, 2)
    if hi is not None and hi > 0:
        out["high"] = round(hi, 2)
    if lo is not None and lo > 0:
        out["low"] = round(lo, 2)
    if vol is not None:
        out["volume"] = vol
    return out


def _fetch_quote_batch(key_to_symbol: dict[str, str]) -> list[dict[str, Any]]:
    if not key_to_symbol:
        return []
    keys = list(key_to_symbol.keys())
    params: list[tuple[str, str]] = [("instrument_key", k) for k in keys]
    r = requests.get(
        f"{API_BASE}/v2/market-quote/quotes",
        params=params,
        headers=_auth_headers(),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    if r.status_code == 401:
        raise PermissionError("Upstox Analytics Token rejected (401)")
    r.raise_for_status()
    body = r.json()
    if str(body.get("status") or "").lower() != "success":
        return []
    data = body.get("data") or {}
    if not isinstance(data, dict):
        return []
    # Response keys may be URL-encoded instrument_key; payload may carry instrument_key or token.
    entries: list[dict[str, Any]] = []
    for resp_key, payload in data.items():
        if not isinstance(payload, dict):
            continue
        sym = None
        for candidate in (
            str(payload.get("instrument_key") or "").strip(),
            str(resp_key or "").strip(),
            str(payload.get("instrument_token") or "").strip(),
        ):
            if candidate and candidate in key_to_symbol:
                sym = key_to_symbol[candidate]
                break
        if not sym:
            from urllib.parse import unquote

            decoded = unquote(str(resp_key or "").strip())
            sym = key_to_symbol.get(decoded)
        if not sym:
            sym = str(payload.get("symbol") or "").strip().upper()
        ent = _quote_entry_from_payload(sym, payload)
        if ent:
            entries.append(ent)
    return entries


def fetch_quotes(
    symbols: list[str],
    *,
    index_names: Optional[dict[str, str]] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """
    Full market quotes for CiM symbols.
    Returns (entries, error_message).
    """
    if not upstox_config.market_data_enabled():
        err = "Upstox market data is not configured"
        _set_last_error(err)
        return [], err

    try:
        upstox_instruments.instrument_map()
    except Exception as e:
        err = f"Upstox instrument map unavailable: {e}"
        _set_last_error(err)
        return [], err

    sym_to_key, unresolved = upstox_instruments.resolve_instrument_keys(
        symbols,
        index_names=index_names,
    )
    if not sym_to_key:
        err = "No Upstox instrument keys resolved"
        if unresolved:
            err += f" ({len(unresolved)} symbols)"
        _set_last_error(err)
        return [], err

    key_to_symbol = {v: k for k, v in sym_to_key.items()}
    entries: list[dict[str, Any]] = []
    keys = list(key_to_symbol.keys())
    try:
        for i in range(0, len(keys), QUOTE_BATCH_SIZE):
            batch_keys = keys[i : i + QUOTE_BATCH_SIZE]
            batch_map = {k: key_to_symbol[k] for k in batch_keys}
            entries.extend(_fetch_quote_batch(batch_map))
    except PermissionError as e:
        _set_last_error(str(e))
        return entries, str(e)
    except requests.RequestException as e:
        err = f"Upstox quote request failed: {e}"
        _set_last_error(err)
        return entries, err

    got = {e["symbol"] for e in entries}
    if unresolved or len(got) < len(sym_to_key):
        missing_n = len(sym_to_key) - len(got) + len(unresolved)
        if missing_n > 0 and entries:
            err = f"Upstox returned no quote for {missing_n} symbol(s)"
            _set_last_error(err)
            return entries, err
        if not entries:
            err = f"Upstox returned no quotes ({missing_n} unresolved)"
            _set_last_error(err)
            return [], err
    _set_last_error(None)
    return entries, None


def fetch_historical_daily(
    instrument_key: str,
    from_date: date,
    to_date: date,
) -> list[list[Any]]:
    """V3 daily candles — each row [timestamp, open, high, low, close, volume, oi]."""
    key = _encode_instrument_key(instrument_key)
    path = (
        f"/v3/historical-candle/{key}/days/1/"
        f"{to_date.isoformat()}/{from_date.isoformat()}"
    )
    r = requests.get(
        f"{API_BASE}{path}",
        headers=_auth_headers(),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    r.raise_for_status()
    body = r.json()
    if str(body.get("status") or "").lower() != "success":
        return []
    candles = (body.get("data") or {}).get("candles") or []
    return candles if isinstance(candles, list) else []


def fetch_historical_minutes(
    instrument_key: str,
    interval: str,
    from_date: date,
    to_date: date,
) -> list[list[Any]]:
    """V3 historical minute candles (backfill). Interval e.g. '5' for 5 minutes."""
    key = _encode_instrument_key(instrument_key)
    path = (
        f"/v3/historical-candle/{key}/minutes/{interval}/"
        f"{to_date.isoformat()}/{from_date.isoformat()}"
    )
    r = requests.get(
        f"{API_BASE}{path}",
        headers=_auth_headers(),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    r.raise_for_status()
    body = r.json()
    if str(body.get("status") or "").lower() != "success":
        return []
    candles = (body.get("data") or {}).get("candles") or []
    return candles if isinstance(candles, list) else []


def fetch_intraday_minutes(
    instrument_key: str,
    interval: str = "5",
) -> list[list[Any]]:
    """V3 intraday candles for the current session."""
    key = _encode_instrument_key(instrument_key)
    path = f"/v3/historical-candle/intraday/{key}/minutes/{interval}"
    r = requests.get(
        f"{API_BASE}{path}",
        headers=_auth_headers(),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    r.raise_for_status()
    body = r.json()
    if str(body.get("status") or "").lower() != "success":
        return []
    candles = (body.get("data") or {}).get("candles") or []
    return candles if isinstance(candles, list) else []
