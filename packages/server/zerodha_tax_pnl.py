"""Import Zerodha Tax P&L / Console P&L CSV as source of truth for realized (and optional unrealized)."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from server.pnl_ledger import (
    BROKER_ZERODHA,
    _normalize_symbol,
    ensure_portfolio_stock,
    infer_broker,
    mark_portfolio_pnl_tracked,
    parse_entry_date,
    parse_entry_price,
    parse_sale_date,
    set_symbol_open_snapshot,
    symbol_open_qty,
)
from server.portfolio_entry import compute_pl_pct

IST = ZoneInfo("Asia/Kolkata")

SYMBOL_KEYS = frozenset({"symbol", "tradingsymbol", "scrip", "scrip_name", "instrument", "stock_name", "stock"})
QTY_KEYS = frozenset({"quantity", "qty", "qty_sold", "quantity_sold"})
BUY_DATE_KEYS = frozenset({"buy_date", "purchase_date", "acquisition_date", "bought_on", "buy_date_"})
SELL_DATE_KEYS = frozenset({"sell_date", "sale_date", "sold_on", "exit_date"})
BUY_AVG_KEYS = frozenset({
    "buy_average", "buy_avg", "average_buy_price", "avg_buy_price", "buy_price", "purchase_price",
})
SELL_AVG_KEYS = frozenset({
    "sell_average", "sell_avg", "average_sell_price", "avg_sell_price", "sell_price", "exit_price",
})
BUY_VALUE_KEYS = frozenset({"buy_value", "buy_amount", "cost", "cost_value", "purchase_value"})
SELL_VALUE_KEYS = frozenset({"sell_value", "sell_amount", "sale_value", "proceeds"})
REALIZED_KEYS = frozenset({
    "realised_pnl", "realized_pnl", "realised_p&l", "realized_p&l",
    "realised_profit", "realized_profit", "realised_gain_loss", "realized_gain_loss",
    "pnl", "p&l", "profit", "gain_loss", "realised_gain__loss", "realized_gain__loss",
})
OPEN_QTY_KEYS = frozenset({"open_quantity", "open_qty", "quantity_open", "net_qty"})
OPEN_AVG_KEYS = frozenset({
    "average_price", "avg_price", "open_average", "buy_avg_open", "average_cost",
})
OPEN_VALUE_KEYS = frozenset({"open_value", "invested", "open_invested"})
UNREALIZED_KEYS = frozenset({
    "unrealised_pnl", "unrealized_pnl", "unrealised_p&l", "unrealized_p&l",
})


def _normalize_header(name: str) -> str:
    raw = str(name or "").strip().lower()
    raw = raw.replace("%", "pct").replace("/", "_").replace("-", "_").replace(" ", "_")
    while "__" in raw:
        raw = raw.replace("__", "_")
    return raw.strip("_")


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    if sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def _pick_column(
    field_map: dict[str, str],
    keys: frozenset[str],
    *,
    exclude_prefixes: Sequence[str] = (),
) -> Optional[str]:
    exclude = tuple(p.lower() for p in exclude_prefixes)

    def _excluded(nk: str) -> bool:
        return any(nk.startswith(p) or f"_{p}" in nk for p in exclude)

    for k in keys:
        nk = _normalize_header(k)
        if nk in field_map and not _excluded(nk):
            return field_map[nk]
    # Prefer longer / more specific header matches (avoid "pnl" hitting unrealized)
    fuzzy: list[tuple[int, str]] = []
    for nk, original in field_map.items():
        if _excluded(nk):
            continue
        for k in keys:
            key = _normalize_header(k)
            if key and key in nk:
                fuzzy.append((len(key), original))
                break
    if fuzzy:
        fuzzy.sort(key=lambda t: t[0], reverse=True)
        return fuzzy[0][1]
    return None


def _parse_qty(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        s = str(raw).strip().replace(",", "")
        if not s or s == "-":
            return None
        v = int(float(s))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_money(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        s = str(raw).strip().replace(",", "").replace("₹", "").replace(" ", "")
        if not s or s == "-":
            return None
        # parentheses negatives
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "-":
        return None
    # reuse ledger helpers when possible
    ed = parse_entry_date(s) or parse_sale_date(s)
    if ed:
        return ed
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    # excel serial?
    try:
        n = float(s)
        if 30000 < n < 60000:
            from datetime import date, timedelta

            base = date(1899, 12, 30)
            return (base + timedelta(days=int(n))).isoformat()
    except (TypeError, ValueError):
        pass
    return None


def _now_ist_iso() -> str:
    return datetime.now(IST).isoformat()


def parse_zerodha_tax_pnl_csv(text: str) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Parse Zerodha Tax P&L / Console P&L CSV.

    Returns (closed_rows, open_rows, parse_errors).
    Closed rows require symbol + qty + realized (or buy/sell values).
    Open rows (optional) come from open_quantity columns on Console P&L exports.
    """
    raw = (text or "").strip()
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    if not raw:
        return [], [], [{"row": 0, "message": "empty file"}]

    # Skip title lines until a header-looking row
    lines = raw.splitlines()
    header_idx = 0
    for i, line in enumerate(lines[:30]):
        low = line.lower()
        if "symbol" in low or "scrip" in low or "tradingsymbol" in low:
            if any(k in low for k in ("realis", "pnl", "p&l", "buy", "sell", "quantity", "qty")):
                header_idx = i
                break
    body = "\n".join(lines[header_idx:])
    delimiter = _detect_delimiter(body)
    reader = csv.DictReader(io.StringIO(body), delimiter=delimiter)
    if not reader.fieldnames:
        return [], [], [{"row": 0, "message": "missing header row"}]

    field_map = {_normalize_header(h): h for h in reader.fieldnames if h}
    sym_col = _pick_column(field_map, SYMBOL_KEYS)
    qty_col = _pick_column(field_map, QTY_KEYS)
    buy_date_col = _pick_column(field_map, BUY_DATE_KEYS)
    sell_date_col = _pick_column(field_map, SELL_DATE_KEYS)
    buy_avg_col = _pick_column(field_map, BUY_AVG_KEYS)
    sell_avg_col = _pick_column(field_map, SELL_AVG_KEYS)
    buy_val_col = _pick_column(field_map, BUY_VALUE_KEYS)
    sell_val_col = _pick_column(field_map, SELL_VALUE_KEYS)
    realized_col = _pick_column(field_map, REALIZED_KEYS, exclude_prefixes=("unreal",))
    open_qty_col = _pick_column(field_map, OPEN_QTY_KEYS)
    open_avg_col = _pick_column(field_map, OPEN_AVG_KEYS)
    open_val_col = _pick_column(field_map, OPEN_VALUE_KEYS)
    unreal_col = _pick_column(field_map, UNREALIZED_KEYS)

    if not sym_col:
        return [], [], [{"row": 0, "message": f"missing symbol column (got: {', '.join(sorted(field_map))})"}]
    if not qty_col and not open_qty_col:
        return [], [], [{"row": 0, "message": "missing quantity / open quantity column"}]
    if not realized_col and not (buy_val_col and sell_val_col) and not (buy_avg_col and sell_avg_col):
        return [], [], [{
            "row": 0,
            "message": "need Realised P&L or Buy/Sell value (or avg) columns",
        }]

    closed_rows: list[dict] = []
    open_rows: list[dict] = []
    errors: list[dict] = []

    for line_no, raw_row in enumerate(reader, start=header_idx + 2):
        sym = _normalize_symbol(raw_row.get(sym_col, ""))
        if not sym or sym in ("TOTAL", "SYMBOL"):
            continue

        qty = _parse_qty(raw_row.get(qty_col)) if qty_col else None
        buy_val = _parse_money(raw_row.get(buy_val_col)) if buy_val_col else None
        sell_val = _parse_money(raw_row.get(sell_val_col)) if sell_val_col else None
        buy_avg = parse_entry_price(raw_row.get(buy_avg_col)) if buy_avg_col else None
        sell_avg = parse_entry_price(raw_row.get(sell_avg_col)) if sell_avg_col else None
        realized = _parse_money(raw_row.get(realized_col)) if realized_col else None

        if qty and buy_avg is None and buy_val is not None:
            buy_avg = round(buy_val / qty, 6)
        if qty and sell_avg is None and sell_val is not None:
            sell_avg = round(sell_val / qty, 6)
        if realized is None and buy_val is not None and sell_val is not None:
            realized = round(sell_val - buy_val, 2)
        if realized is None and qty and buy_avg is not None and sell_avg is not None:
            realized = round(qty * (sell_avg - buy_avg), 2)

        buy_date = _parse_date(raw_row.get(buy_date_col)) if buy_date_col else None
        sell_date = _parse_date(raw_row.get(sell_date_col)) if sell_date_col else None

        # Closed / realized row (Tax P&L capital-gains or Console realised section)
        has_buy_sell = (buy_avg is not None and sell_avg is not None) or (
            buy_val is not None and sell_val is not None
        )
        if qty and (has_buy_sell or realized is not None):
            if realized is None and has_buy_sell:
                if buy_val is not None and sell_val is not None:
                    realized = round(sell_val - buy_val, 2)
                elif buy_avg is not None and sell_avg is not None:
                    realized = round(qty * (sell_avg - buy_avg), 2)
            if buy_avg is None and sell_avg is not None and realized is not None and qty:
                buy_avg = round(sell_avg - (realized / qty), 6)
            if sell_avg is None and buy_avg is not None and realized is not None and qty:
                sell_avg = round(buy_avg + (realized / qty), 6)
            if buy_avg is None or sell_avg is None or realized is None:
                errors.append({"row": line_no, "symbol": sym, "message": "could not resolve buy/sell price or P&L"})
            else:
                closed_rows.append({
                    "symbol": sym,
                    "quantity": qty,
                    "entry_price": float(buy_avg),
                    "exit_price": float(sell_avg),
                    "realized_pl": round(float(realized), 2),
                    "entry_date": buy_date,
                    "sale_date": sell_date,
                    "source_row": line_no,
                })

        # Optional open / unrealized from Console P&L combined export
        open_qty = _parse_qty(raw_row.get(open_qty_col)) if open_qty_col else None
        if open_qty:
            open_avg = parse_entry_price(raw_row.get(open_avg_col)) if open_avg_col else None
            open_val = _parse_money(raw_row.get(open_val_col)) if open_val_col else None
            if open_avg is None and open_val is not None:
                open_avg = round(open_val / open_qty, 6)
            if open_avg is None and buy_avg is not None:
                open_avg = buy_avg
            if open_avg is None:
                errors.append({"row": line_no, "symbol": sym, "message": "open qty without average price"})
            else:
                open_rows.append({
                    "symbol": sym,
                    "quantity": open_qty,
                    "average_price": float(open_avg),
                    "unrealized_pl": _parse_money(raw_row.get(unreal_col)) if unreal_col else None,
                    "source_row": line_no,
                })

    if not closed_rows and not open_rows:
        errors.append({"row": 0, "message": "no realised or open P&L rows parsed"})
    return closed_rows, open_rows, errors


