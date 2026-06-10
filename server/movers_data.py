"""
Market movers: day change, volume, volume surge, and 20-day RVOL from historical_data.

On an NSE session day, when the latest DB bar is still yesterday, ranks use today's
price / change (screener or live overlay) vs the prior session close — not Thu vs Wed.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
SESSION_FINAL_IST = dtime(16, 0)
# screener.price often equals yesterday's close on cold start — treat as stale (use 2-bar hist).
SCREENER_PRICE_STALE_REL_EPS = 0.0001
_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "data" / "nse_calendar.json"
_calendar_cache: Optional[dict[str, set[str]]] = None

# Injected from server after import (avoids circular import).
_MCAP_SQL = """
CASE
  WHEN issued_shares IS NOT NULL AND price IS NOT NULL AND price > 0
  THEN CAST(issued_shares AS REAL) * price
  ELSE market_cap
END
""".strip()

# Prefer latest OHLC close for movers (matches displayed price column).
def configure_paths(*, data_dir: Path) -> None:
    """Encrypted runtime may load this module from app-cache; data stays in install root."""
    global _CALENDAR_PATH, _calendar_cache
    _CALENDAR_PATH = Path(data_dir) / "nse_calendar.json"
    _calendar_cache = None


_MOVERS_MCAP_SQL = """
CASE
  WHEN s.issued_shares IS NOT NULL AND lt.close_latest IS NOT NULL AND lt.close_latest > 0
  THEN CAST(s.issued_shares AS REAL) * lt.close_latest
  WHEN s.issued_shares IS NOT NULL AND s.price IS NOT NULL AND s.price > 0
  THEN CAST(s.issued_shares AS REAL) * s.price
  ELSE s.market_cap
