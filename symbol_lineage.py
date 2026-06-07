"""
NSE ticker rename lineage — fetch and merge OHLC under canonical screener symbols.

See docs/SYMBOL_LINEAGE.md.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
LINEAGE_PATH = BASE_DIR / "data" / "symbol_lineage.json"


def load_lineage_config(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or LINEAGE_PATH
    if not p.is_file():
        return {"version": 1, "symbols": {}}
    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)
    symbols = raw.get("symbols") or {}
    if not isinstance(symbols, dict):
        symbols = {}
    return {"version": raw.get("version", 1), "symbols": symbols}


def get_lineage_entry(canonical: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    sym = str(canonical or "").strip().upper()
    if not sym:
        return None
    cfg = load_lineage_config(path)
    entry = cfg.get("symbols", {}).get(sym)
    if not entry:
        return None
    out = dict(entry)
    out["canonical"] = sym
    return out


def list_lineage_canonicals(path: Optional[Path] = None) -> list[str]:
    cfg = load_lineage_config(path)
    return sorted(str(k).strip().upper() for k in cfg.get("symbols", {}).keys() if str(k).strip())


def yfinance_nse_ticker(nse_symbol: str) -> str:
    return f"{str(nse_symbol).strip().upper()}.NS"


def _parse_day(s: str) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _day_to_row_str(d: date) -> str:
    return d.strftime("%Y-%m-%d") + " 00:00:00+05:30"


def fetch_yfinance_daily(
    symbol: str,
    start: date,
    end: date,
    *,
    yahoo_symbol: Optional[str] = None,
    include_volume: bool = True,
) -> list[tuple[str, float, float, float, float, Optional[float]]]:
    """Returns rows: (date_str, o, h, l, c, v). `yahoo_symbol` overrides .NS mapping."""
    import yfinance as yf

    if end < start:
        return []
    yf_sym = str(yahoo_symbol or "").strip() or yfinance_nse_ticker(symbol)
    start_str = start.strftime("%Y-%m-%d")
    end_str = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        df = yf.download(
            yf_sym,
            start=start_str,
            end=end_str,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception:
        return []
    if df is None or df.empty:
        return []
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.dropna(subset=["Close"])
    rows: list[tuple[str, float, float, float, float, Optional[float]]] = []
    for ts, row in df.iterrows():
        try:
            d = ts.date() if hasattr(ts, "date") else _parse_day(str(ts))
            c = round(float(row["Close"]), 2)
            if c <= 0:
                continue
            rows.append(
                (
                    _day_to_row_str(d),
                    round(float(row["Open"]), 2),
                    round(float(row["High"]), 2),
                    round(float(row["Low"]), 2),
                    c,
                    _volume_from_yahoo_row(row, include_volume=include_volume),
                )
            )
        except Exception:
            continue
    return rows


def _volume_from_yahoo_row(row, *, include_volume: bool = True) -> Optional[float]:
    if not include_volume:
        return None
    try:
        v = float(row.get("Volume", 0) or 0)
    except (TypeError, ValueError):
        return None
    return round(v, 2) if v > 0 else None


def merge_lineage_rows(
    canonical: str,
    entry: dict[str, Any],
    log: Optional[Callable[[str], None]] = None,
) -> list[tuple[str, float, float, float, float, float]]:
    """
    Build full daily series for canonical symbol: predecessors then canonical Yahoo series.
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)

    sym = str(canonical).strip().upper()
    predecessors = entry.get("predecessors") or []
    if not isinstance(predecessors, list):
        predecessors = []

    by_day: dict[str, tuple[str, float, float, float, float, Optional[float]]] = {}

    import_bse_volume = bool(entry.get("import_bse_volume", False))
    hist_yahoo = str(entry.get("historical_yahoo") or "").strip()
    if hist_yahoo:
        today = date.today()
        _log(f"  Lineage: full history via Yahoo {hist_yahoo}")
        full = fetch_yfinance_daily(
            sym,
            date(1990, 1, 1),
            today,
            yahoo_symbol=hist_yahoo,
            include_volume=import_bse_volume,
        )
        _log(f"    {hist_yahoo}: {len(full)} daily bars (volume={'yes' if import_bse_volume else 'OHLC only'})")
        for row in full:
            by_day[str(row[0])[:10]] = row
        # Overlay NSE (.NS) for OHLC + NSE volume on sessions where listed on NSE
        _log(f"  Lineage: overlay {sym}.NS (NSE OHLC + volume)")
        ns_rows = fetch_yfinance_daily(sym, date(2020, 1, 1), today, include_volume=True)
        for row in ns_rows:
            by_day[str(row[0])[:10]] = row
        return [by_day[k] for k in sorted(by_day.keys())]

    for pred in predecessors:
        if not isinstance(pred, dict):
            continue
        old_sym = str(pred.get("nse_symbol") or "").strip().upper()
        until_s = str(pred.get("effective_until") or "").strip()
        if not old_sym or not until_s:
            continue
        until_d = _parse_day(until_s)
        start_d = date(1990, 1, 1)
        yahoo_sym = str(pred.get("yahoo_symbol") or "").strip() or None
        _log(f"  Lineage: {old_sym} -> {sym} (through {until_d})")
        chunk = fetch_yfinance_daily(
            old_sym, start_d, until_d, yahoo_symbol=yahoo_sym, include_volume=import_bse_volume
        )
        label = yahoo_sym or f"{old_sym}.NS"
        _log(f"    {label}: {len(chunk)} daily bars")
        for row in chunk:
            by_day[str(row[0])[:10]] = row

    # Canonical ticker from day after last predecessor (or 1990 if none)
    canon_start = date(1990, 1, 1)
    if predecessors:
        last_until = max(
            _parse_day(str(p.get("effective_until")))
            for p in predecessors
            if isinstance(p, dict) and p.get("effective_until")
        )
        canon_start = last_until + timedelta(days=1)

    today = date.today()
    _log(f"  Lineage: {sym}.NS from {canon_start} to {today}")
    canon_rows = fetch_yfinance_daily(sym, canon_start, today)
    _log(f"    {sym}: {len(canon_rows)} daily bars")
    for row in canon_rows:
        by_day[str(row[0])[:10]] = row

    ordered = [by_day[k] for k in sorted(by_day.keys())]
    return ordered