def _strip_zerodha_closed(ledger: dict, symbols: Optional[set[str]] = None) -> int:
    """Remove Zerodha-tagged closed trades (keep Paytm / pure manual).

    When symbols is set, only strip Zerodha closes for those symbols so other
    FY / scrips remain until a Tax P&L covering them is imported.
    """
    kept: list[dict] = []
    removed = 0
    for t in ledger.get("closed_trades", []) or []:
        if not isinstance(t, dict):
            continue
        sym = _normalize_symbol(t.get("symbol"))
        src = str(t.get("import_source") or "").strip().lower()
        is_z = src.startswith("zerodha") or infer_broker(t) == BROKER_ZERODHA
        if is_z and (symbols is None or sym in symbols):
            removed += 1
            continue
        kept.append(t)
    ledger["closed_trades"] = kept
    return removed


def _strip_zerodha_open(ledger: dict) -> int:
    """Remove every Zerodha-tagged open lot while preserving other brokers."""
    kept: list[dict] = []
    removed = 0
    for position in ledger.get("positions", []) or []:
        if not isinstance(position, dict):
            continue
        src = str(position.get("import_source") or "").strip().lower()
        is_z = src.startswith("zerodha") or infer_broker(position) == BROKER_ZERODHA
        if is_z:
            removed += 1
            continue
        kept.append(position)
    ledger["positions"] = kept
    return removed


