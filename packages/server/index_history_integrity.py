"""
Detect and repair calendar gaps in index_history (chartable indices).

Gap repair is intended for the on-demand admin job / CLI — not the OHLCV update path.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

MIN_GAP_CALENDAR_DAYS = 5
STALE_TAIL_CALENDAR_DAYS = 7
INDEX_HISTORY_START = "2010-01-01"

_log_fn: Optional[Callable[[str], None]] = None


def _install_root() -> Path:
    """Repo root in dev; Client / Client_Test install root when deployed."""
    try:
        from server.core.install_root import get_install_root

        root = get_install_root()
        if (root / "scrape_indices.py").is_file():
            return root
    except Exception:
        pass

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "scrape_indices.py").is_file():
            return candidate
    return here.parents[2]


def _load_scrape_indices():
    root = _install_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    scrape_path = root / "scrape_indices.py"
    if not scrape_path.is_file():
        raise FileNotFoundError(
            f"scrape_indices.py not found under install root {root}"
        )
    spec = importlib.util.spec_from_file_location(
        "scrape_indices_integrity",
        scrape_path,
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _load_nse_index_history():
    root = _install_root()
    nse_path = root / "nse_index_history.py"
    if not nse_path.is_file():
        raise FileNotFoundError(
            f"nse_index_history.py not found under install root {root}"
        )
    spec = importlib.util.spec_from_file_location(
        "nse_index_history_integrity",
        nse_path,
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _symbol_catalog(symbols: Optional[list[str]] = None) -> list[tuple[str, str, str]]:
    scrape = _load_scrape_indices()
    catalog = list(scrape.INDICES)
    if symbols:
        wanted = {str(s).strip() for s in symbols if str(s).strip()}
        catalog = [row for row in catalog if row[0] in wanted]
    return catalog


def _index_row_stats(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*), MIN(SUBSTR(Date, 1, 10)), MAX(SUBSTR(Date, 1, 10))
        FROM index_history
        WHERE Symbol = ?
        """,
        (symbol,),
    )
    count, first_date, last_date = cur.fetchone()
    return {
        "row_count": int(count or 0),
        "first_date": str(first_date)[:10] if first_date else None,
        "last_date": str(last_date)[:10] if last_date else None,
    }


def _gap_dicts(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    min_gap_days: int = MIN_GAP_CALENDAR_DAYS,
) -> list[dict[str, Any]]:
    nih = _load_nse_index_history()
    raw_gaps = nih.find_index_history_gaps(conn, symbol, min_gap_days=min_gap_days)
    out: list[dict[str, Any]] = []
    for start, end in raw_gaps:
        out.append(
            {
                "gap_start": start.isoformat(),
                "gap_end": end.isoformat(),
                "gap_calendar_days": (end - start).days + 1,
            }
        )
    return out


