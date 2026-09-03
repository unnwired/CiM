"""
TradingView estimate/actual overlay for Screener quarterly tables.

Builds four rows aligned to Screener period columns:
  Est. EPS, Reported EPS, Est. revenue, Reported revenue.

Values come from TradingView only. Callers must not pass Screener-backed
or hybrid chart-event rows into build_tv_overlay_rows.

Matching uses TV earnings_release_date (or next-date for upcoming) against
Screener period end (data-date-key or parsed "Sep 2024" label).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# TV print can land up to ~5 months after fiscal quarter end (same window as chart fallback).
DEFAULT_MATCH_MAX_DAYS = 150

_MONTH_INDEX = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_PERIOD_LABEL_RE = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")

TV_ROW_SPECS = (
    ("Est. EPS (TV)", "tv_eps_estimate", "eps_estimate", "eps"),
    ("Reported EPS (TV)", "tv_eps_actual", "eps_actual", "eps"),
    ("Est. revenue (TV)", "tv_rev_estimate", "revenue_estimate", "revenue"),
    ("Reported revenue (TV)", "tv_rev_actual", "revenue_actual", "revenue"),
)


def parse_ymd(value: Any) -> Optional[date]:
    s = str(value or "").strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def period_end_date(period: dict[str, Any] | None) -> Optional[date]:
    """Resolve Screener column end date from date_key or 'Mon YYYY' label."""
    if not isinstance(period, dict):
        return None
    keyed = parse_ymd(period.get("date_key"))
    if keyed is not None:
        return keyed
    label = str(period.get("period") or "").strip()
    m = _PERIOD_LABEL_RE.match(label)
    if not m:
        return None
    month = _MONTH_INDEX.get(m.group(1).lower()) or _MONTH_INDEX.get(m.group(1).lower()[:3])
    try:
        year = int(m.group(2))
    except ValueError:
        return None
    if not month or year < 1990:
        return None
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def release_matches_period(
    release_date: Any,
    period: dict[str, Any] | None,
    *,
    max_days: int = DEFAULT_MATCH_MAX_DAYS,
) -> bool:
    """True when TV print/next date falls within [period_end, period_end + max_days]."""
    release_day = parse_ymd(release_date)
    period_day = period_end_date(period)
    if release_day is None or period_day is None:
        return False
    delta = (release_day - period_day).days
    return 0 <= delta <= int(max_days)


def match_release_to_period_index(
    release_date: Any,
    periods: list[dict[str, Any]],
    *,
    max_days: int = DEFAULT_MATCH_MAX_DAYS,
) -> Optional[int]:
    """
    Pick the best Screener column for a TV release date.
    Prefer the tightest (smallest) delta among matches; ties → later column.
    """
    release_day = parse_ymd(release_date)
    if release_day is None or not periods:
        return None
    best_idx: Optional[int] = None
    best_delta: Optional[int] = None
    for i, period in enumerate(periods):
        period_day = period_end_date(period if isinstance(period, dict) else None)
        if period_day is None:
            continue
        delta = (release_day - period_day).days
        if delta < 0 or delta > int(max_days):
            continue
        if best_delta is None or delta < best_delta or (delta == best_delta and i > (best_idx or -1)):
            best_delta = delta
            best_idx = i
    return best_idx


def _event_richness(event: dict[str, Any]) -> int:
    score = 0
    if event.get("eps_actual") is not None:
        score += 4
    if event.get("revenue_actual") is not None:
        score += 4
    if event.get("eps_estimate") is not None:
        score += 1
    if event.get("revenue_estimate") is not None:
        score += 1
    return score


def _merge_event_into_slot(slot: dict[str, Any], event: dict[str, Any]) -> None:
    for key in ("eps_actual", "eps_estimate", "revenue_actual", "revenue_estimate"):
        incoming = event.get(key)
        if incoming is None:
            continue
        # Richer events are applied first; keep first non-null per field.
        if slot.get(key) is None:
            slot[key] = incoming


def assign_events_to_periods(
    periods: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    max_days: int = DEFAULT_MATCH_MAX_DAYS,
) -> list[dict[str, Any]]:
    """One merged value slot per Screener period column."""
    slots: list[dict[str, Any]] = [{} for _ in periods]
    ranked = sorted(
        (e for e in events if isinstance(e, dict)),
        key=_event_richness,
        reverse=True,
    )
    for event in ranked:
        release = event.get("earnings_release_date") or event.get("earnings_release_next_date")
        idx = match_release_to_period_index(release, periods, max_days=max_days)
        if idx is None:
            continue
        _merge_event_into_slot(slots[idx], event)
    return slots


def build_tv_overlay_rows(
    periods: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    max_days: int = DEFAULT_MATCH_MAX_DAYS,
) -> list[dict[str, Any]]:
    """Return four TV rows aligned to `periods` (values null where unmatched)."""
    n = len(periods or [])
    if n <= 0:
        return [
            {
                "label": label,
                "slug": slug,
                "values": [],
                "is_pdf": False,
                "source": "tradingview",
                "value_kind": kind,
            }
            for label, slug, _field, kind in TV_ROW_SPECS
        ]

    slots = assign_events_to_periods(periods, events, max_days=max_days)
    rows: list[dict[str, Any]] = []
    for label, slug, field, kind in TV_ROW_SPECS:
        values = [slot.get(field) for slot in slots]
        rows.append({
            "label": label,
            "slug": slug,
            "values": values,
            "is_pdf": False,
            "source": "tradingview",
            "value_kind": kind,
        })
    return rows


def normalize_overlay_event(raw: dict[str, Any] | None) -> Optional[dict[str, Any]]:
    """Normalize a TradingView calendar row into overlay event shape.

    Rejects Screener-hybrid chart events if they slip through (source /
    comparison_source containing 'screener').
    """
    if not isinstance(raw, dict):
        return None
    source_blob = " ".join(
        str(raw.get(k) or "")
        for k in ("source", "comparison_source")
    ).lower()
    if "screener" in source_blob:
        return None
    release = (
        str(raw.get("earnings_release_date") or "").strip()
        or str(raw.get("earnings_release_next_date") or "").strip()
    )
    if not release:
        return None

    def _num(v: Any) -> Optional[float]:
        try:
            if v is None or v == "":
                return None
            f = float(v)
            if f != f:  # NaN
                return None
            return f
        except (TypeError, ValueError):
            return None

    return {
        "earnings_release_date": release[:10],
        "eps_actual": _num(raw.get("eps_actual")),
        "eps_estimate": _num(raw.get("eps_estimate")),
        "revenue_actual": _num(raw.get("revenue_actual")),
        "revenue_estimate": _num(raw.get("revenue_estimate")),
    }


def today_ist() -> date:
    return datetime.now(IST).date()
