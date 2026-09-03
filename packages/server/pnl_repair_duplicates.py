"""Repair P&L closed-trade double-books from overlapping manual + Zerodha sells."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _sym(v: Any) -> str:
    return str(v or "").strip().upper()


def _is_zerodha_import_close(t: dict) -> bool:
    src = str(t.get("import_source") or "").strip().lower()
    if src == "zerodha":
        return True
    if src in ("zerodha_positions_today", "zerodha_gap_seed", "manual_promoted_zerodha"):
        return False
    if t.get("zerodha_trade_id") or t.get("zerodha_trade_ids"):
        # positions_today may not set import_source=zerodha
        return src == "zerodha" or (not src and str(t.get("broker") or "").lower() == "zerodha")
    return False


def _is_preferred_close(t: dict) -> bool:
    """Keep bonus-adjusted / positions / manual closes over raw tradebook re-books."""
    src = str(t.get("import_source") or "").strip().lower()
    if src in ("zerodha_positions_today",):
        return True
    if src in ("zerodha", "zerodha_gap_seed"):
        return False
    # Untagged / manual closes are preferred when a zerodha duplicate exists
    return True


def repair_duplicate_closed_trades(ledger: dict) -> dict[str, Any]:
    """
    Remove double-booked closed trades.

    1) Exact duplicates (same symbol/date/qty/exit/|pl|): drop the Zerodha-import copy.
    2) Same symbol/date/exit with overlapping sell qty from preferred + Zerodha-import:
       drop Zerodha-import rows (typical Trent pre-bonus vs post-bonus double sell).
    3) Drop pure gap-seed closes (entry ≈ exit, realized ≈ 0, import_source zerodha).
    """
    closed = [t for t in (ledger.get("closed_trades") or []) if isinstance(t, dict)]
    removed: list[dict] = []
    keep_flags = [True] * len(closed)

    # --- Pass 1: exact duplicates ---
    exact: dict[tuple, list[int]] = defaultdict(list)
    for i, t in enumerate(closed):
        k = (
            _sym(t.get("symbol")),
            str(t.get("sale_date") or "")[:10],
            _i(t.get("qty_sold")),
            round(_f(t.get("exit_price")), 2),
            round(abs(_f(t.get("realized_pl"))), 2),
        )
        exact[k].append(i)

    for idxs in exact.values():
        if len(idxs) < 2:
            continue
        preferred = [i for i in idxs if _is_preferred_close(closed[i])]
        zerodha_ish = [i for i in idxs if _is_zerodha_import_close(closed[i]) or not _is_preferred_close(closed[i])]
        # Keep one preferred; if none, keep first
        keep_one = preferred[0] if preferred else idxs[0]
        for i in idxs:
            if i == keep_one:
                continue
            # Prefer removing zerodha-import duplicates
            if i in zerodha_ish or (_is_zerodha_import_close(closed[i]) and keep_one in preferred):
                keep_flags[i] = False
            elif not preferred and i != keep_one:
                keep_flags[i] = False

    # --- Pass 2: overlapping sells same day/exit (Trent-style) ---
    by_day_exit: dict[tuple, list[int]] = defaultdict(list)
    for i, t in enumerate(closed):
        if not keep_flags[i]:
            continue
        k = (
            _sym(t.get("symbol")),
            str(t.get("sale_date") or "")[:10],
            round(_f(t.get("exit_price")), 1),
        )
        by_day_exit[k].append(i)

    for idxs in by_day_exit.values():
        if len(idxs) < 2:
            continue
        pref = [i for i in idxs if _is_preferred_close(closed[i]) and not _is_zerodha_import_close(closed[i])]
        zimp = [i for i in idxs if _is_zerodha_import_close(closed[i])]
        if not pref or not zimp:
            continue
        pref_qty = sum(_i(closed[i].get("qty_sold")) for i in pref)
        z_qty = sum(_i(closed[i].get("qty_sold")) for i in zimp)
        # If both sides sold similar qty the same day at same exit, drop Zerodha-import side
        if pref_qty > 0 and z_qty > 0 and min(pref_qty, z_qty) / max(pref_qty, z_qty) >= 0.5:
            for i in zimp:
                keep_flags[i] = False

    # --- Pass 3: gap-seed zero P/L noise ---
    for i, t in enumerate(closed):
        if not keep_flags[i]:
            continue
        src = str(t.get("import_source") or "").strip().lower()
        entry = _f(t.get("entry_price"))
        exit_p = _f(t.get("exit_price"))
        pl = _f(t.get("realized_pl"))
        if src == "zerodha" and abs(entry - exit_p) < 0.05 and abs(pl) < 0.05:
            # gap-seed artifact (entry forced to sell price)
            keep_flags[i] = False

    # --- Pass 4: orphan pre-bonus Zerodha closes when preferred (post-bonus) closes exist ---
    pref_entry_by_sym: dict[str, list[float]] = defaultdict(list)
    for i, t in enumerate(closed):
        if not keep_flags[i]:
            continue
        if _is_preferred_close(t) and not _is_zerodha_import_close(t):
            ep = _f(t.get("entry_price"))
            if ep > 0:
                pref_entry_by_sym[_sym(t.get("symbol"))].append(ep)

    for i, t in enumerate(closed):
        if not keep_flags[i]:
            continue
        if not _is_zerodha_import_close(t):
            continue
        sym = _sym(t.get("symbol"))
        prefs = pref_entry_by_sym.get(sym) or []
        if not prefs:
            continue
        prefs_sorted = sorted(prefs)
        med = prefs_sorted[len(prefs_sorted) // 2]
        entry = _f(t.get("entry_price"))
        # Pre-bonus cost basis is ~2x (1:2 bonus) or otherwise far above adjusted lots
        if med > 0 and entry > med * 1.25:
            keep_flags[i] = False

    new_closed: list[dict] = []
    for i, t in enumerate(closed):
        if keep_flags[i]:
            new_closed.append(t)
        else:
            removed.append({
                "symbol": _sym(t.get("symbol")),
                "sale_date": t.get("sale_date"),
                "qty_sold": t.get("qty_sold"),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
                "realized_pl": t.get("realized_pl"),
                "import_source": t.get("import_source"),
                "broker": t.get("broker"),
            })

    ledger["closed_trades"] = new_closed

    before = sum(_f(t.get("realized_pl")) for t in closed)
    after = sum(_f(t.get("realized_pl")) for t in new_closed)
    by_sym_removed: dict[str, float] = defaultdict(float)
    for r in removed:
        by_sym_removed[_sym(r.get("symbol"))] += _f(r.get("realized_pl"))

    return {
        "removed_count": len(removed),
        "removed": removed,
        "realized_before": round(before, 2),
        "realized_after": round(after, 2),
        "realized_delta": round(after - before, 2),
        "removed_pl_by_symbol": {k: round(v, 2) for k, v in sorted(by_sym_removed.items())},
    }
