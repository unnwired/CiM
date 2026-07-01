"""Parse Zerodha Console holdings CSV and reconcile open lots to broker truth."""
from __future__ import annotations

import csv
import io
from typing import Any, Optional

from server.pnl_ledger import (
    _normalize_symbol,
    compute_symbol_avg_entry,
    parse_entry_price,
    set_symbol_open_snapshot,
    symbol_open_qty,
)

HOLDINGS_SYMBOL_KEYS = frozenset({"symbol", "tradingsymbol", "instrument"})
HOLDINGS_QTY_KEYS = frozenset({"quantity", "qty", "qty.", "qty_held"})
HOLDINGS_AVG_KEYS = frozenset({
    "average_price",
    "avg_price",
    "average_cost",
    "avg_cost",
    "avg.",
    "avg",
    "averageprice",
    "buy_avg",
    "buy_average",
    "averagecost",
})
HOLDINGS_INVESTED_KEYS = frozenset({
    "invested",
    "invested_value",
    "investment_value",
    "buy_value",
    "cost",
})

AVG_PRICE_ABS_TOL = 0.05
AVG_PRICE_REL_TOL = 0.001


def _normalize_header(name: str) -> str:
    return str(name or "").strip().lower().replace(" ", "_").replace(".", "")


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


def _parse_qty(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        v = int(float(str(raw).strip().replace(",", "")))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _avg_prices_match(ledger_avg: Optional[float], holdings_avg: Optional[float]) -> bool:
    if ledger_avg is None or holdings_avg is None:
        return ledger_avg == holdings_avg
    diff = abs(ledger_avg - holdings_avg)
    if diff <= AVG_PRICE_ABS_TOL:
        return True
    base = max(abs(ledger_avg), abs(holdings_avg), 1.0)
    return diff / base <= AVG_PRICE_REL_TOL


def parse_zerodha_holdings_csv(text: str) -> tuple[list[dict], list[dict]]:
    """Parse Zerodha holdings export. Returns (rows, parse_errors)."""
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
    sym_col = _pick_column(field_map, HOLDINGS_SYMBOL_KEYS)
    qty_col = _pick_column(field_map, HOLDINGS_QTY_KEYS)
    avg_col = _pick_column(field_map, HOLDINGS_AVG_KEYS)
    invested_col = _pick_column(field_map, HOLDINGS_INVESTED_KEYS)
    missing = []
    if not sym_col:
        missing.append("symbol")
    if not qty_col:
        missing.append("quantity")
    if not avg_col and not invested_col:
        missing.append("average_price")
    if missing:
        detected = ", ".join(sorted(field_map.keys()))
        return [], [{
            "row": 0,
            "message": (
                f"missing columns: {', '.join(sorted(missing))}"
                f" (detected: {detected or 'none'})"
            ),
        }]

    rows: list[dict] = []
    errors: list[dict] = []
    for line_no, raw_row in enumerate(reader, start=2):
        sym = _normalize_symbol(raw_row.get(sym_col, ""))
        qty = _parse_qty(raw_row.get(qty_col))
        avg = parse_entry_price(raw_row.get(avg_col)) if avg_col else None
        if avg is None and invested_col and qty:
            invested = parse_entry_price(raw_row.get(invested_col))
            if invested is not None and qty:
                avg = round(invested / qty, 6)
        if not sym:
            errors.append({"row": line_no, "message": "missing symbol"})
            continue
        if qty is None:
            continue
        if avg is None:
            errors.append({"row": line_no, "message": f"invalid average price for {sym}"})
            continue
        rows.append({
            "symbol": sym,
            "quantity": qty,
            "average_price": avg,
            "source_row": line_no,
        })
    return rows, errors


def compare_ledger_to_holdings(ledger: dict, holdings_rows: list[dict]) -> list[dict]:
    """Return mismatches between ledger open lots and holdings file."""
    mismatches: list[dict] = []
    for row in holdings_rows:
        sym = row["symbol"]
        ledger_qty = symbol_open_qty(ledger, sym)
        ledger_avg = compute_symbol_avg_entry(ledger, sym)
        holdings_qty = row["quantity"]
        holdings_avg = row["average_price"]
        qty_match = ledger_qty == holdings_qty
        avg_match = _avg_prices_match(ledger_avg, holdings_avg)
        if qty_match and avg_match:
            continue
        invested_ledger = round(ledger_qty * ledger_avg, 2) if ledger_avg is not None else None
        invested_holdings = round(holdings_qty * holdings_avg, 2)
        mismatches.append({
            "symbol": sym,
            "ledger_qty": ledger_qty,
            "holdings_qty": holdings_qty,
            "ledger_avg_entry": ledger_avg,
            "holdings_avg_price": holdings_avg,
            "invested_ledger": invested_ledger,
            "invested_holdings": invested_holdings,
        })
    return mismatches


def reconcile_open_to_holdings(
    ledger: dict,
    holdings_rows: list[dict],
    *,
    symbols: Optional[set[str]] = None,
    dry_run: bool = False,
) -> dict[str, list]:
    """
    Replace open lots for symbols that differ from holdings snapshot.
    Does not touch closed trades.
    """
    sym_filter = {_normalize_symbol(s) for s in symbols} if symbols else None
    reconciled: list[dict] = []
    unchanged: list[str] = []
    skipped: list[str] = []

    for row in holdings_rows:
        sym = row["symbol"]
        if sym_filter and sym not in sym_filter:
            skipped.append(sym)
            continue
        ledger_qty = symbol_open_qty(ledger, sym)
        ledger_avg = compute_symbol_avg_entry(ledger, sym)
        holdings_qty = row["quantity"]
        holdings_avg = row["average_price"]
        if ledger_qty == holdings_qty and _avg_prices_match(ledger_avg, holdings_avg):
            unchanged.append(sym)
            continue
        if dry_run:
            reconciled.append({
                "symbol": sym,
                "from_qty": ledger_qty,
                "to_qty": holdings_qty,
                "from_avg": ledger_avg,
                "to_avg": holdings_avg,
            })
            continue
        set_symbol_open_snapshot(
            ledger,
            sym,
            qty=holdings_qty,
            entry_price=holdings_avg,
            import_source="holdings_reconcile",
        )
        reconciled.append({
            "symbol": sym,
            "from_qty": ledger_qty,
            "to_qty": holdings_qty,
            "from_avg": ledger_avg,
            "to_avg": holdings_avg,
        })

    return {"reconciled": reconciled, "unchanged": unchanged, "skipped": skipped}
