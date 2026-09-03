"""Background evaluator for watchlist / earnings / portfolio alerts."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from server import telegram_notify
from server import user_alerts_store as alerts_store
from server.app_code_crypto import current_machine_code
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_thread: Optional[threading.Thread] = None
_stop = threading.Event()
_interval_sec = 75.0


def _log(msg: str) -> None:
    print(f"[alert_evaluator] {msg}", flush=True)


def _is_nse_trading_day(now: Optional[datetime] = None) -> bool:
    """True on NSE session days (weekday not holiday, or special Saturday session)."""
    day = (now or datetime.now(IST)).astimezone(IST).date()
    try:
        from movers_data import _is_nse_session_day

        return bool(_is_nse_session_day(day))
    except Exception:
        # Fallback: weekdays only if calendar unavailable.
        return day.weekday() < 5


def _is_nse_market_hours(now: Optional[datetime] = None) -> bool:
    """
    True only during the cash equity session on an NSE trading day.

    Window matches movers_live: 09:15–15:30 IST inclusive.
    Prevents day-move alerts at midnight when the IST calendar day rolls over
    and yesterday's change_% would otherwise re-fire under a fresh dedup key.
    """
    dt = now or datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    if not _is_nse_trading_day(dt):
        return False
    mins = dt.hour * 60 + dt.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_json_list(path: Path) -> list:
    data = _load_json(path)
    return data if isinstance(data, list) else []


def _parse_watchlists(raw: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w in raw:
        if not isinstance(w, dict):
            continue
        name = str(w.get("name") or "").strip()
        if not name:
            continue
        items = []
        for it in w.get("items") or []:
            if not isinstance(it, dict):
                continue
            sym = str(it.get("symbol") or "").strip().upper()
            typ = str(it.get("type") or "").strip().lower()
            if sym and typ in ("stock", "index"):
                items.append({"symbol": sym, "type": typ})
        out.append({
            "name": name,
            "items": items,
            "notifications_enabled": bool(w.get("notifications_enabled")),
        })
    return out


def _portfolio_stock_symbols(portfolio_path: Path) -> set[str]:
    raw = _load_json(portfolio_path)
    if not isinstance(raw, dict):
        return set()
    out: set[str] = set()
    for it in raw.get("items") or []:
        if not isinstance(it, dict):
            continue
        if str(it.get("type") or "stock").strip().lower() != "stock":
            continue
        sym = str(it.get("symbol") or "").strip().upper()
        if sym:
            out.add(sym)
    return out


def _parse_price_updated_at(raw: Any) -> Optional[datetime]:
    """Parse screener.price_updated_at (IST wall clock, usually 'YYYY-MM-DD HH:MM:SS')."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:19] if fmt != "%Y-%m-%d" else s[:10], fmt)
            return dt.replace(tzinfo=IST)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _is_session_fresh_quote_ts(updated_at: Any, now: Optional[datetime] = None) -> bool:
    """
    True when the quote stamp is from today's cash session (IST date + >= 09:15).

    Blocks yesterday/EOD leftovers from driving day-move alerts after midnight
    or before the open, even if the calendar day has rolled over.
    """
    dt = updated_at if isinstance(updated_at, datetime) else _parse_price_updated_at(updated_at)
    if dt is None:
        return False
    ref = now or datetime.now(IST)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=IST)
    else:
        ref = ref.astimezone(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    if dt.date() != ref.date():
        return False
    mins = dt.hour * 60 + dt.minute
    return mins >= (9 * 60 + 15)


def _finite_pct(raw: Any) -> Optional[float]:
    try:
        if raw is None or raw == "":
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def _screener_day_changes(db_path: Path, symbols: set[str]) -> dict[str, float]:
    """
    Day-move % from screener, only when price_updated_at is session-fresh.

    Stale prior-session rows are omitted so midnight IST rollover cannot re-alert
    on yesterday's change_percent.
    """
    if not symbols or not db_path.is_file():
        return {}
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(screener)")
            cols = {str(r[1]).lower() for r in cur.fetchall()}
            if "change_percent" not in cols:
                return {}
            has_stamp = "price_updated_at" in cols
            placeholders = ",".join("?" for _ in symbols)
            if has_stamp:
                cur.execute(
                    f"SELECT UPPER(TRIM(symbol)), change_percent, price_updated_at "
                    f"FROM screener WHERE UPPER(TRIM(symbol)) IN ({placeholders})",
                    list(symbols),
                )
            else:
                # No stamp column → cannot prove session freshness; skip screener path.
                return {}
            out: dict[str, float] = {}
            now = datetime.now(IST)
            for sym, chg, stamp in cur.fetchall():
                try:
                    if chg is None:
                        continue
                    if not _is_session_fresh_quote_ts(stamp, now=now):
                        continue
                    out[str(sym).upper()] = float(chg)
                except (TypeError, ValueError):
                    continue
            return out
        finally:
            conn.close()
    except Exception:
        return {}


def _live_cache_day_changes(symbols: set[str]) -> dict[str, float]:
    """Day-move % from the in-process movers/Upstox live quote cache (session ticks)."""
    if not symbols:
        return {}
    try:
        from movers_live import cache_quote_fresh, live_cache_snapshot
    except Exception:
        try:
            from server.movers_live import cache_quote_fresh, live_cache_snapshot
        except Exception:
            return {}
    try:
        snap = live_cache_snapshot() or {}
    except Exception:
        return {}
    out: dict[str, float] = {}
    for sym in symbols:
        q = snap.get(sym)
        if not isinstance(q, dict) or not cache_quote_fresh(q):
            continue
        chg = _finite_pct(q.get("change_pct"))
        if chg is None:
            px = _finite_pct(q.get("price"))
            prev = _finite_pct(q.get("previous_close"))
            if px is not None and prev is not None and prev > 0:
                chg = ((px - prev) / prev) * 100.0
        if chg is None:
            continue
        out[sym] = round(float(chg), 2)
    return out


def _on_demand_live_day_changes(symbols: set[str]) -> dict[str, float]:
    """
    Backfill day-move % via movers_live on-demand quotes (Yahoo primary / NSE).

    Avoids Upstox REST quote spam (429) from the 75s alert loop.
    """
    if not symbols:
        return {}
    try:
        from movers_live import _fetch_missing_quote_symbols
    except Exception:
        try:
            from server.movers_live import _fetch_missing_quote_symbols
        except Exception:
            return {}
    try:
        _fetch_missing_quote_symbols(sorted(symbols)[:80], max_n=80, force=False)
    except Exception:
        pass
    return _live_cache_day_changes(symbols)


def _live_cache_price_quotes(symbols: set[str]) -> dict[str, dict[str, float]]:
    """
    Live quote snapshot for absolute price targets.

    Returns {SYM: {price, high?, low?}} from movers_live. Session high/low matter:
    LTP is polled ~every 75s, so a brief wick through a level can miss if we only
    compare last price — day high/low catch that touch.
    """
    if not symbols:
        return {}
    try:
        from movers_live import cache_quote_fresh, live_cache_snapshot
    except Exception:
        try:
            from server.movers_live import cache_quote_fresh, live_cache_snapshot
        except Exception:
            return {}
    try:
        snap = live_cache_snapshot() or {}
    except Exception:
        return {}
    out: dict[str, dict[str, float]] = {}
    for sym in symbols:
        q = snap.get(sym)
        if not isinstance(q, dict) or not cache_quote_fresh(q):
            continue
        px = _finite_pct(q.get("price"))
        if px is None or px <= 0:
            continue
        row: dict[str, float] = {"price": float(px)}
        hi = _finite_pct(q.get("high"))
        lo = _finite_pct(q.get("low"))
        if hi is not None and hi > 0:
            row["high"] = float(hi)
        if lo is not None and lo > 0:
            row["low"] = float(lo)
        out[str(sym).upper()] = row
    return out


def _live_cache_last_prices(symbols: set[str]) -> dict[str, float]:
    """Last traded price from the in-process live quote cache."""
    return {s: float(q["price"]) for s, q in _live_cache_price_quotes(symbols).items()}


def _on_demand_live_price_quotes(symbols: set[str]) -> dict[str, dict[str, float]]:
    if not symbols:
        return {}
    try:
        from movers_live import _fetch_missing_quote_symbols
    except Exception:
        try:
            from server.movers_live import _fetch_missing_quote_symbols
        except Exception:
            return {}
    try:
        _fetch_missing_quote_symbols(sorted(symbols)[:80], max_n=80, force=False)
    except Exception:
        pass
    return _live_cache_price_quotes(symbols)


def _on_demand_live_last_prices(symbols: set[str]) -> dict[str, float]:
    return {s: float(q["price"]) for s, q in _on_demand_live_price_quotes(symbols).items()}


def _session_price_quotes(db_path: Path, symbols: set[str]) -> dict[str, dict[str, float]]:
    """Live/session LTP + session high/low for absolute target alerts (market hours only)."""
    if not symbols:
        return {}
    out = dict(_live_cache_price_quotes(symbols))
    missing = {s for s in symbols if s not in out}
    if missing:
        out.update(_on_demand_live_price_quotes(missing))
    return out


def _session_last_prices(db_path: Path, symbols: set[str]) -> dict[str, float]:
    """Live/session last price for absolute target alerts (market hours only)."""
    return {s: float(q["price"]) for s, q in _session_price_quotes(db_path, symbols).items()}


def _day_move_changes(db_path: Path, symbols: set[str]) -> dict[str, float]:
    """
    Session day-move % for alert evaluation.

    Preference: fresh live cache → on-demand live quotes → session-fresh screener.
    Never returns prior-session screener leftovers.
    """
    if not symbols:
        return {}
    out = dict(_live_cache_day_changes(symbols))
    missing = {s for s in symbols if s not in out}
    if missing:
        out.update(_on_demand_live_day_changes(missing))
    missing = {s for s in symbols if s not in out}
    if missing:
        out.update(_screener_day_changes(db_path, missing))
    return out


def _parse_mcap_value(raw: Any) -> Optional[float]:
    """Accept full INR float or abbreviated UI strings (500M / 50B / 5T)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        try:
            v = float(raw)
            return v if v >= 0 else None
        except (TypeError, ValueError):
            return None
    s = str(raw).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)([MBTmbt])", s)
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    mult = {"m": 1e6, "b": 1e9, "t": 1e12}[m.group(2).lower()]
    return n * mult


def _snap_float(snap: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key not in snap:
            continue
        raw = snap.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _fmt_mcap(val: Any) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    if not (n > 0):
        return "—"
    abs_n = abs(n)
    if abs_n >= 1e12:
        return f"₹{n / 1e12:.2f}T"
    if abs_n >= 1e9:
        return f"₹{n / 1e9:.2f}B"
    if abs_n >= 1e6:
        return f"₹{n / 1e6:.2f}M"
    return f"₹{n:,.0f}"


def _fmt_num(val: Any, *, digits: int = 2, suffix: str = "") -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    return f"{n:.{digits}f}{suffix}"


def _fmt_pct(val: Any) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    return f"{n:+.2f}%"


def format_earnings_alert_body(row: dict[str, Any]) -> str:
    """Rich body for Earnings page alerts (inbox + Telegram)."""
    mcap = row.get("market_cap_basic")
    if mcap is None:
        mcap = row.get("market_cap")
    price = row.get("price")
    if price is None:
        price = row.get("close")
    chg = row.get("change_1d_pct")
    if chg is None:
        chg = row.get("change_percent")
    rel = str(
        row.get("earnings_release_date")
        or row.get("earnings_release_next_date")
        or ""
    ).strip()[:10] or "—"
    lines = [
        f"Mcap: {_fmt_mcap(mcap)} | Price: ₹{_fmt_num(price)} | 1D: {_fmt_pct(chg)}",
        f"Report: {rel}",
        f"EPS est: {_fmt_num(row.get('eps_estimate'))} | EPS beat: {_fmt_pct(row.get('eps_surprise_pct'))}",
        f"Rev est: {_fmt_mcap(row.get('revenue_estimate'))} | Rev beat: {_fmt_pct(row.get('revenue_surprise_pct'))}",
    ]
    return "\n".join(lines)


def build_earnings_fetch_kwargs(snap: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Map Earnings page filter snapshot → fetch_earnings kwargs (incl. earnings_plus)."""
    if not isinstance(snap, dict):
        return None
    mode = str(snap.get("mode") or "reported").strip().lower()
    kwargs: dict[str, Any] = {
        "mode": "upcoming" if mode == "upcoming" else "reported",
        "limit": 2000,
        "use_cache": True,
    }
    if kwargs["mode"] == "reported":
        try:
            kwargs["year"] = int(snap.get("year"))
            kwargs["month"] = int(snap.get("month"))
        except (TypeError, ValueError):
            return None
        for camel, snake in (
            ("epsSurpriseMin", "eps_surprise_min"),
            ("epsSurpriseMax", "eps_surprise_max"),
            ("revenueSurpriseMin", "revenue_surprise_min"),
            ("revenueSurpriseMax", "revenue_surprise_max"),
        ):
            v = _snap_float(snap, camel, snake)
            if v is not None:
                kwargs[snake] = v
        plus = str(
            snap.get("earnings_plus")
            or snap.get("earningsPlusFilter")
            or "all"
        ).strip().lower()
        if plus in ("all", "only", "exclude", "tv_eps_rev_beat"):
            kwargs["earnings_plus"] = plus
        else:
            kwargs["earnings_plus"] = "all"
    else:
        kwargs["period"] = str(snap.get("period") or "this_month")

    for camel, snake in (("mcapMin", "mcap_min"), ("mcapMax", "mcap_max")):
        raw = snap.get(camel)
        if raw is None or raw == "":
            raw = snap.get(snake)
        parsed = _parse_mcap_value(raw)
        if parsed is not None:
            kwargs[snake] = parsed
    return kwargs


def earnings_alert_fetch_kwargs(snap: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Notification fetch kwargs: always reported + current IST calendar month.

    Ignores UI month/year (browsing June must not alert on June) and never
    builds an upcoming fetch — surprise/mcap/Earnings+ filters still apply.
    """
    if not isinstance(snap, dict):
        return None
    today = datetime.now(IST).date()
    locked = {
        **snap,
        "mode": "reported",
        "year": today.year,
        "month": today.month,
    }
    return build_earnings_fetch_kwargs(locked)


def _emit(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    settings: dict[str, Any],
    *,
    source: str,
    kind: str,
    symbol: str,
    title: str,
    body: str,
    watchlist_name: Optional[str] = None,
    meta: Optional[dict] = None,
    dedup_day: Optional[str] = None,
) -> bool:
    """
    Insert an alert if its dedup key is new.

    Day-move alerts pass no dedup_day → once per IST calendar day.
    Earnings alerts should pass release date (+ completeness fingerprint via
    earnings_dedup_day) so the same incomplete report is not re-alerted daily,
    but a later fill-in of missing EPS/revenue can notify again.
    """
    day = str(dedup_day or "").strip() or alerts_store.ist_today_key()
    if len(day) > 10 and "|" not in day:
        day = day[:10]
    key = alerts_store.dedup_key(symbol, kind, day)
    alert = {
        "symbol": symbol,
        "kind": kind,
        "source": source,
        "title": title,
        "body": body,
        "watchlist_name": watchlist_name,
        "dedup_key": key,
        "meta": meta or {},
        "delivered_browser_pending": bool(settings.get("browser_enabled")),
    }
    saved, inserted = alerts_store.append_alert(base_dir, alert, session=session)
    if not inserted or not saved:
        return False
    if settings.get("telegram_enabled"):
        if kind == "portfolio_earnings_reported":
            text = f"Portfolio Update\n{symbol}\n{body}"
        elif kind == "portfolio_earnings_upcoming":
            text = f"Upcoming Portfolio Earnings\n{symbol}\n{body}"
        elif kind in ("price_above", "price_below"):
            text = f"CiM Price Alert\n{title}\n{body}"
        else:
            text = f"CiM Alert\n{title}\n{body}"
        result = telegram_notify.send_for_user(base_dir, session, text)
        if result.get("ok"):
            doc = alerts_store.load_alerts(base_dir, session=session)
            for a in doc.get("alerts") or []:
                if a.get("id") == saved.get("id"):
                    a["delivered_telegram"] = True
                    break
            alerts_store.save_alerts(base_dir, doc, session=session)
        else:
            _log(f"telegram failed: {result.get('error')}")
    return True


def _evaluate_price_targets(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    settings: dict[str, Any],
    db_path: Path,
    stock_syms: set[str],
    sym_to_lists: dict[str, list[str]],
) -> int:
    """
    Absolute price above/below targets for symbols on notification-enabled watchlists.

    Only called during NSE market hours. Fires once then disarms (re-arm in Alerts UI).
    Telegram uses the same path as other alerts when telegram_enabled.
    """
    if not _is_nse_market_hours():
        return 0
    targets = alerts_store.normalize_price_targets(settings.get("price_targets"))
    armed = [
        t for t in targets
        if t.get("armed") and t.get("symbol") in stock_syms
    ]
    if not armed:
        return 0
    need = {t["symbol"] for t in armed}
    quotes = _session_price_quotes(db_path, need)
    if not quotes:
        return 0
    created = 0
    for t in armed:
        sym = t["symbol"]
        q = quotes.get(sym) or {}
        px = q.get("price")
        if px is None or px <= 0:
            continue
        hi = q.get("high")
        lo = q.get("low")
        level = float(t["level"])
        direction = t["direction"]
        # LTP sample (~75s) can miss a brief wick; session high/low catch the touch.
        hit = (
            (direction == "above" and (px >= level or (hi is not None and hi >= level)))
            or (direction == "below" and (px <= level or (lo is not None and lo <= level)))
        )
        if not hit:
            continue
        lists = ", ".join(sym_to_lists.get(sym) or [])
        arrow = "≥" if direction == "above" else "≤"
        touch_px = px
        if direction == "above" and hi is not None and hi >= level:
            touch_px = max(float(px), float(hi))
        elif direction == "below" and lo is not None and lo <= level:
            touch_px = min(float(px), float(lo))
        title = f"{sym} ₹{touch_px:.2f} {arrow} ₹{level:g}"
        cond = "above or equal to" if direction == "above" else "below or equal to"
        body = (
            f"Price {cond} ₹{level:g} (live ₹{px:.2f}"
            + (f", session high ₹{hi:g}" if direction == "above" and hi is not None else "")
            + (f", session low ₹{lo:g}" if direction == "below" and lo is not None else "")
            + ")"
            + (f" · {lists}" if lists else "")
        )
        kind = "price_above" if direction == "above" else "price_below"
        gen = int(t.get("generation") or 0)
        tid = str(t.get("id") or "")
        if _emit(
            base_dir, session, settings,
            source="watchlist",
            kind=kind,
            symbol=sym,
            title=title,
            body=body,
            watchlist_name=(sym_to_lists.get(sym) or [None])[0],
            meta={
                "direction": direction,
                "level": level,
                "price": px,
                "session_high": hi,
                "session_low": lo,
                "touch_price": touch_px,
                "target_id": tid,
            },
            dedup_day=f"{tid}|g{gen}",
        ):
            created += 1
            try:
                alerts_store.mark_price_target_triggered(
                    base_dir, target_id=tid, session=session
                )
            except Exception as e:
                _log(f"disarm price target {tid}: {e}")
    return created


def _evaluate_watchlists(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    watchlists_path: Path,
    db_path: Path,
    settings: dict[str, Any],
    fetch_earnings_fn: Callable[..., dict],
) -> int:
    watchlists = _parse_watchlists(_load_json_list(watchlists_path))
    enabled = [w for w in watchlists if w.get("notifications_enabled")]
    if not enabled:
        return 0
    created = 0
    stock_syms: set[str] = set()
    sym_to_lists: dict[str, list[str]] = {}
    for w in enabled:
        for it in w["items"]:
            if it["type"] != "stock":
                continue
            sym = it["symbol"]
            stock_syms.add(sym)
            sym_to_lists.setdefault(sym, []).append(w["name"])

    if not stock_syms:
        return 0

    # Day-move % only during market hours — not at midnight on a new session day.
    if _is_nse_market_hours():
        day_move_pct = float(settings.get("day_move_pct") or 3.0)
        changes = _day_move_changes(db_path, stock_syms)
        for sym, chg in changes.items():
            # Watchlist: alert when the stock has gone *up* by at least the threshold.
            if chg < day_move_pct:
                continue
            lists = ", ".join(sym_to_lists.get(sym) or [])
            title = f"{sym} +{chg:.2f}% today"
            body = f"Watchlist day move ≥ +{day_move_pct:g}% ({lists})"
            if _emit(
                base_dir, session, settings,
                source="watchlist", kind="day_move_up", symbol=sym,
                title=title, body=body,
                watchlist_name=(sym_to_lists.get(sym) or [None])[0],
                meta={"change_pct": chg, "threshold": day_move_pct},
            ):
                created += 1

    created += _evaluate_price_targets(
        base_dir, session, settings, db_path, stock_syms, sym_to_lists
    )

    today = datetime.now(IST).date()
    try:
        reported = fetch_earnings_fn(
            mode="reported",
            year=today.year,
            month=today.month,
            limit=2000,
            use_cache=True,
            symbols=sorted(stock_syms),
        )
        for row in reported.get("rows") or []:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym not in stock_syms:
                continue
            rel = str(row.get("earnings_release_date") or "").strip()[:10]
            if rel != today.isoformat():
                continue
            lists = ", ".join(sym_to_lists.get(sym) or [])
            title = f"{sym} reported today"
            body = format_earnings_alert_body(row)
            if lists:
                body = f"{body}\nWatchlist: {lists}"
            eps_ready = alerts_store.surprise_ready(row.get("eps_surprise_pct"))
            rev_ready = alerts_store.surprise_ready(row.get("revenue_surprise_pct"))
            if _emit(
                base_dir, session, settings,
                source="watchlist", kind="earnings_reported", symbol=sym,
                title=title, body=body,
                watchlist_name=(sym_to_lists.get(sym) or [None])[0],
                meta={
                    "earnings_release_date": rel,
                    "eps_surprise_pct": row.get("eps_surprise_pct"),
                    "revenue_surprise_pct": row.get("revenue_surprise_pct"),
                    "eps_ready": eps_ready,
                    "revenue_ready": rev_ready,
                },
                dedup_day=alerts_store.earnings_dedup_day(rel, eps_ready, rev_ready),
            ):
                created += 1
    except Exception as e:
        _log(f"watchlist reported earnings: {e}")

    return created


def _evaluate_portfolio(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    portfolio_path: Path,
    db_path: Path,
    settings: dict[str, Any],
    fetch_earnings_fn: Optional[Callable[..., dict]] = None,
) -> int:
    if not settings.get("portfolio_notifications_enabled"):
        return 0
    syms = _portfolio_stock_symbols(portfolio_path)
    if not syms:
        return 0
    try:
        threshold = float(settings.get("portfolio_day_move_pct") or 3.0)
    except (TypeError, ValueError):
        threshold = 3.0
    threshold = max(0.5, min(50.0, threshold))
    created = 0
    if _is_nse_market_hours():
        changes = _day_move_changes(db_path, syms)
        for sym, chg in changes.items():
            # Portfolio: alert when the stock has gone *up* by at least the threshold.
            if chg < threshold:
                continue
            title = f"{sym} +{chg:.2f}% today"
            body = f"Portfolio day move ≥ +{threshold:g}% (up {chg:+.2f}%)"
            if _emit(
                base_dir, session, settings,
                source="portfolio", kind="portfolio_day_move_up", symbol=sym,
                title=title, body=body,
                meta={"change_pct": chg, "threshold": threshold},
            ):
                created += 1

    # Portfolio holdings that reported earnings today → Telegram "Portfolio Update".
    if fetch_earnings_fn is None:
        return created
    today = datetime.now(IST).date()
    try:
        reported = fetch_earnings_fn(
            mode="reported",
            year=today.year,
            month=today.month,
            limit=2000,
            use_cache=True,
            symbols=sorted(syms),
        )
        for row in reported.get("rows") or []:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym not in syms:
                continue
            rel = str(row.get("earnings_release_date") or "").strip()[:10]
            if rel != today.isoformat():
                continue
            body = format_earnings_alert_body(row)
            eps_ready = alerts_store.surprise_ready(row.get("eps_surprise_pct"))
            rev_ready = alerts_store.surprise_ready(row.get("revenue_surprise_pct"))
            if _emit(
                base_dir, session, settings,
                source="portfolio",
                kind="portfolio_earnings_reported",
                symbol=sym,
                title=f"Portfolio Update · {sym}",
                body=body,
                meta={
                    "header": "Portfolio Update",
                    "earnings_release_date": rel,
                    "date": rel,
                    "eps_surprise_pct": row.get("eps_surprise_pct"),
                    "revenue_surprise_pct": row.get("revenue_surprise_pct"),
                    "eps_ready": eps_ready,
                    "revenue_ready": rev_ready,
                },
                dedup_day=alerts_store.earnings_dedup_day(rel, eps_ready, rev_ready),
            ):
                created += 1
    except Exception as e:
        _log(f"portfolio reported earnings: {e}")

    return created


def _evaluate_earnings_page(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    settings: dict[str, Any],
    fetch_earnings_fn: Callable[..., dict],
) -> int:
    if not settings.get("earnings_notifications_enabled"):
        return 0
    snap = settings.get("earnings_filter_snapshot")
    # Always reported + current IST month; never upcoming / past UI months.
    kwargs = earnings_alert_fetch_kwargs(snap if isinstance(snap, dict) else {})
    if not kwargs:
        return 0

    created = 0
    try:
        payload = fetch_earnings_fn(**kwargs)
    except Exception as e:
        _log(f"earnings page fetch: {e}")
        return 0

    for row in payload.get("rows") or []:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        body = format_earnings_alert_body(row)
        kind = "earnings_page_reported"
        rel = str(row.get("earnings_release_date") or "").strip()[:10]
        title = f"{sym} earnings"
        # Once per symbol+release at a given completeness; re-alert when
        # previously missing EPS/revenue surprise data fills in.
        if not rel:
            continue
        # Only alert when the release itself is in the current IST month.
        try:
            rel_d = datetime.strptime(rel, "%Y-%m-%d").date()
        except ValueError:
            continue
        today = datetime.now(IST).date()
        if rel_d.year != today.year or rel_d.month != today.month:
            continue
        eps_ready = alerts_store.surprise_ready(row.get("eps_surprise_pct"))
        rev_ready = alerts_store.surprise_ready(row.get("revenue_surprise_pct"))
        if _emit(
            base_dir, session, settings,
            source="earnings", kind=kind, symbol=sym,
            title=title, body=body,
            meta={
                "filter_mode": "reported",
                "date": rel,
                "eps_surprise_pct": row.get("eps_surprise_pct"),
                "revenue_surprise_pct": row.get("revenue_surprise_pct"),
                "eps_ready": eps_ready,
                "revenue_ready": rev_ready,
                "market_cap": row.get("market_cap_basic") or row.get("market_cap"),
                "price": row.get("price"),
                "change_1d_pct": row.get("change_1d_pct") or row.get("change_percent"),
            },
            dedup_day=alerts_store.earnings_dedup_day(rel, eps_ready, rev_ready),
        ):
            created += 1
    return created


# Notify on the day before and the day of the scheduled release (IST).
UPCOMING_SYMBOL_WATCH_LEAD_DAYS = 1


def _evaluate_upcoming_symbol_watches(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    settings: dict[str, Any],
    fetch_earnings_fn: Callable[..., dict],
) -> int:
    """Per-symbol bells from Earnings Upcoming — independent of page filters."""
    watches = alerts_store.normalize_upcoming_watches(
        settings.get("upcoming_earnings_watches")
    )
    if not watches:
        return 0

    today = datetime.now(IST).date()
    # Drop past releases so bells don't linger after the print.
    try:
        settings = alerts_store.prune_expired_upcoming_watches(
            base_dir, session=session, today=today.isoformat()
        )
        watches = alerts_store.normalize_upcoming_watches(
            settings.get("upcoming_earnings_watches")
        )
    except Exception as e:
        _log(f"prune upcoming watches: {e}")

    armed = [w for w in watches if w.get("enabled")]
    if not armed:
        return 0

    horizon = today + timedelta(days=UPCOMING_SYMBOL_WATCH_LEAD_DAYS)
    due = []
    for w in armed:
        try:
            rel_d = datetime.strptime(w["release_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= rel_d <= horizon:
            due.append(w)
    if not due:
        return 0

    # Enrich from earnings fetch when possible (best-effort).
    row_by_sym: dict[str, dict[str, Any]] = {}
    try:
        payload = fetch_earnings_fn(
            mode="upcoming",
            period="rolling_30_days",
            limit=2000,
            use_cache=True,
            symbols=sorted({w["symbol"] for w in due}),
        )
        for row in payload.get("rows") or []:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym:
                row_by_sym[sym] = row
    except Exception as e:
        _log(f"upcoming symbol watch fetch: {e}")

    created = 0
    for w in due:
        sym = w["symbol"]
        rel = w["release_date"]
        row = row_by_sym.get(sym) or {
            "symbol": sym,
            "earnings_release_next_date": rel,
        }
        try:
            rel_d = datetime.strptime(rel, "%Y-%m-%d").date()
            days_left = (rel_d - today).days
        except ValueError:
            days_left = 0
        when = "today" if days_left == 0 else "tomorrow"
        title = f"{sym} earnings {when}"
        body = format_earnings_alert_body(row)
        body = f"Upcoming report {rel} ({when})\n{body}"
        eps_ready = alerts_store.surprise_ready(row.get("eps_surprise_pct"))
        rev_ready = alerts_store.surprise_ready(row.get("revenue_surprise_pct"))
        if _emit(
            base_dir, session, settings,
            source="earnings",
            kind="earnings_symbol_upcoming",
            symbol=sym,
            title=title,
            body=body,
            meta={
                "header": "Upcoming earnings",
                "earnings_release_next_date": rel,
                "date": rel,
                "days_until": days_left,
                "eps_ready": eps_ready,
                "revenue_ready": rev_ready,
            },
            dedup_day=alerts_store.earnings_dedup_day(rel, eps_ready, rev_ready),
        ):
            created += 1
    return created


def evaluate_namespace(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    *,
    watchlists_path: Path,
    db_path: Path,
    fetch_earnings_fn: Callable[..., dict],
    portfolio_path: Optional[Path] = None,
) -> int:
    settings = alerts_store.load_settings(base_dir, session=session)
    pf_path = portfolio_path or (watchlists_path.parent / "portfolio.json")
    n = 0
    n += _evaluate_watchlists(base_dir, session, watchlists_path, db_path, settings, fetch_earnings_fn)
    n += _evaluate_portfolio(
        base_dir, session, pf_path, db_path, settings, fetch_earnings_fn=fetch_earnings_fn
    )
    n += _evaluate_earnings_page(base_dir, session, settings, fetch_earnings_fn)
    n += _evaluate_upcoming_symbol_watches(base_dir, session, settings, fetch_earnings_fn)
    return n


def discover_sessions(base_dir: Path) -> list[tuple[Optional[dict[str, Any]], Path]]:
    """
    Returns list of (session_or_None, watchlists_path).
    """
    machine = current_machine_code().strip().upper()
    out: list[tuple[Optional[dict[str, Any]], Path]] = []
    local_wl = base_dir / "data" / "watchlists.json"
    if local_wl.is_file():
        out.append((None, local_wl))
    users_root = base_dir / "data" / "users"
    if users_root.is_dir():
        for email_dir in users_root.iterdir():
            if not email_dir.is_dir():
                continue
            machine_dir = email_dir / machine
            if not machine_dir.is_dir():
                continue
            wl = machine_dir / "watchlists.json"
            settings = machine_dir / alerts_store.SETTINGS_FILENAME
            pf = machine_dir / "portfolio.json"
            if wl.is_file() or settings.is_file() or pf.is_file():
                out.append((
                    {"email": email_dir.name.replace("_at_", "@") if "_at_" in email_dir.name else email_dir.name},
                    wl if wl.is_file() else machine_dir / "watchlists.json",
                ))
    seen: set[str] = set()
    unique: list[tuple[Optional[dict[str, Any]], Path]] = []
    for sess, path in out:
        key = str(path.resolve()) if path.exists() else f"{sess}-{path}"
        if key in seen:
            continue
        seen.add(key)
        unique.append((sess, path))
    return unique


def run_once(base_dir: Path, db_path: Path, fetch_earnings_fn: Callable[..., dict]) -> int:
    total = 0
    for session, wl_path in discover_sessions(base_dir):
        try:
            total += evaluate_namespace(
                base_dir,
                session,
                watchlists_path=wl_path,
                db_path=db_path,
                fetch_earnings_fn=fetch_earnings_fn,
                portfolio_path=wl_path.parent / "portfolio.json",
            )
        except Exception:
            _log(f"namespace error:\n{traceback.format_exc()}")
    return total


def _loop(base_dir: Path, db_path: Path, fetch_earnings_fn: Callable[..., dict]) -> None:
    _log("started")
    while not _stop.wait(_interval_sec):
        try:
            n = run_once(base_dir, db_path, fetch_earnings_fn)
            if n:
                _log(f"created {n} alert(s)")
        except Exception:
            _log(f"tick error:\n{traceback.format_exc()}")
    _log("stopped")


def start(base_dir: Path, db_path: Path, fetch_earnings_fn: Callable[..., dict]) -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_loop,
        args=(base_dir, db_path, fetch_earnings_fn),
        name="cim-alert-evaluator",
        daemon=True,
    )
    _thread.start()


def stop() -> None:
    _stop.set()