def _clear_zerodha_import_meta(ledger: dict) -> int:
    """Forget stale Zerodha trade IDs after a broker-wide source-of-truth reset."""
    meta = ledger.get("import_meta")
    if not isinstance(meta, dict):
        meta = {}
        ledger["import_meta"] = meta
    previous = meta.get("zerodha_trade_ids")
    count = len(previous) if isinstance(previous, list) else 0
    meta["zerodha_trade_ids"] = []
    return count


def _count_zerodha_open(ledger: dict) -> int:
    return sum(
        1
        for position in ledger.get("positions", []) or []
        if isinstance(position, dict)
        and (
            str(position.get("import_source") or "").strip().lower().startswith("zerodha")
            or infer_broker(position) == BROKER_ZERODHA
        )
    )


def _require_open_rebuild_source(
    ledger: dict,
    *,
    open_rows: Sequence[dict],
    holdings_rows: Sequence[dict],
    reconcile_holdings: bool,
) -> Optional[dict[str, Any]]:
    """
    Full broker replace strips every Zerodha open lot.
    Refuse when opens would be wiped with no rebuild source.
    """
    existing_opens = _count_zerodha_open(ledger)
    if existing_opens <= 0:
        return None
    if open_rows:
        return None
    if reconcile_holdings and holdings_rows:
        return None
    return {
        "ok": False,
        "errors": [{
            "row": 0,
            "message": (
                "Full Zerodha replace would delete existing open lots, but this Tax P&L "
                "file has no open section. Attach a Holdings CSV and enable Sync holdings, "
                "or upload a Console P&L that includes open quantity."
            ),
        }],
        "closed_added": 0,
        "closed_replaced": 0,
        "open_replaced": existing_opens,
        "open_synced": 0,
        "parse_errors": [],
        "broker": BROKER_ZERODHA,
        "replace_scope": "broker",
    }


