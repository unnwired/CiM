"""Parse Zerodha Kite Positions export (today's session only) and book into P&L ledger."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Optional

from server.pnl_ledger import (
    _normalize_symbol,
    book_fifo,
    ensure_portfolio_stock,
    finalize_symbol_after_book,
    mark_portfolio_pnl_tracked,
    parse_entry_price,
    symbol_open_qty,
    today_sale_date_ist,
)

POSITIONS_PRODUCT_KEYS = frozenset({"product"})
POSITIONS_SYMBOL_KEYS = frozenset({"instrument", "symbol", "tradingsymbol"})
POSITIONS_QTY_KEYS = frozenset({"qty", "qty.", "quantity"})
POSITIONS_AVG_KEYS = frozenset({"avg", "avg.", "average_price", "averageprice"})
POSITIONS_LTP_KEYS = frozenset({"ltp", "last_price"})
POSITIONS_PNL_KEYS = frozenset({"p&l", "pnl", "p_l", "pl"})
POSITIONS_CHG_KEYS = frozenset({"chg", "chg.", "change"})

PRICE_ABS_TOL = 0.05


def _normalize_header(name: str) -> str:
    s = str(name or "").strip().lower().replace(" ", "_")
    if s in ("p&l", "p_l"):
        return "pnl"
    return s.replace(".", "")


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    if sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def _pick_column(field_map: dict[str, str], keys: frozenset[str]) -> Optional[str]:
    for k in keys:
        nk = _normalize_header(k)
        if nk in field_map:
            return field_map[nk]
    return None


def _parse_signed_qty(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip().replace(",", "")))
    except (TypeError, ValueError):
        return None


def _parse_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_zerodha_positions_csv(text: str) -> tuple[list[dict], list[dict]]:
    """Parse Kite Positions CSV (today only). Returns normalized rows + parse errors."""
    raw = (text or "").strip()
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    if not raw:
        return [], [{"row": 0, "message": "empty file"}]

    delimiter = _detect_delimiter(raw)
    reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
    if not reader.fieldnames:
        return [], [{"row": 0, "message": "missing header row"}]

    field_map = {_normalize_header(h): h for h in reader.fieldnames if h}
    prod_col = _pick_column(field_map, POSITIONS_PRODUCT_KEYS)
    sym_col = _pick_column(field_map, POSITIONS_SYMBOL_KEYS)
    qty_col = _pick_column(field_map, POSITIONS_QTY_KEYS)
    avg_col = _pick_column(field_map, POSITIONS_AVG_KEYS)
    ltp_col = _pick_column(field_map, POSITIONS_LTP_KEYS)
    pnl_col = _pick_column(field_map, POSITIONS_PNL_KEYS)
    chg_col = _pick_column(field_map, POSITIONS_CHG_KEYS)

    missing = []
    if not sym_col:
        missing.append("instrument")
    if not qty_col:
        missing.append("qty")
    if not avg_col:
        missing.append("avg")
    if missing:
        return [], [{"row": 0, "message": f"missing columns: {', '.join(sorted(missing))}"}]

    rows: list[dict] = []
    errors: list[dict] = []
    today = today_sale_date_ist()

    for line_no, raw_row in enumerate(reader, start=2):
        product = str(raw_row.get(prod_col, "CNC") if prod_col else "CNC").strip().upper()
        if product != "CNC":
            continue
        sym = _normalize_symbol(raw_row.get(sym_col, ""))
        signed_qty = _parse_signed_qty(raw_row.get(qty_col))
        avg = parse_entry_price(raw_row.get(avg_col))
        if not sym:
            errors.append({"row": line_no, "message": "missing instrument"})
            continue
        if signed_qty is None or signed_qty == 0:
            continue
        if avg is None:
            errors.append({"row": line_no, "message": f"invalid avg for {sym}"})
            continue

        side = "sell" if signed_qty < 0 else "buy"
        qty = abs(signed_qty)
        row = {
            "symbol": sym,
            "side": side,
            "qty": qty,
            "avg": avg,
            "ltp": _parse_float(raw_row.get(ltp_col)) if ltp_col else None,
            "broker_pnl": _parse_float(raw_row.get(pnl_col)) if pnl_col else None,
            "broker_chg": _parse_float(raw_row.get(chg_col)) if chg_col else None,
            "trade_date": today,
            "source_row": line_no,
        }
        rows.append(row)

    return rows, errors


def _position_already_booked(ledger: dict, row: dict) -> bool:
    """Dedupe: same symbol + today + qty + price already imported or manually booked."""
    sym = row["symbol"]
    today = row["trade_date"]
    qty = row["qty"]
    price = row["avg"]
    side = row["side"]

    if side == "sell":
        total_same_day_price = 0
        for t in ledger.get("closed_trades", []):
            if not isinstance(t, dict):
                continue
            if _normalize_symbol(t.get("symbol")) != sym:
                continue
            if str(t.get("sale_date") or "")[:10] != today:
                continue
            exit_p = parse_entry_price(t.get("exit_price"))
            if exit_p is None or abs(exit_p - price) > PRICE_ABS_TOL:
                continue
            total_same_day_price += int(t.get("qty_sold") or 0)
        return total_same_day_price >= qty

    for p in ledger.get("positions", []):
        if not isinstance(p, dict):
            continue
        if _normalize_symbol(p.get("symbol")) != sym:
            continue
        if str(p.get("entry_date") or "")[:10] != today:
            continue
        if int(p.get("qty") or 0) != qty:
            continue
        entry = parse_entry_price(p.get("entry_price"))
        if entry is not None and abs(entry - price) <= PRICE_ABS_TOL:
            src = str(p.get("import_source") or "")
            if src in ("zerodha_positions_today", "manual"):
                return True
    return False


def preview_todays_positions(ledger: dict, rows: list[dict]) -> dict:
    """Classify positions rows into apply vs skip; optional P&L cross-check."""
    positions_today: list[dict] = []
    to_apply: list[dict] = []
    skipped: list[dict] = []
    pnl_check: list[dict] = []

    for row in rows:
        entry = {
            "symbol": row["symbol"],
            "side": row["side"],
            "qty": row["qty"],
            "avg": row["avg"],
            "broker_pnl": row.get("broker_pnl"),
            "broker_chg": row.get("broker_chg"),
        }
        positions_today.append(entry)
        if _position_already_booked(ledger, row):
            skipped.append({**entry, "reason": "already_booked"})
            continue
        if row["side"] == "sell" and symbol_open_qty(ledger, row["symbol"]) < row["qty"]:
            skipped.append({**entry, "reason": "insufficient_open_qty"})
            continue
        to_apply.append(entry)

        if row["side"] == "sell" and row.get("broker_pnl") is not None:
            pnl_check.append({
                "symbol": row["symbol"],
                "broker_pnl": row["broker_pnl"],
                "note": "realized after apply",
            })

    return {
        "positions_today": positions_today,
        "positions_to_apply": to_apply,
        "positions_skipped": skipped,
        "positions_pnl_check": pnl_check,
    }


def apply_todays_positions(
    ledger: dict,
    portfolio_items: list,
    rows: list[dict],
    *,
    quote_map: Optional[dict[str, dict]] = None,
    dry_run: bool = False,
) -> dict:
    """Book today's sells via FIFO and add today's buys as open lots."""
    quote_map = quote_map or {}
    preview = preview_todays_positions(ledger, rows)
    if dry_run:
        return {
            **preview,
            "buys_applied": len([r for r in preview["positions_to_apply"] if r["side"] == "buy"]),
            "sells_applied": len([r for r in preview["positions_to_apply"] if r["side"] == "sell"]),
            "closed_trades_added": 0,
        }

    buys_applied = 0
    sells_applied = 0
    closed_added = 0
    errors: list[dict] = []

    row_by_key = {(r["symbol"], r["side"], r["qty"], r["avg"]): r for r in rows}
    for entry in preview["positions_to_apply"]:
        row = row_by_key.get((entry["symbol"], entry["side"], entry["qty"], entry["avg"]))
        if not row:
            continue
        sym = row["symbol"]
        qsnap = quote_map.get(sym, {})
        try:
            ensure_portfolio_stock(portfolio_items, sym)
            mark_portfolio_pnl_tracked(portfolio_items, sym)
            if row["side"] == "sell":
                trades = book_fifo(
                    ledger,
                    symbol=sym,
                    exit_price=row["avg"],
                    qty_sold=row["qty"],
                    sale_date=row["trade_date"],
                    quote_snapshot=qsnap,
                    portfolio_items=portfolio_items,
                )
                for t in trades:
                    t["import_source"] = "zerodha_positions_today"
                sells_applied += 1
                closed_added += len(trades)
                finalize_symbol_after_book(ledger, portfolio_items, sym)
            else:
                pos = {
                    "id": str(uuid.uuid4()),
                    "symbol": sym,
                    "entry_price": row["avg"],
                    "qty": row["qty"],
                    "entry_date": row["trade_date"],
                    "created_at": f"{row['trade_date']}T15:30:00",
                    "import_source": "zerodha_positions_today",
                }
                ledger.setdefault("positions", []).append(pos)
                from server.pnl_cash import record_buy_cost

                record_buy_cost(
                    ledger,
                    qty=int(row["qty"]),
                    entry_price=float(row["avg"]),
                    position_id=str(pos["id"]),
                    symbol=sym,
                    ref_key=(
                        f"buy:zerodha_pos:{sym}:{row['qty']}:{row['avg']}:{row['trade_date']}"
                    ),
                )
                buys_applied += 1
        except ValueError as exc:
            errors.append({"symbol": sym, "message": str(exc)})

    return {
        **preview,
        "buys_applied": buys_applied,
        "sells_applied": sells_applied,
        "closed_trades_added": closed_added,
        "errors": errors,
    }
