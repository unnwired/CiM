"""P&L ledger — open positions, book (realized trades), portfolio-linked symbols."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from server.portfolio_entry import compute_pl_pct, parse_entry_price


def _default_ledger() -> dict:
    return {
        "positions": [],
        "closed_trades": [],
        "cycle_seq": {},
        "active_cycle": {},
        "import_meta": {"zerodha_trade_ids": []},
        "available_cash": 0.0,
        "cash_log": [],
        "cash_refs": {},
    }


def load_ledger(path: Path) -> dict:
    if not path.exists():
        return _default_ledger()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_ledger()
        positions = data.get("positions", [])
        closed = data.get("closed_trades", [])
        if not isinstance(positions, list):
            positions = []
        if not isinstance(closed, list):
            closed = []
        cycle_seq = data.get("cycle_seq", {})
        active_cycle = data.get("active_cycle", {})
        if not isinstance(cycle_seq, dict):
            cycle_seq = {}
        if not isinstance(active_cycle, dict):
            active_cycle = {}
        import_meta = data.get("import_meta", {})
        if not isinstance(import_meta, dict):
            import_meta = {}
        zids = import_meta.get("zerodha_trade_ids", [])
        if not isinstance(zids, list):
            zids = []
        cash_log = data.get("cash_log", [])
        if not isinstance(cash_log, list):
            cash_log = []
        cash_refs = data.get("cash_refs", {})
        if not isinstance(cash_refs, dict):
            cash_refs = {}
        try:
            available_cash = round(float(data.get("available_cash") or 0), 2)
        except (TypeError, ValueError):
            available_cash = 0.0
        return {
            "positions": positions,
            "closed_trades": closed,
            "cycle_seq": cycle_seq,
            "active_cycle": active_cycle,
            "import_meta": {"zerodha_trade_ids": zids},
            "available_cash": available_cash,
            "cash_log": cash_log,
            "cash_refs": cash_refs,
        }
    except Exception:
        return _default_ledger()


def save_ledger(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _normalize_symbol(sym: Any) -> str:
    return str(sym or "").strip().upper()


def _parse_qty(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_exit_price(raw: Any) -> Optional[float]:
    return parse_entry_price(raw)


def parse_sale_date(raw: Any) -> Optional[str]:
    """Validate YYYY-MM-DD calendar date."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


parse_entry_date = parse_sale_date


def today_sale_date_ist() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


def _now_ist_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()


def _ensure_cycle_maps(ledger: dict) -> None:
    if not isinstance(ledger.get("cycle_seq"), dict):
        ledger["cycle_seq"] = {}
    if not isinstance(ledger.get("active_cycle"), dict):
        ledger["active_cycle"] = {}


def _sorted_open_positions(ledger: dict, symbol: str) -> list[dict]:
    """Open lots for symbol in FIFO order (oldest buy first)."""
    sym = _normalize_symbol(symbol)
    indexed: list[tuple[int, dict]] = []
    for i, p in enumerate(ledger.get("positions", [])):
        if not isinstance(p, dict):
            continue
        if _normalize_symbol(p.get("symbol")) != sym:
            continue
        q = _parse_qty(p.get("qty"))
        if not q:
            continue
        indexed.append((i, p))

    def sort_key(item: tuple[int, dict]) -> tuple:
        idx, p = item
        ed = parse_entry_date(p.get("entry_date"))
        created = str(p.get("created_at") or "")
        if ed:
            return (0, ed, created, idx)
        return (1, created or str(idx).zfill(8), idx)

    indexed.sort(key=sort_key)
    return [p for _, p in indexed]


def symbol_open_qty(ledger: dict, symbol: str) -> int:
    sym = _normalize_symbol(symbol)
    total = 0
    for p in ledger.get("positions", []):
        if not isinstance(p, dict):
            continue
        if _normalize_symbol(p.get("symbol")) != sym:
            continue
        q = _parse_qty(p.get("qty"))
        if q:
            total += q
    return total


def _begin_cycle_if_needed(ledger: dict, symbol: str) -> int:
    """Start a new cycle when symbol has no active cycle (re-buy after full close)."""
    _ensure_cycle_maps(ledger)
    sym = _normalize_symbol(symbol)
    active = ledger["active_cycle"]
    if sym in active:
        return int(active[sym])
    seq = ledger["cycle_seq"]
    next_id = int(seq.get(sym, 0)) + 1
    seq[sym] = next_id
    active[sym] = next_id
    return next_id


def _active_cycle_id(ledger: dict, symbol: str) -> int:
    _ensure_cycle_maps(ledger)
    sym = _normalize_symbol(symbol)
    if sym in ledger["active_cycle"]:
        return int(ledger["active_cycle"][sym])
    return _begin_cycle_if_needed(ledger, sym)