END
""".strip()


def _movers_mcap_expr() -> str:
    return _MOVERS_MCAP_SQL.replace("\n", " ")


def _movers_base_sql() -> str:
    return f"""
    WITH ranked AS (
        SELECT
            Symbol,
            Date,
            Close,
            Volume,
            ROW_NUMBER() OVER (PARTITION BY Symbol ORDER BY Date DESC) AS rn
        FROM historical_data
    ),
    last_two AS (
        SELECT
            Symbol AS symbol,
            MAX(CASE WHEN rn = 1 THEN Date END) AS as_of_date,
            MAX(CASE WHEN rn = 1 THEN Close END) AS close_latest,
            MAX(CASE WHEN rn = 2 THEN Close END) AS close_prior,
            MAX(CASE WHEN rn = 1 THEN Volume END) AS volume_today,
            MAX(CASE WHEN rn = 2 THEN Volume END) AS volume_prior
        FROM ranked
        WHERE rn <= 2
        GROUP BY Symbol
    ),
    avg20 AS (
        SELECT Symbol AS symbol, AVG(Volume) AS avg_volume_20d
        FROM ranked
        WHERE rn <= 20 AND Volume IS NOT NULL
        GROUP BY Symbol
    )
    SELECT
        s.symbol AS symbol,
        lt.as_of_date AS as_of_date,
        lt.close_latest AS eod_close,
        lt.close_prior AS eod_prev_close,
        lt.close_latest AS price,
        s.price AS screener_price,
        s.change_percent AS screener_change_pct,
        CASE
            WHEN lt.close_prior IS NOT NULL AND lt.close_prior > 0 AND lt.close_latest IS NOT NULL
            THEN ROUND((lt.close_latest - lt.close_prior) / lt.close_prior * 100.0, 2)
            ELSE s.change_percent
        END AS change_pct,
        ({_movers_mcap_expr()}) AS market_cap,
        s.pe AS pe,
        s.issued_shares AS issued_shares,
        s.nse_sector AS nse_sector,
        s.nse_industry AS nse_industry,
        lt.volume_today AS volume_today,
        lt.volume_prior AS volume_prior,
        CASE
            WHEN lt.volume_prior IS NOT NULL AND lt.volume_prior > 0 AND lt.volume_today IS NOT NULL
            THEN ROUND((lt.volume_today - lt.volume_prior) / lt.volume_prior * 100.0, 2)
            ELSE NULL
        END AS volume_change_pct,
        a.avg_volume_20d AS avg_volume_20d,
        CASE
            WHEN a.avg_volume_20d IS NOT NULL AND a.avg_volume_20d > 0 AND lt.volume_today IS NOT NULL
            THEN ROUND(CAST(lt.volume_today AS REAL) / a.avg_volume_20d, 2)
            ELSE NULL
        END AS rvol_20d
    FROM screener s
    LEFT JOIN last_two lt ON UPPER(TRIM(lt.symbol)) = UPPER(TRIM(s.symbol))
    LEFT JOIN avg20 a ON UPPER(TRIM(a.symbol)) = UPPER(TRIM(s.symbol))
    """


def load_movers_universe(conn, mcap_sql: str) -> pd.DataFrame:
    global _MCAP_SQL
    if mcap_sql:
        _MCAP_SQL = mcap_sql.strip()
    sql = _movers_base_sql()
    df = pd.read_sql_query(sql, conn)
    if df.empty:
        return df
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    for col in (
        "price",
        "change_pct",
        "market_cap",
        "pe",
        "volume_today",
        "volume_prior",
        "volume_change_pct",
        "avg_volume_20d",
        "rvol_20d",
        "issued_shares",
        "eod_close",
        "eod_prev_close",
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _finite_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def _load_nse_calendar() -> dict[str, set[str]]:
    global _calendar_cache
    if _calendar_cache is not None:
        return _calendar_cache
    default: dict[str, set[str]] = {"holidays": set(), "special_sessions": set()}
    try:
        with open(_CALENDAR_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        _calendar_cache = {
            "holidays": {str(x) for x in (raw.get("holidays") or []) if x},
            "special_sessions": {str(x) for x in (raw.get("special_sessions") or []) if x},
        }
    except Exception:
        _calendar_cache = default
    return _calendar_cache


def _is_nse_session_day(d: date) -> bool:
    cal = _load_nse_calendar()
    ds = d.strftime("%Y-%m-%d")
    w = d.weekday()
    if w < 5:
        return ds not in cal["holidays"]
    return ds in cal["special_sessions"]


def _session_day_intraday_active() -> bool:
    """Session day before 16:00 IST — movers should reflect today vs prior close."""
    now = datetime.now(IST)
    if not _is_nse_session_day(now.date()):
        return False
    return now.time() < SESSION_FINAL_IST


def _parse_as_of_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def screener_price_moved_materially(price: float, reference_close: float) -> bool:
    """True when screener price differs materially from the prior session close."""
    px = _finite_or_none(price)
    ref = _finite_or_none(reference_close)
    if px is None or ref is None or ref <= 0:
        return False
    return abs(px - ref) > ref * SCREENER_PRICE_STALE_REL_EPS


def should_apply_live_day_change(
    existing_chg: Optional[float],
    live_chg: Optional[float],
) -> bool:
    """Avoid clobbering a real historical % with a stale live or screener 0 on startup."""
    if live_chg is None:
        return False
    if existing_chg is None:
        return True
    try:
        ex = float(existing_chg)
        lv = float(live_chg)
    except (TypeError, ValueError):
        return True
    if abs(lv) < 0.005 and abs(ex) > 0.05:
        return False
    return True


def apply_session_day_adjustment(df: pd.DataFrame) -> pd.DataFrame:
    """
    When historical_data's latest bar is before today, use screener price vs the last
    stored close only when it differs materially; otherwise keep the two-bar historical %.
    """
    if df.empty or not _session_day_intraday_active():
        return df
    today = datetime.now(IST).date()
    today_s = today.strftime("%Y-%m-%d")
    out = df.copy()
    for idx, row in out.iterrows():
        as_of = _parse_as_of_date(row.get("as_of_date"))
        if as_of is not None and as_of >= today:
            continue
        ref = _finite_or_none(row.get("eod_close"))
        if ref is None or ref <= 0:
            continue
        hist_chg = _finite_or_none(row.get("change_pct"))
        px = _finite_or_none(row.get("screener_price"))
        chg = _finite_or_none(row.get("screener_change_pct"))
        if px is not None and px > 0 and screener_price_moved_materially(px, ref):
            out.at[idx, "price"] = round(px, 2)
            out.at[idx, "change_pct"] = round((px - ref) / ref * 100.0, 2)
            out.at[idx, "as_of_date"] = today_s
        elif chg is not None and should_apply_live_day_change(hist_chg, chg):
            out.at[idx, "change_pct"] = round(chg, 2)
            if px is not None and px > 0:
                out.at[idx, "price"] = round(px, 2)
            out.at[idx, "as_of_date"] = today_s
    return out


def filter_day_change_by_side(df: pd.DataFrame, side: str) -> pd.DataFrame:
    """Gainers: strictly positive %; losers: strictly negative % (exclude flat zeros)."""
    side_n = (side or "gainers").strip().lower()
    if side_n == "losers":
        return df[df["change_pct"] < 0]
    return df[df["change_pct"] > 0]


def _apply_mcap_filter(df: pd.DataFrame, min_mcap: Optional[float], max_mcap: Optional[float]) -> pd.DataFrame:
    out = df
    if min_mcap is not None:
        out = out[out["market_cap"].notna() & (out["market_cap"] >= float(min_mcap))]
    if max_mcap is not None:
        out = out[out["market_cap"].notna() & (out["market_cap"] <= float(max_mcap))]
    return out


def _apply_sector_filter(df: pd.DataFrame, allowed: Optional[set]) -> pd.DataFrame:
    if not allowed:
        return df
    return df[df["symbol"].isin(allowed)]


def _row_to_dict(row: pd.Series, rank: int) -> dict[str, Any]:
    def _f(v):
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return None
        return v

    return {
        "rank": rank,
        "symbol": row["symbol"],
        "price": _f(row.get("price")),
        "change_pct": _f(row.get("change_pct")),
        "market_cap": _f(row.get("market_cap")),
        "pe": _f(row.get("pe")),
        "volume": _f(row.get("volume_today")),
        "volume_prior": _f(row.get("volume_prior")),
        "volume_change_pct": _f(row.get("volume_change_pct")),
        "avg_volume_20d": _f(row.get("avg_volume_20d")),
        "rvol_20d": _f(row.get("rvol_20d")),
        "as_of_date": row.get("as_of_date"),
    }


def query_day_change(
    conn,
    *,
    mcap_sql: str,
    side: str,
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
    allowed_symbols: Optional[set],
) -> dict[str, Any]:
    df = load_movers_universe(conn, mcap_sql)
    df = apply_session_day_adjustment(df)
    df = _apply_mcap_filter(df, min_mcap, max_mcap)
    df = _apply_sector_filter(df, allowed_symbols)
    df = df[df["change_pct"].notna()]
    df = filter_day_change_by_side(df, side)
    ascending = side == "losers"
    df = df.sort_values("change_pct", ascending=ascending, na_position="last")
    top = df.head(limit)
    as_of = None
    if "as_of_date" in top.columns and top["as_of_date"].notna().any():
        as_of = str(top["as_of_date"].dropna().iloc[0])
    rows = [_row_to_dict(top.iloc[i], i + 1) for i in range(len(top))]
    return {
        "mode": "day_change",
        "side": side,
        "limit": limit,
        "as_of_date": as_of,
        "count": len(rows),
        "data": rows,
    }


def query_volume(
    conn,
    *,
    mcap_sql: str,
    volume_mode: str,
    limit: int,
    min_mcap: Optional[float],
    max_mcap: Optional[float],
    allowed_symbols: Optional[set],
) -> dict[str, Any]:
    df = load_movers_universe(conn, mcap_sql)
    df = apply_session_day_adjustment(df)
    df = _apply_mcap_filter(df, min_mcap, max_mcap)
    df = _apply_sector_filter(df, allowed_symbols)

    mode = (volume_mode or "absolute").strip().lower()
    if mode == "surge":
        df = df[df["volume_change_pct"].notna()]
        sort_col = "volume_change_pct"
        ascending = False
    elif mode == "rvol":
        df = df[df["rvol_20d"].notna()]
        sort_col = "rvol_20d"
        ascending = False
    else:
        df = df[df["volume_today"].notna()]
        sort_col = "volume_today"
        ascending = False
        mode = "absolute"

    df = df.sort_values(sort_col, ascending=ascending, na_position="last")
    top = df.head(limit)
    as_of = None
    if "as_of_date" in top.columns and top["as_of_date"].notna().any():
        as_of = str(top["as_of_date"].dropna().iloc[0])
    rows = [_row_to_dict(top.iloc[i], i + 1) for i in range(len(top))]
    return {
        "mode": "volume",
        "volume_mode": mode,
        "limit": limit,
        "as_of_date": as_of,
        "count": len(rows),
        "data": rows,
    }


def movers_meta(conn, mcap_sql: str) -> dict[str, Any]:
    df = load_movers_universe(conn, mcap_sql)
    df = apply_session_day_adjustment(df)
    with_vol = int(df["volume_today"].notna().sum()) if not df.empty else 0
    with_chg = int(df["change_pct"].notna().sum()) if not df.empty else 0
    as_of = None
    if "as_of_date" in df.columns:
        ser = df["as_of_date"].dropna()
        if not ser.empty:
            as_of = str(ser.iloc[0])
    return {
        "total_symbols": len(df),
        "with_volume": with_vol,
        "with_change_pct": with_chg,
        "as_of_date": as_of,
        "note": (
            "Session day: today vs prior close when the latest DB bar is before today; "
            "otherwise last two daily bars from historical_data."
        ),
        "session_intraday": _session_day_intraday_active(),
    }
