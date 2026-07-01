"""Average daily share-volume filter from historical_data."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional, Set


def normalize_avg_volume_params(filter_def: dict[str, Any]) -> dict[str, Any]:
    period = max(1, min(60, int(filter_def.get("period", 10) or 10)))
    condition = str(filter_def.get("condition", "above") or "above").strip().lower()
    if condition not in ("above", "above_eq", "below", "below_eq"):
        condition = "above"
    min_volume = filter_def.get("min_volume")
    max_volume = filter_def.get("max_volume")
    min_v = float(min_volume) if min_volume is not None and min_volume != "" else None
    max_v = float(max_volume) if max_volume is not None and max_volume != "" else None
    return {
        "period": period,
        "condition": condition,
        "min_volume": min_v,
        "max_volume": max_v,
    }


def query_avg_volume_symbols(
    conn: sqlite3.Connection,
    filter_def: dict[str, Any],
    sector_symbols: Optional[Set[str]] = None,
) -> list[str]:
    params = normalize_avg_volume_params(filter_def)
    period = params["period"]
    min_v = params["min_volume"]
    max_v = params["max_volume"]
    condition = params["condition"]

    if min_v is None and max_v is None:
        raise ValueError("Provide at least min_volume or max_volume")

    having_parts: list[str] = []
    having_params: list[float] = []
    if min_v is not None:
        if condition in ("above", "above_eq"):
            op = ">=" if condition == "above_eq" else ">"
            having_parts.append(f"avg_volume {op} ?")
            having_params.append(min_v)
    if max_v is not None:
        if condition in ("below", "below_eq"):
            op = "<=" if condition == "below_eq" else "<"
            having_parts.append(f"avg_volume {op} ?")
            having_params.append(max_v)
        elif min_v is not None and condition in ("above", "above_eq"):
            pass
        elif max_v is not None and min_v is None:
            having_parts.append("avg_volume <= ?")
            having_params.append(max_v)

    if not having_parts:
        if min_v is not None:
            op = ">=" if condition == "above_eq" else ">"
            having_parts.append(f"avg_volume {op} ?")
            having_params.append(min_v)
        elif max_v is not None:
            op = "<=" if condition == "below_eq" else "<"
            having_parts.append(f"avg_volume {op} ?")
            having_params.append(max_v)

    having_sql = " AND ".join(having_parts)
    sql = f"""
    WITH ranked AS (
        SELECT
            UPPER(TRIM(Symbol)) AS symbol,
            Volume,
            ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(Symbol)) ORDER BY Date DESC) AS rn
        FROM historical_data
        WHERE Volume IS NOT NULL AND Volume > 0
    ),
    avg_v AS (
        SELECT symbol, AVG(Volume) AS avg_volume
        FROM ranked
        WHERE rn <= ?
        GROUP BY symbol
        HAVING {having_sql}
    )
    SELECT symbol FROM avg_v ORDER BY avg_volume DESC
    """
    cur = conn.cursor()
    cur.execute(sql, [period, *having_params])
    results = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
    if sector_symbols is not None:
        results = [s for s in results if s in sector_symbols]
    return results
