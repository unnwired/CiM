"""
Fetch index constituent rows from NSE live API (when allowed) or official archive CSV + screener/live cache.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import time
from typing import Any, Callable, Optional
from urllib.parse import quote

import requests as req

ARCHIVE_BASE = "https://nsearchives.nseindia.com/content/indices/"

# Yahoo / internal symbol -> NSE archive constituent list filename
INDEX_ARCHIVE_CSV: dict[str, str] = {
    "^NSEI": "ind_nifty50list.csv",
    "^NSEBANK": "ind_niftybanklist.csv",
    "^NSMIDCP": "ind_niftymidcap100list.csv",
    "^NSEMDCP50": "ind_niftymidcap50list.csv",
    "^CNXSC": "ind_niftysmallcap100list.csv",
    "^CNXIT": "ind_niftyitlist.csv",
    "^CNXFMCG": "ind_niftyfmcglist.csv",
    "^CNXPHARMA": "ind_niftypharmalist.csv",
    "^CNXAUTO": "ind_niftyautolist.csv",
    "^CNXMETAL": "ind_niftymetallist.csv",
    "^CNXREALTY": "ind_niftyrealtylist.csv",
    "^CNXENERGY": "ind_niftyenergylist.csv",
    "^CNXINFRA": "ind_niftyinfralist.csv",
    "^CNXINDDEF": "ind_niftyindiadefence_list.csv",
    "^CNXPSUBANK": "ind_niftypsubanklist.csv",
    "^CNXPSE": "ind_niftypselist.csv",
    "^CNXMNC": "ind_niftymnclist.csv",
    "^CNXSERVICE": "ind_niftyservicelist.csv",
    "^CNXMEDIA": "ind_niftymedialist.csv",
    "^CNXDIVOP": "ind_niftydivopp50list.csv",
    "^CNXNXT50": "ind_niftynext50list.csv",
    "^CNX100": "ind_nifty100list.csv",
    "^CNX200": "ind_nifty200list.csv",
    "^CRSLDX": "ind_nifty500list.csv",
    "^CNXSMLCP50": "ind_niftysmallcap50list.csv",
    "^CNXCMDT": "ind_niftycommoditieslist.csv",
}

NSE_INDEX_MAP: dict[str, str] = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
    "^NSMIDCP": "NIFTY MIDCAP 100",
    "^NSEMDCP50": "NIFTY MIDCAP 50",
    "^CNXFMCG": "NIFTY FMCG",
    "^CNXPHARMA": "NIFTY PHARMA",
    "^CNXAUTO": "NIFTY AUTO",
    "^CNXMETAL": "NIFTY METAL",
    "^CNXREALTY": "NIFTY REALTY",
    "^CNXENERGY": "NIFTY ENERGY",
    "^CNXINFRA": "NIFTY INFRA",
    "^CNXINDDEF": "NIFTY INDIA DEFENCE",
    "^CNXPSUBANK": "NIFTY PSU BANK",
    "^CNXSC": "NIFTY SMALLCAP 100",
    "^CNXCMDT": "NIFTY COMMODITIES",
    "^CNXPSE": "NIFTY PSE",
    "^CNXMNC": "NIFTY MNC",
    "^CNXSERVICE": "NIFTY SERVICES SECTOR",
    "^CNXMEDIA": "NIFTY MEDIA",
    "^CNXDIVOP": "NIFTY DIVIDEND OPPORTUNITIES 50",
    "^CNXNXT50": "NIFTY NEXT 50",
    "^CNX100": "NIFTY 100",
    "^CNX200": "NIFTY 200",
    "^CRSLDX": "NIFTY 500",
    "^CNXSMLCP50": "NIFTY SMLCAP 50",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def make_nse_session() -> req.Session:
    s = req.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=15)
        time.sleep(1.5)
        s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
        time.sleep(1.5)
    except Exception:
        pass
    return s


def _encode_index(index_name: str) -> str:
    return quote(index_name, safe="")


def fetch_live_constituents(session: req.Session, nse_name: str) -> list[dict]:
    url = f"https://www.nseindia.com/api/equity-stockIndices?index={_encode_index(nse_name)}"
    r = session.get(url, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"NSE API HTTP {r.status_code}")
    return r.json().get("data", []) or []


def _fetch_archive_text(csv_file: str) -> str:
    url = ARCHIVE_BASE + csv_file
    r = req.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"NSE archive HTTP {r.status_code} for {csv_file}")
    text = r.text
    if text.lstrip().startswith("<!"):
        raise RuntimeError(f"NSE archive not CSV: {csv_file}")
    return text


def parse_archive_constituents(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
    if not reader.fieldnames:
        return out
    fields = {h.strip(): h for h in reader.fieldnames}
    sym_key = fields.get("Symbol") or fields.get("SYMBOL")
    name_key = fields.get("Company Name") or fields.get("NAME") or fields.get("Security Name")
    if not sym_key:
        return out
    for row in reader:
        sym = str(row.get(sym_key) or "").strip().upper()
        if not sym:
            continue
        nm = str(row.get(name_key) or sym).strip() if name_key else sym
        out.append({"symbol": sym, "company_name": nm})
    return out


def _screener_map(conn: sqlite3.Connection) -> dict[str, tuple]:
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT symbol, market_cap, change_percent, price, nse_sector, issued_shares
            FROM screener
            """
        )
        out = {}
        for sym, mcap, chg, price, sector, issued in cur.fetchall():
            out[str(sym or "").upper().strip()] = (mcap, chg, price, sector, issued)
        return out
    except Exception:
        return {}


