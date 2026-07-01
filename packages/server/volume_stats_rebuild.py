"""Precomputed average daily volume stats for fast avg_volume filter."""
from __future__ import annotations

import sqlite3
from typing import Callable, Optional, Sequence

from filter_rebuild_registry import VOLUME_STATS_PERIODS


def ensure_symbol_volume_stats_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS symbol_volume_stats (
            symbol TEXT NOT NULL PRIMARY KEY,
            avg_volume_10 REAL,
            avg_volume_20 REAL,
            avg_volume_30 REAL,
            as_of_date TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_symbol_volume_stats_avg20 "
        "ON symbol_volume_stats(avg_volume_20)"
    )


def _volume_stats_sql(max_period: int = 30) -> str:
    return f"""
    WITH ranked AS (
        SELECT
            UPPER(TRIM(Symbol)) AS symbol,
            SUBSTR(Date, 1, 10) AS dt,
            Volume,
            ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(Symbol)) ORDER BY Date DESC) AS rn
        FROM historical_data
        WHERE Volume IS NOT NULL AND Volume > 0
    ),
    agg AS (
        SELECT
            symbol,
            MAX(CASE WHEN rn = 1 THEN dt END) AS as_of_date,
            AVG(CASE WHEN rn <= 10 THEN Volume END) AS avg_volume_10,
            AVG(CASE WHEN rn <= 20 THEN Volume END) AS avg_volume_20,
            AVG(CASE WHEN rn <= 30 THEN Volume END) AS avg_volume_30
        FROM ranked
        WHERE rn <= {int(max_period)}
        GROUP BY symbol
    )
    SELECT symbol, avg_volume_10, avg_volume_20, avg_volume_30, as_of_date
    FROM agg
    """


def rebuild_volume_stats_universe(
    conn: sqlite3.Connection,
    *,
    symbols: Optional[Sequence[str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
) -> int:
    ensure_symbol_volume_stats_table(conn)
    cur = conn.cursor()

    def msg(text: str) -> None:
        if message_callback:
            message_callback(text)

    if symbols is not None:
        sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not sym_list:
            return 0
        msg(f"Rebuilding volume stats for {len(sym_list)} symbol(s)…")
        placeholders = ",".join(["?"] * len(sym_list))
        cur.execute(
            f"DELETE FROM symbol_volume_stats WHERE symbol IN ({placeholders})",
            sym_list,
        )
        base_sql = _volume_stats_sql()
        cur.execute(
            f"SELECT * FROM ({base_sql}) WHERE symbol IN ({placeholders})",
            sym_list,
        )
        rows = cur.fetchall()
        if progress_callback:
            progress_callback(0, max(len(rows), 1))
        cur.executemany(
            """
            INSERT INTO symbol_volume_stats (
                symbol, avg_volume_10, avg_volume_20, avg_volume_30, as_of_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                avg_volume_10=excluded.avg_volume_10,
                avg_volume_20=excluded.avg_volume_20,
                avg_volume_30=excluded.avg_volume_30,
                as_of_date=excluded.as_of_date,
                updated_at=CURRENT_TIMESTAMP
            """,
            rows,
        )
        conn.commit()
        if progress_callback:
            progress_callback(len(rows), max(len(rows), 1))
        return len(rows)

    msg("Rebuilding volume stats for full universe…")
    cur.execute("DELETE FROM symbol_volume_stats")
    conn.commit()
    cur.execute(_volume_stats_sql())
    rows = cur.fetchall()
    total = len(rows)
    if progress_callback:
        progress_callback(0, max(total, 1))
    batch = 500
    for i in range(0, total, batch):
        chunk = rows[i:i + batch]
        cur.executemany(
            """
            INSERT INTO symbol_volume_stats (
                symbol, avg_volume_10, avg_volume_20, avg_volume_30, as_of_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            chunk,
        )
        conn.commit()
        if progress_callback:
            progress_callback(min(i + len(chunk), total), max(total, 1))
    msg(f"Volume stats rebuilt for {total} symbols.")
    return total


def avg_volume_column_for_period(period: int) -> Optional[str]:
    if period == 10:
        return "avg_volume_10"
    if period == 20:
        return "avg_volume_20"
    if period == 30:
        return "avg_volume_30"
    return None


def query_avg_volume_from_stats(
    conn: sqlite3.Connection,
    filter_def: dict,
    sector_symbols: Optional[set[str]] = None,
) -> Optional[list[str]]:
    from avg_volume_filter import normalize_avg_volume_params

    params = normalize_avg_volume_params(filter_def)
    period = params["period"]
    col = avg_volume_column_for_period(period)
    if col is None:
        return None
    min_v = params["min_volume"]
    max_v = params["max_volume"]
    condition = params["condition"]
    if min_v is None and max_v is None:
        return None

    having: list[str] = [f"{col} IS NOT NULL"]
    args: list[float] = []
    if min_v is not None and condition in ("above", "above_eq"):
        op = ">=" if condition == "above_eq" else ">"
        having.append(f"{col} {op} ?")
        args.append(float(min_v))
    elif max_v is not None:
        op = "<=" if condition == "below_eq" else "<"
        having.append(f"{col} {op} ?")
        args.append(float(max_v))
    elif min_v is not None:
        op = ">" if condition == "above" else ">="
        having.append(f"{col} {op} ?")
        args.append(float(min_v))

    sql = f"SELECT symbol FROM symbol_volume_stats WHERE {' AND '.join(having)} ORDER BY {col} DESC"
    cur = conn.cursor()
    cur.execute(sql, args)
    results = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
    if sector_symbols is not None:
        results = [s for s in results if s in sector_symbols]
    return results