def _end_cycle_if_closed(ledger: dict, symbol: str) -> None:
    sym = _normalize_symbol(symbol)
    if symbol_open_qty(ledger, sym) > 0:
        return
    active = ledger.get("active_cycle")
    if isinstance(active, dict) and sym in active:
        del active[sym]


def _portfolio_stock_symbols(portfolio_items: list) -> list[str]:
    out = []
    seen = set()
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if str(it.get("type", "stock")).strip().lower() != "stock":
            continue
        sym = _normalize_symbol(it.get("symbol"))
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return sorted(out)


def _portfolio_entry_hint(portfolio_items: list, symbol: str) -> Optional[float]:
    sym = _normalize_symbol(symbol)
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        return parse_entry_price(it.get("entry_price"))
    return None


def _portfolio_draft_qty(portfolio_items: list, symbol: str) -> Optional[int]:
    sym = _normalize_symbol(symbol)
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        return _parse_qty(it.get("pnl_draft_qty"))
    return None


def _set_portfolio_placeholder_draft(
    portfolio_items: list,
    symbol: str,
    *,
    entry_price: Any = None,
    qty: Any = None,
) -> None:
    sym = _normalize_symbol(symbol)
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        if str(it.get("type", "stock")).strip().lower() != "stock":
            continue
        if entry_price is not None:
            ep = parse_entry_price(entry_price)
            if ep is None:
                raise ValueError("entry_price must be positive")
            it["entry_price"] = ep
        if qty is not None:
            q = _parse_qty(qty)
            if q is None:
                raise ValueError("qty must be a positive integer")
            it["pnl_draft_qty"] = q
        return
    raise ValueError("symbol not in portfolio")


def _clear_portfolio_placeholder_draft(portfolio_items: list, symbol: str) -> None:
    sym = _normalize_symbol(symbol)
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        it.pop("pnl_draft_qty", None)
        return


def remove_symbol_from_portfolio_items(portfolio_items: list, symbol: str) -> bool:
    """Remove stock from portfolio list. Returns True if an item was removed."""
    sym = _normalize_symbol(symbol)
    before = len(portfolio_items)
    portfolio_items[:] = [
        it
        for it in portfolio_items
        if not (
            isinstance(it, dict)
            and _normalize_symbol(it.get("symbol")) == sym
            and str(it.get("type", "stock")).strip().lower() == "stock"
        )
    ]
    return len(portfolio_items) < before


def mark_portfolio_pnl_tracked(portfolio_items: list, symbol: str) -> None:
    """Mark a portfolio stock as managed by the P&L ledger (sync on full close)."""
    sym = _normalize_symbol(symbol)
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        if str(it.get("type", "stock")).strip().lower() != "stock":
            continue
        it["pnl_tracked"] = True
        return


def _has_closed_trades(ledger: dict, symbol: str) -> bool:
    sym = _normalize_symbol(symbol)
    for t in ledger.get("closed_trades", []):
        if not isinstance(t, dict):
            continue
        if _normalize_symbol(t.get("symbol")) == sym:
            return True
    return False


def _portfolio_item_pnl_tracked(portfolio_items: list, symbol: str) -> bool:
    sym = _normalize_symbol(symbol)
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        if str(it.get("type", "stock")).strip().lower() != "stock":
            continue
        return bool(it.get("pnl_tracked"))
    return False


def purge_dead_positions(ledger: dict) -> bool:
    """Drop open lots with missing/zero qty (ledger hygiene)."""
    positions = ledger.get("positions", [])
    kept = [p for p in positions if isinstance(p, dict) and _parse_qty(p.get("qty"))]
    changed = len(kept) != len(positions)
    if changed:
        ledger["positions"] = kept
    return changed


def should_remove_portfolio_after_full_close(
    portfolio_items: list,
    ledger: dict,
    symbol: str,
) -> bool:
    """True when symbol has no open qty and should leave Portfolio after a full P&L close."""
    sym = _normalize_symbol(symbol)
    if symbol_open_qty(ledger, sym) > 0:
        return False
    active = ledger.get("active_cycle")
    if isinstance(active, dict) and sym in active:
        return False
    if _portfolio_item_pnl_tracked(portfolio_items, sym):
        return True
    # Legacy rows booked before pnl_tracked flag existed.
    return _has_closed_trades(ledger, sym)


def finalize_symbol_after_book(ledger: dict, portfolio_items: list, symbol: str) -> bool:
    """Purge dead lots and remove Portfolio row when a symbol is fully closed."""
    sym = _normalize_symbol(symbol)
    purge_dead_positions(ledger)
    if not should_remove_portfolio_after_full_close(portfolio_items, ledger, sym):
        return False
    return remove_symbol_from_portfolio_items(portfolio_items, sym)


