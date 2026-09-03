"""
30m session bar builder — invoked from server run_fetch_ohlcv / admin job.

Usually co-written during scrape_4h (shared 5m fetch). This CLI rebuilds 30m alone.
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
) -> dict:
    from server.bars_30m import (
        BARS_30M_INCREMENTAL_SESSION_DAYS,
        build_bars_30m_for_symbols,
        load_nse_calendar,
        reconcile_30m_backfill_meta,
        symbols_needing_30m_backfill,
        symbols_needing_30m_refresh,
        try_mark_universe_30m_backfill_complete,
    )
    from server.bars_4h import recent_completed_4h_session_dates

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

        reconcile_30m_backfill_meta(conn, sym_list)

        needing_depth = symbols_needing_30m_backfill(conn, sym_list)
        backfill_all = bool(backfill and full_universe)

        if backfill_all:
            if message_callback:
                message_callback(f"30m full backfill: {len(sym_list)} symbols...")
            _merge_stats(
                totals,
                build_bars_30m_for_symbols(
                    conn,
                    sym_list,
                    BASE_DIR,
                    backfill=True,
                    progress_callback=progress_callback,
                    message_callback=message_callback,
                    cancel_check=cancel_check,
                ),
            )
        else:
            cal = load_nse_calendar(BASE_DIR)
            recent = recent_completed_4h_session_dates(
                BARS_30M_INCREMENTAL_SESSION_DAYS,
                holidays=cal["holidays"],
                special_sessions=cal["special_sessions"],
                base_dir=BASE_DIR,
            )
            latest = recent[0]
            missing_latest = symbols_needing_30m_refresh(conn, sym_list, recent)
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
                        f"30m already current — skipped ({len(sym_list)} symbols, "
                        f"sessions {window})"
                    )
                totals["skipped"] = len(sym_list)
                return totals

            if needing_depth:
                sample = ", ".join(needing_depth[:5])
                extra = f" (+{len(needing_depth) - 5} more)" if len(needing_depth) > 5 else ""
                if message_callback:
                    message_callback(
                        f"30m history catch-up for {len(needing_depth)} symbols "
                        f"(e.g. {sample}{extra})..."
                    )
                _merge_stats(
                    totals,
                    build_bars_30m_for_symbols(
                        conn,
                        needing_depth,
                        BASE_DIR,
                        backfill=True,
                        progress_callback=progress_callback,
                        message_callback=message_callback,
                        cancel_check=cancel_check,
                    ),
                )

            if refresh_only:
                if message_callback:
                    message_callback(
                        f"30m incremental refresh for {len(refresh_only)} symbols "
                        f"(sessions through {latest.isoformat()})..."
                    )
                _merge_stats(
                    totals,
                    build_bars_30m_for_symbols(
                        conn,
                        refresh_only,
                        BASE_DIR,
                        backfill=False,
                        progress_callback=progress_callback,
                        message_callback=message_callback,
                        cancel_check=cancel_check,
                    ),
                )

        if full_universe:
            try_mark_universe_30m_backfill_complete(conn, sym_list)
        return totals
    finally:
        conn.close()