def _is_stale_tail(last_date: Optional[str], *, max_lag_days: int = STALE_TAIL_CALENDAR_DAYS) -> bool:
    if not last_date:
        return True
    try:
        last = datetime.strptime(str(last_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return True
    cutoff = date.today() - timedelta(days=max_lag_days)
    return last < cutoff


def scan_index_history(
    conn: sqlite3.Connection,
    *,
    symbols: Optional[list[str]] = None,
    min_gap_days: int = MIN_GAP_CALENDAR_DAYS,
) -> dict[str, Any]:
    """Return per-symbol gap report for chartable indices."""
    symbol_rows: list[dict[str, Any]] = []
    total_gaps = 0

    for symbol, name, category in _symbol_catalog(symbols):
        stats = _index_row_stats(conn, symbol)
        gaps = _gap_dicts(conn, symbol, min_gap_days=min_gap_days)
        stale_tail = _is_stale_tail(stats.get("last_date"))
        total_gaps += len(gaps)
        symbol_rows.append(
            {
                "symbol": symbol,
                "name": name,
                "category": category,
                "row_count": stats["row_count"],
                "first_date": stats["first_date"],
                "last_date": stats["last_date"],
                "stale_tail": stale_tail,
                "gaps": gaps,
                "gap_count": len(gaps),
            }
        )

    affected = [s for s in symbol_rows if s["gap_count"] or (s["row_count"] == 0 and s["category"] == "equity")]
    return {
        "symbols_scanned": len(symbol_rows),
        "symbols_with_gaps": len([s for s in symbol_rows if s["gap_count"]]),
        "total_gap_ranges": total_gaps,
        "symbols": symbol_rows,
        "affected_symbols": [s["symbol"] for s in affected],
    }


def _repair_yahoo_gaps(
    conn: sqlite3.Connection,
    symbol: str,
    category: str,
    gaps: list[dict[str, Any]],
    *,
    usd_inr: float,
) -> int:
    import yfinance as yf

    scrape = _load_scrape_indices()
    convert = scrape.convert_commodity
    cursor = conn.cursor()
    written = 0

    ranges = gaps or [{"gap_start": INDEX_HISTORY_START, "gap_end": date.today().isoformat()}]
    for gap in ranges:
        gap_start = datetime.strptime(gap["gap_start"], "%Y-%m-%d").date()
        gap_end = datetime.strptime(gap["gap_end"], "%Y-%m-%d").date()
        start = (gap_start - timedelta(days=3)).strftime("%Y-%m-%d")
        end = (gap_end + timedelta(days=3)).strftime("%Y-%m-%d")
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            continue
        df = df.reset_index()
        df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
        for _, row in df.iterrows():
            try:
                date_str = (
                    row["Date"].strftime("%Y-%m-%d")
                    if hasattr(row["Date"], "strftime")
                    else str(row["Date"])[:10]
                )
                o = float(row["Open"])
                h = float(row["High"])
                low = float(row["Low"])
                c = float(row["Close"])
                v = float(row.get("Volume", 0) or 0)
                if category == "commodity":
                    o = convert(symbol, o, usd_inr)
                    h = convert(symbol, h, usd_inr)
                    low = convert(symbol, low, usd_inr)
                    c = convert(symbol, c, usd_inr)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO index_history
                        (Symbol, Date, Open, High, Low, Close, Volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, date_str, round(o, 2), round(h, 2), round(low, 2), round(c, 2), round(v, 2)),
                )
                written += 1
            except Exception:
                continue
    if written:
        conn.commit()
    return written


def repair_index_gaps(
    conn: sqlite3.Connection,
    *,
    symbols: Optional[list[str]] = None,
    min_gap_days: int = MIN_GAP_CALENDAR_DAYS,
    log_fn: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Backfill index_history gaps for chartable indices.

    Equity: Upstox primary via scrape_indices.scrape_history, Yahoo secondary.
    Commodities: Yahoo gap windows.
    """
    scrape = _load_scrape_indices()

    def log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    scan = scan_index_history(conn, symbols=symbols, min_gap_days=min_gap_days)
    catalog = _symbol_catalog(symbols)
    total = len(catalog)
    rows_inserted = 0
    gaps_found = scan["total_gap_ranges"]
    errors: list[str] = []
    repaired_symbols: list[str] = []

    if dry_run:
        return {
            **scan,
            "dry_run": True,
            "rows_inserted": 0,
            "errors": [],
            "repaired_symbols": scan.get("affected_symbols", []),
        }

    usd_inr = scrape.get_usd_inr()
    for idx, (symbol, name, category) in enumerate(catalog, start=1):
        if cancel_check:
            cancel_check()

        sym_scan = next((s for s in scan["symbols"] if s["symbol"] == symbol), None)
        gaps = (sym_scan or {}).get("gaps") or []
        needs_repair = bool(gaps) or (sym_scan and sym_scan.get("row_count", 0) == 0)
        msg = f"Index gap repair {idx}/{total}: {name} ({symbol})"
        if progress_cb:
            progress_cb(idx - 1, total, msg)
        if not needs_repair:
            continue

        log(f"{name} ({symbol}): {len(gaps)} gap range(s)")
        try:
            if category == "equity":
                written = 0
                if gaps:
                    gap_fn = getattr(scrape, "backfill_equity_index_gaps", None)
                    if callable(gap_fn):
                        written += int(
                            gap_fn(symbol, name, "equity", usd_inr, conn) or 0
                        )
                written += int(
                    scrape.scrape_history(symbol, name, "equity", usd_inr, conn) or 0
                )
                rows_inserted += written
            else:
                rows_inserted += _repair_yahoo_gaps(
                    conn, symbol, category, gaps, usd_inr=usd_inr
                )
            repaired_symbols.append(symbol)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            log(f"  [X] {symbol}: {exc}")

    if progress_cb:
        progress_cb(total, total, "Index gap repair complete")

    return {
        "symbols_scanned": total,
        "gaps_found": gaps_found,
        "rows_inserted": rows_inserted,
        "errors": errors,
        "repaired_symbols": repaired_symbols,
        "scan": scan,
    }



def purge_non_session_index_bars(
    conn: sqlite3.Connection,
    *,
    symbols: Optional[list[str]] = None,
    since: Optional[str] = None,
) -> dict[str, Any]:
    """
    Delete equity-index daily bars on non-NSE session days (weekends / holidays).

    Weekly and other chart timeframes are aggregated from daily at request time,
    so purging bad dailies corrects all TFs without a separate rewrite.
    """
    try:
        from movers_data import _is_nse_session_day as _session_ok
    except Exception:
        try:
            from server.movers_data import _is_nse_session_day as _session_ok
        except Exception:
            _session_ok = lambda d: d.weekday() < 5  # noqa: E731

    catalog = _symbol_catalog(symbols)
    equity_syms = [s for s, _n, cat in catalog if str(cat).lower() == "equity"]
    if not equity_syms:
        return {"symbols": 0, "deleted": 0, "dates": []}

    placeholders = ",".join("?" for _ in equity_syms)
    sql = f"SELECT DISTINCT SUBSTR(Date,1,10) FROM index_history WHERE Symbol IN ({placeholders})"
    params: list[Any] = list(equity_syms)
    if since:
        sql += " AND SUBSTR(Date,1,10) >= ?"
        params.append(str(since)[:10])
    cur = conn.cursor()
    dates = [str(r[0])[:10] for r in cur.execute(sql, params).fetchall() if r and r[0]]
    bad_dates: list[str] = []
    for ds in dates:
        try:
            day = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not _session_ok(day):
            bad_dates.append(ds)
    deleted = 0
    for ds in bad_dates:
        cur.execute(
            f"DELETE FROM index_history WHERE Symbol IN ({placeholders}) AND SUBSTR(Date,1,10) = ?",
            [*equity_syms, ds],
        )
        deleted += int(cur.rowcount or 0)
    if deleted:
        conn.commit()
    return {
        "symbols": len(equity_syms),
        "deleted": deleted,
        "dates": bad_dates,
    }


def format_integrity_report(result: dict[str, Any]) -> str:
    """Human-readable summary for job logs / CLI."""
    if "symbols" in result and "symbols_scanned" in result and "rows_inserted" not in result:
        lines = [
            f"Index history scan: {result['symbols_scanned']} symbol(s), "
            f"{result['symbols_with_gaps']} with gaps, "
            f"{result['total_gap_ranges']} gap range(s) total.",
        ]
        for sym in result.get("symbols", []):
            if not sym.get("gap_count"):
                continue
            lines.append(
                f"  {sym['symbol']} ({sym['name']}): {sym['gap_count']} gap(s), "
                f"rows={sym['row_count']}, range={sym['first_date']}..{sym['last_date']}"
            )
            for gap in sym.get("gaps", [])[:2]:
                lines.append(f"    {gap['gap_start']} -> {gap['gap_end']} ({gap['gap_calendar_days']}d)")
        return "\n".join(lines)

    lines = [
        "Index chart gap repair complete.",
        f"Symbols scanned: {result.get('symbols_scanned', 0)}",
        f"Gap ranges found: {result.get('gaps_found', 0)}",
        f"Bars written: {result.get('rows_inserted', 0)}",
    ]
    repaired = result.get("repaired_symbols") or []
    if repaired:
        lines.append(f"Repaired: {', '.join(repaired)}")
    errors = result.get("errors") or []
    if errors:
        lines.append("Errors:")
        lines.extend(f"  {e}" for e in errors[:10])
    if result.get("dry_run"):
        lines.insert(0, "[dry-run] No data written.")
    return "\n".join(lines)