def _ledger_open_symbols(ledger: dict) -> set[str]:
    syms: set[str] = set()
    for lot in ledger.get("positions", []):
        if not isinstance(lot, dict):
            continue
        sym = _normalize_symbol(lot.get("symbol"))
        if sym and _parse_qty(lot.get("qty")):
            syms.add(sym)
    return syms


def reconcile_pnl_portfolio_sync(portfolio_items: list, ledger: dict) -> dict:
    """
  Repair Portfolio ↔ P&L drift: drop fully closed P&L symbols still in Portfolio,
  purge dead zero-qty lots, ensure open ledger symbols exist in Portfolio, and push
  P&L entry (weighted avg of open lots) to Portfolio.
  """
    ledger_changed = purge_dead_positions(ledger)
    removed: list[str] = []
    for sym in list(_portfolio_stock_symbols(portfolio_items)):
        if not should_remove_portfolio_after_full_close(portfolio_items, ledger, sym):
            continue
        if remove_symbol_from_portfolio_items(portfolio_items, sym):
            removed.append(sym)
    added: list[str] = []
    pf_syms = set(_portfolio_stock_symbols(portfolio_items))
    for sym in sorted(_ledger_open_symbols(ledger)):
        if sym in pf_syms:
            continue
        ensure_portfolio_stock(portfolio_items, sym)
        added.append(sym)
        pf_syms.add(sym)
    entries_synced = sync_all_portfolio_entries_from_pnl(portfolio_items, ledger)
    return {
        "portfolio_changed": bool(removed) or bool(added) or entries_synced,
        "ledger_changed": ledger_changed,
        "removed_symbols": removed,
        "added_symbols": added,
        "entries_synced": entries_synced,
    }


def compute_symbol_avg_entry(ledger: dict, symbol: str) -> Optional[float]:
    """Weighted average entry across open lots for a symbol (Portfolio display when P&L is master)."""
    sym = _normalize_symbol(symbol)
    total_qty = 0
    total_cost = 0.0
    for lot in _sorted_open_positions(ledger, sym):
        q = _parse_qty(lot.get("qty"))
        e = parse_entry_price(lot.get("entry_price"))
        if q and e is not None:
            total_qty += q
            total_cost += q * e
    if total_qty <= 0:
        return None
    return round(total_cost / total_qty, 2)


def sync_portfolio_entry_from_pnl(
    portfolio_items: list,
    ledger: dict,
    symbol: str,
) -> bool:
    """Overwrite Portfolio entry_price with P&L weighted avg when open lots exist. Returns True if changed."""
    sym = _normalize_symbol(symbol)
    avg = compute_symbol_avg_entry(ledger, sym)
    if avg is None:
        return False
    for it in portfolio_items:
        if not isinstance(it, dict):
            continue
        if _normalize_symbol(it.get("symbol")) != sym:
            continue
        if str(it.get("type", "stock")).strip().lower() != "stock":
            continue
        old = parse_entry_price(it.get("entry_price"))
        if old == avg:
            return False
        it["entry_price"] = avg
        return True
    return False


def sync_all_portfolio_entries_from_pnl(portfolio_items: list, ledger: dict) -> bool:
    """Push P&L entries to Portfolio for every symbol with open lots."""
    changed = False
    for sym in _portfolio_stock_symbols(portfolio_items):
        if symbol_open_qty(ledger, sym) <= 0:
            continue
        if sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym):
            changed = True
    return changed


def ensure_portfolio_stock(portfolio_items: list, symbol: str) -> None:
    sym = _normalize_symbol(symbol)
    if not sym:
        raise ValueError("symbol required")
    if sym in _portfolio_stock_symbols(portfolio_items):
        mark_portfolio_pnl_tracked(portfolio_items, sym)
        return
    portfolio_items.append({"symbol": sym, "type": "stock", "pnl_tracked": True})


def _enrich_open_row(row: dict, quote: dict) -> dict:
    entry = parse_entry_price(row.get("entry_price"))
    qty = _parse_qty(row.get("qty"))
    price = quote.get("price")
    sym = _normalize_symbol(row.get("symbol"))

    invested = None
    unrealized_pl = None
    pl_pct = None
    if entry is not None and qty is not None:
        invested = round(entry * qty, 2)
    if entry is not None and qty is not None and price is not None:
        try:
            unrealized_pl = round(qty * (float(price) - entry), 2)
        except (TypeError, ValueError):
            pass
        pl_pct = compute_pl_pct(price, entry)

    out = dict(row)
    out["symbol"] = sym
    out["market_cap"] = quote.get("market_cap")
    out["price"] = price
    out["change_1d"] = quote.get("change_1d")
    out["change_1m"] = quote.get("change_1m")
    out["as_of_date"] = quote.get("as_of_date")
    out["entry_price"] = entry
    out["qty"] = qty
    out["invested"] = invested
    out["pl_pct"] = pl_pct
    out["unrealized_pl"] = unrealized_pl
    out["is_placeholder"] = bool(row.get("is_placeholder"))
    out["entry_date"] = parse_entry_date(row.get("entry_date"))
    return out


