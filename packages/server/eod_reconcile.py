"""
Reconcile local OHLCV with NSE official bhavcopy and refresh screener %.
Runs on server startup and after price/OHLCV update jobs.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable, Optional

_lock = threading.Lock()
_running = False
_last_result: dict = {"ok": False, "bars": 0, "screener_updated": 0, "error": None}


def last_reconcile_status() -> dict:
    return dict(_last_result)


def run_eod_bhavcopy_reconcile(
    db_path: Path,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
    audit_integrity: bool = True,
) -> int:
    """Overlay screener price/1D% from NSE bhavcopy; sync from historical_data if bhav offline."""
    global _running, _last_result
    with _lock:
        if _running:
            return int(_last_result.get("screener_updated") or _last_result.get("bars") or 0)
        _running = True
    screener_updated = 0
    err = None
    try:
        import sys

        root = db_path.resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        from server.nse_bhavcopy import last_reconcile_metrics, reconcile_recent_eod_from_nse
        from scrape_daily import get_all_screener_symbols, sync_screener_prices_from_latest_bars

        conn = sqlite3.connect(str(db_path))
        try:
            symbols = get_all_screener_symbols(conn)
            screener_updated = reconcile_recent_eod_from_nse(conn, symbols, log_fn=log_fn)
            if screener_updated == 0:
                if log_fn:
                    log_fn("[eod_reconcile] bhavcopy unavailable — syncing screener from historical_data")
                sync_screener_prices_from_latest_bars(conn, log_fn=log_fn)
            if audit_integrity:
                try:
                    from server.ohlc_integrity import audit_after_reconcile

                    audit_after_reconcile(
                        conn,
                        lookback_calendar_days=14,
                        auto_repair=False,
                        log_fn=log_fn,
                    )
                except Exception as audit_err:
                    if log_fn:
                        log_fn(f"[eod_reconcile] integrity audit warning: {audit_err}")
        finally:
            conn.close()
        metrics = last_reconcile_metrics()
        _last_result = {
            "ok": True,
            "bars": screener_updated,
            "screener_updated": screener_updated,
            "historical_data_writes": metrics.get("historical_data_writes", 0),
            "error": None,
        }
        try:
            from server import market_data_version as mdv

            mdv.record_eod_publish(db_path, bars=screener_updated)
        except Exception as bump_err:
            if log_fn:
                log_fn(f"[eod_reconcile] market-data-version bump warning: {bump_err}")
    except Exception as e:
        err = str(e)
        _last_result = {
            "ok": False,
            "bars": screener_updated,
            "screener_updated": screener_updated,
            "error": err,
        }
        try:
            from server import market_data_version as mdv

            mdv.mark_eod_failed(db_path, error=err)
        except Exception:
            pass
        if log_fn:
            log_fn(f"[eod_reconcile] warning: {err}")
    finally:
        with _lock:
            _running = False
    return screener_updated


def schedule_startup_reconcile(db_path: Path) -> None:
    """Background reconcile so Market Map / charts match NSE after restart."""

    def _worker():
        def _log(msg: str) -> None:
            print(msg, flush=True)

        n = run_eod_bhavcopy_reconcile(db_path, log_fn=_log)
        if n:
            try:
                import importlib

                srv = importlib.import_module("server.server")
                if hasattr(srv, "invalidate_chart_cache"):
                    srv.invalidate_chart_cache()
            except Exception:
                pass
            _log(f"[eod_reconcile] startup complete: {n} screener symbol(s) updated from bhavcopy")

    threading.Thread(target=_worker, name="eod-bhavcopy-startup", daemon=True).start()
