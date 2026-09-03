"""Merge Zerodha Console tradebook CSV into the P&L ledger (FIFO, dedupe by trade_id)."""
from __future__ import annotations

import copy
import csv
import io
import uuid
from datetime import date, datetime
from typing import Any, Optional

from server.pnl_ledger import (
    BROKER_MANUAL,
    BROKER_ZERODHA,
    _begin_cycle_if_needed,
    _normalize_symbol,
    _sorted_open_positions,
    book_fifo,
    consolidate_open_lots,
    ensure_portfolio_stock,
    finalize_symbol_after_book,
    infer_broker,
    mark_portfolio_pnl_tracked,
    parse_entry_price,
    parse_sale_date,
    reconcile_pnl_portfolio_sync,
    symbol_open_qty,
    sync_portfolio_entry_from_pnl,
)

ZERODHA_REQUIRED_COLUMNS = frozenset({
    "symbol",
    "trade_date",
    "trade_type",
    "quantity",
    "price",
    "trade_id",
})


def _normalize_header(name: str) -> str:
    return str(name or "").strip().lower().replace(" ", "_")


def parse_zerodha_trade_date(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return parse_sale_date(s)


def _parse_trade_id(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "e" in s.lower():
        try:
            return str(int(float(s)))
        except (TypeError, ValueError):
            pass
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _parse_quantity(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        v = int(float(str(raw).strip().replace(",", "")))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_price(raw: Any) -> Optional[float]:
    return parse_entry_price(raw)


def _parse_execution_time(raw: Any) -> str:
    s = str(raw or "").strip()
    return s if s else ""


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    if sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def parse_zerodha_tradebook_csv(text: str) -> tuple[list[dict], list[dict]]:
    """
    Parse Zerodha Console tradebook CSV/TSV.
    Returns (rows, parse_errors) where each row is normalized for import.
    """
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
    missing = [c for c in ZERODHA_REQUIRED_COLUMNS if c not in field_map]
    if missing:
        return [], [{"row": 0, "message": f"missing columns: {', '.join(sorted(missing))}"}]

    rows: list[dict] = []
    errors: list[dict] = []

    for line_no, raw_row in enumerate(reader, start=2):
        def col(key: str) -> Any:
            return raw_row.get(field_map.get(key, ""), "")

        sym = _normalize_symbol(col("symbol"))
        trade_type = str(col("trade_type") or "").strip().lower()
        segment = str(col("segment") or "EQ").strip().upper()
        trade_date = parse_zerodha_trade_date(col("trade_date"))
        qty = _parse_quantity(col("quantity"))
        price = _parse_price(col("price"))
        trade_id = _parse_trade_id(col("trade_id"))

        if segment and segment != "EQ":
            continue

        if not sym:
            errors.append({"row": line_no, "message": "missing symbol"})
            continue
        if trade_type not in ("buy", "sell"):
            errors.append({"row": line_no, "message": f"invalid trade_type: {trade_type!r}"})
            continue
        if not trade_date:
            errors.append({"row": line_no, "message": "invalid trade_date"})
            continue
        if qty is None:
            errors.append({"row": line_no, "message": "invalid quantity"})
            continue
        if price is None:
            errors.append({"row": line_no, "message": "invalid price"})
            continue
        if not trade_id:
            errors.append({"row": line_no, "message": "missing trade_id"})
            continue

        rows.append({
            "symbol": sym,
            "trade_date": trade_date,
            "trade_type": trade_type,
            "quantity": qty,
            "price": price,
            "trade_id": trade_id,
            "order_id": str(col("order_id") or "").strip(),
            "order_execution_time": _parse_execution_time(col("order_execution_time")),
            "exchange": str(col("exchange") or "").strip().upper(),
            "source_row": line_no,
        })

    rows.sort(key=lambda r: (
        r["trade_date"],
        r.get("order_execution_time") or "",
        r.get("order_id") or "",
        r["trade_id"],
    ))
    return rows, errors


def aggregate_zerodha_fills(rows: list[dict]) -> list[dict]:
    """Merge partial fills that share symbol, date, price, side, and order_id."""
    if not rows:
        return rows
    out: list[dict] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        j = i + 1
        oid = str(r.get("order_id") or "")
        key = (r["symbol"], r["trade_date"], r["price"], r["trade_type"], oid)
        trade_ids = [r["trade_id"]]
        qty = r["quantity"]
        while j < len(rows):
            n = rows[j]
            nkey = (
                n["symbol"],
                n["trade_date"],
                n["price"],
                n["trade_type"],
                str(n.get("order_id") or ""),
            )
            if nkey != key:
                break
            trade_ids.append(n["trade_id"])
            qty += n["quantity"]
            j += 1
        merged = dict(r)
        merged["quantity"] = qty
        merged["trade_ids"] = trade_ids
        merged["trade_id"] = trade_ids[0]
        out.append(merged)
        i = j
    return out


def _ensure_import_meta(ledger: dict) -> dict:
    meta = ledger.get("import_meta")
    if not isinstance(meta, dict):
        meta = {}
        ledger["import_meta"] = meta
    ids = meta.get("zerodha_trade_ids")
    if not isinstance(ids, list):
        meta["zerodha_trade_ids"] = []
    return meta


def known_zerodha_trade_ids(ledger: dict) -> set[str]:
    ids: set[str] = set()
    meta = ledger.get("import_meta")
    if isinstance(meta, dict):
        for x in meta.get("zerodha_trade_ids") or []:
            if x is not None and str(x).strip():
                ids.add(str(x).strip())
    for p in ledger.get("positions", []):
        if isinstance(p, dict) and p.get("zerodha_trade_id"):
            ids.add(str(p["zerodha_trade_id"]))
        if isinstance(p, dict):
            for x in p.get("zerodha_trade_ids") or []:
                if x is not None and str(x).strip():
                    ids.add(str(x).strip())
    for t in ledger.get("closed_trades", []):
        if isinstance(t, dict) and t.get("zerodha_trade_id"):
            ids.add(str(t["zerodha_trade_id"]))
    return ids


def _register_zerodha_trade_id(ledger: dict, trade_id: str) -> None:
    meta = _ensure_import_meta(ledger)
    tid = str(trade_id).strip()
    ids = meta.setdefault("zerodha_trade_ids", [])
    if tid and tid not in ids:
        ids.append(tid)


def _register_zerodha_row_ids(ledger: dict, row: dict) -> None:
    for tid in row.get("trade_ids") or [row["trade_id"]]:
        _register_zerodha_trade_id(ledger, tid)


def _trade_ids_from_rows(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        for tid in row.get("trade_ids") or [row["trade_id"]]:
            if tid is not None and str(tid).strip():
                out.add(str(tid).strip())
    return out


def _strip_symbol_ledger_state(ledger: dict, symbols: set[str]) -> dict[str, int]:
    """Remove Zerodha open/closed history for symbols before a Zerodha rebuild.

    Paytm and manual lots/trades for the same NSE symbol are preserved.
    """
    from server.pnl_ledger import ensure_broker_tags

    ensure_broker_tags(ledger)
    syms = {_normalize_symbol(s) for s in symbols}
    counts = {"positions_removed": 0, "closed_removed": 0, "positions_kept_other_broker": 0}

    kept_pos: list[dict] = []
    for p in ledger.get("positions", []):
        if not isinstance(p, dict):
            continue
        if _normalize_symbol(p.get("symbol")) in syms and infer_broker(p) == BROKER_ZERODHA:
            counts["positions_removed"] += 1
            continue
        if _normalize_symbol(p.get("symbol")) in syms:
            counts["positions_kept_other_broker"] += 1
        kept_pos.append(p)
    ledger["positions"] = kept_pos

    kept_closed: list[dict] = []
    for t in ledger.get("closed_trades", []):
        if not isinstance(t, dict):
            continue
        if _normalize_symbol(t.get("symbol")) in syms and infer_broker(t) == BROKER_ZERODHA:
            counts["closed_removed"] += 1
            continue
        kept_closed.append(t)
    ledger["closed_trades"] = kept_closed

    for sym in syms:
        # Only clear cycle state when no open lots remain for the symbol.
        if symbol_open_qty(ledger, sym) <= 0:
            if isinstance(ledger.get("active_cycle"), dict):
                ledger["active_cycle"].pop(sym, None)
            if isinstance(ledger.get("cycle_seq"), dict):
                ledger["cycle_seq"].pop(sym, None)

    return counts


def _unregister_zerodha_trade_ids(ledger: dict, trade_ids: set[str]) -> int:
    meta = _ensure_import_meta(ledger)
    ids = meta.get("zerodha_trade_ids", [])
    if not isinstance(ids, list):
        ids = []
    drop = {str(t) for t in trade_ids}
    new_ids = [i for i in ids if str(i) not in drop]
    removed = len(ids) - len(new_ids)
    meta["zerodha_trade_ids"] = new_ids
    return removed


def _clear_manual_open_lots(ledger: dict, symbols: set[str]) -> int:
    """Deprecated no-op — broker tags mean append import must not wipe Manual/Paytm lots.

    Kept for callers/tests; always returns 0.
    """
    return 0


def _promote_manual_lots_to_zerodha(ledger: dict, symbol: str, need_qty: int) -> int:
    """Re-tag oldest Manual lots as Zerodha until need_qty is covered. Returns qty promoted.

    Paytm lots are never promoted. Used when a Zerodha sell arrives but open Zerodha
    qty is short — common when pre-import inventory was left as Manual.
    """
    need = int(need_qty or 0)
    if need <= 0:
        return 0
    sym = _normalize_symbol(symbol)
    promoted = 0
    for lot in _sorted_open_positions(ledger, sym, brokers=(BROKER_MANUAL,)):
        if promoted >= need:
            break
        lot_qty = int(lot.get("qty") or 0)
        if lot_qty <= 0:
            continue
        take = min(need - promoted, lot_qty)
        if take >= lot_qty:
            lot["broker"] = BROKER_ZERODHA
            if not lot.get("import_source"):
                lot["import_source"] = "manual_promoted_zerodha"
            promoted += lot_qty
        else:
            # Split: keep remainder Manual, promote slice to Zerodha.
            rem = lot_qty - take
            lot["qty"] = rem
            seed = {
                "id": str(uuid.uuid4()),
                "symbol": sym,
                "entry_price": lot.get("entry_price"),
                "qty": take,
                "entry_date": lot.get("entry_date"),
                "created_at": lot.get("created_at") or f"{lot.get('entry_date') or '1970-01-01'}T12:00:00",
                "broker": BROKER_ZERODHA,
                "import_source": "manual_promoted_zerodha",
            }
            ledger.setdefault("positions", []).append(seed)
            promoted += take
    return promoted


def _seed_zerodha_gap_lot(
    ledger: dict,
    portfolio_items: list,
    *,
    symbol: str,
    qty: int,
    entry_price: float,
    entry_date: str,
) -> dict:
    """Create a Zerodha open lot so a tradebook sell can book when buys are missing."""
    sym = _normalize_symbol(symbol)
    ensure_portfolio_stock(portfolio_items, sym)
    if symbol_open_qty(ledger, sym) == 0:
        _begin_cycle_if_needed(ledger, sym)
    mark_portfolio_pnl_tracked(portfolio_items, sym)
    pos = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": float(entry_price),
        "qty": int(qty),
        "entry_date": entry_date,
        "created_at": f"{entry_date}T00:00:00",
        "broker": BROKER_ZERODHA,
        "import_source": "zerodha_gap_seed",
    }
    ledger.setdefault("positions", []).append(pos)
    sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    return pos


def _ensure_zerodha_qty_for_sell(
    ledger: dict,
    portfolio_items: list,
    row: dict,
) -> dict[str, int]:
    """Make sure Zerodha open qty covers this sell (promote Manual, then gap-seed)."""
    sym = row["symbol"]
    need = int(row["quantity"])
    have = symbol_open_qty(ledger, sym, brokers=(BROKER_ZERODHA,))
    meta = {"promoted_manual_qty": 0, "gap_seed_qty": 0}
    if need <= have:
        return meta
    short = need - have
    promoted = _promote_manual_lots_to_zerodha(ledger, sym, short)
    meta["promoted_manual_qty"] = promoted
    short -= promoted
    if short > 0:
        _seed_zerodha_gap_lot(
            ledger,
            portfolio_items,
            symbol=sym,
            qty=short,
            entry_price=float(row["price"]),
            entry_date=row["trade_date"],
        )
        meta["gap_seed_qty"] = short
    return meta


def _row_fully_imported(row: dict, known: set[str]) -> bool:
    ids = row.get("trade_ids") or [row["trade_id"]]
    return bool(ids) and all(str(tid) in known for tid in ids)


def _import_buy_row(
    ledger: dict,
    portfolio_items: list,
    row: dict,
) -> None:
    sym = row["symbol"]
    ensure_portfolio_stock(portfolio_items, sym)
    if symbol_open_qty(ledger, sym) == 0:
        _begin_cycle_if_needed(ledger, sym)
    mark_portfolio_pnl_tracked(portfolio_items, sym)

    created_at = row.get("order_execution_time") or f"{row['trade_date']}T12:00:00"
    pos = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": row["price"],
        "qty": row["quantity"],
        "entry_date": row["trade_date"],
        "created_at": created_at,
        "zerodha_trade_id": row["trade_id"],
        "zerodha_trade_ids": list(row.get("trade_ids") or [row["trade_id"]]),
        "import_source": "zerodha",
        "broker": BROKER_ZERODHA,
    }
    ledger.setdefault("positions", []).append(pos)
    sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    _register_zerodha_row_ids(ledger, row)
    from server.pnl_cash import record_buy_cost

    record_buy_cost(
        ledger,
        qty=int(row["quantity"]),
        entry_price=float(row["price"]),
        position_id=str(pos["id"]),
        symbol=sym,
        ref_key=f"buy:zerodha:{row['trade_id']}",
    )


def _closed_sell_qty_for_day(
    ledger: dict,
    symbol: str,
    sale_date: str,
    *,
    exit_price: Optional[float] = None,
) -> int:
    """How many shares already closed for symbol on sale_date (optionally same exit)."""
    sym = _normalize_symbol(symbol)
    day = str(sale_date or "")[:10]
    total = 0
    for t in ledger.get("closed_trades", []) or []:
        if not isinstance(t, dict):
            continue
        if _normalize_symbol(t.get("symbol")) != sym:
            continue
        if str(t.get("sale_date") or "")[:10] != day:
            continue
        if exit_price is not None:
            try:
                if abs(float(t.get("exit_price")) - float(exit_price)) > 0.51:
                    continue
            except (TypeError, ValueError):
                continue
        q = t.get("qty_sold")
        try:
            total += int(float(q))
        except (TypeError, ValueError):
            pass
    return total


def _import_sell_row(
    ledger: dict,
    portfolio_items: list,
    row: dict,
    quote_snapshot: dict,
) -> tuple[list[dict], dict[str, int]]:
    sym = row["symbol"]
    ensure_portfolio_stock(portfolio_items, sym)
    mark_portfolio_pnl_tracked(portfolio_items, sym)

    # If this sell was already booked (positions-today / manual) for the same day+exit,
    # do not gap-seed and re-book — that double-counts realized P&L (Trent bug).
    already = _closed_sell_qty_for_day(
        ledger, sym, row["trade_date"], exit_price=float(row["price"]),
    )
    need = int(row["quantity"])
    z_open = symbol_open_qty(ledger, sym, brokers=(BROKER_ZERODHA,))
    m_open = symbol_open_qty(ledger, sym, brokers=(BROKER_MANUAL,))
    if already >= need and (z_open + m_open) < need:
        meta = {
            "promoted_manual_qty": 0,
            "gap_seed_qty": 0,
            "skipped_duplicate_sell": need,
        }
        _register_zerodha_row_ids(ledger, row)
        return [], meta

    seed_meta = _ensure_zerodha_qty_for_sell(ledger, portfolio_items, row)

    trades = book_fifo(
        ledger,
        symbol=sym,
        exit_price=row["price"],
        qty_sold=row["quantity"],
        sale_date=row["trade_date"],
        quote_snapshot=quote_snapshot,
        portfolio_items=portfolio_items,
        brokers=(BROKER_ZERODHA,),
    )
    for t in trades:
        t["zerodha_trade_id"] = row["trade_id"]
        t["zerodha_trade_ids"] = list(row.get("trade_ids") or [row["trade_id"]])
        t["import_source"] = "zerodha"
        t["broker"] = BROKER_ZERODHA
    _register_zerodha_row_ids(ledger, row)
    finalize_symbol_after_book(ledger, portfolio_items, sym)
    return trades, seed_meta


def preview_zerodha_merge(
    ledger: dict,
    portfolio_items: list,
    csv_text: str,
    *,
    rebuild: bool = False,
) -> dict:
    """Dry-run merge; does not mutate ledger or portfolio."""
    ledger_copy = copy.deepcopy(ledger)
    portfolio_copy = copy.deepcopy(portfolio_items)
    return merge_zerodha_tradebook(
        ledger_copy,
        portfolio_copy,
        csv_text,
        quote_map={},
        dry_run=True,
        rebuild=rebuild,
    )


def merge_zerodha_tradebook(
    ledger: dict,
    portfolio_items: list,
    csv_text: str,
    *,
    quote_map: Optional[dict[str, dict]] = None,
    dry_run: bool = False,
    rebuild: bool = False,
) -> dict:
    """
    Merge Zerodha tradebook into ledger + portfolio_items.

    rebuild=True: for every symbol in the file, wipe open/closed history and replay
    all CSV rows (use with a full tradebook export — fixes a bad prior import).
    rebuild=False: append only trade_ids not already imported.
    """
    quote_map = quote_map or {}
    rows, parse_errors = parse_zerodha_tradebook_csv(csv_text)
    rows = aggregate_zerodha_fills(rows)
    symbols_in_file = {r["symbol"] for r in rows}
    trade_ids_in_file = _trade_ids_from_rows(rows)

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "rebuild": rebuild,
        "parsed_rows": len(rows),
        "parse_errors": parse_errors,
        "skipped_duplicate": 0,
        "buys_applied": 0,
        "sells_applied": 0,
        "closed_trades_added": 0,
        "manual_lots_removed": 0,
        "lots_consolidated": 0,
        "gap_seed_qty": 0,
        "manual_promoted_qty": 0,
        "symbols": [],
        "symbols_in_file": sorted(symbols_in_file),
        "date_from": None,
        "date_to": None,
        "errors": [],
        "warnings": [],
        "portfolio_symbols_added": 0,
        "rebuild_strip": None,
        "trade_ids_cleared": 0,
        "open_qty_after": {},
    }

    if parse_errors and not rows:
        summary["ok"] = False
        return summary

    if rebuild:
        summary["rebuild_strip"] = _strip_symbol_ledger_state(ledger, symbols_in_file)
        summary["trade_ids_cleared"] = _unregister_zerodha_trade_ids(ledger, trade_ids_in_file)
        known = set()
        pending = list(rows)
        summary["skipped_duplicate"] = 0
    else:
        known = known_zerodha_trade_ids(ledger)
        pending = [r for r in rows if not _row_fully_imported(r, known)]
        summary["skipped_duplicate"] = len(rows) - len(pending)

    symbols_touched: set[str] = set()
    pf_before = {
        _normalize_symbol(it.get("symbol"))
        for it in portfolio_items
        if isinstance(it, dict)
    }

    # Append mode never wipes Manual/Paytm lots — broker tags own that boundary.
    # (Previously cleared Manual lots here, which caused Zerodha sells to fail.)

    if pending:
        summary["date_from"] = pending[0]["trade_date"]
        summary["date_to"] = pending[-1]["trade_date"]

    for row in pending:
        sym = row["symbol"]
        symbols_touched.add(sym)
        qsnap = quote_map.get(sym, {})
        try:
            if row["trade_type"] == "buy":
                _import_buy_row(ledger, portfolio_items, row)
                summary["buys_applied"] += 1
            else:
                trades, seed_meta = _import_sell_row(ledger, portfolio_items, row, qsnap)
                summary["gap_seed_qty"] += int(seed_meta.get("gap_seed_qty") or 0)
                summary["manual_promoted_qty"] += int(seed_meta.get("promoted_manual_qty") or 0)
                if seed_meta.get("skipped_duplicate_sell"):
                    summary["warnings"].append({
                        "symbol": sym,
                        "trade_id": row["trade_id"],
                        "message": (
                            f"Skipped sell of {seed_meta['skipped_duplicate_sell']} — already "
                            f"booked for {row['trade_date']} (avoids double-counting P&L)"
                        ),
                    })
                else:
                    summary["sells_applied"] += 1
                    summary["closed_trades_added"] += len(trades)
                if seed_meta.get("gap_seed_qty"):
                    summary["warnings"].append({
                        "symbol": sym,
                        "trade_id": row["trade_id"],
                        "message": (
                            f"Seeded {seed_meta['gap_seed_qty']} Zerodha share(s) before sell "
                            f"(buys missing from ledger / truncated tradebook)"
                        ),
                    })
                if seed_meta.get("promoted_manual_qty"):
                    summary["warnings"].append({
                        "symbol": sym,
                        "trade_id": row["trade_id"],
                        "message": (
                            f"Promoted {seed_meta['promoted_manual_qty']} Manual share(s) "
                            f"to Zerodha for sell"
                        ),
                    })
        except ValueError as exc:
            summary["errors"].append({
                "row": row.get("source_row"),
                "symbol": sym,
                "trade_id": row["trade_id"],
                "message": str(exc),
            })
            # Continue remaining rows — do not fail-fast on one bad sell.
            continue

    if not dry_run:
        summary["lots_consolidated"] = consolidate_open_lots(ledger)
        for sym in sorted(symbols_in_file):
            summary["open_qty_after"][sym] = symbol_open_qty(ledger, sym)

    pf_after = {
        _normalize_symbol(it.get("symbol"))
        for it in portfolio_items
        if isinstance(it, dict)
    }
    summary["portfolio_symbols_added"] = len(pf_after - pf_before)
    summary["symbols"] = sorted(symbols_touched)
    summary["ok"] = len(summary["errors"]) == 0
    return summary


def _bool_flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "")