def build_open_rows(
    portfolio_items: list,
    ledger: dict,
    quote_map: dict[str, dict],
) -> list[dict]:
    """Merge portfolio stocks with ledger positions; placeholder rows for stocks without lots."""
    positions = [p for p in ledger.get("positions", []) if isinstance(p, dict)]
    pf_stocks = _portfolio_stock_symbols(portfolio_items)

    rows: list[dict] = []
    by_symbol: dict[str, list[dict]] = {}
    for p in positions:
        sym = _normalize_symbol(p.get("symbol"))
        if sym not in pf_stocks:
            continue
        by_symbol.setdefault(sym, []).append(p)

    for sym in pf_stocks:
        lots = by_symbol.get(sym, [])
        quote = quote_map.get(sym, {})
        if lots:
            fifo_lots = _sorted_open_positions(ledger, sym)
            for lot in fifo_lots:
                row = {
                    "id": lot.get("id") or str(uuid.uuid4()),
                    "symbol": sym,
                    "entry_price": lot.get("entry_price"),
                    "qty": lot.get("qty"),
                    "entry_date": lot.get("entry_date"),
                    "is_placeholder": False,
                }
                rows.append(_enrich_open_row(row, quote))
        else:
            hint = _portfolio_entry_hint(portfolio_items, sym)
            draft_qty = _portfolio_draft_qty(portfolio_items, sym)
            row = {
                "id": f"placeholder-{sym}",
                "symbol": sym,
                "entry_price": hint,
                "qty": draft_qty,
                "is_placeholder": True,
            }
            rows.append(_enrich_open_row(row, quote))

    return rows


def _normalize_closed_trade(t: dict) -> dict:
    out = dict(t)
    if not out.get("sale_date"):
        ba = out.get("booked_at")
        if ba:
            out["sale_date"] = str(ba)[:10]
    if out.get("entry_date"):
        out["entry_date"] = parse_entry_date(out.get("entry_date"))
    try:
        out["cycle_id"] = int(out.get("cycle_id") or 1)
    except (TypeError, ValueError):
        out["cycle_id"] = 1
    return out


def build_closed_rows(closed_trades: list) -> dict:
    profit = []
    loss = []
    for t in closed_trades:
        if not isinstance(t, dict):
            continue
        norm = _normalize_closed_trade(t)
        pl = norm.get("realized_pl")
        try:
            pl_f = float(pl) if pl is not None else 0.0
        except (TypeError, ValueError):
            pl_f = 0.0
        if pl_f >= 0:
            profit.append(norm)
        else:
            loss.append(norm)

    def sort_key(x: dict) -> tuple:
        sd = str(x.get("sale_date") or "")
        ba = str(x.get("booked_at") or "")
        return (sd, ba)

    profit.sort(key=sort_key, reverse=True)
    loss.sort(key=sort_key, reverse=True)
    return {"profit": profit, "loss": loss}


def add_position(
    ledger: dict,
    *,
    symbol: str,
    entry_price: float,
    qty: int,
    portfolio_items: list,
    entry_date: Optional[str] = None,
) -> dict:
    sym = _normalize_symbol(symbol)
    if sym not in _portfolio_stock_symbols(portfolio_items):
        raise ValueError("symbol not in portfolio")
    entry = parse_entry_price(entry_price)
    q = _parse_qty(qty)
    ed = parse_entry_date(entry_date) or today_sale_date_ist()
    if entry is None:
        raise ValueError("entry_price must be positive")
    if q is None:
        raise ValueError("qty must be a positive integer")

    had_open = symbol_open_qty(ledger, sym) > 0
    if not had_open:
        _begin_cycle_if_needed(ledger, sym)

    mark_portfolio_pnl_tracked(portfolio_items, sym)

    pos = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": entry,
        "qty": q,
        "entry_date": ed,
        "created_at": _now_ist_iso(),
    }
    ledger.setdefault("positions", []).append(pos)
    sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    from server.pnl_cash import record_buy_cost

    record_buy_cost(
        ledger,
        qty=q,
        entry_price=entry,
        position_id=str(pos["id"]),
        symbol=sym,
    )
    return pos


