"""Stored-only quote fields for P&L — screener + historical_data, no live overlay."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

_SCREENER_PRICE_STALE_REL_EPS = 0.0001


def _session_intraday_active() -> bool:
    try:
        from server import movers_data

        return bool(movers_data._session_day_intraday_active())
    except Exception:
        return False


def _eod_trade_date(conn: sqlite3.Connection, db_path: Optional[str] = None) -> Optional[str]:
    try:
        if db_path:
            from server import market_data_version as mdv

            ver = mdv.get_version(db_path)
            td = ver.get("eod_trade_date")
            if td:
                return str(td)[:10]
    except Exception:
        pass
    return None


def get_stored_quote_map(
    conn: sqlite3.Connection,
    symbols: list[str],
    *,
    db_path: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """
    Per-symbol stored price, 1D/1M %, market_cap, as_of_date.
    Uses the non-live branch of server._apply_live_screener_ohlc (no movers_live).
    """
    syms = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if not syms:
        return {}

    out: dict[str, dict[str, Any]] = {s: {} for s in syms}
    placeholders = ",".join("?" for _ in syms)

    # Market cap: issued_shares × price when available (stale market_cap column is not trusted).
    mc_sql = f"""
        SELECT symbol, market_cap, price, issued_shares
        FROM screener
        WHERE symbol IN ({placeholders})
    """
    mc_df = pd.read_sql_query(mc_sql, conn, params=syms)
    shares_by_sym: dict[str, float] = {}
    if not mc_df.empty:
        mc_df["symbol"] = mc_df["symbol"].astype(str).str.strip().str.upper()
        for _, row in mc_df.iterrows():
            sym = row["symbol"]
            if sym not in out:
                continue
            shares = row.get("issued_shares")
            px = row.get("price")
            mc = None
            try:
                if shares is not None and pd.notna(shares) and px is not None and pd.notna(px):
                    sh = float(shares)
                    p = float(px)
                    if sh > 0 and p > 0:
                        mc = round(sh * p, 0)
            except (TypeError, ValueError):
                mc = None
            if mc is None:
                mc = row.get("market_cap")
            if mc is not None and pd.notna(mc):
                out[sym]["market_cap"] = round(float(mc), 0)
            sh = row.get("issued_shares")
            if sh is not None and pd.notna(sh):
                try:
                    fv = float(sh)
                    if fv > 0:
                        shares_by_sym[sym] = fv
                except (TypeError, ValueError):
                    pass

    session_intraday = _session_intraday_active()
    today_s = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    eps = _SCREENER_PRICE_STALE_REL_EPS

    sym_filter = f"AND s.symbol IN ({placeholders})"

    if session_intraday and today_s:
        day_chg_sql = f"""
            SELECT s.symbol AS symbol,
              CASE
                WHEN substr((SELECT MAX(Date) FROM historical_data h WHERE h.Symbol = s.symbol), 1, 10) < '{today_s}'
                     AND s.price IS NOT NULL AND s.price > 0
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) IS NOT NULL
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) > 0
                     AND ABS(
                       s.price - (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                     ) > (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) * {eps}
                THEN ROUND((
                  s.price
                  - (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                ) / (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) * 100, 2)
                ELSE ROUND((
                  (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                  - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = s.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
                ) / NULLIF((
                  SELECT Close FROM historical_data h3 WHERE h3.Symbol = s.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
                ), 0) * 100, 2)
              END AS day_chg_pct,
              CASE
                WHEN substr((SELECT MAX(Date) FROM historical_data h WHERE h.Symbol = s.symbol), 1, 10) < '{today_s}'
                     AND s.price IS NOT NULL AND s.price > 0
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) IS NOT NULL
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) > 0
                     AND ABS(
                       s.price - (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                     ) > (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) * {eps}
                THEN ROUND(s.price, 2)
                ELSE (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
              END AS display_price,
              substr((SELECT MAX(Date) FROM historical_data h WHERE h.Symbol = s.symbol), 1, 10) AS bar_date
            FROM screener s
            WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = s.symbol)
            {sym_filter}
        """
        day_chg = pd.read_sql_query(day_chg_sql, conn, params=syms)
    else:
        day_chg_sql = f"""
            SELECT s.symbol AS symbol,
              ROUND((
                (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = s.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
              ) / NULLIF((
                SELECT Close FROM historical_data h3 WHERE h3.Symbol = s.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
              ), 0) * 100, 2) AS day_chg_pct,
              (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) AS display_price,
              substr((SELECT MAX(Date) FROM historical_data h WHERE h.Symbol = s.symbol), 1, 10) AS bar_date
            FROM screener s
            WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = s.symbol)
            {sym_filter}
        """
        day_chg = pd.read_sql_query(day_chg_sql, conn, params=syms)

    if not day_chg.empty:
        for _, row in day_chg.iterrows():
            sym = str(row["symbol"]).strip().upper()
            if sym not in out:
                continue
            px = row.get("display_price")
            ch = row.get("day_chg_pct")
            bd = row.get("bar_date")
            if px is not None and pd.notna(px):
                out[sym]["price"] = round(float(px), 2)
            if ch is not None and pd.notna(ch):
                out[sym]["change_1d"] = round(float(ch), 2)
            if bd is not None and pd.notna(bd):
                out[sym]["as_of_date"] = str(bd)[:10]

    month_chg_sql = f"""
        SELECT s.symbol AS symbol,
          ROUND((
            (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
            - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = s.symbol AND SUBSTR(h2.Date,1,7) <
               SUBSTR((SELECT MAX(Date) FROM historical_data h3 WHERE h3.Symbol = s.symbol),1,7)
               ORDER BY h2.Date DESC LIMIT 1)
          ) / NULLIF((
            SELECT Close FROM historical_data h4 WHERE h4.Symbol = s.symbol AND SUBSTR(h4.Date,1,7) <
               SUBSTR((SELECT MAX(Date) FROM historical_data h5 WHERE h5.Symbol = s.symbol),1,7)
               ORDER BY h4.Date DESC LIMIT 1
          ), 0) * 100, 2) AS month_chg_pct
        FROM screener s
        WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = s.symbol)
        {sym_filter}
    """
    month_chg = pd.read_sql_query(month_chg_sql, conn, params=syms)
    if not month_chg.empty:
        for _, row in month_chg.iterrows():
            sym = str(row["symbol"]).strip().upper()
            if sym not in out:
                continue
            m = row.get("month_chg_pct")
            if m is not None and pd.notna(m):
                out[sym]["change_1m"] = round(float(m), 2)

    eod = _eod_trade_date(conn, db_path)
    for sym in syms:
        if "as_of_date" not in out[sym] and eod:
            out[sym]["as_of_date"] = eod
        sh = shares_by_sym.get(sym)
        px = out[sym].get("price")
        if sh and px is not None:
            try:
                p = float(px)
                if p > 0:
                    out[sym]["market_cap"] = round(sh * p, 0)
            except (TypeError, ValueError):
                pass

    return out
