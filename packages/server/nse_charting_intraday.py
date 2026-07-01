"""
NSE charting service 5-minute intraday fetch (fallback when Yahoo 5m is empty).

Uses GET https://charting.nseindia.com/v1/charts/symbolHistoricalData
(POST returns empty payloads as of 2026).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

IST = ZoneInfo("Asia/Kolkata")

HISTORICAL_URL = "https://charting.nseindia.com/v1/charts/symbolHistoricalData"
TOKEN_CONFIG_NAME = "nse_index_chart_tokens.json"

_SESSION: requests.Session | None = None


def _chart_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://charting.nseindia.com/",
            }
        )
        try:
            s.get("https://charting.nseindia.com/", timeout=15)
        except requests.RequestException:
            pass
        _SESSION = s
    return _SESSION


def load_nse_chart_token_map(base_dir: Path) -> dict[str, dict[str, str]]:
    path = base_dir / "config" / TOKEN_CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict[str, str]] = {}
        for sym, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            token = str(cfg.get("token") or "").strip()
            if not token:
                continue
            out[str(sym).strip().upper()] = {
                "token": token,
                "chartSymbol": str(cfg.get("chartSymbol") or sym).strip(),
            }
        return out
    except Exception:
        return {}


def get_nse_chart_token(symbol: str, base_dir: Path) -> Optional[dict[str, str]]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    return load_nse_chart_token_map(base_dir).get(sym)


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def parse_nse_charting_candles(payload: Any) -> list[tuple]:
    """Parse API JSON into (dt, o, h, l, c, v) rows matching bars_4h Yahoo shape."""
    if isinstance(payload, dict):
        inner = payload.get("data")
        candles = inner if isinstance(inner, list) else []
    elif isinstance(payload, list):
        candles = payload
    else:
        return []

    rows: list[tuple] = []
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        try:
            ts = candle.get("time") or candle.get("Timestamp") or candle.get("timestamp")
            if ts is None:
                continue
            ts_num = int(ts)
            if ts_num > 1_000_000_000_000:
                ts_num //= 1000
            # NSE charting encodes IST session wall-clock in UTC epoch slots (+5:30 skew).
            # Treat UTC hh:mm as IST hh:mm so 09:15–15:30 buckets align with NSE session.
            dt = datetime.fromtimestamp(ts_num, tz=timezone.utc).replace(tzinfo=IST)
            o = float(candle.get("open") or candle.get("Open") or 0)
            h = float(candle.get("high") or candle.get("High") or 0)
            low = float(candle.get("low") or candle.get("Low") or 0)
            c = float(candle.get("close") or candle.get("Close") or 0)
            v = float(candle.get("volume") or candle.get("Volume") or 0)
            if c <= 0:
                continue
            rows.append((dt, round(o, 2), round(h, 2), round(low, 2), round(c, 2), round(v, 2)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_nse_charting_5m(
    token: str,
    start: datetime,
    end: datetime,
    *,
    chart_symbol: str = "INDEX",
    pause_sec: float = 0.35,
) -> list[tuple]:
    """Fetch 5m index candles for [start, end] via NSE charting GET API."""
    tok = str(token or "").strip()
    if not tok:
        return []
    start_ist = _ensure_tz(start)
    end_ist = _ensure_tz(end)
    params = {
        "token": tok,
        "symbol": chart_symbol,
        "fromDate": int(start_ist.timestamp()),
        "toDate": int(end_ist.timestamp()),
        "exch": "N",
        "exchType": "C",
        "interval": "5",
        "chartType": "I",
        "timeInterval": "5",
        "symbolType": "Index",
    }
    try:
        r = _chart_session().get(HISTORICAL_URL, params=params, timeout=25)
        if r.status_code != 200:
            return []
        body = r.json()
        if not body.get("status"):
            return []
        return parse_nse_charting_candles(body.get("data"))
    except Exception:
        return []
    finally:
        if pause_sec > 0:
            time.sleep(pause_sec)
