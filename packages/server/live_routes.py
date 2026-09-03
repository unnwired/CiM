"""HTTP + WebSocket routes for Upstox focus live ticks + movers universe LTPC."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect

from server.upstox_stream_worker import (
    combined_status,
    focus_manager,
    manager as stream_manager,
    movers_manager,
    subscribe_movers_universe,
    unsubscribe_movers_universe,
)

router = APIRouter(tags=["live"])

_OHLC_SEED_SOURCES = frozenset(
    {"upstox", "upstox_session_seed", "nse_quote", "bulk", "yfinance"}
)


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


def _positive_finite(v: Any) -> Optional[float]:
    f = _finite(v)
    if f is None or f <= 0:
        return None
    return f


def _quote_rank(q: dict[str, Any]) -> int:
    """Higher = prefer for price/change when merging layers."""
    src = str(q.get("source") or "").strip().lower()
    if src in ("upstox_session_seed", "upstox_backfill"):
        return 4
    if src in _OHLC_SEED_SOURCES:
        return 3
    if src == "upstox_stream":
        return 2
    if src == "upstox_stream_ltpc":
        return 1
    return 0


def _merge_live_quote_layers(*layers: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Combine cache / movers LTPC / focus REST so session HOD is never dropped."""
    quotes = [q for q in layers if isinstance(q, dict) and q]
    if not quotes:
        return None
    sym = str(quotes[0].get("symbol") or "").strip().upper()
    merged: dict[str, Any] = {"symbol": sym} if sym else {}
    highs: list[float] = []
    lows: list[float] = []
    opens: list[tuple[int, float]] = []
    best_price: tuple[int, str, float] = (-1, "", 0.0)

    for q in quotes:
        if sym and not merged.get("symbol"):
            merged["symbol"] = str(q.get("symbol") or sym).strip().upper()
        px = _positive_finite(q.get("price"))
        rank = _quote_rank(q)
        updated = str(q.get("updated_at") or "")
        if px is not None and (rank, updated) >= (best_price[0], best_price[1]):
            best_price = (rank, updated, px)
            merged["price"] = round(px, 2)
        for field, bucket, agg in (
            ("high", highs, max),
            ("low", lows, min),
        ):
            val = _positive_finite(q.get(field))
            if val is not None:
                bucket.append(val)
        op = _positive_finite(q.get("open"))
        if op is not None:
            opens.append((rank, op))
        pc = _positive_finite(q.get("previous_close"))
        if pc is not None:
            merged["previous_close"] = round(pc, 2)
        chg = _finite(q.get("change_pct"))
        if chg is not None:
            merged["change_pct"] = round(chg, 2)
        vol = _finite(q.get("volume"))
        if vol is not None and vol >= 0:
            merged["volume"] = vol
        src = q.get("source")
        if src and rank >= merged.get("_rank", -1):
            merged["source"] = src
            merged["_rank"] = rank
        if updated:
            merged["updated_at"] = updated

    px = _positive_finite(merged.get("price"))
    if highs:
        merged["high"] = round(max(highs + ([px] if px is not None else [])), 2)
    elif px is not None:
        merged["high"] = round(px, 2)
    if lows:
        merged["low"] = round(min(lows + ([px] if px is not None else [])), 2)
    elif px is not None:
        merged["low"] = round(px, 2)
    if opens:
        opens.sort(key=lambda t: t[0], reverse=True)
        merged["open"] = round(opens[0][1], 2)
    elif px is not None:
        merged["open"] = round(px, 2)
    merged.pop("_rank", None)
    if px is None and merged.get("change_pct") is None:
        return None
    return merged


def _needs_rest_ohlc(q: dict[str, Any]) -> bool:
    """True when quote likely lacks authoritative session OHLC (LTPC stub)."""
    op = _positive_finite(q.get("open"))
    if op is None:
        return True
    hi = _positive_finite(q.get("high"))
    px = _positive_finite(q.get("price"))
    if hi is None:
        return True
    src = str(q.get("source") or "").strip().lower()
    if src in ("upstox_session_seed", "upstox", "nse_quote", "bulk", "yfinance"):
        return False
    if px is not None and abs(hi - px) < 0.015 and op is not None and abs(op - px) < 0.015:
        return True
    if px is not None and abs(hi - px) < 0.015:
        return True
    return False


def _enrich_session_ohlc(symbols: list[str], merged: dict[str, Any]) -> None:
    """REST day-quote seed for symbols still missing authoritative session high."""
    missing = [
        sym
        for sym in symbols
        if sym not in merged or _needs_rest_ohlc(merged.get(sym) or {})
    ]
    if not missing:
        return
    try:
        from server import movers_live, upstox_client, upstox_config

        if not upstox_config.market_data_enabled():
            return
        batch = missing[:12]
        entries, _err = upstox_client.fetch_quotes(batch)
        if entries:
            movers_live._merge_cache(entries)
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            sym = str(entry.get("symbol") or "").strip().upper()
            if not sym:
                continue
            combined = _merge_live_quote_layers(merged.get(sym), entry)
            if combined:
                merged[sym] = combined
    except Exception:
        pass


@router.get("/api/live/status")
def live_status():
    return combined_status()


