"""
4H session bar builder — invoked from server run_fetch_ohlcv.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

BASE_DIR = Path(__file__).resolve().parent


def connect_db():
    import sys

    root = str(BASE_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    from db_sqlite import connect_sqlite

    return connect_sqlite(BASE_DIR / "data" / "nse_data.db")


def get_all_screener_symbols(conn) -> list[str]:
    rows = conn.execute("SELECT symbol FROM screener WHERE symbol IS NOT NULL").fetchall()
    return [str(r[0]).strip().upper() for r in rows if r and r[0]]


def _merge_stats(into: dict, part: dict) -> None:
    for key in ("updated", "failed", "skipped", "processed"):
        into[key] = into.get(key, 0) + int(part.get(key, 0) or 0)
    src = part.get("sources") or {}
    if isinstance(src, dict):
        dest = into.setdefault("sources", {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0, "failed": 0})
        for k, v in src.items():
            dest[k] = int(dest.get(k) or 0) + int(v or 0)
    misses = part.get("misses") or []
    if isinstance(misses, list) and misses:
        dest_m = into.setdefault("misses", [])
        for m in misses:
            if m not in dest_m and len(dest_m) < 50:
                dest_m.append(m)


def run(
    *,
    symbols: Optional[list[str]] = None,
    backfill: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    also_30m: bool = True,
) -> dict:
    from server.bars_4h import (
        BARS_4H_INCREMENTAL_SESSION_DAYS,
        build_bars_4h_for_symbols,
        load_nse_calendar,
        recent_completed_4h_session_dates,
        reconcile_4h_backfill_meta,
        symbols_needing_4h_backfill,
        symbols_needing_4h_refresh,
        try_mark_universe_backfill_complete,
    )

    conn = connect_db()
    totals = {
        "updated": 0,
        "failed": 0,
        "skipped": 0,
        "processed": 0,
        "sources": {"upstox": 0, "yahoo": 0, "nse": 0, "none": 0, "failed": 0},
        "skipped_current": 0,
        "misses": [],
    }
    try:
        sym_list = symbols
        if sym_list is None:
            sym_list = get_all_screener_symbols(conn)
        full_universe = symbols is None

        # Never auto-force universe 90d from meta. Explicit backfill=True only
        # (admin full rebuild / scoped depth catch-up / live limited catch-up).
        reconcile_4h_backfill_meta(conn, sym_list)

        needing_depth = symbols_needing_4h_backfill(conn, sym_list)
        backfill_all = bool(backfill and full_universe)

        if backfill_all:
            if message_callback:
                message_callback(f"4H full backfill: {len(sym_list)} symbols...")
            _merge_stats(
                totals,
                build_bars_4h_for_symbols(
                    conn,
                    sym_list,
                    BASE_DIR,
                    backfill=True,
                    progress_callback=progress_callback,
                    message_callback=message_callback,
                    cancel_check=cancel_check,
                    also_30m=also_30m,
                ),
            )
        else:
            cal = load_nse_calendar(BASE_DIR)
            recent = recent_completed_4h_session_dates(
                BARS_4H_INCREMENTAL_SESSION_DAYS,
                holidays=cal["holidays"],
                special_sessions=cal["special_sessions"],
                base_dir=BASE_DIR,
            )
            latest = recent[0]
            missing_latest = symbols_needing_4h_refresh(conn, sym_list, recent)
            depth_set = set(needing_depth)
            refresh_only = [s for s in missing_latest if s not in depth_set]
            work_n = len(depth_set) + len(refresh_only)
            skipped_current = max(0, len(sym_list) - work_n)
            totals["skipped_current"] = skipped_current

            if not needing_depth and not refresh_only:
                if message_callback:
                    window = (
                        f"{recent[-1].isoformat()}..{latest.isoformat()}"
                        if len(recent) > 1
                        else latest.isoformat()
                    )
                    message_callback(
                        f"4H already current — skipped ({len(sym_list)} symbols, "
                        f"sessions {window})"
                    )
                totals["skipped"] = len(sym_list)
                return totals

            if needing_depth:
                sample = ", ".join(needing_depth[:5])
                extra = f" (+{len(needing_depth) - 5} more)" if len(needing_depth) > 5 else ""
                if message_callback:
                    message_callback(
                        f"4H history catch-up for {len(needing_depth)} symbols "
                        f"(e.g. {sample}{extra})..."
                    )
                _merge_stats(
                    totals,
                    build_bars_4h_for_symbols(
                        conn,
                        needing_depth,
                        BASE_DIR,
                        backfill=True,
                        progress_callback=progress_callback,
                        message_callback=message_callback,
                        cancel_check=cancel_check,
                        also_30m=also_30m,
                    ),
                )

            if refresh_only:
                window = (
                    f"{recent[-1].isoformat()}..{latest.isoformat()}"
                    if len(recent) > 1
                    else latest.isoformat()
                )
                if message_callback:
                    message_callback(
                        f"4H incremental refresh: {len(refresh_only)} symbols missing "
                        f"sessions in {window} "
                        f"({skipped_current} already current skipped)..."
                    )
                _merge_stats(
                    totals,
                    build_bars_4h_for_symbols(
                        conn,
                        refresh_only,
                        BASE_DIR,
                        backfill=False,
                        progress_callback=progress_callback,
                        message_callback=message_callback,
                        cancel_check=cancel_check,
                        also_30m=also_30m,
                    ),
                )
            elif message_callback and skipped_current:
                if len(recent) > 1:
                    message_callback(
                        f"4H skip-if-current: {skipped_current} symbols already have "
                        f"{recent[-1].isoformat()}..{latest.isoformat()}"
                    )
                else:
                    message_callback(
                        f"4H skip-if-current: {skipped_current} symbols already have {latest.isoformat()}"
                    )

        if full_universe:
            try_mark_universe_backfill_complete(conn, sym_list)

        if message_callback and totals.get("misses"):
            sample = ", ".join(totals["misses"][:8])
            extra = f" (+{len(totals['misses']) - 8} more)" if len(totals["misses"]) > 8 else ""
            message_callback(
                f"4H Upstox misses ({len(totals['misses'])}): {sample}{extra}"
            )

        return totals
    finally:
        conn.close()
