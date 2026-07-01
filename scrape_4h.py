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


def run(
    *,
    symbols: Optional[list[str]] = None,
    backfill: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    from server.bars_4h import (
        META_BACKFILL_COMPLETE,
        build_bars_4h_for_symbols,
        get_meta,
        reconcile_4h_backfill_meta,
        symbols_needing_4h_backfill,
        try_mark_universe_backfill_complete,
    )

    conn = connect_db()
    totals = {"updated": 0, "failed": 0, "skipped": 0, "processed": 0}
    try:
        sym_list = symbols
        if sym_list is None:
            sym_list = get_all_screener_symbols(conn)
        full_universe = symbols is None

        reconcile_4h_backfill_meta(conn, sym_list)

        if not backfill and get_meta(conn, META_BACKFILL_COMPLETE) != "1":
            backfill = True

        needing = symbols_needing_4h_backfill(conn, sym_list)
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
                ),
            )
        else:
            if needing:
                sample = ", ".join(needing[:5])
                extra = f" (+{len(needing) - 5} more)" if len(needing) > 5 else ""
                if message_callback:
                    message_callback(
                        f"4H history catch-up for {len(needing)} symbols (e.g. {sample}{extra})..."
                    )
                _merge_stats(
                    totals,
                    build_bars_4h_for_symbols(
                        conn,
                        needing,
                        BASE_DIR,
                        backfill=True,
                        progress_callback=progress_callback,
                        message_callback=message_callback,
                        cancel_check=cancel_check,
                    ),
                )
            if message_callback:
                message_callback(f"4H incremental refresh: {len(sym_list)} symbols...")
            _merge_stats(
                totals,
                build_bars_4h_for_symbols(
                    conn,
                    sym_list,
                    BASE_DIR,
                    backfill=False,
                    progress_callback=progress_callback,
                    message_callback=message_callback,
                    cancel_check=cancel_check,
                ),
            )

        if full_universe:
            try_mark_universe_backfill_complete(conn, sym_list)

        return totals
    finally:
        conn.close()