def _empty_tradebook_summary(*, dry_run: bool = False) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry_run,
        "rebuild": False,
        "parsed_rows": 0,
        "parse_errors": [],
        "skipped_duplicate": 0,
        "buys_applied": 0,
        "sells_applied": 0,
        "closed_trades_added": 0,
        "manual_lots_removed": 0,
        "lots_consolidated": 0,
        "gap_seed_qty": 0,
        "manual_promoted_qty": 0,
        "symbols": [],
        "symbols_in_file": [],
        "date_from": None,
        "date_to": None,
        "errors": [],
        "warnings": [],
        "portfolio_symbols_added": 0,
        "rebuild_strip": None,
        "trade_ids_cleared": 0,
        "open_qty_after": {},
        "tradebook_skipped": True,
    }


def validate_zerodha_import_inputs(
    csv_text: str,
    holdings_csv: Optional[str] = None,
    positions_csv: Optional[str] = None,
    *,
    reconcile_holdings: bool = True,
    import_todays_positions: bool = False,
) -> Optional[str]:
    """Return an error message when the request has no actionable import input."""
    has_tradebook = bool(str(csv_text or "").strip())
    has_holdings = bool(str(holdings_csv or "").strip())
    has_positions = bool(str(positions_csv or "").strip())

    if has_tradebook:
        return None
    if has_holdings and reconcile_holdings:
        return None
    if has_positions and import_todays_positions:
        return None
    if has_holdings and not reconcile_holdings:
        return (
            "Holdings file attached but Sync open to holdings is off — enable it or attach a tradebook CSV."
        )
    if has_positions and not import_todays_positions:
        return (
            "Positions file attached but Apply today's positions is off — enable it or attach a tradebook CSV."
        )
    return (
        "Attach a tradebook CSV, a holdings file (with sync enabled), "
        "or a positions file (with apply enabled)."
    )


