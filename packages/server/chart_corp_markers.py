"""Chart markers for stock splits (S) and cash dividends (D)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

SPLIT_MARKER_COLOR = "#a371f7"
DIVIDEND_MARKER_COLOR = "#d29922"

_STANDARD_SPLIT_RATIOS = (2.0, 3.0, 4.0, 5.0, 10.0)


def _norm_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _parse_ymd(raw: Any) -> Optional[str]:
    s = str(raw or "").strip()
    return s[:10] if len(s) >= 10 else None


def _infer_split_ratio(price_move: float, tolerance: float = 0.08) -> Optional[float]:
    if price_move <= 0:
        return None
    for rat in _STANDARD_SPLIT_RATIOS:
        if abs(price_move - (1.0 / rat)) <= tolerance:
            return rat
    return None


def load_split_markers_from_db(conn, symbol: str) -> list[dict[str, Any]]:
    sym = _norm_symbol(symbol)
    if not sym:
        return []
    try:
        import split_utils as su

        su.ensure_stock_split_events_table(conn)
    except Exception:
        pass
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT split_date, ratio, status
            FROM stock_split_events
            WHERE symbol = ? AND status IN ('applied', 'pending', 'failed')
            ORDER BY split_date ASC
            """,
            (sym,),
        )
        for split_date, ratio, status in cur.fetchall():
            d = _parse_ymd(split_date)
            if not d or d in seen:
                continue
            try:
                rat = float(ratio)
            except (TypeError, ValueError):
                continue
            if rat <= 1.0001:
                continue
            seen.add(d)
            out.append({
                "date": d,
                "kind": "split",
                "label": "S",
                "ratio": rat,
                "status": str(status or "").strip().lower(),
                "color": SPLIT_MARKER_COLOR,
            })
    except Exception:
        pass
    try:
        from server.corp_actions import load_corp_actions
        from server.core.install_root import get_data_dir

        for action in load_corp_actions(get_data_dir()):
            if _norm_symbol(action.get("symbol")) != sym:
                continue
            if str(action.get("action_type") or "").strip().lower() != "split":
                continue
            d = _parse_ymd(action.get("record_date") or action.get("ex_date"))
            if not d or d in seen:
                continue
            try:
                rat = float(action.get("ratio") or action.get("split_ratio") or 0)
            except (TypeError, ValueError):
                rat = 0.0
            if rat <= 1.0001:
                continue
            seen.add(d)
            out.append({
                "date": d,
                "kind": "split",
                "label": "S",
                "ratio": rat,
                "status": "registry",
                "color": SPLIT_MARKER_COLOR,
            })
    except Exception:
        pass
    out.sort(key=lambda m: m.get("date", ""))
    return out


def load_dividend_markers_yfinance(symbol: str, *, years_back: int = 12) -> list[dict[str, Any]]:
    sym = _norm_symbol(symbol)
    if not sym:
        return []
    try:
        import yfinance as yf
    except Exception:
        return []
    cutoff = datetime.now(IST).date() - timedelta(days=max(365, years_back * 366))
    out: list[dict[str, Any]] = []
    try:
        divs = yf.Ticker(f"{sym}.NS").dividends
        if divs is None or len(divs) == 0:
            return []
        for ts, amount in divs.items():
            try:
                amt = float(amount)
            except (TypeError, ValueError):
                continue
            if amt <= 0:
                continue
            dt_obj = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if getattr(dt_obj, "tzinfo", None) is not None:
                dt_obj = dt_obj.astimezone(IST)
            bar_d = dt_obj.date() if hasattr(dt_obj, "date") else cutoff
            if bar_d < cutoff:
                continue
            out.append({
                "date": bar_d.isoformat(),
                "kind": "dividend",
                "label": "D",
                "amount": round(amt, 4),
                "color": DIVIDEND_MARKER_COLOR,
            })
    except Exception:
        return []
    out.sort(key=lambda m: m.get("date", ""))
    return out


def load_corp_markers_for_chart(
    conn,
    symbol: str,
    *,
    include_dividends: bool = True,
) -> list[dict[str, Any]]:
    markers = load_split_markers_from_db(conn, symbol)
    if include_dividends:
        markers.extend(load_dividend_markers_yfinance(symbol))
    markers.sort(key=lambda m: (m.get("date", ""), m.get("kind", "")))
    return markers


def detect_unapplied_splits_from_history(
    conn,
    *,
    lookback_days: int = 90,
    tolerance: float = 0.08,
) -> list[dict[str, Any]]:
    """
    Fast SQL pass over recent daily bars — finds nominal split gaps (e.g. 2:1 → ~50% drop).
  Returns list of {symbol, split_date, ratio, source}.
    """
    import split_utils as su

    su.ensure_stock_split_events_table(conn)
    lookback_days = max(7, int(lookback_days))
    fetch_from = (datetime.now(IST).date() - timedelta(days=lookback_days + 30)).isoformat()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            WITH day_bars AS (
              SELECT Symbol,
                     substr(Date, 1, 10) AS d,
                     CAST(Close AS REAL) AS c
              FROM historical_data
              WHERE substr(Date, 1, 10) >= ?
                AND Close IS NOT NULL AND Close > 0
            ),
            paired AS (
              SELECT Symbol, d, c,
                     LAG(c) OVER (PARTITION BY Symbol ORDER BY d) AS prev_c
              FROM day_bars
            )
            SELECT Symbol, d, c, prev_c
            FROM paired
            WHERE prev_c IS NOT NULL AND prev_c > 0
              AND d >= date('now', '-{int(lookback_days)} days')
            """,
            (fetch_from,),
        )
        rows = cur.fetchall()
    except Exception:
        return []

    hits: list[dict[str, Any]] = []
    for sym_raw, split_date, cur_c, prev_c in rows:
        sym = _norm_symbol(sym_raw)
        sd = _parse_ymd(split_date)
        if not sym or not sd:
            continue
        try:
            move = float(cur_c) / float(prev_c)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        ratio = _infer_split_ratio(move, tolerance=tolerance)
        if ratio is None:
            continue
        if su.is_split_applied(conn, sym, sd, ratio):
            continue
        hits.append({
            "symbol": sym,
            "split_date": sd,
            "ratio": ratio,
            "source": "db_discontinuity",
        })
    return hits
