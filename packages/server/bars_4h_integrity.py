"""
Detect and repair bad 4H session bars (bars_4h).

4H bars come from Yahoo 5m history; corporate actions and stale incremental
updates can leave scale cliffs or flat wrong prices. Repair scales mismatched
sessions to daily historical_data anchors before falling back to Yahoo rebuild.

The bars_4h_quarantine table is a host-only repair ledger — it never blocks charts.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

BARS_4H_DISCONTINUITY_THRESHOLD = 0.25
BARS_4H_DAILY_ANCHOR_TOLERANCE = 0.05
BARS_4H_FLATLINE_MIN_SESSIONS = 5
BARS_4H_FLATLINE_DAILY_MOVE_MIN = 0.02
BARS_4H_SCAN_MIN_SESSIONS = 5
BARS_4H_AUTO_REPAIR_CAP = 50
META_REPAIR_QUEUE_SNAPSHOT = "bars_4h_repair_queue_snapshot"

_last_summary: dict[str, Any] = {
    "anomalies": [],
    "repaired": [],
    "failed": [],
    "pending_repair": [],
    "last_scan_at": None,
    "last_repair_at": None,
}
_lock = threading.Lock()


def last_bars_4h_integrity_summary() -> dict[str, Any]:
    with _lock:
        return dict(_last_summary)


def _set_summary(**kwargs: Any) -> None:
    with _lock:
        _last_summary.update(kwargs)


def ensure_bars_4h_quarantine_table(conn: sqlite3.Connection) -> None:
    """Host-only repair queue (legacy table name: bars_4h_quarantine)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bars_4h_quarantine (
            Symbol TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            flagged_at TEXT NOT NULL,
            repair_attempts INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def is_symbol_4h_quarantined(conn: sqlite3.Connection, symbol: str) -> bool:
    """True if symbol is on the host repair queue (does not block charts)."""
    ensure_bars_4h_quarantine_table(conn)
    sym = str(symbol or "").strip().upper()
    if not sym:
        return False
    row = conn.execute(
        "SELECT 1 FROM bars_4h_quarantine WHERE Symbol=? LIMIT 1",
        (sym,),
    ).fetchone()
    return row is not None


def quarantine_reason(conn: sqlite3.Connection, symbol: str) -> Optional[str]:
    ensure_bars_4h_quarantine_table(conn)
    sym = str(symbol or "").strip().upper()
    row = conn.execute(
        "SELECT reason FROM bars_4h_quarantine WHERE Symbol=?",
        (sym,),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _flag_repair_pending(conn: sqlite3.Connection, symbol: str, reason: str) -> None:
    ensure_bars_4h_quarantine_table(conn)
    sym = str(symbol).strip().upper()
    conn.execute(
        """
        INSERT INTO bars_4h_quarantine (Symbol, reason, flagged_at, repair_attempts)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(Symbol) DO UPDATE SET
            reason=excluded.reason,
            flagged_at=excluded.flagged_at,
            repair_attempts=bars_4h_quarantine.repair_attempts + 1
        """,
        (sym, reason[:500], date.today().isoformat()),
    )
    conn.commit()


def clear_4h_quarantine(conn: sqlite3.Connection, symbol: str) -> None:
    ensure_bars_4h_quarantine_table(conn)
    sym = str(symbol).strip().upper()
    conn.execute("DELETE FROM bars_4h_quarantine WHERE Symbol=?", (sym,))
    conn.commit()


def list_quarantined_symbols(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Host-only repair queue entries."""
    ensure_bars_4h_quarantine_table(conn)
    rows = conn.execute(
        "SELECT Symbol, reason, flagged_at, repair_attempts "
        "FROM bars_4h_quarantine ORDER BY Symbol ASC"
    ).fetchall()
    return [
        {
            "symbol": str(r[0]),
            "reason": str(r[1]),
            "flagged_at": str(r[2]),
            "repair_attempts": int(r[3] or 0),
        }
        for r in rows
    ]


def _persist_repair_queue_snapshot(conn: sqlite3.Connection) -> None:
    from server.bars_4h import ensure_updater_meta_table, set_meta

    ensure_updater_meta_table(conn)
    payload = json.dumps(list_quarantined_symbols(conn))
    set_meta(conn, META_REPAIR_QUEUE_SNAPSHOT, payload)


def _session_end_closes(
    conn: sqlite3.Connection,
    symbol: str,
    cutoff: str,
) -> list[tuple[str, float]]:
    rows = conn.execute(
        """
        SELECT SessionDate, Bucket, Close
        FROM bars_4h
        WHERE Symbol=? AND SessionDate >= ?
        ORDER BY SessionDate ASC, Bucket ASC
        """,
        (symbol, cutoff),
    ).fetchall()
    by_session: dict[str, float] = {}
    for sd, _bucket, close in rows:
        if close is None or float(close) <= 0:
            continue
        by_session[str(sd)] = float(close)
    return sorted(by_session.items())


def _daily_closes(
    conn: sqlite3.Connection,
    symbol: str,
    cutoff: str,
) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT substr(Date, 1, 10) AS day, Close
        FROM historical_data
        WHERE Symbol=? AND substr(Date, 1, 10) >= ?
        ORDER BY day ASC
        """,
        (symbol, cutoff),
    ).fetchall()
    out: dict[str, float] = {}
    for day, close in rows:
        if day and close is not None and float(close) > 0:
            out[str(day)] = float(close)
    if out:
        return out
    rows = conn.execute(
        """
        SELECT substr(Date, 1, 10) AS day, Close
        FROM index_history
        WHERE Symbol=? AND substr(Date, 1, 10) >= ?
        ORDER BY day ASC
        """,
        (symbol, cutoff),
    ).fetchall()
    for day, close in rows:
        if day and close is not None and float(close) > 0:
            out[str(day)] = float(close)
    return out


def _scale_session_bars(
    conn: sqlite3.Connection,
    symbol: str,
    session_date: str,
    factor: float,
) -> int:
    from server.bars_4h import ensure_bars_4h_table

    if abs(factor - 1.0) < 1e-6:
        return 0
    ensure_bars_4h_table(conn)
    sym = str(symbol).strip().upper()
    rows = conn.execute(
        """
        SELECT BarStart, Open, High, Low, Close, Volume
        FROM bars_4h WHERE Symbol=? AND SessionDate=?
        """,
        (sym, session_date),
    ).fetchall()
    n = 0
    for bar_start, o, h, l, c, v in rows:
        conn.execute(
            """
            UPDATE bars_4h
            SET Open=?, High=?, Low=?, Close=?, Volume=?
            WHERE Symbol=? AND BarStart=?
            """,
            (
                round(float(o) * factor, 2),
                round(float(h) * factor, 2),
                round(float(l) * factor, 2),
                round(float(c) * factor, 2),
                round(float(v or 0), 2),
                sym,
                bar_start,
            ),
        )
        n += 1
    return n


def _scale_sessions_before(
    conn: sqlite3.Connection,
    symbol: str,
    before_session_date: str,
    factor: float,
) -> int:
    sym = str(symbol).strip().upper()
    rows = conn.execute(
        """
        SELECT DISTINCT SessionDate FROM bars_4h
        WHERE Symbol=? AND SessionDate < ?
        ORDER BY SessionDate ASC
        """,
        (sym, before_session_date),
    ).fetchall()
    total = 0
    for (sd,) in rows:
        total += _scale_session_bars(conn, sym, str(sd), factor)
    return total


def rescale_bars_4h_from_daily_anchor(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    lookback_calendar_days: int = 60,
    tolerance: float = BARS_4H_DAILY_ANCHOR_TOLERANCE,
) -> dict[str, Any]:
    """Scale each session's 4H OHLC so session-end close matches daily close."""
    sym = str(symbol).strip().upper()
    cutoff = (date.today() - timedelta(days=max(1, int(lookback_calendar_days)))).isoformat()
    daily = _daily_closes(conn, sym, cutoff)
    sessions = _session_end_closes(conn, sym, cutoff)
    scaled_dates: list[str] = []
    bars_touched = 0
    for sd, h_close in sessions:
        d_close = daily.get(sd)
        if d_close is None or d_close <= 0 or h_close <= 0:
            continue
        factor = d_close / h_close
        if abs(factor - 1.0) <= tolerance:
            continue
        bars_touched += _scale_session_bars(conn, sym, sd, factor)
        scaled_dates.append(sd)
    if scaled_dates:
        conn.commit()
    return {
        "symbol": sym,
        "scaled_sessions": len(scaled_dates),
        "bars_touched": bars_touched,
        "session_dates": scaled_dates[:20],
    }


def rescale_bars_4h_at_discontinuities(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    lookback_calendar_days: int = 60,
    discontinuity_threshold: float = BARS_4H_DISCONTINUITY_THRESHOLD,
    tolerance: float = BARS_4H_DAILY_ANCHOR_TOLERANCE,
) -> dict[str, Any]:
    """
    At each 4H cliff, scale all pre-cliff sessions so the prior session aligns
    with daily (handles corp-action boundaries without waiting on Yahoo 5m).
    """
    sym = str(symbol).strip().upper()
    cutoff = (date.today() - timedelta(days=max(1, int(lookback_calendar_days)))).isoformat()
    daily = _daily_closes(conn, sym, cutoff)
    sessions = _session_end_closes(conn, sym, cutoff)
    cliffs_fixed = 0
    bars_touched = 0

    for i in range(1, len(sessions)):
        prev_sd, prev_h = sessions[i - 1]
        sd, h = sessions[i]
        if prev_h <= 0 or h <= 0:
            continue
        h_pct = abs((h - prev_h) / prev_h)
        if h_pct <= discontinuity_threshold:
            continue
        d_prev = daily.get(prev_sd)
        d_curr = daily.get(sd)
        if d_prev is None or d_curr is None or d_prev <= 0 or d_curr <= 0:
            continue
        d_pct = abs((d_curr - d_prev) / d_prev)

        factor: Optional[float] = None
        if d_pct < discontinuity_threshold * 0.6:
            ratios = []
            for psd, ph in sessions[:i]:
                dp = daily.get(psd)
                if dp and ph > 0:
                    ratios.append(dp / ph)
            if ratios:
                factor = statistics.median(ratios)
        elif abs(d_prev / prev_h - 1.0) > tolerance:
            factor = d_prev / prev_h

        if factor is None or abs(factor - 1.0) <= tolerance:
            continue
        bars_touched += _scale_sessions_before(conn, sym, sd, factor)
        cliffs_fixed += 1

    if bars_touched:
        conn.commit()
    return {
        "symbol": sym,
        "cliffs_fixed": cliffs_fixed,
        "bars_touched": bars_touched,
    }


def rescale_bars_4h_to_daily(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    lookback_calendar_days: int = 60,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Run per-session anchor rescale then cliff bulk rescale."""
    sym = str(symbol).strip().upper()
    anchor = rescale_bars_4h_from_daily_anchor(
        conn, sym, lookback_calendar_days=lookback_calendar_days
    )
    cliff = rescale_bars_4h_at_discontinuities(
        conn, sym, lookback_calendar_days=lookback_calendar_days
    )
    if log_fn and (anchor["scaled_sessions"] or cliff["cliffs_fixed"]):
        log_fn(
            f"[bars_4h_integrity] {sym} daily rescale: "
            f"{anchor['scaled_sessions']} session(s), {cliff['cliffs_fixed']} cliff(s)"
        )
    return {"anchor": anchor, "cliff": cliff}


def scan_bars_4h_anomalies(
    conn: sqlite3.Connection,
    *,
    lookback_calendar_days: int = 45,
    discontinuity_threshold: float = BARS_4H_DISCONTINUITY_THRESHOLD,
    daily_anchor_tolerance: float = BARS_4H_DAILY_ANCHOR_TOLERANCE,
    symbols: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    if symbols:
        sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    else:
        rows = conn.execute(
            "SELECT symbol FROM screener WHERE symbol IS NOT NULL AND TRIM(symbol) != ''"
        ).fetchall()
        sym_list = [str(r[0]).strip().upper() for r in rows if r and r[0]]

    cutoff = (date.today() - timedelta(days=max(1, int(lookback_calendar_days)))).isoformat()
    anomalies: list[dict[str, Any]] = []

    for sym in sym_list:
        sessions = _session_end_closes(conn, sym, cutoff)
        if len(sessions) < BARS_4H_SCAN_MIN_SESSIONS:
            continue

        daily = _daily_closes(conn, sym, cutoff)

        prev_sd, prev_close = sessions[0]
        for sd, close in sessions[1:]:
            if prev_close > 0:
                pct = (close - prev_close) / prev_close
                if abs(pct) > discontinuity_threshold:
                    anomalies.append(
                        {
                            "symbol": sym,
                            "kind": "discontinuity",
                            "date": sd,
                            "prev_date": prev_sd,
                            "prev_close": round(prev_close, 2),
                            "close": round(close, 2),
                            "pct": round(pct * 100, 2),
                        }
                    )
            prev_sd, prev_close = sd, close

        for sd, close in sessions:
            d_close = daily.get(sd)
            if d_close is None or d_close <= 0:
                continue
            ratio = close / d_close
            if abs(ratio - 1.0) > daily_anchor_tolerance:
                anomalies.append(
                    {
                        "symbol": sym,
                        "kind": "daily_anchor",
                        "date": sd,
                        "bars_4h_close": round(close, 2),
                        "daily_close": round(d_close, 2),
                        "pct": round((ratio - 1.0) * 100, 2),
                    }
                )

        flat_n = BARS_4H_FLATLINE_MIN_SESSIONS
        if len(sessions) >= flat_n:
            window = sessions[-flat_n:]
            closes = [c for _, c in window]
            if len(set(round(c, 2) for c in closes)) == 1:
                first_sd, first_c = window[0]
                last_sd, _last_c = window[-1]
                d_first = daily.get(first_sd)
                d_last = daily.get(last_sd)
                if (
                    d_first is not None
                    and d_last is not None
                    and d_first > 0
                    and abs((d_last - d_first) / d_first) >= BARS_4H_FLATLINE_DAILY_MOVE_MIN
                    and abs(first_c - d_last) / d_last > daily_anchor_tolerance
                ):
                    anomalies.append(
                        {
                            "symbol": sym,
                            "kind": "flatline",
                            "date": last_sd,
                            "flat_close": round(closes[0], 2),
                            "daily_last": round(d_last, 2),
                            "sessions": flat_n,
                        }
                    )

    summary = {
        "anomalies": anomalies,
        "symbol_count": len({a["symbol"] for a in anomalies}),
        "last_scan_at": date.today().isoformat(),
    }
    _set_summary(**summary)
    return anomalies


def _symbols_from_anomalies(anomalies: list[dict[str, Any]]) -> list[str]:
    return sorted({str(a["symbol"]).strip().upper() for a in anomalies if a.get("symbol")})


def purge_bars_4h(conn: sqlite3.Connection, symbol: str) -> int:
    from server.bars_4h import ensure_bars_4h_table

    ensure_bars_4h_table(conn)
    sym = str(symbol).strip().upper()
    cur = conn.execute("DELETE FROM bars_4h WHERE Symbol=?", (sym,))
    conn.commit()
    return int(cur.rowcount or 0)


def rebuild_bars_4h_symbol(
    conn: sqlite3.Connection,
    base_dir: Path,
    symbol: str,
    *,
    backfill: bool = True,
    log_fn: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict[str, int]:
    from server.bars_4h import build_bars_4h_for_symbols

    sym = str(symbol).strip().upper()
    if backfill:
        if log_fn:
            log_fn(f"[bars_4h_integrity] full 4H rebuild for {sym}…")
        purge_bars_4h(conn, sym)
    elif log_fn:
        log_fn(f"[bars_4h_integrity] incremental 4H refresh for {sym}…")
    return build_bars_4h_for_symbols(
        conn,
        [sym],
        base_dir,
        backfill=backfill,
        message_callback=log_fn,
        cancel_check=cancel_check,
    )


def repair_bars_4h_symbol(
    conn: sqlite3.Connection,
    base_dir: Path,
    symbol: str,
    *,
    lookback_calendar_days: int = 45,
    log_fn: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    """
    Repair one symbol: daily rescale → incremental Yahoo → full Yahoo → rescale again.
    Never blocks the chart; flags host repair queue only if still anomalous.
    """
    sym = str(symbol).strip().upper()
    steps: list[str] = []

    rescale_bars_4h_to_daily(conn, sym, lookback_calendar_days=lookback_calendar_days, log_fn=log_fn)
    steps.append("daily_rescale")
    remaining = scan_bars_4h_anomalies(
        conn, symbols=[sym], lookback_calendar_days=lookback_calendar_days
    )
    if not remaining:
        clear_4h_quarantine(conn, sym)
        return {"symbol": sym, "ok": True, "steps": steps}

    if cancel_check and cancel_check():
        return {"symbol": sym, "ok": False, "steps": steps, "cancelled": True}

    rebuild_bars_4h_symbol(
        conn, base_dir, sym, backfill=False, log_fn=log_fn, cancel_check=cancel_check
    )
    steps.append("yahoo_incremental")
    rescale_bars_4h_to_daily(conn, sym, lookback_calendar_days=lookback_calendar_days, log_fn=log_fn)
    steps.append("daily_rescale_post_incremental")
    remaining = scan_bars_4h_anomalies(
        conn, symbols=[sym], lookback_calendar_days=lookback_calendar_days
    )
    if not remaining:
        clear_4h_quarantine(conn, sym)
        return {"symbol": sym, "ok": True, "steps": steps}

    if cancel_check and cancel_check():
        return {"symbol": sym, "ok": False, "steps": steps, "cancelled": True}

    rebuild_bars_4h_symbol(
        conn, base_dir, sym, backfill=True, log_fn=log_fn, cancel_check=cancel_check
    )
    steps.append("yahoo_full")
    rescale_bars_4h_to_daily(conn, sym, lookback_calendar_days=lookback_calendar_days, log_fn=log_fn)
    steps.append("daily_rescale_post_full")
    remaining = scan_bars_4h_anomalies(
        conn, symbols=[sym], lookback_calendar_days=lookback_calendar_days
    )
    if not remaining:
        clear_4h_quarantine(conn, sym)
        if log_fn:
            log_fn(f"[bars_4h_integrity] {sym} 4H bars repaired")
        return {"symbol": sym, "ok": True, "steps": steps}

    kinds = sorted({a.get("kind", "?") for a in remaining})
    _flag_repair_pending(conn, sym, f"residual_anomaly: {','.join(kinds)}")
    if log_fn:
        log_fn(
            f"[bars_4h_integrity] {sym} still has 4H anomalies after repair "
            f"({','.join(kinds)}) — chart still served; host queue updated"
        )
    return {"symbol": sym, "ok": False, "steps": steps, "residual_kinds": kinds}


def rescan_rescale_symbol_if_needed(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    lookback_calendar_days: int = 120,
    max_passes: int = 3,
) -> bool:
    """
    On chart load: if this symbol's 4H bars mismatch daily, rescale immediately.
    Returns True when a rescale was applied.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return False
    applied = False
    for _ in range(max(1, int(max_passes))):
        hits = scan_bars_4h_anomalies(
            conn, symbols=[sym], lookback_calendar_days=lookback_calendar_days
        )
        if not hits:
            break
        rescale_bars_4h_to_daily(conn, sym, lookback_calendar_days=lookback_calendar_days)
        applied = True
    remaining = scan_bars_4h_anomalies(
        conn, symbols=[sym], lookback_calendar_days=lookback_calendar_days
    )
    if remaining:
        _flag_repair_pending(
            conn,
            sym,
            f"chart_load_residual: {','.join(sorted({h.get('kind', '?') for h in remaining}))}",
        )
    else:
        clear_4h_quarantine(conn, sym)
    return applied


def rebuild_bars_4h_after_corp_action(
    conn: sqlite3.Connection,
    base_dir: Path,
    symbol: str,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """After split/bonus daily refresh — rescale 4H to daily, then incremental Yahoo."""
    repair_bars_4h_symbol(conn, base_dir, symbol, lookback_calendar_days=60, log_fn=log_fn)
    _persist_repair_queue_snapshot(conn)


def repair_bars_4h_anomalies(
    conn: sqlite3.Connection,
    base_dir: Path,
    *,
    symbols: Optional[list[str]] = None,
    lookback_calendar_days: int = 45,
    max_symbols: int = BARS_4H_AUTO_REPAIR_CAP,
    log_fn: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    if symbols:
        to_repair = [str(s).strip().upper() for s in symbols if str(s).strip()]
    else:
        anomalies = scan_bars_4h_anomalies(
            conn, lookback_calendar_days=lookback_calendar_days
        )
        to_repair = _symbols_from_anomalies(anomalies)

    to_repair = to_repair[: max(1, int(max_symbols))]
    repaired: list[str] = []
    failed: list[dict[str, str]] = []
    pending: list[str] = []

    for sym in to_repair:
        if cancel_check and cancel_check():
            break
        try:
            outcome = repair_bars_4h_symbol(
                conn,
                base_dir,
                sym,
                lookback_calendar_days=lookback_calendar_days,
                log_fn=log_fn,
                cancel_check=cancel_check,
            )
            if outcome.get("ok"):
                repaired.append(sym)
            else:
                pending.append(sym)
                if outcome.get("cancelled"):
                    failed.append({"symbol": sym, "error": "cancelled"})
        except Exception as exc:
            failed.append({"symbol": sym, "error": type(exc).__name__})
            _flag_repair_pending(conn, sym, f"exception:{type(exc).__name__}")
            pending.append(sym)
            if log_fn:
                log_fn(f"[bars_4h_integrity] {sym} repair error: {exc}")

    _persist_repair_queue_snapshot(conn)
    result = {
        "repaired": repaired,
        "failed": failed,
        "pending_repair": pending,
        "quarantined": pending,
        "repaired_count": len(repaired),
        "failed_count": len(failed),
        "pending_repair_count": len(pending),
        "quarantined_count": len(pending),
        "last_repair_at": date.today().isoformat(),
    }
    _set_summary(
        repaired=repaired,
        failed=failed,
        pending_repair=pending,
        quarantined=pending,
        last_repair_at=result["last_repair_at"],
    )
    return result


def audit_and_repair_after_4h_build(
    conn: sqlite3.Connection,
    base_dir: Path,
    *,
    lookback_calendar_days: int = 45,
    auto_repair: bool = True,
    max_auto_repair: int = BARS_4H_AUTO_REPAIR_CAP,
    log_fn: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    anomalies = scan_bars_4h_anomalies(conn, lookback_calendar_days=lookback_calendar_days)
    sym_count = len({a["symbol"] for a in anomalies})
    if log_fn and sym_count:
        log_fn(
            f"[bars_4h_integrity] scan: {sym_count} symbol(s) with 4H scale issues "
            f"(last {lookback_calendar_days} day(s))"
        )
    repair_result = None
    if auto_repair and sym_count:
        repair_result = repair_bars_4h_anomalies(
            conn,
            base_dir,
            lookback_calendar_days=lookback_calendar_days,
            max_symbols=max_auto_repair,
            log_fn=log_fn,
            cancel_check=cancel_check,
        )
    _persist_repair_queue_snapshot(conn)
    pending = list_quarantined_symbols(conn)
    return {
        "anomaly_count": len(anomalies),
        "symbol_count": sym_count,
        "anomalies": anomalies[:50],
        "repair": repair_result,
        "pending_repair_count": len(pending),
        "quarantined_count": len(pending),
    }