def _effective_market_cap(
    stored_mcap,
    price,
    issued_shares,
    *,
    live_price: Optional[float] = None,
) -> Optional[float]:
    """Full INR market cap: prefer issued_shares × price (live price when available)."""
    px = live_price if live_price is not None else price
    try:
        if issued_shares is not None and px is not None and float(px) > 0:
            sh = float(issued_shares)
            if sh > 0:
                return round(sh * float(px), 0)
    except (TypeError, ValueError):
        pass
    try:
        if stored_mcap is not None:
            v = float(stored_mcap)
            if v > 0:
                # Legacy screener rows may store crores — promote to rupees when plausible.
                if v < 1_000_000:
                    v *= 1e7
                return round(v, 0)
    except (TypeError, ValueError):
        pass
    return None


def _live_snap_for_symbol(symbol: str) -> Optional[dict]:
    try:
        import movers_live as ml

        snap = ml.get_symbol_live_snapshot(symbol, allow_fetch=False)
        return snap if isinstance(snap, dict) else None
    except Exception:
        return None


def _day_chg_from_history(conn: sqlite3.Connection, symbol: str) -> Optional[float]:
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ROUND((
                (SELECT Close FROM historical_data h1 WHERE h1.Symbol = ? ORDER BY h1.Date DESC LIMIT 1)
                - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = ? ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
            ) / NULLIF((
                SELECT Close FROM historical_data h3 WHERE h3.Symbol = ? ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
            ), 0) * 100, 2)
            """,
            (symbol, symbol, symbol),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return None


def enrich_archive_rows(
    archive_rows: list[dict[str, str]],
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    screener = _screener_map(conn)
    stocks: list[dict[str, Any]] = []
    for row in archive_rows:
        sym = row["symbol"]
        sc = screener.get(sym)
        mcap = None
        chg = sc[1] if sc and sc[1] is not None else None
        price = sc[2] if sc and sc[2] is not None else None
        sector = sc[3] if sc else None
        issued = sc[4] if sc and len(sc) > 4 else None

        snap = _live_snap_for_symbol(sym)
        live_px = None
        if snap:
            if snap.get("price") is not None:
                live_px = round(float(snap["price"]), 2)
                price = live_px
            if snap.get("change_pct") is not None:
                chg = round(float(snap["change_pct"]), 2)

        if sc:
            mcap = _effective_market_cap(sc[0], sc[2], issued, live_price=live_px)

        if chg is None:
            hist = _day_chg_from_history(conn, sym)
            if hist is not None:
                chg = round(hist, 2)

        stocks.append({
            "symbol": sym,
            "company_name": row.get("company_name") or sym,
            "market_cap": mcap,
            "last_price": round(float(price), 2) if price is not None else None,
            "change_pct": chg,
            "nse_sector": sector,
        })
    return stocks


def parse_live_rows(
    raw_items: list[dict],
    nse_name: str,
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    screener = _screener_map(conn)
    stocks: list[dict[str, Any]] = []
    for item in raw_items:
        sym = str(item.get("symbol", "") or "").strip()
        if not sym or sym.upper() == nse_name.upper():
            continue
        meta = item.get("meta") or {}
        key = sym.upper()
        sc = screener.get(key)
        pch = item.get("pChange")
        chg = round(float(pch), 2) if pch is not None else (
            round(float(sc[1]), 2) if sc and sc[1] is not None else None
        )
        lp = round(float(item.get("lastPrice", 0) or 0), 2)
        issued = sc[4] if sc and len(sc) > 4 else None
        mcap = _effective_market_cap(sc[0], sc[2], issued, live_price=lp) if sc else None
        stocks.append({
            "symbol": sym,
            "company_name": meta.get("companyName", sym),
            "last_price": lp,
            "change_pct": chg,
            "market_cap": mcap,
            "nse_sector": sc[3] if sc else None,
        })
    return stocks


def fetch_constituents_for_symbol(
    symbol: str,
    conn: sqlite3.Connection,
    *,
    session: Optional[req.Session] = None,
) -> tuple[list[dict[str, Any]], str, Optional[str]]:
    """
    Returns (constituents, data_source, error).
    data_source: 'nse_live' | 'nse_archive'
    """
    nse_name = NSE_INDEX_MAP.get(symbol)
    if not nse_name:
        return [], "", f"Unknown index symbol {symbol}"

    sess = session or make_nse_session()
    try:
        raw = fetch_live_constituents(sess, nse_name)
        if raw:
            rows = parse_live_rows(raw, nse_name, conn)
            if rows:
                return rows, "nse_live", None
    except Exception:
        pass

    csv_file = INDEX_ARCHIVE_CSV.get(symbol)
    if not csv_file:
        return [], "", "No archive constituent list configured for this index"

    try:
        text = _fetch_archive_text(csv_file)
        archive = parse_archive_constituents(text)
        if not archive:
            return [], "", f"Archive list empty: {csv_file}"
        rows = enrich_archive_rows(archive, conn)
        return rows, "nse_archive", None
    except Exception as e:
        return [], "", str(e)
