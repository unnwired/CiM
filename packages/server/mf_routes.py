"""HTTP routes for AMFI mutual funds (daily NAV catalog + chart + favorites)."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Query, Request

from server import mf_favorites_store as fav_store
from server import mf_nav

router = APIRouter(tags=["mf"])

_base_dir: Optional[Path] = None
_db_path: Optional[Path] = None
_resolve_session = None


def configure(
    *,
    base_dir: Path,
    db_path: Path,
    resolve_session=None,
) -> None:
    global _base_dir, _db_path, _resolve_session
    _base_dir = Path(base_dir)
    _db_path = Path(db_path)
    _resolve_session = resolve_session


def _conn() -> sqlite3.Connection:
    if _db_path is None:
        raise HTTPException(status_code=503, detail="MF store not configured")
    conn = sqlite3.connect(str(_db_path), timeout=30.0)
    mf_nav.setup_db(conn)
    return conn


def _session(request: Request):
    if _resolve_session is None:
        return None
    return _resolve_session(request)


@router.get("/api/mf/categories")
def mf_categories(all_plans: int = Query(0)):
    try:
        conn = _conn()
        try:
            if int(all_plans):
                cur = conn.execute(
                    """
                    SELECT category, COUNT(*) AS n
                    FROM mf_schemes
                    GROUP BY category
                    ORDER BY n DESC, category ASC
                    """
                )
            else:
                cur = conn.execute(
                    """
                    SELECT category, COUNT(*) AS n
                    FROM mf_schemes
                    WHERE plan_kind = 'direct_growth'
                    GROUP BY category
                    ORDER BY n DESC, category ASC
                    """
                )
            rows = [{"category": r[0], "count": int(r[1])} for r in cur.fetchall()]
        finally:
            conn.close()
        return {"data": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/mf/schemes")
def mf_schemes(
    request: Request,
    q: str = Query(""),
    category: str = Query(""),
    favorites_only: int = Query(0),
    all_plans: int = Query(0),
    limit: int = Query(2000),
):
    try:
        fav: set[str] = set()
        if _base_dir is not None:
            fav = set(fav_store.load_favorites(_base_dir, session=_session(request)))

        conn = _conn()
        try:
            sql = [
                "SELECT scheme_code, scheme_name, amc, category, isin, plan_kind,",
                "       last_nav, nav_date, updated_at",
                "FROM mf_schemes WHERE 1=1",
            ]
            params: list[Any] = []
            if not int(all_plans):
                sql.append("AND plan_kind = 'direct_growth'")
            cat = (category or "").strip()
            if cat:
                sql.append("AND category = ?")
                params.append(cat)
            query = (q or "").strip().lower()
            if query:
                sql.append("AND (lower(scheme_name) LIKE ? OR lower(amc) LIKE ? OR scheme_code LIKE ?)")
                like = f"%{query}%"
                params.extend([like, like, f"%{query}%"])
            if int(favorites_only) and fav:
                placeholders = ",".join("?" for _ in fav)
                sql.append(f"AND scheme_code IN ({placeholders})")
                params.extend(sorted(fav))
            elif int(favorites_only):
                return {"data": [], "favorites": []}
            sql.append("ORDER BY scheme_name ASC LIMIT ?")
            lim = max(1, min(int(limit or 2000), 5000))
            params.append(lim)
            cur = conn.execute(" ".join(sql), params)
            out = []
            for r in cur.fetchall():
                code = str(r[0])
                out.append(
                    {
                        "scheme_code": code,
                        "scheme_name": r[1],
                        "amc": r[2],
                        "category": r[3],
                        "isin": r[4],
                        "plan_kind": r[5],
                        "last_nav": r[6],
                        "nav_date": r[7],
                        "updated_at": r[8],
                        "favorite": code in fav,
                    }
                )
        finally:
            conn.close()
        return {"data": out, "favorites": sorted(fav)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/mf/favorites")
def get_mf_favorites(request: Request):
    if _base_dir is None:
        raise HTTPException(status_code=503, detail="MF store not configured")
    codes = fav_store.load_favorites(_base_dir, session=_session(request))
    return {"scheme_codes": codes}


@router.put("/api/mf/favorites")
def put_mf_favorites(request: Request, payload: dict = Body(...)):
    if _base_dir is None:
        raise HTTPException(status_code=503, detail="MF store not configured")
    try:
        codes = fav_store.save_favorites(
            _base_dir,
            (payload or {}).get("scheme_codes"),
            session=_session(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"scheme_codes": codes, "status": "saved"}


@router.get("/api/mf/nav/{scheme_code}")
def mf_nav_chart(
    scheme_code: str,
    timeframe: str = Query("1D"),
    ema1: Optional[int] = Query(None),
    ema2: Optional[int] = Query(None),
    ema3: Optional[int] = Query(None),
    ema4: Optional[int] = Query(None),
):
    from server import server as srv

    code = str(scheme_code or "").strip()
    if not code.isdigit():
        raise HTTPException(status_code=400, detail="Invalid scheme code")
    if timeframe == "4H":
        raise HTTPException(status_code=400, detail="Mutual fund charts are daily NAV only (no 4H)")
    if timeframe not in srv.TIMEFRAME_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe: {timeframe}")

    ema_periods = [p for p in [ema1, ema2, ema3, ema4] if p is not None]

    try:
        conn = _conn()
        try:
            mf_nav.ensure_history(conn, code)
            raw_df = pd.read_sql_query(
                """
                SELECT SUBSTR(Date,1,10) AS Date, Open, High, Low, Close, Volume
                FROM mf_nav_history
                WHERE scheme_code = ?
                ORDER BY Date ASC
                """,
                conn,
                params=(code,),
            )
            meta = conn.execute(
                "SELECT scheme_name, last_nav, nav_date FROM mf_schemes WHERE scheme_code = ?",
                (code,),
            ).fetchone()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No NAV history for scheme '{code}'")

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")
    raw_df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    if raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No NAV history for scheme '{code}'")

    try:
        bars = srv.aggregate_ohlcv(raw_df, timeframe)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Aggregation failed: {e}") from e

    day_change_pct = None
    if len(raw_df) >= 2:
        try:
            c0 = float(raw_df.iloc[-2]["Close"])
            c1 = float(raw_df.iloc[-1]["Close"])
            if c0 > 0 and math.isfinite(c0) and math.isfinite(c1):
                day_change_pct = round((c1 - c0) / c0 * 100.0, 2)
        except (TypeError, ValueError, IndexError):
            day_change_pct = None

    result = srv._assemble_chart_result(code, timeframe, bars, day_change_pct, ema_periods, None)
    if meta:
        result["scheme_name"] = meta[0]
        result["last_nav"] = meta[1]
        result["nav_date"] = meta[2]
    result["pricePanelTitle"] = "NAV"
    return result