def add_stock(
    ledger: dict,
    *,
    symbol: str,
    entry_price: float,
    qty: int,
    portfolio_items: list,
    entry_date: Optional[str] = None,
) -> dict:
    """Add symbol to portfolio (if needed) and create an open position."""
    ensure_portfolio_stock(portfolio_items, symbol)
    return add_position(
        ledger,
        symbol=symbol,
        entry_price=entry_price,
        qty=qty,
        portfolio_items=portfolio_items,
        entry_date=entry_date,
    )


def patch_position(
    ledger: dict,
    position_id: str,
    *,
    entry_price: Any = None,
    qty: Any = None,
    entry_date: Any = None,
) -> dict:
    pid = str(position_id or "").strip()
    for p in ledger.get("positions", []):
        if not isinstance(p, dict):
            continue
        if str(p.get("id")) != pid:
            continue
        if entry_price is not None:
            ep = parse_entry_price(entry_price)
            if ep is None:
                raise ValueError("entry_price must be positive")
            p["entry_price"] = ep
        if qty is not None:
            q = _parse_qty(qty)
            if q is None:
                raise ValueError("qty must be a positive integer")
            p["qty"] = q
        if entry_date is not None:
            ed = parse_entry_date(entry_date)
            if ed is None:
                raise ValueError("entry_date must be YYYY-MM-DD")
            p["entry_date"] = ed
        if not p.get("created_at"):
            p["created_at"] = _now_ist_iso()
        return p
    raise ValueError("position not found")


def delete_position(ledger: dict, position_id: str) -> None:
    pid = str(position_id or "").strip()
    positions = ledger.get("positions", [])
    ledger["positions"] = [p for p in positions if isinstance(p, dict) and str(p.get("id")) != pid]
    if not any(str(p.get("id")) == pid for p in positions if isinstance(p, dict)):
        raise ValueError("position not found")


def ensure_position_from_placeholder(
    ledger: dict,
    *,
    symbol: str,
    entry_price: float,
    qty: int,
    portfolio_items: list,
    entry_date: Optional[str] = None,
) -> dict:
    """Create a real position when user edits a placeholder row."""
    sym = _normalize_symbol(symbol)
    if sym not in _portfolio_stock_symbols(portfolio_items):
        raise ValueError("symbol not in portfolio")
    entry = parse_entry_price(entry_price)
    q = _parse_qty(qty)
    ed = parse_entry_date(entry_date) or today_sale_date_ist()
    if entry is None:
        raise ValueError("entry_price must be positive")
    if q is None:
        raise ValueError("qty must be a positive integer")

    positions = ledger.setdefault("positions", [])
    for p in positions:
        if isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym:
            p["entry_price"] = entry
            p["qty"] = q
            p["entry_date"] = ed
            if not p.get("id"):
                p["id"] = str(uuid.uuid4())
            if not p.get("created_at"):
                p["created_at"] = _now_ist_iso()
            mark_portfolio_pnl_tracked(portfolio_items, sym)
            sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
            return p

    if symbol_open_qty(ledger, sym) == 0:
        _begin_cycle_if_needed(ledger, sym)

    mark_portfolio_pnl_tracked(portfolio_items, sym)

    pos = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": entry,
        "qty": q,
        "entry_date": ed,
        "created_at": _now_ist_iso(),
    }
    positions.append(pos)
    sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    from server.pnl_cash import record_buy_cost

    record_buy_cost(
        ledger,
        qty=q,
        entry_price=entry,
        position_id=str(pos["id"]),
        symbol=sym,
    )
    return pos


def _book_position_slice(
    ledger: dict,
    target: dict,
    *,
    exit_price: float,
    qty_sold: int,
    sale_date: str,
    entry_price_override: Any,
    quote_snapshot: dict,
    portfolio_items: list,
) -> dict:
    sym = _normalize_symbol(target.get("symbol"))
    if sym not in _portfolio_stock_symbols(portfolio_items):
        raise ValueError("symbol not in portfolio")

    exit_p = _parse_exit_price(exit_price)
    qs = _parse_qty(qty_sold)
    sd = parse_sale_date(sale_date)
    if exit_p is None:
        raise ValueError("exit_price must be positive")
    if qs is None:
        raise ValueError("qty_sold must be a positive integer")
    if sd is None:
        raise ValueError("sale_date must be YYYY-MM-DD")

    entry = (
        parse_entry_price(entry_price_override)
        if entry_price_override is not None
        else parse_entry_price(target.get("entry_price"))
    )
    if entry is None:
        raise ValueError("entry_price must be set before booking")

    open_qty = _parse_qty(target.get("qty"))
    if open_qty is None:
        raise ValueError("open qty must be set before booking")
    if qs > open_qty:
        raise ValueError("qty_sold exceeds open qty")

    realized_pl = round(qs * (exit_p - entry), 2)
    realized_pl_pct = compute_pl_pct(exit_p, entry)
    cycle_id = _active_cycle_id(ledger, sym)
    lot_entry_date = parse_entry_date(target.get("entry_date"))

    now = _now_ist_iso()
    trade = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": entry,
        "exit_price": exit_p,
        "qty_bought": open_qty,
        "qty_sold": qs,
        "realized_pl": realized_pl,
        "realized_pl_pct": realized_pl_pct,
        "market_cap": quote_snapshot.get("market_cap"),
        "as_of_date": quote_snapshot.get("as_of_date"),
        "entry_date": lot_entry_date,
        "sale_date": sd,
        "cycle_id": cycle_id,
        "booked_at": now,
    }
    ledger.setdefault("closed_trades", []).append(trade)

    pid = str(target.get("id"))
    remaining = open_qty - qs
    positions = ledger.get("positions", [])
    if remaining <= 0:
        ledger["positions"] = [p for p in positions if str(p.get("id")) != pid]
    else:
        target["qty"] = remaining
        if entry_price_override is not None:
            target["entry_price"] = entry

    from server.pnl_cash import record_sell_proceeds

    record_sell_proceeds(
        ledger,
        qty_sold=qs,
        exit_price=exit_p,
        trade_id=str(trade["id"]),
        symbol=sym,
    )
    return trade