def _ledger_zerodha_realized_by_symbol(ledger: dict, symbols: set[str]) -> dict[str, float]:
    out: dict[str, float] = {s: 0.0 for s in symbols}
    for t in ledger.get("closed_trades", []) or []:
        if not isinstance(t, dict):
            continue
        sym = _normalize_symbol(t.get("symbol"))
        if sym not in symbols:
            continue
        src = str(t.get("import_source") or "").strip().lower()
        if not (src.startswith("zerodha") or infer_broker(t) == BROKER_ZERODHA):
            continue
        try:
            out[sym] = round(out.get(sym, 0.0) + float(t.get("realized_pl") or 0), 2)
        except (TypeError, ValueError):
            continue
    return out


def apply_zerodha_tax_pnl(
    ledger: dict,
    portfolio_items: list,
    *,
    closed_rows: Sequence[dict],
    open_rows: Optional[Sequence[dict]] = None,
    replace_zerodha_closed: bool = True,
    apply_open_from_file: bool = True,
    full_broker_replace: bool = True,
) -> dict[str, Any]:
    """
    Replace Zerodha P&L with Tax/Console rows while preserving other brokers.

    full_broker_replace=True is the source-of-truth mode used by the Zerodha Tax
    P&L endpoint: all prior Zerodha open and closed rows are removed before the
    uploaded rows are rebuilt. Optional holdings reconciliation runs afterward.
    """
    file_symbols = {
        _normalize_symbol(r.get("symbol"))
        for r in [*closed_rows, *(open_rows or [])]
        if r.get("symbol")
    }
    cim_before = _ledger_zerodha_realized_by_symbol(ledger, file_symbols) if file_symbols else {}

    summary: dict[str, Any] = {
        "ok": True,
        "closed_replaced": 0,
        "closed_added": 0,
        "open_replaced": 0,
        "open_synced": 0,
        "trade_ids_cleared": 0,
        "broker": BROKER_ZERODHA,
        "replace_scope": "broker" if full_broker_replace else "symbols",
        "symbols": [],
        "realized_total": 0.0,
        "errors": [],
        "by_symbol": {},
        "cim_realized_before": cim_before,
    }

    if full_broker_replace:
        summary["closed_replaced"] = _strip_zerodha_closed(ledger)
        summary["open_replaced"] = _strip_zerodha_open(ledger)
        summary["trade_ids_cleared"] = _clear_zerodha_import_meta(ledger)
    elif replace_zerodha_closed and file_symbols:
        summary["closed_replaced"] = _strip_zerodha_closed(ledger, file_symbols)

    symbols: set[str] = set()
    by_symbol: dict[str, float] = {}
    realized_total = 0.0

    for row in closed_rows:
        sym = row["symbol"]
        qty = int(row["quantity"])
        entry = float(row["entry_price"])
        exit_p = float(row["exit_price"])
        pl = round(float(row["realized_pl"]), 2)
        ensure_portfolio_stock(portfolio_items, sym)
        mark_portfolio_pnl_tracked(portfolio_items, sym)
        trade = {
            "id": str(uuid.uuid4()),
            "symbol": sym,
            "entry_price": entry,
            "exit_price": exit_p,
            "qty_bought": qty,
            "qty_sold": qty,
            "realized_pl": pl,
            "realized_pl_pct": compute_pl_pct(exit_p, entry),
            "entry_date": row.get("entry_date"),
            "sale_date": row.get("sale_date") or row.get("entry_date") or datetime.now(IST).date().isoformat(),
            "cycle_id": 1,
            "booked_at": _now_ist_iso(),
            "broker": BROKER_ZERODHA,
            "import_source": "zerodha_tax_pnl",
        }
        ledger.setdefault("closed_trades", []).append(trade)
        symbols.add(sym)
        by_symbol[sym] = round(by_symbol.get(sym, 0.0) + pl, 2)
        realized_total += pl
        summary["closed_added"] += 1

    if apply_open_from_file and open_rows:
        for row in open_rows:
            sym = row["symbol"]
            ensure_portfolio_stock(portfolio_items, sym)
            mark_portfolio_pnl_tracked(portfolio_items, sym)
            set_symbol_open_snapshot(
                ledger,
                sym,
                qty=int(row["quantity"]),
                entry_price=float(row["average_price"]),
                import_source="zerodha_tax_pnl_open",
                broker=BROKER_ZERODHA,
                replace_brokers=(BROKER_ZERODHA,),
            )
            symbols.add(sym)
            summary["open_synced"] += 1

    summary["symbols"] = sorted(symbols)
    summary["realized_total"] = round(realized_total, 2)
    summary["by_symbol"] = dict(sorted(by_symbol.items(), key=lambda kv: kv[1]))
    compare = []
    for sym in summary["symbols"]:
        tax = round(by_symbol.get(sym, 0.0), 2)
        cim = round(cim_before.get(sym, 0.0), 2)
        compare.append({
            "symbol": sym,
            "cim_realized": cim,
            "tax_realized": tax,
            "delta": round(tax - cim, 2),
        })
    compare.sort(key=lambda r: abs(r["delta"]), reverse=True)
    summary["compare"] = compare
    summary["open_qty_after"] = {
        sym: symbol_open_qty(ledger, sym) for sym in summary["symbols"]
    }
    return summary