def lineage_backfill_needed(
    conn,
    canonical: str,
    entry: Optional[dict[str, Any]] = None,
) -> bool:
    """True if DB earliest bar is missing or starts after rename boundary."""
    entry = entry or get_lineage_entry(canonical)
    if not entry:
        return False
    preds = entry.get("predecessors") or []
    if not preds:
        return False
    cur = conn.cursor()
    cur.execute(
        "SELECT MIN(substr(Date,1,10)) FROM historical_data WHERE Symbol = ?",
        (str(canonical).strip().upper(),),
    )
    row = cur.fetchone()
    min_s = row[0] if row and row[0] else None
    if not min_s:
        return True
    try:
        min_d = _parse_day(min_s)
    except Exception:
        return True
    first_pred = preds[0]
    until_s = str(first_pred.get("effective_until") or "")[:10]
    if not until_s:
        return False
    until_d = _parse_day(until_s)
    # Earliest bar must start well before the rename, not merely a few weeks of old ticker.
    min_start_s = str(entry.get("min_history_start") or "2005-01-01").strip()[:10]
    try:
        required_start = _parse_day(min_start_s)
    except Exception:
        required_start = date(2005, 1, 1)
    return min_d > required_start


def write_lineage_to_db(
    conn,
    canonical: str,
    rows: list[tuple[str, float, float, float, float, float]],
    overwrite_overlap: bool = True,
) -> int:
    """Insert daily bars under canonical symbol. Returns rows written."""
    sym = str(canonical).strip().upper()
    if not rows:
        return 0
    cursor = conn.cursor()
    if overwrite_overlap:
        for date_str, o, h, l, c, v in rows:
            day = str(date_str)[:10]
            cursor.execute(
                "DELETE FROM historical_data WHERE Symbol=? AND substr(Date,1,10)=?",
                (sym, day),
            )
    data = [(sym, ds, o, h, l, c, c, v, None) for ds, o, h, l, c, v in rows]
    # v may be None when BSE backfill supplies OHLC only (NSE volume differs by scale)
    cursor.executemany(
        "INSERT INTO historical_data (Symbol, Date, Open, High, Low, Close, AdjClose, Volume, MarketCap) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        data,
    )
    conn.commit()
    return len(data)


def _ensure_updater_meta_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS updater_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()


def set_lineage_backfill_meta(conn, canonical: str) -> None:
    _ensure_updater_meta_table(conn)
    cur = conn.cursor()
    key = f"lineage_backfill:{str(canonical).strip().upper()}"
    cur.execute(
        """
        INSERT INTO updater_meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, datetime.now().isoformat()),
    )
    conn.commit()


def run_lineage_backfill(
    conn,
    canonical: str,
    log: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    sym = str(canonical).strip().upper()
    entry = get_lineage_entry(sym)
    if not entry:
        return {"symbol": sym, "ok": False, "error": "no_lineage_config"}
    rows = merge_lineage_rows(sym, entry, log=log)
    if not rows:
        return {"symbol": sym, "ok": False, "error": "no_rows_from_yfinance"}
    n = write_lineage_to_db(conn, sym, rows)
    set_lineage_backfill_meta(conn, sym)
    min_d = str(rows[0][0])[:10]
    max_d = str(rows[-1][0])[:10]
    return {
        "symbol": sym,
        "ok": True,
        "rows_written": n,
        "min_date": min_d,
        "max_date": max_d,
    }