def book_fifo(
    ledger: dict,
    *,
    symbol: str,
    exit_price: float,
    qty_sold: int,
    sale_date: str,
    quote_snapshot: dict,
    portfolio_items: list,
) -> list[dict]:
    """Sell qty from symbol using FIFO (oldest buy date / lot first)."""
    sym = _normalize_symbol(symbol)
    if sym not in _portfolio_stock_symbols(portfolio_items):
        raise ValueError("symbol not in portfolio")

    total = symbol_open_qty(ledger, sym)
    qs = _parse_qty(qty_sold)
    if qs is None:
        raise ValueError("qty_sold must be a positive integer")
    if qs > total:
        raise ValueError("qty_sold exceeds open qty")

    lots = _sorted_open_positions(ledger, sym)
    if not lots:
        raise ValueError("no open positions for symbol")

    remaining = qs
    trades: list[dict] = []
    for lot in lots:
        if remaining <= 0:
            break
        lot_qty = _parse_qty(lot.get("qty"))
        if not lot_qty:
            continue
        take = min(remaining, lot_qty)
        trade = _book_position_slice(
            ledger,
            lot,
            exit_price=exit_price,
            qty_sold=take,
            sale_date=sale_date,
            entry_price_override=None,
            quote_snapshot=quote_snapshot,
            portfolio_items=portfolio_items,
        )
        trades.append(trade)
        remaining -= take

    if remaining > 0:
        raise ValueError("qty_sold exceeds open qty")

    _end_cycle_if_closed(ledger, sym)
    sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    return trades


def book_position(
    ledger: dict,
    *,
    position_id: str,
    exit_price: float,
    qty_sold: int,
    sale_date: str,
    entry_price_override: Any = None,
    quote_snapshot: dict,
    portfolio_items: list,
) -> dict:
    pid = str(position_id or "").strip()
    if pid.startswith("placeholder-"):
        raise ValueError("save entry and qty before booking")

    positions = ledger.get("positions", [])
    target = None
    for p in positions:
        if isinstance(p, dict) and str(p.get("id")) == pid:
            target = p
            break
    if target is None:
        raise ValueError("position not found")

    sym = _normalize_symbol(target.get("symbol"))
    trade = _book_position_slice(
        ledger,
        target,
        exit_price=exit_price,
        qty_sold=qty_sold,
        sale_date=sale_date,
        entry_price_override=entry_price_override,
        quote_snapshot=quote_snapshot,
        portfolio_items=portfolio_items,
    )
    _end_cycle_if_closed(ledger, sym)
    sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    return trade


def patch_placeholder_or_position(
    ledger: dict,
    position_id: str,
    *,
    entry_price: Any,
    qty: Any,
    portfolio_items: list,
    entry_date: Any = None,
) -> dict:
    """PATCH handler: placeholder rows create a position; real rows update."""
    pid = str(position_id or "").strip()
    if pid.startswith("placeholder-"):
        sym = pid.replace("placeholder-", "", 1)
        if sym not in _portfolio_stock_symbols(portfolio_items):
            raise ValueError("symbol not in portfolio")

        if entry_price is not None or qty is not None:
            _set_portfolio_placeholder_draft(
                portfolio_items,
                sym,
                entry_price=entry_price,
                qty=qty,
            )

        resolved_entry = _portfolio_entry_hint(portfolio_items, sym)
        resolved_qty = _portfolio_draft_qty(portfolio_items, sym)
        if resolved_entry is not None and resolved_qty is not None:
            pos = ensure_position_from_placeholder(
                ledger,
                symbol=sym,
                entry_price=resolved_entry,
                qty=resolved_qty,
                portfolio_items=portfolio_items,
                entry_date=entry_date,
            )
            _clear_portfolio_placeholder_draft(portfolio_items, sym)
            return pos

        return {
            "id": pid,
            "symbol": sym,
            "entry_price": resolved_entry,
            "qty": resolved_qty,
            "is_placeholder": True,
        }
    else:
        pos = patch_position(
            ledger,
            pid,
            entry_price=entry_price,
            qty=qty,
            entry_date=entry_date,
        )
        sym = _normalize_symbol(pos.get("symbol"))
        sync_portfolio_entry_from_pnl(portfolio_items, ledger, sym)
    return pos