def preview_zerodha_tax_pnl(
    ledger: dict,
    portfolio_items: list,
    csv_text: str,
    *,
    replace_zerodha_closed: bool = True,
    apply_open_from_file: bool = True,
    full_broker_replace: bool = True,
    holdings_csv: Optional[str] = None,
    reconcile_holdings: bool = False,
) -> dict[str, Any]:
    import copy

    from server.zerodha_holdings import (
        compare_ledger_to_holdings,
        parse_zerodha_holdings_csv,
        reconcile_open_to_holdings,
    )

    closed_rows, open_rows, errors = parse_zerodha_tax_pnl_csv(csv_text)
    if errors and full_broker_replace:
        return {
            "ok": False,
            "parse_errors": errors,
            "errors": errors,
            "parsed_closed": len(closed_rows),
            "parsed_open": len(open_rows),
            "closed_added": 0,
            "closed_replaced": 0,
            "open_replaced": 0,
            "open_synced": 0,
            "broker": BROKER_ZERODHA,
            "replace_scope": "broker",
        }

    holdings_rows: list[dict] = []
    holdings_errors: list[dict] = []
    if holdings_csv and str(holdings_csv).strip() and reconcile_holdings:
        holdings_rows, holdings_errors = parse_zerodha_holdings_csv(holdings_csv)
        if holdings_errors:
            return {
                "ok": False,
                "parse_errors": errors,
                "errors": holdings_errors,
                "holdings_parse_errors": holdings_errors,
                "holdings_parsed": len(holdings_rows),
                "parsed_closed": len(closed_rows),
                "parsed_open": len(open_rows),
                "closed_added": 0,
                "closed_replaced": 0,
                "open_replaced": 0,
                "open_synced": 0,
                "broker": BROKER_ZERODHA,
                "replace_scope": "broker",
            }

    if full_broker_replace:
        blocked = _require_open_rebuild_source(
            ledger,
            open_rows=open_rows,
            holdings_rows=holdings_rows,
            reconcile_holdings=reconcile_holdings,
        )
        if blocked:
            blocked["parsed_closed"] = len(closed_rows)
            blocked["parsed_open"] = len(open_rows)
            return blocked

    ledger_copy = copy.deepcopy(ledger)
    portfolio_copy = copy.deepcopy(portfolio_items)
    summary = apply_zerodha_tax_pnl(
        ledger_copy,
        portfolio_copy,
        closed_rows=closed_rows,
        open_rows=open_rows,
        replace_zerodha_closed=replace_zerodha_closed,
        apply_open_from_file=apply_open_from_file,
        full_broker_replace=full_broker_replace,
    )
    summary["parsed_closed"] = len(closed_rows)
    summary["parsed_open"] = len(open_rows)
    summary["parse_errors"] = errors

    if holdings_rows and reconcile_holdings:
        summary["holdings_parsed"] = len(holdings_rows)
        summary["holdings_parse_errors"] = holdings_errors
        summary["holdings_mismatches"] = compare_ledger_to_holdings(ledger_copy, holdings_rows)
        summary["holdings_reconcile"] = reconcile_open_to_holdings(
            ledger_copy, holdings_rows, dry_run=False,
        )
        for r in holdings_rows:
            summary.setdefault("open_qty_after", {})[r["symbol"]] = symbol_open_qty(
                ledger_copy, r["symbol"],
            )
    return summary


