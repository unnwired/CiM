"""Corporate action registry for P&L ledger (bonus/split on open lots)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

from server.pnl_ledger import (
    _normalize_symbol,
    apply_bonus,
    apply_split_to_open_lots,
    symbol_open_qty,
    today_sale_date_ist,
)


def _repo_corp_actions_path() -> Path:
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    return repo_root / "data" / "corp_actions.json"


def _corp_actions_path(data_dir: Optional[Path] = None) -> Path:
    if data_dir:
        return Path(data_dir) / "corp_actions.json"
    return _repo_corp_actions_path()


def load_corp_actions(data_dir: Optional[Path] = None) -> list[dict]:
    """Load corp actions from data_dir/corp_actions.json or repo default."""
    paths: list[Path] = [_corp_actions_path(data_dir), _repo_corp_actions_path()]
    for path in paths:
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            actions = raw.get("actions") if isinstance(raw, dict) else raw
            if isinstance(actions, list):
                return [a for a in actions if isinstance(a, dict)]
    return []


def upsert_split_corp_action(
    data_dir: Optional[Path],
    *,
    symbol: str,
    ex_date: str,
    ratio: float,
    source: str = "split_watch",
) -> bool:
    """
    Persist a split in install data_dir/corp_actions.json so Upstox OHLC adjustment
    (upstox_adjust) can back-adjust pre-split bars on refresh.
    """
    sym = _normalize_symbol(symbol)
    rd = _parse_record_date(ex_date)
    if not sym or not rd:
        return False
    try:
        rat = float(ratio)
    except (TypeError, ValueError):
        return False
    if rat <= 1.0001:
        return False

    target = _corp_actions_path(data_dir)
    actions: list[dict] = []
    if target.is_file():
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            existing = raw.get("actions") if isinstance(raw, dict) else raw
            if isinstance(existing, list):
                actions = [a for a in existing if isinstance(a, dict)]
        except (OSError, json.JSONDecodeError):
            actions = []

    kept: list[dict] = []
    replaced = False
    for action in actions:
        a_sym = _normalize_symbol(action.get("symbol"))
        a_type = str(action.get("action_type") or "").strip().lower()
        a_rd = _parse_record_date(action.get("record_date") or action.get("ex_date"))
        try:
            a_rat = float(action.get("ratio") or action.get("split_ratio") or 0)
        except (TypeError, ValueError):
            a_rat = 0.0
        if a_sym == sym and a_type == "split" and a_rd == rd:
            if abs(a_rat - rat) < 1e-6:
                kept.append(action)
                replaced = True
                continue
            # Same ex-date, different ratio — replace with latest detection.
            replaced = True
            continue
        kept.append(action)

    if not replaced:
        kept.append({
            "symbol": sym,
            "action_type": "split",
            "record_date": rd,
            "ex_date": rd,
            "ratio": rat,
            "split_ratio": rat,
            "source": source,
        })
    kept.sort(key=lambda a: (a.get("record_date", ""), a.get("symbol", "")))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"actions": kept}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def _parse_record_date(raw: Any) -> Optional[str]:
    s = str(raw or "").strip()
    return s[:10] if len(s) >= 10 else None


def _action_applied(ledger: dict, symbol: str, action: dict) -> bool:
    sym = _normalize_symbol(symbol)
    meta = ledger.get("corp_actions_applied")
    if not isinstance(meta, dict):
        return False
    key = f"{sym}:{action.get('action_type')}:{action.get('record_date')}"
    return key in meta.get("keys", [])


def _mark_action_applied(ledger: dict, symbol: str, action: dict) -> None:
    sym = _normalize_symbol(symbol)
    meta = ledger.setdefault("corp_actions_applied", {"keys": []})
    keys = meta.setdefault("keys", [])
    key = f"{sym}:{action.get('action_type')}:{action.get('record_date')}"
    if key not in keys:
        keys.append(key)


def _lot_flag_indicates_action(ledger: dict, action: dict) -> bool:
    """True when open lots already carry the adjustment marker for this action.

    Guards against double-application when a bonus/split was applied via the manual
    repair path (which stamps the lot flag but never recorded the corp_actions_applied
    key). Without this, the registry treats the action as pending and re-applies it,
    halving cost basis and inflating gains.
    """
    sym = _normalize_symbol(action.get("symbol"))
    action_type = str(action.get("action_type") or "").strip().lower()
    lots = [
        p
        for p in ledger.get("positions", [])
        if isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym
    ]
    if not lots:
        return False

    if action_type == "bonus":
        num = int(action.get("ratio_num") or 1)
        den = int(action.get("ratio_den") or 2)
        flag = f"bonus_adjusted_{num}_{den}"
        return any(bool(p.get(flag)) for p in lots)

    if action_type == "split":
        try:
            ratio = float(action.get("ratio") or action.get("split_ratio") or 0)
        except (TypeError, ValueError):
            ratio = 0.0
        if ratio <= 0:
            return False
        for p in lots:
            if not p.get("split_adjusted"):
                continue
            try:
                lot_ratio = float(p.get("split_ratio") or 0)
            except (TypeError, ValueError):
                lot_ratio = 0.0
            if abs(lot_ratio - ratio) < 1e-9:
                return True
        return False

    return False


def backfill_applied_from_lot_flags(
    ledger: dict,
    symbols: set[str],
    actions: list[dict],
) -> list[str]:
    """Record corp_actions_applied keys for actions already reflected by lot flags.

    Heals legacy ledgers where a bonus/split was applied via the manual repair path
    (lot flag set, registry key missing). Returns the list of keys backfilled.
    """
    syms = {_normalize_symbol(s) for s in symbols}
    healed: list[str] = []
    for action in actions:
        sym = _normalize_symbol(action.get("symbol"))
        if sym not in syms:
            continue
        if _action_applied(ledger, sym, action):
            continue
        if _lot_flag_indicates_action(ledger, action):
            _mark_action_applied(ledger, sym, action)
            healed.append(
                f"{sym}:{action.get('action_type')}:{action.get('record_date')}"
            )
    return healed


def pending_corp_actions(
    ledger: dict,
    symbols: set[str],
    actions: list[dict],
    *,
    as_of: Optional[str] = None,
) -> list[dict]:
    """Actions with record_date <= as_of for symbols in set, not yet applied."""
    today = as_of or today_sale_date_ist()
    syms = {_normalize_symbol(s) for s in symbols}
    out: list[dict] = []
    for action in actions:
        sym = _normalize_symbol(action.get("symbol"))
        if sym not in syms:
            continue
        rd = _parse_record_date(action.get("record_date"))
        if not rd or rd > today:
            continue
        if _action_applied(ledger, sym, action):
            continue
        if _lot_flag_indicates_action(ledger, action):
            continue
        if symbol_open_qty(ledger, sym) <= 0:
            continue
        out.append(dict(action, symbol=sym, record_date=rd))
    out.sort(key=lambda a: (a.get("record_date", ""), a.get("symbol", "")))
    return out


def apply_corp_action_to_ledger(ledger: dict, action: dict) -> dict[str, Any]:
    """Apply one registry action to open lots."""
    sym = _normalize_symbol(action.get("symbol"))
    action_type = str(action.get("action_type") or "").strip().lower()
    if _action_applied(ledger, sym, action):
        return {"symbol": sym, "skipped": True, "reason": "already_applied"}

    if action_type == "bonus":
        num = int(action.get("ratio_num") or 1)
        den = int(action.get("ratio_den") or 2)
        result = apply_bonus(ledger, sym, ratio_num=num, ratio_den=den)
        if result.get("bonus_shares_added", 0) > 0 or result.get("lots_adjusted"):
            _mark_action_applied(ledger, sym, action)
        return {"symbol": sym, "action_type": "bonus", **result}

    if action_type == "split":
        ratio = float(action.get("ratio") or action.get("split_ratio") or 1)
        ex_date = _parse_record_date(action.get("record_date") or action.get("ex_date"))
        result = apply_split_to_open_lots(ledger, sym, ratio=ratio, ex_date=ex_date)
        if result.get("lots_adjusted"):
            _mark_action_applied(ledger, sym, action)
        return {"symbol": sym, "action_type": "split", **result}

    return {"symbol": sym, "skipped": True, "reason": f"unknown action_type: {action_type}"}


def apply_pending_corp_actions(
    ledger: dict,
    symbols: set[str],
    actions: list[dict],
    *,
    as_of: Optional[str] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Apply all pending corp actions for symbols. Returns summary per action."""
    if not dry_run:
        backfill_applied_from_lot_flags(ledger, symbols, actions)
    pending = pending_corp_actions(ledger, symbols, actions, as_of=as_of)
    applied: list[dict] = []
    for action in pending:
        if dry_run:
            applied.append({
                "symbol": action["symbol"],
                "action_type": action.get("action_type"),
                "record_date": action.get("record_date"),
                "dry_run": True,
            })
            continue
        applied.append(apply_corp_action_to_ledger(ledger, action))
    return applied


def same_day_sell_likely(ledger: dict, holdings_rows: list[dict]) -> list[dict]:
    """Heuristic: open qty > holdings qty after today's sells may mean missing positions file."""
    hints: list[dict] = []
    for row in holdings_rows:
        sym = row["symbol"]
        ledger_qty = symbol_open_qty(ledger, sym)
        holdings_qty = row["quantity"]
        if ledger_qty > holdings_qty:
            hints.append({
                "symbol": sym,
                "ledger_qty": ledger_qty,
                "holdings_qty": holdings_qty,
                "delta": ledger_qty - holdings_qty,
                "same_day_sell_likely": True,
            })
    return hints
