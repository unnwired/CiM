"""Split/bonus price adjustment for Upstox raw OHLC (Yahoo auto_adjust parity)."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from server.corp_actions import load_corp_actions


def _parse_ymd(raw: Any) -> Optional[date]:
    s = str(raw or "").strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _action_ex_date(action: dict[str, Any]) -> Optional[date]:
    for key in ("ex_date", "record_date", "exDate", "recordDate"):
        d = _parse_ymd(action.get(key))
        if d:
            return d
    return None


def _price_multiplier_for_action(action: dict[str, Any]) -> float:
    """
    Factor applied to OHLC on bars strictly before the action's ex/record date.
    Split ratio R (1->R): multiply prices by 1/R.
    Bonus N:M (N new per M held): multiply by M/(N+M).
    """
    action_type = str(action.get("action_type") or action.get("type") or "").strip().lower()
    if action_type == "split":
        try:
            ratio = float(action.get("ratio") or action.get("split_ratio") or 0)
        except (TypeError, ValueError):
            ratio = 0.0
        if ratio <= 0:
            return 1.0
        return 1.0 / ratio
    if action_type == "bonus":
        try:
            num = float(action.get("ratio_num") or 1)
            den = float(action.get("ratio_den") or 1)
        except (TypeError, ValueError):
            return 1.0
        if num <= 0 or den <= 0:
            return 1.0
        return den / (num + den)
    return 1.0


def _actions_from_split_watch(data_dir: Optional[Path]) -> list[dict[str, Any]]:
    """Optional split_watch.json may list applied/pending events with ratios."""
    if not data_dir:
        return []
    path = Path(data_dir) / "split_watch.json"
    if not path.is_file():
        return []
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for key in ("events", "applied", "pending", "actions"):
            rows = raw.get(key)
            if isinstance(rows, list):
                out.extend(a for a in rows if isinstance(a, dict))
        # Flat per-symbol maps occasionally used by watch log
        for sym, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            if payload.get("action_type") or payload.get("split_ratio") or payload.get("ratio"):
                out.append({**payload, "symbol": payload.get("symbol") or sym})
    return out


def load_adjustment_actions(
    *,
    data_dir: Optional[Path] = None,
    symbol: Optional[str] = None,
) -> list[dict[str, Any]]:
    actions = list(load_corp_actions(data_dir))
    actions.extend(_actions_from_split_watch(data_dir))
    sym = _normalize_symbol(symbol) if symbol else None
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        a_sym = _normalize_symbol(action.get("symbol"))
        if not a_sym:
            continue
        if sym and a_sym != sym:
            continue
        ex = _action_ex_date(action)
        if not ex:
            continue
        mult = _price_multiplier_for_action(action)
        if abs(mult - 1.0) < 1e-12:
            continue
        key = f"{a_sym}:{action.get('action_type')}:{ex.isoformat()}:{mult}"
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({**action, "symbol": a_sym, "_ex_date": ex, "_price_mult": mult})
    cleaned.sort(key=lambda a: a["_ex_date"])
    return cleaned


def cumulative_price_factor(
    bar_date: date,
    actions: Sequence[dict[str, Any]],
) -> float:
    """Product of multipliers for every action whose ex-date is strictly after bar_date."""
    factor = 1.0
    for action in actions:
        ex = action.get("_ex_date") or _action_ex_date(action)
        if not isinstance(ex, date):
            continue
        if bar_date < ex:
            mult = float(action.get("_price_mult") or _price_multiplier_for_action(action))
            factor *= mult
    return factor


def _bar_date_from_row(row: Any) -> Optional[date]:
    if isinstance(row, (list, tuple)) and row:
        raw = row[0]
    elif isinstance(row, dict):
        raw = row.get("date") or row.get("Date") or row.get("timestamp")
    else:
        raw = None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return _parse_ymd(raw)


def adjust_ohlcv_rows(
    symbol: str,
    rows: Sequence[Any],
    *,
    data_dir: Optional[Path] = None,
    actions: Optional[Sequence[dict[str, Any]]] = None,
) -> list[Any]:
    """
    Adjust Upstox raw daily/intraday OHLC to continuous (split/bonus) prices.
    Accepts rows as (date, o, h, l, c, v) or Upstox candle lists
    [ts, o, h, l, c, volume, oi].
    """
    acts = list(actions) if actions is not None else load_adjustment_actions(data_dir=data_dir, symbol=symbol)
    if not acts or not rows:
        return list(rows)

    out: list[Any] = []
    for row in rows:
        bar_d = _bar_date_from_row(row)
        if bar_d is None:
            out.append(row)
            continue
        factor = cumulative_price_factor(bar_d, acts)
        if abs(factor - 1.0) < 1e-12:
            out.append(row)
            continue
        if isinstance(row, tuple):
            row_l = list(row)
        elif isinstance(row, list):
            row_l = list(row)
        else:
            out.append(row)
            continue
        # Indices 1..4 = O H L C; 5 = volume (inverse for share count continuity)
        for i in (1, 2, 3, 4):
            if i < len(row_l) and row_l[i] is not None:
                try:
                    row_l[i] = round(float(row_l[i]) * factor, 2)
                except (TypeError, ValueError):
                    pass
        if len(row_l) > 5 and row_l[5] is not None and factor > 0:
            try:
                row_l[5] = round(float(row_l[5]) / factor, 2)
            except (TypeError, ValueError):
                pass
        out.append(type(row)(row_l) if isinstance(row, tuple) else row_l)
    return out