def run_zerodha_tax_pnl_import(
    ledger: dict,
    portfolio_items: list,
    csv_text: str,
    *,
    replace_zerodha_closed: bool = True,
    apply_open_from_file: bool = True,
    full_broker_replace: bool = True,
    holdings_csv: Optional[str] = None,
    reconcile_holdings: bool = False,
) -> dict[str, Any]:
    closed_rows, open_rows, errors = parse_zerodha_tax_pnl_csv(csv_text)
    # A broker-wide destructive replacement must never proceed from a partial
    # parse. The existing ledger remains untouched until the whole file validates.
    if errors:
        return {
            "ok": False,
            "parse_errors": errors,
            "errors": errors,
            "closed_added": 0,
            "closed_replaced": 0,
            "open_replaced": 0,
            "open_synced": 0,
        }

    holdings_rows: list[dict] = []
    holdings_errors: list[dict] = []
    if holdings_csv and str(holdings_csv).strip() and reconcile_holdings:
        from server.zerodha_holdings import parse_zerodha_holdings_csv

        holdings_rows, holdings_errors = parse_zerodha_holdings_csv(holdings_csv)
        if holdings_errors:
            return {
                "ok": False,
                "parse_errors": errors,
                "errors": holdings_errors,
                "holdings_parse_errors": holdings_errors,
                "holdings_parsed": len(holdings_rows),
                "closed_added": 0,
                "closed_replaced": 0,
                "open_replaced": 0,
                "open_synced": 0,
            }

    if full_broker_replace:
        blocked = _require_open_rebuild_source(
            ledger,
            open_rows=open_rows,
            holdings_rows=holdings_rows,
            reconcile_holdings=reconcile_holdings,
        )
        if blocked:
            blocked["parsed_closed"] = len(closed_rows)
            blocked["parsed_open"] = len(open_rows)
            return blocked

    summary = apply_zerodha_tax_pnl(
        ledger,
        portfolio_items,
        closed_rows=closed_rows,
        open_rows=open_rows,
        replace_zerodha_closed=replace_zerodha_closed,
        apply_open_from_file=apply_open_from_file,
        full_broker_replace=full_broker_replace,
    )
    summary["parsed_closed"] = len(closed_rows)
    summary["parsed_open"] = len(open_rows)
    summary["parse_errors"] = errors

    if holdings_rows and reconcile_holdings:
        from server.zerodha_holdings import (
            compare_ledger_to_holdings,
            reconcile_open_to_holdings,
        )

        summary["holdings_parsed"] = len(holdings_rows)
        summary["holdings_parse_errors"] = holdings_errors
        summary["holdings_mismatches"] = compare_ledger_to_holdings(ledger, holdings_rows)
        summary["holdings_reconcile"] = reconcile_open_to_holdings(
            ledger, holdings_rows, dry_run=False,
        )
        for r in holdings_rows:
            summary.setdefault("open_qty_after", {})[r["symbol"]] = symbol_open_qty(ledger, r["symbol"])
    return summary
