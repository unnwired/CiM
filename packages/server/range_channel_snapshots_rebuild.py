"""Precomputed range-channel pass/fail rows for canonical default params."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Callable, Optional, Sequence

from filter_rebuild_registry import RANGE_CHANNEL_CANONICAL_PARAMS
from range_channel_filter import evaluate_range_channel, normalize_range_channel_params


def canonical_params_hash(params: dict[str, Any] | None = None) -> str:
    base = dict(RANGE_CHANNEL_CANONICAL_PARAMS)
    if params:
        base.update(params)
    raw = json.dumps(base, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def filter_params_match_canonical(filter_def: dict[str, Any]) -> bool:
    norm = normalize_range_channel_params(filter_def)
    canon = normalize_range_channel_params(RANGE_CHANNEL_CANONICAL_PARAMS)
    keys = (
        "timeframe",
        "lookback_bars",
        "max_channel_width_pct",
        "macd_allowed_stragglers",
        "hist_flat_stragglers",
        "spike_ratio",
        "spike_min_delta",
    )
    return all(norm.get(k) == canon.get(k) for k in keys)


def ensure_range_channel_snapshots_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS range_channel_snapshots (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            params_hash TEXT NOT NULL,
            passes INTEGER NOT NULL,
            channel_width_pct REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, timeframe, params_hash)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_range_channel_snapshots_pass "
        "ON range_channel_snapshots(timeframe, params_hash, passes)"
    )


def _load_candles_batch(cursor, symbols: Sequence[str]) -> dict[str, list]:
    if not symbols:
        return {}
    placeholders = ",".join(["?"] * len(symbols))
    cursor.execute(
        f"SELECT Symbol, SUBSTR(Date,1,10) as dt, Open, High, Low, Close "
        f"FROM historical_data WHERE Symbol IN ({placeholders}) ORDER BY Symbol ASC, Date ASC",
        list(symbols),
    )
    out: dict[str, list] = {str(s).strip().upper(): [] for s in symbols}
    for row in cursor.fetchall():
        sym = str(row[0]).strip().upper()
        if sym in out and row[1] and row[2] is not None:
            out[sym].append((row[1], row[2], row[3], row[4], row[5]))
    return out


def rebuild_range_channel_snapshots(
    conn: sqlite3.Connection,
    *,
    timeframes: Sequence[str],
    symbols: Optional[Sequence[str]] = None,
    params: Optional[dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
) -> int:
    ensure_range_channel_snapshots_table(conn)
    cur = conn.cursor()
    eval_params = dict(RANGE_CHANNEL_CANONICAL_PARAMS)
    if params:
        eval_params.update(params)
    p_hash = canonical_params_hash(eval_params)
    tf_list = [str(t).strip().upper() for t in timeframes if str(t).strip()]
    if not tf_list:
        tf_list = [str(eval_params.get("timeframe", "3D")).strip().upper()]

    def msg(text: str) -> None:
        if message_callback:
            message_callback(text)

    if symbols is not None:
        sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
    else:
        cur.execute("SELECT symbol FROM screener ORDER BY symbol ASC")
        sym_list = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]

    if not sym_list:
        return 0

    msg(f"Rebuilding range channel snapshots ({', '.join(tf_list)}) for {len(sym_list)} symbols…")
    if symbols is None:
        for tf in tf_list:
            cur.execute(
                "DELETE FROM range_channel_snapshots WHERE timeframe = ? AND params_hash = ?",
                (tf, p_hash),
            )
        conn.commit()

    batch_size = 120
    total_rows = 0
    total_syms = len(sym_list)
    if progress_callback:
        progress_callback(0, total_syms)

    for i in range(0, total_syms, batch_size):
        batch = sym_list[i:i + batch_size]
        candles_map = _load_candles_batch(cur, batch)
        upsert_rows = []
        for sym in batch:
            daily = candles_map.get(sym, [])
            if not daily:
                continue
            for tf in tf_list:
                body = {**eval_params, "timeframe": tf}
                try:
                    passes = evaluate_range_channel(daily, body)
                except Exception:
                    passes = False
                upsert_rows.append((sym, tf, p_hash, 1 if passes else 0, None))
        if upsert_rows:
            cur.executemany(
                """
                INSERT INTO range_channel_snapshots (
                    symbol, timeframe, params_hash, passes, channel_width_pct, updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, timeframe, params_hash) DO UPDATE SET
                    passes=excluded.passes,
                    channel_width_pct=excluded.channel_width_pct,
                    updated_at=CURRENT_TIMESTAMP
                """,
                upsert_rows,
            )
            conn.commit()
            total_rows += len(upsert_rows)
        if progress_callback:
            progress_callback(min(i + len(batch), total_syms), total_syms)

    msg(f"Range channel snapshots: {total_rows} rows written.")
    return total_rows


def query_range_channel_from_snapshots(
    conn: sqlite3.Connection,
    filter_def: dict[str, Any],
    sector_symbols: Optional[set[str]] = None,
) -> Optional[list[str]]:
    if not filter_params_match_canonical(filter_def):
        return None
    norm = normalize_range_channel_params(filter_def)
    tf = str(norm["timeframe"]).strip().upper()
    p_hash = canonical_params_hash()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbol FROM range_channel_snapshots
        WHERE timeframe = ? AND params_hash = ? AND passes = 1
        ORDER BY symbol ASC
        """,
        (tf, p_hash),
    )
    results = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
    if sector_symbols is not None:
        results = [s for s in results if s in sector_symbols]
    return results
