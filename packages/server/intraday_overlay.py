"""Stateless intraday overlay — live fetch only, never writes shared DB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from server import live_quote_providers, movers_live

IST = timezone(timedelta(hours=5, minutes=30))
# Must finish within ~25s (Tailscale funnel / Cloudflare tunnel ~30s origin limit).
MAX_SYMBOLS_PER_REQUEST = 12


def _finite(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _positive_finite(v: Any) -> float | None:
    """OHLC must be > 0 — zero poisons candle merge (0→price spike)."""
    f = _finite(v)
    if f is None or f <= 0:
        return None
    return f


def _index_name_map(symbols: list[str]) -> dict[str, str]:
    wanted = {str(s or "").strip().upper() for s in symbols if s}
    if not wanted:
        return {}
    out: dict[str, str] = {}
    getter = movers_live._get_db_connection
    if getter is None:
        return out
    try:
        conn = getter()
        try:
            cur = conn.cursor()
            ph = ",".join("?" * len(wanted))
            cur.execute(
                f"SELECT symbol, name FROM indices WHERE UPPER(TRIM(symbol)) IN ({ph})",
                tuple(wanted),
            )
            for sym, name in cur.fetchall():
                key = str(sym or "").strip().upper()
                nm = str(name or key).strip()
                if key and nm:
                    out[key] = nm
        finally:
            conn.close()
    except Exception:
        pass
    return out


def fetch_patch(symbols: list[str]) -> dict[str, Any]:
    """Fetch live quotes for symbols; returns per-symbol snapshot dict."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ordered.append(sym)
        if len(ordered) >= MAX_SYMBOLS_PER_REQUEST:
            break

    provider_error: str | None = None
    if ordered:
        # Fast path: NSE quote-equity is blocked on showcase hosts — skip slow bulk/quote NSE.
        idx_names = _index_name_map(ordered)
        extra, provider_error = live_quote_providers.fetch_live_quotes(
            ordered,
            index_names=idx_names,
        )
        if extra:
            movers_live._merge_cache(extra)

    cache = movers_live.live_cache_snapshot()
    as_of = datetime.now(IST).isoformat()
    out: dict[str, dict[str, Any]] = {}
    for sym in ordered:
        snap = cache.get(sym) or {}
        if not movers_live.cache_quote_fresh(snap):
            continue
        price = _positive_finite(snap.get("price"))
        if price is None:
            continue
        out[sym] = {
            "price": round(price, 2),
            "open": _positive_finite(snap.get("open")),
            "high": _positive_finite(snap.get("high")),
            "low": _positive_finite(snap.get("low")),
            "volume": _finite(snap.get("volume")),
            "previous_close": _positive_finite(snap.get("previous_close")),
            "change_pct": _finite(snap.get("change_pct")),
            "as_of": as_of,
            "source": snap.get("source"),
        }

    session_intraday = False
    try:
        session_intraday = bool(movers_live._load_movers_data_module()._session_day_intraday_active())
    except Exception:
        pass

    return {
        "as_of": as_of,
        "symbols": out,
        "requested": len(ordered),
        "returned": len(out),
        "nse_error": provider_error if not out else None,
        "session_intraday": session_intraday,
    }
