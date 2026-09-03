"""Upstox V3 live stream managers — focus (full) + movers universe (LTPC)."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from server import tick_candle_engine, upstox_client, upstox_config, upstox_instruments
from server.upstox_stream_proto import decode_feed_response

IST = timezone(timedelta(hours=5, minutes=30))
API_BASE = "https://api.upstox.com"
AUTHORIZE_PATH = "/v3/feed/market-data-feed/authorize"
# Legacy per-context caps (portfolio / market-map on focus socket if ever used).
MAX_PORTFOLIO_LTPC = 25
MAX_MARKET_MAP_LTPC = 750
# Dedicated movers LTPC socket — under Upstox individual LTPC limit of 5000.
MAX_MOVERS_LTPC = 5000
MAX_FOCUS_SYMBOLS = 5
# Focus keeps session candles longer; movers is LTPC-only ranking (quotes, not candles).
RECENT_CACHE_TTL_SEC = 6 * 60 * 60
MOVERS_QUOTE_TTL_SEC = 45 * 60

_HTTP = requests.Session()
_HTTP.trust_env = False


def _now_iso() -> str:
    return datetime.now(IST).isoformat()


def _finite(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:
            return None
        return f
    except Exception:
        return None


def _mode_rank(mode: str) -> int:
    normalized = str(mode or "").strip().lower()
    if normalized == "full":
        return 2
    if normalized == "ltpc":
        return 1
    return 0


def _normalize_mode(mode: str) -> str:
    return "full" if str(mode or "").strip().lower() == "full" else "ltpc"


def _bucket_minute(ts_ms: Any) -> str:
    try:
        ts = int(ts_ms) / 1000.0
        dt = datetime.fromtimestamp(ts, tz=IST).replace(second=0, microsecond=0)
    except Exception:
        dt = datetime.now(IST).replace(second=0, microsecond=0)
    return dt.isoformat()


def _session_ohlc_from_minutes(candles: dict[str, dict[str, Any]]) -> dict[str, float]:
    """Aggregate session open/high/low/last from 1-minute candles (9:15 → now)."""
    if not candles:
        return {}
    ordered = sorted(candles.values(), key=lambda c: str(c.get("time") or ""))
    if not ordered:
        return {}
    first_open = None
    last_close = None
    highs: list[float] = []
    lows: list[float] = []
    vol = 0.0
    for c in ordered:
        op = _finite(c.get("open"))
        hi = _finite(c.get("high"))
        lo = _finite(c.get("low"))
        cl = _finite(c.get("close"))
        if first_open is None and op is not None:
            first_open = op
        if hi is not None:
            highs.append(hi)
        if lo is not None:
            lows.append(lo)
        if cl is not None:
            last_close = cl
        try:
            vol += float(c.get("volume") or 0)
        except (TypeError, ValueError):
            pass
    out: dict[str, float] = {}
    if first_open is not None:
        out["open"] = round(first_open, 2)
    if highs:
        out["high"] = round(max(highs), 2)
    if lows:
        out["low"] = round(min(lows), 2)
    if last_close is not None:
        out["price"] = round(last_close, 2)
    if vol > 0:
        out["volume"] = vol
    return out


class UpstoxStreamManager:
    """One Upstox WebSocket connection (one of the two allowed per user)."""

    def __init__(
        self,
        *,
        name: str = "stream",
        max_symbols: int = 800,
        force_mode: Optional[str] = None,
    ) -> None:
        self.name = str(name or "stream")
        self.max_symbols = int(max_symbols)
        self.force_mode = _normalize_mode(force_mode) if force_mode else None
        self._lock = threading.RLock()
        self._contexts: dict[str, dict[str, str]] = {}
        self._symbol_to_key: dict[str, str] = {}
        self._key_to_symbol: dict[str, str] = {}
        self._quotes: dict[str, dict[str, Any]] = {}
        # 1-minute buckets (IST) keyed by minute iso → bar
        self._candles: dict[str, dict[str, dict[str, Any]]] = {}
        # Running session (1D) candle per symbol — focus tick engine only
        self._day_candles: dict[str, dict[str, Any]] = {}
        self._touched: dict[str, float] = {}
        self._version = 0
        self._backfill_gen = 0
        self._backfill_lock = threading.Lock()
        self._evict_counter = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._status: dict[str, Any] = {
            "name": self.name,
            "enabled": False,
            "running": False,
            "connected": False,
            "last_error": None,
            "last_message_at": None,
            "last_connect_at": None,
            "subscription_count": 0,
            "full_count": 0,
            "ltpc_count": 0,
            "source": f"upstox_stream_{self.name}",
            "force_mode": self.force_mode,
            "max_symbols": self.max_symbols,
        }
        self._listeners: list = []
        self._quote_version = 0

    def add_listener(self, callback) -> None:
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        with self._lock:
            self._listeners = [c for c in self._listeners if c is not callback]

    def _notify_listeners(self, payload: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(payload)
            except Exception:
                pass

    def quote_version(self) -> int:
        with self._lock:
            return int(self._quote_version)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._status,
                "configured": upstox_config.market_data_enabled(),
                "contexts": {k: dict(v) for k, v in self._contexts.items()},
                "symbols": sorted(self._symbol_to_key.keys()),
                "quote_count": len(self._quotes),
                "quote_symbols": sorted(self._quotes.keys())[:50],
                "cached_quotes": len(self._quotes),
                "cached_candle_symbols": len(self._candles),
            }

    def subscribe(self, context: str, symbols: list[str], mode: str = "ltpc") -> dict[str, Any]:
        ctx = str(context or "default").strip()[:80] or "default"
        mode = self.force_mode or _normalize_mode(mode)
        ordered = []
        seen = set()
        for raw in symbols or []:
            sym = str(raw or "").strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                ordered.append(sym)
            if len(ordered) >= self.max_symbols:
                break
        if (ctx == "portfolio" and mode == "ltpc"):
            ordered = ordered[:MAX_PORTFOLIO_LTPC]
        if ctx == "basket" and mode == "ltpc":
            ordered = ordered[:MAX_PORTFOLIO_LTPC]
        if ctx == "market-map" and mode == "ltpc":
            ordered = ordered[:MAX_MARKET_MAP_LTPC]

        with self._lock:
            self._contexts[ctx] = {sym: mode for sym in ordered}
            self._version += 1
            desired = self._desired_unlocked()
            self._status["subscription_count"] = len(desired)
            self._status["full_count"] = sum(1 for m in desired.values() if m == "full")
            self._status["ltpc_count"] = sum(1 for m in desired.values() if m != "full")
        # Resolve instrument keys sync (needed for WS); backfill/seed async so HTTP
        # /api/live/subscribe returns immediately when switching chart focus.
        self._resolve_instruments()
        self._ensure_thread()
        self._schedule_backfill()
        return self.status()

    def unsubscribe(self, context: str) -> dict[str, Any]:
        ctx = str(context or "default").strip()[:80] or "default"
        with self._lock:
            self._contexts.pop(ctx, None)
            self._version += 1
            desired = self._desired_unlocked()
            self._status["subscription_count"] = len(desired)
            self._status["full_count"] = sum(1 for m in desired.values() if m == "full")
            self._status["ltpc_count"] = sum(1 for m in desired.values() if m != "full")
        self._resolve_instruments()
        self._schedule_backfill()
        return self.status()

    def clear_all(self) -> dict[str, Any]:
        with self._lock:
            self._contexts.clear()
            self._version += 1
            self._status["subscription_count"] = 0
            self._status["full_count"] = 0
            self._status["ltpc_count"] = 0
        self._resolve_instruments()
        self._schedule_backfill()
        return self.status()

    def candles(self, symbol: str) -> dict[str, Any]:
        sym = str(symbol or "").strip().upper()
        with self._lock:
            rows = list((self._candles.get(sym) or {}).values())
            rows.sort(key=lambda r: str(r.get("time") or ""))
            quote = dict(self._quotes.get(sym) or {})
            day = dict(self._day_candles.get(sym) or {})
            last_1m = rows[-1] if rows else None
        return {
            "symbol": sym,
            "candles": rows,
            "quote": quote,
            "day": day or None,
            "last_1m": last_1m,
            "bundle": tick_candle_engine.focus_candle_bundle(last_1m, day or None),
            "as_of": _now_iso(),
        }

    def _focus_candle_payload(self, symbol: str) -> dict[str, Any]:
        """Authenticated display snapshot for one focus symbol (not raw tick republish)."""
        with self._lock:
            minutes = self._candles.get(symbol) or {}
            last_1m = None
            if minutes:
                last_key = max(minutes.keys())
                last_1m = dict(minutes[last_key])
            day = dict(self._day_candles.get(symbol) or {})
        return {symbol: tick_candle_engine.focus_candle_bundle(last_1m, day or None)}

    def _apply_tick_candles(
        self,
        symbol: str,
        *,
        price: float,
        ts_ms: Any,
        session_open: Optional[float] = None,
        session_high: Optional[float] = None,
        session_low: Optional[float] = None,
        volume: float = 0.0,
        source: str = "upstox_tick",
    ) -> dict[str, Any]:
        """Update 1m + 1D for focus feed. Skipped on movers LTPC manager."""
        if self.force_mode == "ltpc":
            return {}
        minute_key = tick_candle_engine.ist_minute_iso(ts_ms)
        with self._lock:
            prev_1m = (self._candles.get(symbol) or {}).get(minute_key)
            prev_day = self._day_candles.get(symbol)
        bar_1m = tick_candle_engine.apply_tick_to_minute(
            prev_1m, price=price, ts_ms=ts_ms, volume=volume, source=source
        )
        bar_1d = tick_candle_engine.apply_tick_to_day(
            prev_day,
            price=price,
            ts_ms=ts_ms,
            session_open=session_open,
            session_high=session_high,
            session_low=session_low,
            volume=volume,
            source=source,
        )
        with self._lock:
            self._candles.setdefault(symbol, {})[minute_key] = bar_1m
            self._day_candles[symbol] = bar_1d
            self._touched[symbol] = time.time()
            self._evict_old_locked()
        return tick_candle_engine.focus_candle_bundle(bar_1m, bar_1d)

    def quotes(self, symbols: Optional[list[str]] = None) -> dict[str, Any]:
        wanted = {str(s or "").strip().upper() for s in symbols or [] if str(s or "").strip()}
        with self._lock:
            if wanted:
                data = {s: dict(q) for s, q in self._quotes.items() if s in wanted}
            else:
                data = {s: dict(q) for s, q in self._quotes.items()}
        return {"as_of": _now_iso(), "symbols": data}

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._status["running"] = False
            self._status["connected"] = False

    def _desired(self) -> dict[str, str]:
        with self._lock:
            return self._desired_unlocked()

    def _desired_unlocked(self) -> dict[str, str]:
        desired: dict[str, str] = {}
        for sub in self._contexts.values():
            for sym, mode in sub.items():
                if _mode_rank(mode) > _mode_rank(desired.get(sym, "")):
                    desired[sym] = mode
        return desired

    def _resolve_instruments(self) -> None:
        """Map desired symbols → instrument keys (local/cache). Does not call Upstox REST."""
        desired = self._desired()
        if not desired:
            with self._lock:
                self._symbol_to_key = {}
                self._key_to_symbol = {}
                if self.force_mode == "ltpc":
                    self._quotes.clear()
                    self._candles.clear()
                    self._day_candles.clear()
                    self._touched.clear()
            return
        try:
            upstox_instruments.instrument_map()
            resolved, unresolved = upstox_instruments.resolve_instrument_keys(list(desired.keys()))
        except Exception as exc:
            with self._lock:
                self._status["last_error"] = f"instrument resolution failed: {exc}"
            return

        with self._lock:
            self._symbol_to_key = dict(resolved)
            self._key_to_symbol = {key: sym for sym, key in resolved.items()}
            self._status["subscription_count"] = len(resolved)
            self._status["full_count"] = sum(1 for s in resolved if desired.get(s) == "full")
            self._status["ltpc_count"] = sum(1 for s in resolved if desired.get(s) != "full")
            if unresolved:
                self._status["last_error"] = (
                    f"unresolved symbols: {len(unresolved)} ({', '.join(unresolved[:5])})"
                )
            elif str(self._status.get("last_error") or "").startswith("unresolved symbols:"):
                self._status["last_error"] = None

    def _schedule_backfill(self) -> None:
        """Run minute/session seed off the request thread (focus switches must stay snappy)."""
        with self._lock:
            self._backfill_gen += 1
            gen = self._backfill_gen

        def runner() -> None:
            with self._backfill_lock:
                with self._lock:
                    if gen != self._backfill_gen:
                        return
                try:
                    self._backfill_and_seed_symbols(gen)
                except Exception as exc:
                    with self._lock:
                        if gen == self._backfill_gen:
                            self._status["last_error"] = f"backfill failed: {exc}"

        threading.Thread(
            target=runner,
            name=f"upstox-backfill-{self.name}",
            daemon=True,
        ).start()

    def seed_session_quotes_sync(self, symbols: list[str]) -> None:
        """Blocking session OHLC seed for chart focus — runs before first LTPC paints."""
        wanted = []
        seen: set[str] = set()
        for raw in symbols or []:
            sym = str(raw or "").strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                wanted.append(sym)
        if not wanted:
            return
        self._resolve_instruments()
        with self._lock:
            resolved = dict(self._symbol_to_key)
        for sym in wanted:
            if sym in resolved:
                self._seed_session_quote(sym)

    def _backfill_and_seed_symbols(self, gen: int) -> None:
        desired = self._desired()
        with self._lock:
            resolved = dict(self._symbol_to_key)
        for sym, mode in desired.items():
            with self._lock:
                if gen != self._backfill_gen:
                    return
            if sym not in resolved:
                continue
            if mode == "full":
                self._backfill_intraday(sym, resolved[sym])
            else:
                self._seed_session_quote(sym)

    def _resolve_and_backfill(self) -> None:
        """Sync resolve + sync backfill (tests / rare callers). Prefer _schedule_backfill in subscribe."""
        self._resolve_instruments()
        desired = self._desired()
        with self._lock:
            resolved = dict(self._symbol_to_key)
            gen = self._backfill_gen
        for sym, mode in desired.items():
            if mode == "full" and sym in resolved:
                self._backfill_intraday(sym, resolved[sym])
            with self._lock:
                if gen != self._backfill_gen and gen != 0:
                    break

    def _backfill_intraday(self, symbol: str, key: str) -> None:
        try:
            rows = upstox_client.fetch_intraday_minutes(key, interval="1")
        except Exception as exc:
            with self._lock:
                self._status["last_error"] = f"{symbol} intraday backfill failed: {exc}"
            rows = None
        parsed: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            try:
                ts, op, hi, lo, close, vol = row[:6]
                minute = _bucket_minute(
                    datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() * 1000
                    if isinstance(ts, str)
                    else ts
                )
                parsed[minute] = {
                    "time": minute,
                    "open": round(float(op), 2),
                    "high": round(float(hi), 2),
                    "low": round(float(lo), 2),
                    "close": round(float(close), 2),
                    "volume": float(vol or 0),
                    "source": "upstox_backfill",
                    "final": True,
                }
            except Exception:
                continue
        if parsed:
            with self._lock:
                self._candles.setdefault(symbol, {}).update(parsed)
                self._touched[symbol] = time.time()
        # Always seed day quote OHLC so 1D candle has full session body (9:15 → now),
        # not a stub that starts at the first live LTP after reconnect/switch.
        self._seed_session_quote(symbol)

    def _seed_session_quote(self, symbol: str) -> None:
        """Seed quote open/high/low/price from REST day quote + minute aggregate."""
        rest: dict[str, Any] = {}
        try:
            entries, _err = upstox_client.fetch_quotes([symbol])
            if entries and isinstance(entries[0], dict):
                rest = entries[0]
        except Exception as exc:
            with self._lock:
                self._status["last_error"] = f"{symbol} session quote seed failed: {exc}"

        with self._lock:
            minutes = dict(self._candles.get(symbol) or {})
            prev = dict(self._quotes.get(symbol) or {})
        from_min = _session_ohlc_from_minutes(minutes)

        def _pick(*vals: Any) -> Optional[float]:
            for v in vals:
                n = _finite(v)
                if n is not None:
                    return n
            return None

        px = _pick(rest.get("price"), from_min.get("price"), prev.get("price"))
        op = _pick(rest.get("open"), from_min.get("open"), prev.get("open"))
        hi_candidates = [
            _finite(rest.get("high")),
            _finite(from_min.get("high")),
            _finite(prev.get("high")),
            px,
            op,
        ]
        lo_candidates = [
            _finite(rest.get("low")),
            _finite(from_min.get("low")),
            _finite(prev.get("low")),
            px,
            op,
        ]
        hi_vals = [x for x in hi_candidates if x is not None]
        lo_vals = [x for x in lo_candidates if x is not None]
        hi = max(hi_vals) if hi_vals else None
        lo = min(lo_vals) if lo_vals else None
        if px is None and op is None:
            return
        if px is None:
            px = op
        # Never invent session open from LTP — wait for REST/minute seed.
        if hi is None:
            hi = max(x for x in (op, px) if x is not None)
        if lo is None:
            lo = min(x for x in (op, px) if x is not None)

        cp = _pick(rest.get("previous_close"), prev.get("previous_close"))
        change_pct = _finite(rest.get("change_pct"))
        if change_pct is None and px is not None and cp is not None and cp > 0:
            change_pct = round((px - cp) / cp * 100.0, 2)
        if change_pct is None:
            change_pct = _finite(prev.get("change_pct"))

        quote: dict[str, Any] = {
            "symbol": symbol,
            "price": round(px, 2),
            "previous_close": round(cp, 2) if cp is not None else None,
            "change_pct": change_pct,
            "open": round(op, 2) if op is not None else None,
            "high": round(hi, 2) if hi is not None else None,
            "low": round(lo, 2) if lo is not None else None,
            "updated_at": _now_iso(),
            "source": "upstox_session_seed",
        }
        vol = _pick(rest.get("volume"), from_min.get("volume"), prev.get("volume"))
        if vol is not None:
            quote["volume"] = vol

        with self._lock:
            self._quotes[symbol] = quote
            self._touched[symbol] = time.time()
            self._quote_version += 1
        candle_bundle = {}
        if self.force_mode != "ltpc" and px is not None:
            candle_bundle = self._apply_tick_candles(
                symbol,
                price=float(px),
                ts_ms=None,
                session_open=_finite(op),
                session_high=_finite(hi),
                session_low=_finite(lo),
                volume=float(vol or 0),
                source="upstox_session_seed",
            )
        notify_payload: dict[str, Any] = {
            "type": "quote",
            "symbol": symbol,
            "quote": quote,
            "quotes": {symbol: quote},
        }
        if candle_bundle:
            notify_payload["candles"] = {symbol: candle_bundle}
        self._notify_listeners(notify_payload)
        # Share session O/H/L with movers ranking cache so Market Movers charts keep HOD.
        try:
            from server import movers_live

            movers_live.ingest_stream_quotes([quote])
        except Exception:
            pass

    def _ensure_thread(self) -> None:
        # Always clear stop so a prior LIVE-off can be turned back on without a process restart.
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"upstox-live-{self.name}",
            daemon=True,
        )
        self._thread.start()

    def _thread_main(self) -> None:
        asyncio.run(self._run_forever())

    async def _run_forever(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            desired = self._desired()
            if not desired:
                with self._lock:
                    self._status["running"] = False
                    self._status["connected"] = False
                await asyncio.sleep(1.0)
                continue
            try:
                await self._connect_once()
                backoff = 2.0
            except Exception as exc:
                with self._lock:
                    self._status["running"] = True
                    self._status["connected"] = False
                    self._status["last_error"] = str(exc)
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 1.7)

    def _authorized_url(self) -> str:
        token = upstox_config.analytics_token()
        if not token:
            raise RuntimeError("UPSTOX_ANALYTICS_TOKEN is not set")
        resp = _HTTP.get(
            f"{API_BASE}{AUTHORIZE_PATH}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=(5.0, 20.0),
        )
        if resp.status_code == 401:
            raise PermissionError("Upstox Analytics Token rejected for WebSocket authorize")
        resp.raise_for_status()
        body = resp.json()
        url = ((body.get("data") or {}).get("authorized_redirect_uri") or "").strip()
        if not url:
            raise RuntimeError("Upstox authorize response did not include authorized_redirect_uri")
        return url

    async def _connect_once(self) -> None:
        import websockets

        if not upstox_config.market_data_enabled():
            raise RuntimeError("Upstox market data is disabled or not configured")
        # LTPC movers: resolve keys only (no REST backfill). Full focus still seeds session OHLC.
        if self.force_mode == "ltpc":
            self._resolve_instruments()
        else:
            self._resolve_and_backfill()
        # Authorize off the asyncio loop — sync requests must not stall feed recv.
        url = await asyncio.to_thread(self._authorized_url)
        token = upstox_config.analytics_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "*/*"}
        try:
            ws_cm = websockets.connect(
                url, additional_headers=headers, ping_interval=20, ping_timeout=20, proxy=None
            )
        except TypeError:
            try:
                ws_cm = websockets.connect(
                    url, extra_headers=headers, ping_interval=20, ping_timeout=20, proxy=None
                )
            except TypeError:
                ws_cm = websockets.connect(url, extra_headers=headers, ping_interval=20, ping_timeout=20)
        async with ws_cm as ws:
            with self._lock:
                self._status["enabled"] = True
                self._status["running"] = True
                self._status["connected"] = True
                self._status["last_connect_at"] = _now_iso()
                self._status["last_error"] = None
            sent_version = -1
            while not self._stop.is_set():
                if not self._desired():
                    break
                with self._lock:
                    version = self._version
                if version != sent_version:
                    await self._send_subscription(ws)
                    sent_version = version
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                if isinstance(raw, str):
                    continue
                self._handle_feed_bytes(raw)

    async def _send_subscription(self, ws) -> None:
        desired = self._desired()
        with self._lock:
            sym_to_key = dict(self._symbol_to_key)
        ltpc_keys = [sym_to_key[s] for s, m in desired.items() if m == "ltpc" and s in sym_to_key]
        full_keys = [sym_to_key[s] for s, m in desired.items() if m == "full" and s in sym_to_key]
        # Upstox accepts large instrumentKeys lists; chunk to keep frames reasonable.
        chunk = 800
        for mode, keys in (("ltpc", ltpc_keys), ("full", full_keys)):
            if not keys:
                continue
            for i in range(0, len(keys), chunk):
                part = keys[i : i + chunk]
                payload = {
                    "guid": str(uuid.uuid4()),
                    "method": "sub",
                    "data": {"mode": mode, "instrumentKeys": part},
                }
                await ws.send(json.dumps(payload).encode("utf-8"))

    def _handle_feed_bytes(self, raw: bytes) -> None:
        data = decode_feed_response(raw)
        feeds = data.get("feeds") or {}
        now = _now_iso()
        with self._lock:
            self._status["last_message_at"] = now
            self._status["connected"] = True
        for key, feed in feeds.items():
            sym = self._key_to_symbol.get(str(key))
            if not sym:
                continue
            self._apply_feed(sym, feed, data.get("currentTs"))

    def _extract_ltpc(self, feed: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        ohlc_rows: list[dict[str, Any]] = []
        ltpc = feed.get("ltpc") or {}
        full = feed.get("fullFeed") or {}
        first = feed.get("firstLevelWithGreeks") or {}
        if full:
            node = full.get("marketFF") or full.get("indexFF") or {}
            ltpc = node.get("ltpc") or ltpc
            market_ohlc = node.get("marketOHLC") or {}
            ohlc_rows = market_ohlc.get("ohlc") or []
        elif first:
            ltpc = first.get("ltpc") or ltpc
        return ltpc, ohlc_rows

    def _day_ohlc_from_rows(self, ohlc_rows: list[dict[str, Any]]) -> dict[str, float]:
        """Pick day-session OHLC from marketOHLC rows (interval 1d / day / D)."""
        out: dict[str, float] = {}
        for row in ohlc_rows or []:
            interval = str(row.get("interval") or "").strip().upper()
            if interval not in ("1D", "D", "DAY", "1DAY", "DAYS"):
                continue
            op = _finite(row.get("open"))
            hi = _finite(row.get("high"))
            lo = _finite(row.get("low"))
            if op is not None:
                out["open"] = round(op, 2)
            if hi is not None:
                out["high"] = round(hi, 2)
            if lo is not None:
                out["low"] = round(lo, 2)
            break
        return out

    def _apply_feed(self, symbol: str, feed: dict[str, Any], current_ts: Any) -> None:
        ltpc, ohlc_rows = self._extract_ltpc(feed)
        ltp = _finite(ltpc.get("ltp"))
        cp = _finite(ltpc.get("cp"))
        ltt = ltpc.get("ltt") or current_ts
        # Movers LTPC path: LTP + prev close for ranking, plus running session O/H/L
        # so live charts keep the day high even after price falls back.
        if self.force_mode == "ltpc":
            if ltp is None:
                return
            with self._lock:
                prev = self._quotes.get(symbol) or {}
                prev_cp = _finite(prev.get("previous_close"))
                prev_open = _finite(prev.get("open"))
                prev_high = _finite(prev.get("high"))
                prev_low = _finite(prev.get("low"))
            use_cp = cp if cp is not None else prev_cp
            op = prev_open
            hi_vals = [x for x in (prev_high, ltp) if x is not None]
            lo_vals = [x for x in (prev_low, ltp) if x is not None]
            hi = max(hi_vals) if hi_vals else None
            lo = min(lo_vals) if lo_vals else None
            quote = {
                "symbol": symbol,
                "price": round(ltp, 2),
                "previous_close": round(use_cp, 2) if use_cp is not None else None,
                "change_pct": (
                    round((ltp - use_cp) / use_cp * 100.0, 2)
                    if use_cp and use_cp > 0
                    else prev.get("change_pct")
                ),
                "open": round(op, 2) if op is not None else None,
                "high": round(hi, 2) if hi is not None else None,
                "low": round(lo, 2) if lo is not None else None,
                "updated_at": _now_iso(),
                "source": "upstox_stream",
            }
            with self._lock:
                self._quotes[symbol] = quote
                self._touched[symbol] = time.time()
                self._quote_version += 1
                self._maybe_evict_locked()
            self._notify_listeners(
                {"type": "quote", "symbol": symbol, "quote": quote, "quotes": {symbol: quote}}
            )
            return

        day_ohlc = self._day_ohlc_from_rows(ohlc_rows)
        if ltp is not None:
            with self._lock:
                prev = dict(self._quotes.get(symbol) or {})
            prev_open = _finite(prev.get("open"))
            prev_high = _finite(prev.get("high"))
            prev_low = _finite(prev.get("low"))
            op = day_ohlc.get("open")
            if op is None:
                op = prev_open
            hi = day_ohlc.get("high")
            lo = day_ohlc.get("low")
            if hi is None:
                hi = max(x for x in (prev_high, ltp) if x is not None)
            else:
                hi = max(hi, ltp, *(x for x in (prev_high,) if x is not None))
            if lo is None:
                lo = min(x for x in (prev_low, ltp) if x is not None)
            else:
                lo = min(lo, ltp, *(x for x in (prev_low,) if x is not None))
            quote = {
                "symbol": symbol,
                "price": round(ltp, 2),
                "previous_close": round(cp, 2) if cp is not None else prev.get("previous_close"),
                "change_pct": (
                    round((ltp - cp) / cp * 100.0, 2)
                    if cp and cp > 0
                    else prev.get("change_pct")
                ),
                "open": round(op, 2) if op is not None else None,
                "high": round(hi, 2) if hi is not None else None,
                "low": round(lo, 2) if lo is not None else None,
                "updated_at": _now_iso(),
                "source": "upstox_stream",
            }
            candle_bundle = self._apply_tick_candles(
                symbol,
                price=float(ltp),
                ts_ms=ltt,
                session_open=_finite(op),
                session_high=_finite(hi),
                session_low=_finite(lo),
                source="upstox_tick",
            )
            with self._lock:
                self._quotes[symbol] = quote
                self._touched[symbol] = time.time()
                self._quote_version += 1
                self._maybe_evict_locked()
            notify_payload: dict[str, Any] = {
                "type": "quote",
                "symbol": symbol,
                "quote": quote,
                "quotes": {symbol: quote},
            }
            if candle_bundle:
                notify_payload["candles"] = {symbol: candle_bundle}
            self._notify_listeners(notify_payload)

        candle_updates: dict[str, dict[str, Any]] = {}
        for row in ohlc_rows:
            if str(row.get("interval") or "").upper() != "I1":
                continue
            try:
                minute = _bucket_minute(row.get("ts"))
                candle_updates[minute] = {
                    "time": minute,
                    "open": round(float(row.get("open")), 2),
                    "high": round(float(row.get("high")), 2),
                    "low": round(float(row.get("low")), 2),
                    "close": round(float(row.get("close")), 2),
                    "volume": float(row.get("vol") or 0),
                    "source": "upstox_stream",
                    "final": False,
                    "tf": "1m",
                }
            except Exception:
                continue
        if candle_updates:
            with self._lock:
                self._candles.setdefault(symbol, {}).update(candle_updates)
                self._touched[symbol] = time.time()
                self._evict_old_locked()
            # Prefer exchange I1 rows when present; refresh day from minutes + quote.
            if ltp is not None:
                with self._lock:
                    q = dict(self._quotes.get(symbol) or {})
                self._apply_tick_candles(
                    symbol,
                    price=float(ltp),
                    ts_ms=ltt,
                    session_open=_finite(q.get("open")),
                    session_high=_finite(q.get("high")),
                    session_low=_finite(q.get("low")),
                    source="upstox_stream",
                )

    def clear_caches(self) -> None:
        """Drop all cached quotes/candles (e.g. when movers LIVE turns off)."""
        with self._lock:
            self._quotes.clear()
            self._candles.clear()
            self._day_candles.clear()
            self._touched.clear()

    def _cache_ttl_sec(self) -> float:
        return float(MOVERS_QUOTE_TTL_SEC if self.force_mode == "ltpc" else RECENT_CACHE_TTL_SEC)

    def _evict_old_locked(self) -> None:
        desired = set(self._desired_unlocked().keys())
        # Always drop symbols that are no longer subscribed.
        for sym in list(self._quotes.keys()):
            if desired and sym not in desired:
                self._quotes.pop(sym, None)
                self._candles.pop(sym, None)
                self._day_candles.pop(sym, None)
                self._touched.pop(sym, None)
        cutoff = time.time() - self._cache_ttl_sec()
        stale = [sym for sym, ts in self._touched.items() if ts < cutoff]
        for sym in stale:
            # Keep currently subscribed movers quotes even if quiet (illiquid) —
            # only TTL-drop symbols that are also off the desired set, or focus extras.
            if desired and sym in desired and self.force_mode == "ltpc":
                continue
            self._touched.pop(sym, None)
            self._quotes.pop(sym, None)
            self._candles.pop(sym, None)
            self._day_candles.pop(sym, None)
        # Movers never needs minute candles — reclaim if any slipped in.
        if self.force_mode == "ltpc" and self._candles:
            self._candles.clear()
        if self.force_mode == "ltpc" and self._day_candles:
            self._day_candles.clear()

    def _maybe_evict_locked(self) -> None:
        self._evict_counter += 1
        if self._evict_counter % 128 == 0:
            self._evict_old_locked()


# Conn 1: chart focus + page LTPC contexts (portfolio / watchlist / market-map).
# Focus context is forced to full in live_routes; other contexts stay ltpc.
focus_manager = UpstoxStreamManager(
    name="focus",
    max_symbols=MAX_MARKET_MAP_LTPC,
    force_mode=None,
)
# Conn 2: movers universe — LTPC only.
movers_manager = UpstoxStreamManager(
    name="movers",
    max_symbols=MAX_MOVERS_LTPC,
    force_mode="ltpc",
)
# Backward-compatible alias used by live_routes / chart path.
manager = focus_manager

_movers_listener_installed = False


def combined_status() -> dict[str, Any]:
    focus = focus_manager.status()
    movers = movers_manager.status()
    return {
        "configured": upstox_config.market_data_enabled(),
        "source": "upstox_stream",
        "focus": focus,
        "movers": movers,
        # Flat fields for older clients expecting focus status at top level.
        **{k: focus.get(k) for k in (
            "enabled", "running", "connected", "last_error", "last_message_at",
            "last_connect_at", "subscription_count", "full_count", "ltpc_count",
            "quote_count", "contexts", "symbols", "cached_quotes", "cached_candle_symbols",
        )},
        "universe_subscribed": bool((movers.get("contexts") or {}).get("movers")),
        "universe_size": int(movers.get("subscription_count") or 0),
        "universe_connected": bool(movers.get("connected")),
        "universe_quotes": int(movers.get("cached_quotes") or 0),
        "stream_mode": "ltpc",
    }


def _ensure_movers_cache_listener() -> None:
    global _movers_listener_installed
    if _movers_listener_installed:
        return

    def _on_tick(payload: dict[str, Any]) -> None:
        quote = payload.get("quote")
        if not isinstance(quote, dict):
            return
        try:
            from server import movers_live

            movers_live.ingest_stream_quotes([quote])
        except Exception:
            pass

    movers_manager.add_listener(_on_tick)
    _movers_listener_installed = True


def subscribe_movers_universe(symbols: Optional[list[str]] = None) -> dict[str, Any]:
    """Subscribe screener (or provided) universe on the dedicated LTPC connection."""
    _ensure_movers_cache_listener()
    if not upstox_config.market_data_enabled():
        raise RuntimeError("Upstox market data is disabled or not configured")
    if symbols is None:
        try:
            from server import movers_live

            symbols = movers_live.stream_universe_symbols()
        except Exception as exc:
            raise RuntimeError(f"movers universe unavailable: {exc}") from exc
    ordered = []
    seen = set()
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            ordered.append(sym)
        if len(ordered) >= MAX_MOVERS_LTPC:
            break
    # Mark active before subscribe so light polls skip REST even while instruments resolve.
    try:
        from server import movers_live

        movers_live.set_universe_stream_active(
            True,
            universe_size=len(ordered),
            stream_status={"connected": False},
        )
    except Exception:
        pass
    status = movers_manager.subscribe("movers", ordered, mode="ltpc")
    try:
        from server import movers_live

        movers_live.set_universe_stream_active(
            True,
            universe_size=len(ordered),
            stream_status=status,
        )
    except Exception:
        pass
    return combined_status()


def unsubscribe_movers_universe() -> dict[str, Any]:
    # Drop ranking cache first so UI/API stop reading stale "live" quotes immediately.
    try:
        from server import movers_live

        movers_live.set_universe_stream_active(False, universe_size=0, stream_status={})
        movers_live.clear_stream_quote_cache()
    except Exception:
        pass
    status = movers_manager.unsubscribe("movers")
    movers_manager.clear_caches()
    # Stop the LTPC thread so it cannot keep filling RAM after LIVE off.
    try:
        movers_manager.stop()
    except Exception:
        pass
    return combined_status()