def consolidate_open_lots(ledger: dict, *, symbol: Optional[str] = None) -> int:
    """
    Merge open lots that share symbol, entry_date, and entry_price (FIFO order preserved).
    Returns the number of lots folded into another.
    """
    sym_filter = _normalize_symbol(symbol) if symbol else None
    positions = ledger.get("positions", [])
    if not isinstance(positions, list):
        return 0

    merged: list[dict] = []
    bucket_idx: dict[tuple, int] = {}
    removed = 0

    for p in positions:
        if not isinstance(p, dict):
            continue
        sym = _normalize_symbol(p.get("symbol"))
        if sym_filter and sym != sym_filter:
            merged.append(p)
            continue
        qty = _parse_qty(p.get("qty"))
        entry = parse_entry_price(p.get("entry_price"))
        ed = parse_entry_date(p.get("entry_date")) or ""
        if not sym or not qty or entry is None:
            merged.append(p)
            continue

        key = (sym, ed, entry)
        if key not in bucket_idx:
            bucket_idx[key] = len(merged)
            merged.append(dict(p))
            continue

        target = merged[bucket_idx[key]]
        target["qty"] = int(target.get("qty") or 0) + qty
        removed += 1

        extra_id = p.get("zerodha_trade_id")
        if extra_id:
            ids = list(target.get("zerodha_trade_ids") or [])
            if target.get("zerodha_trade_id") and target["zerodha_trade_id"] not in ids:
                ids.insert(0, str(target["zerodha_trade_id"]))
            if str(extra_id) not in ids:
                ids.append(str(extra_id))
            target["zerodha_trade_ids"] = ids
            target["zerodha_trade_id"] = ids[0]

        created = str(p.get("created_at") or "")
        target_created = str(target.get("created_at") or "")
        if created and (not target_created or created < target_created):
            target["created_at"] = created

    if removed:
        ledger["positions"] = merged
    return removed


def apply_bonus(
    ledger: dict,
    symbol: str,
    *,
    ratio_num: int = 1,
    ratio_den: int = 2,
) -> dict[str, int]:
    """
    Apply bonus ratio (ratio_num new shares per ratio_den held).
    Example: 1:2 bonus → ratio_num=1, ratio_den=2 (same as apply_bonus_1_2).
    """
    sym = _normalize_symbol(symbol)
    if ratio_den <= 0 or ratio_num <= 0:
        raise ValueError("ratio_num and ratio_den must be positive")
    lots = [
        p for p in ledger.get("positions", [])
        if isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym
    ]
    if not lots:
        return {"lots_adjusted": 0, "bonus_shares_added": 0, "lots_consolidated": 0, "open_qty": 0}

    total_qty = 0
    total_invested = 0.0
    min_entry_date = ""
    min_created = ""
    trade_ids: list[str] = []
    import_source = None
    for p in lots:
        qty = _parse_qty(p.get("qty")) or 0
        entry = parse_entry_price(p.get("entry_price"))
        if not qty or entry is None:
            continue
        total_qty += qty
        total_invested += qty * entry
        ed = parse_entry_date(p.get("entry_date")) or ""
        if ed and (not min_entry_date or ed < min_entry_date):
            min_entry_date = ed
        created = str(p.get("created_at") or "")
        if created and (not min_created or created < min_created):
            min_created = created
        ids = list(p.get("zerodha_trade_ids") or [])
        if not ids and p.get("zerodha_trade_id"):
            ids = [p["zerodha_trade_id"]]
        for tid in ids:
            if tid and str(tid) not in trade_ids:
                trade_ids.append(str(tid))
        if not import_source and p.get("import_source"):
            import_source = p.get("import_source")

    bonus = (total_qty * ratio_num) // ratio_den
    if bonus <= 0:
        return {
            "lots_adjusted": 0,
            "bonus_shares_added": 0,
            "lots_consolidated": 0,
            "open_qty": total_qty,
        }

    new_qty = total_qty + bonus
    new_entry = round(total_invested / new_qty, 6)
    removed = len(lots)

    kept = [
        p for p in ledger.get("positions", [])
        if not (isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym)
    ]
    tag = f"bonus_adjusted_{ratio_num}_{ratio_den}"
    kept.append({
        "id": lots[0].get("id") or str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": new_entry,
        "qty": new_qty,
        "entry_date": min_entry_date or None,
        "created_at": min_created or None,
        "zerodha_trade_id": trade_ids[0] if trade_ids else None,
        "zerodha_trade_ids": trade_ids or None,
        "import_source": import_source,
        tag: True,
        "bonus_adjusted_1_2": ratio_num == 1 and ratio_den == 2,
    })
    ledger["positions"] = kept

    return {
        "lots_adjusted": 1,
        "bonus_shares_added": bonus,
        "lots_consolidated": max(0, removed - 1),
        "open_qty": new_qty,
    }


