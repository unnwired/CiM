"""Dual EPS+Rev beat flags for Market Map (Surprise vs Estimates, latest quarter)."""

from __future__ import annotations

from typing import Iterable

# Portfolio/watchlist row highlights use a rolling window; Market Map badges use the
# latest reported quarter (same persistence model as Earnings+ on the tile).


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").strip().upper()


def is_dual_beat_report_row(row: dict) -> bool:
    """Matches frontend portfolioEarnings.isDualBeatRow / server _is_dual_beat_report_row."""
    try:
        eps = float(row.get("eps_surprise_pct"))
        rev = float(row.get("revenue_surprise_pct"))
    except (TypeError, ValueError):
        return False
    if eps < 0 or rev < 0:
        return False
    if (
        row.get("eps_actual") is None
        and row.get("revenue_actual") is None
        and eps == 0
        and rev == 0
    ):
        return False
    return True


def _latest_reported_row_by_symbol(rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        sym = _normalize_symbol(row.get("symbol"))
        date = str(row.get("earnings_release_date") or "").strip()
        if not sym or not date:
            continue
        prev = latest.get(sym)
        if not prev or date > str(prev.get("earnings_release_date") or ""):
            latest[sym] = row
    return latest


def read_dual_beat_symbols(symbols: Iterable[str]) -> set[str]:
    from tradingview_earnings import _fetch_reported_rows_for_symbols

    normalized = [s for s in dict.fromkeys(_normalize_symbol(x) for x in symbols) if s]
    if not normalized:
        return set()

    rows = _fetch_reported_rows_for_symbols(
        normalized,
        max_age_days=None,
        mcap_min=None,
        mcap_max=None,
        eps_surprise_min=None,
        eps_surprise_max=None,
        revenue_surprise_min=None,
        revenue_surprise_max=None,
        legacy_both_positive=False,
    )
    out: set[str] = set()
    for sym, row in _latest_reported_row_by_symbol(rows).items():
        if is_dual_beat_report_row(row):
            out.add(sym)
    return out


def attach_earnings_beat_flags(rows: list[dict]) -> None:
    beats = read_dual_beat_symbols(r.get("symbol") for r in rows)
    for row in rows:
        sym = _normalize_symbol(row.get("symbol"))
        row["earnings_beat"] = sym in beats
