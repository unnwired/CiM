"""Available cash ledger for P&L — auto-updates on buys/sells; bank deposit/withdraw."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_CASH_LOG_MAX = 500


def ensure_cash_state(ledger: dict) -> None:
    if "available_cash" not in ledger:
        ledger["available_cash"] = 0.0
    if not isinstance(ledger.get("cash_log"), list):
        ledger["cash_log"] = []
    if not isinstance(ledger.get("cash_refs"), dict):
        ledger["cash_refs"] = {}


def get_available_cash(ledger: dict) -> float:
    ensure_cash_state(ledger)
    try:
        return round(float(ledger.get("available_cash") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _round_inr(val: float) -> float:
    return round(float(val), 2)


def _apply_cash_delta(
    ledger: dict,
    delta: float,
    *,
    kind: str,
    ref_key: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> float:
    ensure_cash_state(ledger)
    if ref_key:
        refs = ledger["cash_refs"]
        if refs.get(ref_key):
            return get_available_cash(ledger)
        refs[ref_key] = True

    bal = _round_inr(get_available_cash(ledger) + float(delta))
    ledger["available_cash"] = bal
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "amount": _round_inr(delta),
        "balance_after": bal,
        "at": datetime.now(IST).isoformat(),
    }
    if ref_key:
        entry["ref_key"] = ref_key
    if meta:
        for k, v in meta.items():
            if v is not None:
                entry[k] = v
    log = ledger["cash_log"]
    log.append(entry)
    if len(log) > _CASH_LOG_MAX:
        ledger["cash_log"] = log[-_CASH_LOG_MAX:]
    return bal


def record_sell_proceeds(
    ledger: dict,
    *,
    qty_sold: int,
    exit_price: float,
    trade_id: str,
    symbol: str,
) -> float:
    qs = int(qty_sold)
    px = float(exit_price)
    if qs <= 0 or px <= 0:
        return get_available_cash(ledger)
    amount = _round_inr(qs * px)
    ref = f"sell:trade:{trade_id}"
    return _apply_cash_delta(
        ledger,
        amount,
        kind="sell_credit",
        ref_key=ref,
        meta={"symbol": str(symbol or "").strip().upper(), "qty": qs, "price": px},
    )


def record_buy_cost(
    ledger: dict,
    *,
    qty: int,
    entry_price: float,
    position_id: str,
    symbol: str,
    ref_key: Optional[str] = None,
) -> float:
    q = int(qty)
    px = float(entry_price)
    if q <= 0 or px <= 0:
        return get_available_cash(ledger)
    amount = _round_inr(q * px)
    ref = ref_key or f"buy:position:{position_id}"
    return _apply_cash_delta(
        ledger,
        -amount,
        kind="buy_debit",
        ref_key=ref,
        meta={"symbol": str(symbol or "").strip().upper(), "qty": q, "price": px},
    )


def record_bank_deposit(ledger: dict, amount: float, *, note: Optional[str] = None) -> float:
    amt = float(amount)
    if amt <= 0:
        raise ValueError("amount must be positive")
    return _apply_cash_delta(
        ledger,
        amt,
        kind="bank_deposit",
        meta={"note": (note or "").strip() or None},
    )


def record_bank_withdrawal(ledger: dict, amount: float, *, note: Optional[str] = None) -> float:
    amt = float(amount)
    if amt <= 0:
        raise ValueError("amount must be positive")
    return _apply_cash_delta(
        ledger,
        -amt,
        kind="bank_withdrawal",
        meta={"note": (note or "").strip() or None},
    )


def set_available_cash_balance(
    ledger: dict,
    target: float,
    *,
    note: Optional[str] = None,
) -> float:
    tgt = float(target)
    if tgt < 0:
        raise ValueError("available_cash cannot be negative")
    current = get_available_cash(ledger)
    delta = _round_inr(tgt - current)
    if abs(delta) < 0.005:
        return current
    return _apply_cash_delta(
        ledger,
        delta,
        kind="manual_adjustment",
        meta={"note": (note or "").strip() or "manual balance"},
    )
