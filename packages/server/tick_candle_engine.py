"""Focus-symbol tick candle engine (1m + 1D).

Upstox ToS / product constraints (display-only showcase):
- Feed stays server-side; browser receives display snapshots for the authenticated session only.
- Focus full-mode is one chart symbol (see live_routes); do not fan out raw ticks publicly.
- Max two Upstox sockets are already used (focus + movers LTPC) — this module does not open more.
- Movers LTPC path must not call this engine (bandwidth / subscription limits).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _finite(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _positive(v: Any) -> Optional[float]:
    f = _finite(v)
    if f is None or f <= 0:
        return None
    return f


def ist_now() -> datetime:
    return datetime.now(IST)


def ist_minute_iso(ts_ms: Any = None) -> str:
    try:
        if ts_ms is not None:
            ts = int(ts_ms) / 1000.0
            dt = datetime.fromtimestamp(ts, tz=IST)
        else:
            dt = ist_now()
    except Exception:
        dt = ist_now()
    return dt.replace(second=0, microsecond=0).isoformat()


def ist_day_ymd(ts_ms: Any = None) -> str:
    try:
        if ts_ms is not None:
            ts = int(ts_ms) / 1000.0
            dt = datetime.fromtimestamp(ts, tz=IST)
        else:
            dt = ist_now()
    except Exception:
        dt = ist_now()
    return dt.strftime("%Y-%m-%d")


def apply_tick_to_minute(
    existing: Optional[dict[str, Any]],
    *,
    price: float,
    ts_ms: Any = None,
    volume: float = 0.0,
    source: str = "upstox_tick",
) -> dict[str, Any]:
    """Update or open the current 1-minute bucket from a trade/LTP tick."""
    px = float(price)
    minute = ist_minute_iso(ts_ms)
    prev = existing if isinstance(existing, dict) else None
    same = prev is not None and str(prev.get("time") or "") == minute
    if same:
        op = _positive(prev.get("open"))
        if op is None:
            op = px
        hi = max(x for x in (_positive(prev.get("high")), px, op) if x is not None)
        lo = min(x for x in (_positive(prev.get("low")), px, op) if x is not None)
        vol = float(prev.get("volume") or 0) + float(volume or 0)
        return {
            "time": minute,
            "open": round(op, 2),
            "high": round(hi, 2),
            "low": round(lo, 2),
            "close": round(px, 2),
            "volume": vol,
            "source": source,
            "final": False,
            "tf": "1m",
        }
    return {
        "time": minute,
        "open": round(px, 2),
        "high": round(px, 2),
        "low": round(px, 2),
        "close": round(px, 2),
        "volume": float(volume or 0),
        "source": source,
        "final": False,
        "tf": "1m",
    }


def apply_tick_to_day(
    existing: Optional[dict[str, Any]],
    *,
    price: float,
    ts_ms: Any = None,
    session_open: Optional[float] = None,
    session_high: Optional[float] = None,
    session_low: Optional[float] = None,
    volume: float = 0.0,
    source: str = "upstox_tick",
) -> dict[str, Any]:
    """Update today's session candle. Open locks once set (seed or first tick with open)."""
    px = float(price)
    day = ist_day_ymd(ts_ms)
    prev = existing if isinstance(existing, dict) else None
    same = prev is not None and str(prev.get("time") or "")[:10] == day

    seeded_open = _positive(session_open)
    prev_open = _positive(prev.get("open")) if same else None
    # Never invent open from LTP when we lack a session open — leave prior or omit.
    op = seeded_open if seeded_open is not None else prev_open

    hi_candidates = [
        _positive(session_high),
        _positive(prev.get("high")) if same else None,
        px,
        op,
    ]
    lo_candidates = [
        _positive(session_low),
        _positive(prev.get("low")) if same else None,
        px,
        op,
    ]
    hi_vals = [x for x in hi_candidates if x is not None]
    lo_vals = [x for x in lo_candidates if x is not None]
    hi = max(hi_vals) if hi_vals else px
    lo = min(lo_vals) if lo_vals else px
    vol_prev = float(prev.get("volume") or 0) if same else 0.0

    out: dict[str, Any] = {
        "time": day,
        "high": round(hi, 2),
        "low": round(lo, 2),
        "close": round(px, 2),
        "volume": vol_prev + float(volume or 0),
        "source": source,
        "final": False,
        "tf": "1D",
    }
    if op is not None:
        out["open"] = round(op, 2)
        out["high"] = round(max(hi, op), 2)
        out["low"] = round(min(lo, op), 2)
    return out


def focus_candle_bundle(
    minute: Optional[dict[str, Any]],
    day: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Display payload for authenticated /ws/live clients (not a raw tick republish)."""
    out: dict[str, Any] = {}
    if isinstance(minute, dict) and minute:
        out["1m"] = dict(minute)
    if isinstance(day, dict) and day:
        out["1D"] = dict(day)
    return out
