"""Orchestrate selective filter-data rebuild from registry keys."""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from filter_rebuild_registry import (
    INDICATOR_FAMILIES,
    SNAPSHOT_TIMEFRAME_OPTIONS,
    indicator_families_for_keys,
    keys_for_engine,
    normalize_snapshot_timeframe,
    resolve_keys,
)
from range_channel_snapshots_rebuild import rebuild_range_channel_snapshots
from volume_stats_rebuild import rebuild_volume_stats_universe


def _resolve_incremental_symbols(conn, days_back: int) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT Symbol FROM historical_data WHERE Date >= date('now', ?) ORDER BY Symbol ASC",
        (f"-{max(0, int(days_back))} day",),
    )
    return [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]


def _default_timeframes_for_keys(keys: list[str]) -> tuple[str, ...]:
    if any(k in keys for k in ("price_ohlc", "ema", "macd", "stochrsi")):
        return tuple(SNAPSHOT_TIMEFRAME_OPTIONS)
    return tuple()


def run_filter_rebuild(
    *,
    keys: Sequence[str],
    mode: str = "full",
    timeframes: Optional[Sequence[str]] = None,
    days_back: int = 1,
    get_db_connection: Callable[[], Any],
    load_scrape_daily_module: Callable[[], Any],
    set_job: Callable[..., None],
    finish_job: Callable[[str], None],
    fail_job: Callable[[str], None],
    invalidate_filter_cache: Callable[[], None],
    job_state: dict,
) -> None:
    """Background worker: rebuild only selected registry keys."""
    key_list = [str(k).strip().lower() for k in (keys or []) if str(k).strip()]
    if not key_list:
        fail_job("No filter rebuild keys selected.")
        return

    entries = resolve_keys(key_list)
    if not entries:
        fail_job("No valid filter rebuild keys.")
        return

    mode_norm = str(mode or "full").strip().lower()
    incremental = mode_norm == "incremental"
    vol_keys = keys_for_engine(key_list, "volume_stats")
    range_keys = keys_for_engine(key_list, "range_channel_snapshots")
    snap_keys = keys_for_engine(key_list, "indicator_snapshots")
    families = indicator_families_for_keys(snap_keys)

    tf_input = [
        normalize_snapshot_timeframe(t)
        for t in (timeframes or [])
        if str(t).strip()
    ]
    tf_input = [t for t in tf_input if t]
    if snap_keys and not tf_input:
        tf_input = list(_default_timeframes_for_keys(snap_keys))
    if range_keys and not tf_input:
        tf_input = ["3D"]

    snap_tfs = tuple(tf_input) if snap_keys else tuple()
    range_tfs = tuple(tf_input) if range_keys else tuple()

    job_state["meta"] = {
        "scope": mode_norm,
        "mode": mode_norm,
        "keys": key_list,
        "timeframes_requested": list(tf_input),
        "families": sorted(families),
    }

    # Cooperative cancellation: the progress/message callbacks are the safe points
    # where a pending cancel is noticed and JobCancelled is raised. The rebuild
    # engines call these per batch, so cancel interrupts mid-phase rather than
    # only between phases.
    from server.admin_job_control import JobCancelled, raise_if_cancelled

    def on_msg(msg: str) -> None:
        raise_if_cancelled()
        job_state["message"] = msg

    def on_prog(done: int, total: int) -> None:
        raise_if_cancelled()
        job_state["progress"] = int(done)
        job_state["total"] = max(int(total), 1)

    conn = None
    try:
        raise_if_cancelled()
        conn = get_db_connection()
        symbols_override = None
        if incremental:
            symbols_override = _resolve_incremental_symbols(conn, days_back)
            if not symbols_override and not (vol_keys or range_keys or snap_keys):
                conn.close()
                finish_job("No recently changed symbols; incremental rebuild skipped.")
                return
            on_msg(
                f"Incremental rebuild for {len(symbols_override or [])} recently changed symbol(s)…"
            )

        raise_if_cancelled()
        if vol_keys:
            on_msg("Rebuilding average volume stats…")
            rebuild_volume_stats_universe(
                conn,
                symbols=symbols_override if incremental else None,
                progress_callback=on_prog,
                message_callback=on_msg,
            )

        raise_if_cancelled()
        if range_keys:
            on_msg(f"Rebuilding range channel snapshots ({', '.join(range_tfs or ('3D',))})…")
            rebuild_range_channel_snapshots(
                conn,
                timeframes=range_tfs or ("3D",),
                symbols=symbols_override if incremental else None,
                progress_callback=on_prog,
                message_callback=on_msg,
            )

        raise_if_cancelled()
        if snap_keys:
            mod = load_scrape_daily_module()
            fam_list = sorted(families) if families else sorted(INDICATOR_FAMILIES)
            on_msg(
                f"Rebuilding indicator snapshots ({', '.join(fam_list)}) "
                f"for {', '.join(snap_tfs) or 'default timeframes'}…"
            )
            clear_first = (
                not incremental
                and families >= INDICATOR_FAMILIES
                and not symbols_override
            )
            n = mod.rebuild_indicator_snapshots_universe(
                clear_first=clear_first,
                symbols_override=symbols_override,
                timeframes_override=snap_tfs or None,
                families_override=families if families else None,
                progress_callback=on_prog,
                message_callback=on_msg,
            )
            job_state["meta"]["symbols_recomputed"] = n

        conn.close()
        conn = None
        invalidate_filter_cache()
        labels = ", ".join(e["label"] for e in entries)
        finish_job(f"Filter rebuild completed: {labels}.")
    except JobCancelled:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise
    except Exception as exc:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        fail_job(str(exc))