@router.post("/api/live/subscribe")
def live_subscribe(body: dict = Body(default={})):
    context = str(body.get("context") or "focus").strip() or "focus"
    mode = str(body.get("mode") or "full").strip() or "full"
    raw = body.get("symbols")
    if isinstance(raw, str):
        symbols = [s.strip() for s in raw.split(",") if s.strip()]
    elif isinstance(raw, list):
        symbols = [str(s).strip() for s in raw if str(s).strip()]
    else:
        symbols = []
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols required")
    # Focus mode: only the first symbol (true live tick for chart focus).
    if context == "focus":
        symbols = symbols[:1]
        mode = "full"
    try:
        status = stream_manager.subscribe(context, symbols, mode=mode)
        if context == "focus" and symbols:
            stream_manager.seed_session_quotes_sync(symbols[:1])
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/live/unsubscribe")
def live_unsubscribe(body: dict = Body(default={})):
    context = str(body.get("context") or "focus").strip() or "focus"
    try:
        return stream_manager.unsubscribe(context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/live/movers/start")
def live_movers_start(body: dict = Body(default={})):
    """Start full-universe LTPC stream for Market Movers ranking."""
    raw = body.get("symbols") if isinstance(body, dict) else None
    symbols = None
    if isinstance(raw, list):
        symbols = [str(s).strip() for s in raw if str(s).strip()]
    elif isinstance(raw, str) and raw.strip():
        symbols = [s.strip() for s in raw.split(",") if s.strip()]
    try:
        return subscribe_movers_universe(symbols)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/live/movers/stop")
def live_movers_stop():
    try:
        return unsubscribe_movers_universe()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/live/quotes")
def live_quotes(symbols: str = Query("")):
    """Return cached live quotes for requested symbols.

    Merges focus-stream quotes with the movers universe LTPC cache so Market Movers
    can poll LTP/% for the visible table without flooding the browser WebSocket.
    """
    syms = [s.strip().upper() for s in str(symbols or "").split(",") if s.strip()]
    focus = (focus_manager.quotes(syms or None).get("symbols") or {})
    movers = (movers_manager.quotes(syms or None).get("symbols") or {})
    cache: dict[str, Any] = {}
    try:
        from server import movers_live

        cache = movers_live.live_cache_snapshot() or {}
    except Exception:
        cache = {}

    if syms:
        wanted = syms
    else:
        wanted = sorted(set(focus) | set(movers) | set(cache))

    merged: dict[str, Any] = {}
    for sym in wanted:
        q = _merge_live_quote_layers(cache.get(sym), movers.get(sym), focus.get(sym))
        if q:
            merged[sym] = q

    if syms:
        _enrich_session_ohlc(syms, merged)

    try:
        from datetime import datetime, timezone

        as_of = datetime.now(timezone.utc).isoformat()
    except Exception:
        as_of = None
    return {"as_of": as_of, "symbols": merged}


@router.get("/api/live/candles/{symbol}")
def live_candles(symbol: str):
    return stream_manager.candles(symbol)


class _WsHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, default=str)
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.remove(ws)


_hub = _WsHub()
_listener_loop: Optional[asyncio.AbstractEventLoop] = None


def _on_stream_quote(payload: dict[str, Any]) -> None:
    """Broadcast focus display snapshots only — never flood clients with movers ticks.

    Upstox ToS: authenticated session display only; no public raw-tick redistribution.
    """
    loop = _listener_loop
    if loop is None:
        return
    quotes = payload.get("quotes") or {}
    if not quotes and not payload.get("candles"):
        return
    msg = {
        "type": "snapshot",
        "quotes": quotes,
        "candles": payload.get("candles") or {},
        "status": combined_status(),
    }
    try:
        asyncio.run_coroutine_threadsafe(_hub.broadcast(msg), loop)
    except Exception:
        pass


@router.websocket("/ws/live")
async def live_websocket(websocket: WebSocket):
    global _listener_loop
    await websocket.accept()
    await _hub.add(websocket)
    _listener_loop = asyncio.get_running_loop()
    stream_manager.add_listener(_on_stream_quote)
    try:
        # Initial status + current focus quotes
        await websocket.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "status": combined_status(),
                    "quotes": stream_manager.quotes().get("symbols") or {},
                },
                default=str,
            )
        )
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            action = str(msg.get("action") or "").strip().lower()
            context = str(msg.get("context") or "focus").strip() or "focus"
            if action == "subscribe":
                symbols = msg.get("symbols") or []
                if isinstance(symbols, str):
                    symbols = [s.strip() for s in symbols.split(",") if s.strip()]
                mode = str(msg.get("mode") or "full")
                if context == "focus":
                    symbols = list(symbols)[:1]
                    mode = "full"
                status = await asyncio.to_thread(
                    stream_manager.subscribe, context, list(symbols), mode
                )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "subscribed",
                            "status": status,
                            "quotes": stream_manager.quotes(
                                [str(s).upper() for s in symbols] if symbols else None
                            ).get("symbols")
                            or {},
                        },
                        default=str,
                    )
                )
            elif action == "unsubscribe":
                status = await asyncio.to_thread(stream_manager.unsubscribe, context)
                await websocket.send_text(
                    json.dumps({"type": "unsubscribed", "status": status}, default=str)
                )
            elif action == "movers_start":
                # Never block the shared asyncio loop on universe resolve / subscribe.
                status = await asyncio.to_thread(subscribe_movers_universe)
                await websocket.send_text(
                    json.dumps({"type": "movers_started", "status": status}, default=str)
                )
            elif action == "movers_stop":
                status = await asyncio.to_thread(unsubscribe_movers_universe)
                await websocket.send_text(
                    json.dumps({"type": "movers_stopped", "status": status}, default=str)
                )
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await _hub.remove(websocket)
        # Keep listener registered — cheap and shared across clients.