def apply_bonus_1_2(ledger: dict, symbol: str) -> dict[str, int]:
    """Apply 1:2 bonus on total open qty (1 new share per 2 held). One consolidated lot after."""
    return apply_bonus(ledger, symbol, ratio_num=1, ratio_den=2)


def apply_split_to_open_lots(
    ledger: dict,
    symbol: str,
    *,
    ratio: float,
    ex_date: Optional[str] = None,
) -> dict[str, int]:
    """Apply stock split: qty multiplied by ratio, entry divided by ratio; invested unchanged."""
    sym = _normalize_symbol(symbol)
    if ratio <= 0:
        raise ValueError("ratio must be positive")
    lots = [
        p for p in ledger.get("positions", [])
        if isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym
    ]
    if not lots:
        return {"lots_adjusted": 0, "lots_consolidated": 0, "open_qty": 0}

    total_qty = 0
    total_invested = 0.0
    min_entry_date = ""
    min_created = ""
    trade_ids: list[str] = []
    import_source = None
    for p in lots:
        qty = _parse_qty(p.get("qty")) or 0
        entry = parse_entry_price(p.get("entry_price"))
        if not qty or entry is None:
            continue
        total_qty += qty
        total_invested += qty * entry
        ed = parse_entry_date(p.get("entry_date")) or ""
        if ed and (not min_entry_date or ed < min_entry_date):
            min_entry_date = ed
        created = str(p.get("created_at") or "")
        if created and (not min_created or created < min_created):
            min_created = created
        ids = list(p.get("zerodha_trade_ids") or [])
        if not ids and p.get("zerodha_trade_id"):
            ids = [p["zerodha_trade_id"]]
        for tid in ids:
            if tid and str(tid) not in trade_ids:
                trade_ids.append(str(tid))
        if not import_source and p.get("import_source"):
            import_source = p.get("import_source")

    new_qty = int(round(total_qty * ratio))
    if new_qty <= 0:
        return {"lots_adjusted": 0, "lots_consolidated": 0, "open_qty": total_qty}
    new_entry = round(total_invested / new_qty, 6)
    removed = len(lots)

    kept = [
        p for p in ledger.get("positions", [])
        if not (isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym)
    ]
    lot = {
        "id": lots[0].get("id") or str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": new_entry,
        "qty": new_qty,
        "entry_date": min_entry_date or None,
        "created_at": min_created or None,
        "zerodha_trade_id": trade_ids[0] if trade_ids else None,
        "zerodha_trade_ids": trade_ids or None,
        "import_source": import_source,
        "split_adjusted": True,
        "split_ratio": ratio,
    }
    if ex_date:
        lot["split_ex_date"] = ex_date
    kept.append(lot)
    ledger["positions"] = kept

    return {
        "lots_adjusted": 1,
        "lots_consolidated": max(0, removed - 1),
        "open_qty": new_qty,
    }


def set_symbol_open_snapshot(
    ledger: dict,
    symbol: str,
    *,
    qty: int,
    entry_price: float,
    entry_date: Optional[str] = None,
    import_source: Optional[str] = None,
) -> None:
    """Replace all open lots for symbol with one lot (holdings sync / repair)."""
    sym = _normalize_symbol(symbol)
    qs = _parse_qty(qty)
    entry = parse_entry_price(entry_price)
    if not qs or entry is None:
        raise ValueError("qty and entry_price required")

    kept = [
        p for p in ledger.get("positions", [])
        if not (isinstance(p, dict) and _normalize_symbol(p.get("symbol")) == sym)
    ]
    lot: dict = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "entry_price": entry,
        "qty": qs,
        "entry_date": parse_entry_date(entry_date) if entry_date else None,
    }
    if import_source:
        lot["import_source"] = import_source
    kept.append(lot)
    ledger["positions"] = kept