def run_zerodha_import_pipeline(
    ledger: dict,
    portfolio_items: list,
    *,
    csv_text: str,
    holdings_csv: Optional[str] = None,
    positions_csv: Optional[str] = None,
    quote_map: Optional[dict[str, dict]] = None,
    dry_run: bool = False,
    rebuild: bool = False,
    reconcile_holdings: bool = True,
    import_todays_positions: bool = False,
    validate_positions_pnl: bool = True,
    apply_corp_actions: bool = True,
    data_dir: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Full Zerodha import: tradebook → corp actions → holdings reconcile → today's positions.
    """
    from pathlib import Path

    from server.corp_actions import (
        apply_pending_corp_actions,
        load_corp_actions,
        same_day_sell_likely,
    )
    from server.zerodha_holdings import (
        compare_ledger_to_holdings,
        parse_zerodha_holdings_csv,
        reconcile_open_to_holdings,
    )
    from server.zerodha_positions import (
        apply_todays_positions,
        parse_zerodha_positions_csv,
        preview_todays_positions,
    )

    quote_map = quote_map or {}
    tradebook_text = str(csv_text or "").strip()
    if tradebook_text:
        summary = merge_zerodha_tradebook(
            ledger,
            portfolio_items,
            tradebook_text,
            quote_map=quote_map,
            dry_run=dry_run,
            rebuild=rebuild,
        )
        symbols_in_file = set(summary.get("symbols_in_file") or [])
    else:
        if rebuild:
            rebuild = False
        summary = _empty_tradebook_summary(dry_run=dry_run)
        symbols_in_file = set()

    summary["holdings_mismatches"] = []
    summary["holdings_reconcile"] = None
    summary["corp_actions_applied"] = []
    summary["positions_today"] = []
    summary["positions_to_apply"] = []
    summary["positions_skipped"] = []
    summary["positions_pnl_check"] = []
    summary["same_day_sell_likely"] = []

    corp_symbols = set(symbols_in_file)

    holdings_rows: list[dict] = []
    if holdings_csv and str(holdings_csv).strip():
        holdings_rows, holdings_errors = parse_zerodha_holdings_csv(holdings_csv)
        summary["holdings_parsed"] = len(holdings_rows)
        summary["holdings_parse_errors"] = holdings_errors
        if holdings_errors and not holdings_rows:
            summary["ok"] = False
            summary["errors"] = summary.get("errors", []) + holdings_errors
            return summary
        corp_symbols |= {r["symbol"] for r in holdings_rows}

    position_rows: list[dict] = []
    if positions_csv and str(positions_csv).strip():
        position_rows, pos_errors = parse_zerodha_positions_csv(positions_csv)
        summary["positions_parsed"] = len(position_rows)
        summary["positions_parse_errors"] = pos_errors
        if pos_errors and not position_rows:
            summary["ok"] = False
            summary["errors"] = summary.get("errors", []) + pos_errors
            return summary
        corp_symbols |= {r["symbol"] for r in position_rows}

    if apply_corp_actions and corp_symbols:
        actions = load_corp_actions(Path(data_dir) if data_dir else None)
        corp = apply_pending_corp_actions(
            ledger,
            corp_symbols,
            actions,
            dry_run=dry_run,
        )
        summary["corp_actions_applied"] = corp
        if not dry_run:
            for sym in corp_symbols:
                summary.setdefault("open_qty_after", {})[sym] = symbol_open_qty(ledger, sym)

    if holdings_rows:
        summary["holdings_mismatches"] = compare_ledger_to_holdings(ledger, holdings_rows)
        if reconcile_holdings:
            rec = reconcile_open_to_holdings(
                ledger,
                holdings_rows,
                dry_run=dry_run,
            )
            summary["holdings_reconcile"] = rec
            if not dry_run:
                for sym in {r["symbol"] for r in holdings_rows}:
                    summary.setdefault("open_qty_after", {})[sym] = symbol_open_qty(ledger, sym)
        summary["same_day_sell_likely"] = same_day_sell_likely(ledger, holdings_rows)

    if position_rows:
        pos_preview = preview_todays_positions(ledger, position_rows)
        summary["positions_today"] = pos_preview.get("positions_today", [])
        summary["positions_to_apply"] = pos_preview.get("positions_to_apply", [])
        summary["positions_skipped"] = pos_preview.get("positions_skipped", [])
        if validate_positions_pnl:
            summary["positions_pnl_check"] = pos_preview.get("positions_pnl_check", [])
        if import_todays_positions:
            pos_result = apply_todays_positions(
                ledger,
                portfolio_items,
                position_rows,
                quote_map=quote_map,
                dry_run=dry_run,
            )
            summary["positions_buys_applied"] = pos_result.get("buys_applied", 0)
            summary["positions_sells_applied"] = pos_result.get("sells_applied", 0)
            summary["positions_closed_added"] = pos_result.get("closed_trades_added", 0)
            summary["positions_to_apply"] = pos_result.get("positions_to_apply", [])
            summary["positions_skipped"] = pos_result.get("positions_skipped", [])
            if pos_result.get("errors"):
                summary["errors"] = summary.get("errors", []) + pos_result["errors"]
                summary["ok"] = False

    if not dry_run:
        consolidated = consolidate_open_lots(ledger)
        summary["lots_consolidated"] = summary.get("lots_consolidated", 0) + consolidated
        affected = symbols_in_file | {r["symbol"] for r in holdings_rows} | {r["symbol"] for r in position_rows}
        for sym in sorted(affected):
            summary.setdefault("open_qty_after", {})[sym] = symbol_open_qty(ledger, sym)
    else:
        affected = symbols_in_file | {r["symbol"] for r in holdings_rows} | {r["symbol"] for r in position_rows}
        for sym in sorted(affected):
            summary.setdefault("open_qty_after", {})[sym] = symbol_open_qty(ledger, sym)

    return summary


def preview_zerodha_import(
    ledger: dict,
    portfolio_items: list,
    *,
    csv_text: str,
    holdings_csv: Optional[str] = None,
    positions_csv: Optional[str] = None,
    rebuild: bool = False,
    reconcile_holdings: bool = True,
    import_todays_positions: bool = False,
    validate_positions_pnl: bool = True,
    apply_corp_actions: bool = True,
    data_dir: Optional[Any] = None,
) -> dict:
    """Dry-run full import pipeline."""
    ledger_copy = copy.deepcopy(ledger)
    portfolio_copy = copy.deepcopy(portfolio_items)
    return run_zerodha_import_pipeline(
        ledger_copy,
        portfolio_copy,
        csv_text=csv_text,
        holdings_csv=holdings_csv,
        positions_csv=positions_csv,
        quote_map={},
        dry_run=False,
        rebuild=rebuild,
        reconcile_holdings=reconcile_holdings,
        import_todays_positions=import_todays_positions,
        validate_positions_pnl=validate_positions_pnl,
        apply_corp_actions=apply_corp_actions,
        data_dir=data_dir,
    )


def reconcile_holdings_only(
    ledger: dict,
    portfolio_items: list,
    holdings_csv: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Standalone holdings sync without tradebook re-import."""
    from server.zerodha_holdings import (
        compare_ledger_to_holdings,
        parse_zerodha_holdings_csv,
        reconcile_open_to_holdings,
    )
    from server.pnl_ledger import reconcile_pnl_portfolio_sync

    rows, parse_errors = parse_zerodha_holdings_csv(holdings_csv)
    summary: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "holdings_parsed": len(rows),
        "holdings_parse_errors": parse_errors,
        "holdings_mismatches": [],
        "holdings_reconcile": None,
    }
    if parse_errors and not rows:
        summary["ok"] = False
        return summary
    summary["holdings_mismatches"] = compare_ledger_to_holdings(ledger, rows)
    rec = reconcile_open_to_holdings(ledger, rows, dry_run=dry_run)
    summary["holdings_reconcile"] = rec
    if not dry_run:
        consolidate_open_lots(ledger)
        reconcile_pnl_portfolio_sync(portfolio_items, ledger)
        summary["open_qty_after"] = {
            r["symbol"]: symbol_open_qty(ledger, r["symbol"]) for r in rows
        }
    return summary
