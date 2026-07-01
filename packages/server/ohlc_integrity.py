"""
Detect and repair OHLC scale discontinuities in historical_data.

Charts use Yahoo split-adjusted series; bhavcopy nominal rows injected into
historical_data create false cliffs. This module scans for jumps and refreshes
affected symbols from Yahoo auto_adjust=True history.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, timedelta
from typing import Any, Callable, Optional

OHLC_DISCONTINUITY_THRESHOLD = 0.25
OHLC_SCAN_MIN_BARS = 5
OHLC_AUTO_REPAIR_CAP = 80

_last_scan_summary: dict[str, Any] = {
    "anomalies": [],
    "repaired": [],
    "failed": [],
    "last_scan_at": None,
    "last_repair_at": None,
}
_scan_lock = threading.Lock()


def last_integrity_summary() -> dict[str, Any]:
    with _scan_lock:
        return dict(_last_scan_summary)


def _set_scan_summary(**kwargs: Any) -> None:
    with _scan_lock:
        _last_scan_summary.update(kwargs)


def scan_ohlc_discontinuities(
    conn: sqlite3.Connection,
    *,
    lookback_calendar_days: int = 30,
    threshold: float = OHLC_DISCONTINUITY_THRESHOLD,
    symbols: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """
    Flag symbols with day-over-day |close/prev_close - 1| > threshold in lookback window.
    Returns list of anomaly records (one per jump; symbol may appear multiple times).
    """
    cur = conn.cursor()
    if symbols:
        sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    else:
        cur.execute(
            "SELECT symbol FROM screener WHERE symbol IS NOT NULL AND TRIM(symbol) != ''"
        )
        sym_list = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]

    cutoff = (date.today() - timedelta(days=max(1, int(lookback_calendar_days)))).isoformat()
    anomalies: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()

    for sym in sym_list:
        cur.execute(
            """
            SELECT substr(Date, 1, 10) AS day, Close
            FROM historical_data
            WHERE Symbol = ? AND substr(Date, 1, 10) >= ?
            ORDER BY day ASC
            """,
            (sym, cutoff),
        )
        rows = [(str(d), float(c)) for d, c in cur.fetchall() if d and c is not None and c > 0]
        if len(rows) < OHLC_SCAN_MIN_BARS:
            continue
        prev_day, prev_close = rows[0]
        for day, close in rows[1:]:
            if prev_close > 0:
                pct = (close - prev_close) / prev_close
                if abs(pct) > threshold:
                    anomalies.append(
                        {
                            "symbol": sym,
                            "date": day,
                            "prev_date": prev_day,
                            "prev_close": round(prev_close, 2),
                            "close": round(close, 2),
                            "pct": round(pct * 100, 2),
                        }
                    )
                    seen_symbols.add(sym)
            prev_day, prev_close = day, close

    summary = {
        "anomalies": anomalies,
        "symbol_count": len(seen_symbols),
        "last_scan_at": date.today().isoformat(),
    }
    _set_scan_summary(**summary)
    return anomalies


def repair_ohlc_anomalies(
    conn: sqlite3.Connection,
    *,
    symbols: Optional[list[str]] = None,
    lookback_calendar_days: int = 30,
    threshold: float = OHLC_DISCONTINUITY_THRESHOLD,
    max_symbols: int = OHLC_AUTO_REPAIR_CAP,
    log_fn: Optional[Callable[[str], None]] = None,
    apply_bhav_screener_overlay: bool = True,
) -> dict[str, Any]:
    """
    Scan for discontinuities; Yahoo-refresh each affected symbol.
    Optionally re-apply bhavcopy screener overlay (price/1D% only) after refresh.
    """
    import split_utils as su

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    if symbols:
        to_repair = [str(s).strip().upper() for s in symbols if str(s).strip()]
    else:
        anomalies = scan_ohlc_discontinuities(
            conn,
            lookback_calendar_days=lookback_calendar_days,
            threshold=threshold,
        )
        to_repair = sorted({a["symbol"] for a in anomalies})

    to_repair = to_repair[: max(1, int(max_symbols))]
    repaired: list[str] = []
    failed: list[dict[str, str]] = []

    for sym in to_repair:
        try:
            ok, err = su.apply_symbol_history_refresh(conn, sym)
            if not ok:
                failed.append({"symbol": sym, "error": err or "refresh_failed"})
                _log(f"[ohlc_integrity] {sym} refresh failed: {err}")
                continue
            repaired.append(sym)
            _log(f"[ohlc_integrity] {sym} refreshed from Yahoo (auto_adjust=True)")
        except Exception as exc:
            failed.append({"symbol": sym, "error": type(exc).__name__})
            _log(f"[ohlc_integrity] {sym} refresh error: {exc}")

    if apply_bhav_screener_overlay and repaired:
        try:
            from nse_bhavcopy import sync_screener_from_bhavcopy

            n = sync_screener_from_bhavcopy(conn, repaired, log_fn=log_fn)
            _log(f"[ohlc_integrity] bhavcopy screener overlay for {n} repaired symbol(s)")
        except Exception as exc:
            _log(f"[ohlc_integrity] screener overlay warning: {exc}")
    elif repaired:
        for sym in repaired:
            try:
                su.recalc_screener_change_for_symbol(conn, sym)
            except Exception:
                pass

    result = {
        "repaired": repaired,
        "failed": failed,
        "repaired_count": len(repaired),
        "failed_count": len(failed),
        "last_repair_at": date.today().isoformat(),
    }
    _set_scan_summary(repaired=repaired, failed=failed, last_repair_at=result["last_repair_at"])
    return result


def audit_after_reconcile(
    conn: sqlite3.Connection,
    *,
    lookback_calendar_days: int = 14,
    auto_repair: bool = False,
    max_auto_repair: int = 10,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Post-EOD scan; optionally auto-repair a capped batch of flagged symbols."""
    anomalies = scan_ohlc_discontinuities(conn, lookback_calendar_days=lookback_calendar_days)
    sym_count = len({a["symbol"] for a in anomalies})
    if log_fn and sym_count:
        log_fn(
            f"[ohlc_integrity] post-reconcile audit: {sym_count} symbol(s) with "
            f">{OHLC_DISCONTINUITY_THRESHOLD:.0%} day-over-day jumps in last "
            f"{lookback_calendar_days} day(s)"
        )
    repair_result = None
    if auto_repair and sym_count:
        repair_result = repair_ohlc_anomalies(
            conn,
            lookback_calendar_days=lookback_calendar_days,
            max_symbols=max_auto_repair,
            log_fn=log_fn,
            apply_bhav_screener_overlay=True,
        )
    return {
        "anomaly_count": len(anomalies),
        "symbol_count": sym_count,
        "anomalies": anomalies[:50],
        "repair": repair_result,
    }
