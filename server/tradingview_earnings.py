"""

TradingView India screener — earnings beats (reported) and upcoming releases.

Uses TradingView's scanner API (same data family as Financials → Earnings).

"""



from __future__ import annotations



import calendar

import time

from datetime import datetime, timedelta

from typing import Any, Literal

from zoneinfo import ZoneInfo



IST = ZoneInfo("Asia/Kolkata")

MIN_REPORT_YEAR = 2024

_CACHE_TTL_SEC = 300  # 5 minutes



# In-memory cache: cache_key -> (rows, fetched_at)

_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}



Mode = Literal["reported", "upcoming"]

Period = Literal["this_month", "next_month", "month_after", "coming_week", "rolling_30_days", "rolling_20_days"]


def lookup_tv_close_prices(symbols: list[str]) -> dict[str, float]:
    """TradingView last close for symbols missing from local screener (NSE preferred)."""
    return {s: m["price"] for s, m in lookup_tv_market_metrics(symbols).items() if m.get("price")}


def lookup_tv_market_metrics(symbols: list[str]) -> dict[str, dict[str, float | None]]:
    """TradingView close + 1D % for symbols missing from local screener (NSE preferred)."""
    wanted = list(
        dict.fromkeys(
            str(s or "").strip().upper() for s in symbols if str(s or "").strip()
        )
    )
    if not wanted:
        return {}
    try:
        from tradingview_screener import col, stocks
    except ImportError:
        return {}

    out: dict[str, dict[str, float | None]] = {}
    chunk_size = 80
    for i in range(0, len(wanted), chunk_size):
        chunk = wanted[i : i + chunk_size]
        try:
            q = (
                stocks("india")
                .select("name", "close", "change", "change|1W")
                .where(col("name").isin(chunk))
                .limit(len(chunk) * 3)
            )
            _total, df = q.get_scanner_data()
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, rec in df.iterrows():
            sym = str(rec.get("name") or "").strip().upper()
            if not sym or sym in out:
                continue
            px = _num(rec.get("close"))
            chg = _num(rec.get("change"))
            chg_1w = _num(rec.get("change|1W"))
            chg_2w = None
            if chg_1w is not None:
                chg_2w = round(((1 + chg_1w / 100) ** 2 - 1) * 100, 2)
            out[sym] = {
                "price": round(px, 2) if px is not None and px > 0 else None,
                "change_1d_pct": round(chg, 2) if chg is not None else None,
                "change_2w_pct": chg_2w,
            }
    return out





def current_year_ist() -> int:

    return datetime.now(IST).year





def current_month_ist() -> int:

    return datetime.now(IST).month





def available_report_years() -> list[int]:

    y = current_year_ist()

    return list(range(MIN_REPORT_YEAR, y + 1))





def clamp_report_year(year: int | None) -> int:

    y = int(year if year is not None else current_year_ist())

    lo, hi = MIN_REPORT_YEAR, current_year_ist()

    if y < lo or y > hi:

        raise ValueError(f"year must be between {lo} and {hi}")

    return y





def resolve_report_month(month: int | None) -> int | None:

    """

    month 1–12 = that calendar month (IST).

    month 0 = all months in the selected year.

    month None = current calendar month (default).

    """

    if month is None:

        return current_month_ist()

    m = int(month)

    if m == 0:

        return None

    if m < 1 or m > 12:

        raise ValueError("month must be 1–12, or 0 for all months in year")

    return m


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:

    idx = year * 12 + (month - 1) + delta

    return idx // 12, (idx % 12) + 1





def validate_period(period: str | None) -> Period:

    p = (period or "this_month").strip().lower()

    allowed = ("this_month", "next_month", "month_after", "coming_week", "rolling_30_days", "rolling_20_days")

    if p not in allowed:

        raise ValueError(f"period must be one of: {', '.join(allowed)}")

    return p  # type: ignore[return-value]





def _parse_ticker(ticker: str) -> tuple[str, str]:

    raw = str(ticker or "").strip().upper()

    if ":" in raw:

        ex, sym = raw.split(":", 1)

        return ex.strip(), sym.strip()

    return "", raw





def _dedupe_nse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:

    """Prefer NSE listing when the same name appears on BSE and NSE."""

    by_symbol: dict[str, dict[str, Any]] = {}

    for row in rows:

        sym = row.get("symbol")

        if not sym:

            continue

        prev = by_symbol.get(sym)

        if prev is None:

            by_symbol[sym] = row

            continue

        if row.get("exchange") == "NSE" and prev.get("exchange") != "NSE":

            by_symbol[sym] = row

    out = list(by_symbol.values())

    # Same issuer on BSE and NSE often uses different TV symbols (e.g. M_M vs M&M).
    # Collapse identical market_cap rows, keeping the NSE line.
    seen_mcap: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted(
        out,
        key=lambda r: (0 if r.get("exchange") == "NSE" else 1),
    ):
        mc = _num(row.get("market_cap_basic"))
        if mc is None or mc <= 0:
            deduped.append(row)
            continue
        key = int(round(mc))
        if key in seen_mcap:
            continue
        seen_mcap.add(key)
        deduped.append(row)
    return deduped





def _num(v: Any) -> float | None:

    if v is None:

        return None

    try:

        f = float(v)

        if f != f:  # NaN

            return None

        return f

    except (TypeError, ValueError):

        return None


def _surprise_pct_fq(
    actual: float | None,
    estimate: float | None,
    tv_pct: Any = None,
) -> float | None:
    """
    Surprise % for filters and table: prefer TV field, else compute from actual vs estimate.
    Equal actual/estimate → 0% (met consensus). Supports min=0 filters (meet or beat).
    """
    tv = _num(tv_pct)
    if tv is not None:
        return tv
    a = _num(actual)
    e = _num(estimate)
    if a is None or e is None:
        return None
    if e == 0:
        if a == 0:
            return 0.0
        return 100.0 if a > 0 else -100.0
    pct = ((a - e) / abs(e)) * 100.0
    if abs(pct) < 1e-9:
        return 0.0
    return pct


def _passes_surprise_bound(
    value: float | None,
    *,
    min_val: float | None,
    max_val: float | None,
) -> bool:
    if min_val is not None:
        if value is None:
            return False
        if value < min_val - 1e-9:
            return False
    if max_val is not None:
        if value is None:
            return False
        if value > max_val + 1e-9:
            return False
    return True


def _unix_to_ts(raw: Any) -> float | None:

    if raw is None:

        return None

    try:

        ts = float(raw)

        if ts > 1e12:

            ts /= 1000.0

        return ts

    except (TypeError, ValueError):

        return None





def _unix_to_ist_date_str(raw: Any) -> str | None:

    ts = _unix_to_ts(raw)

    if ts is None:

        return None

    try:

        return datetime.fromtimestamp(ts, tz=IST).strftime("%Y-%m-%d")

    except (OSError, OverflowError, ValueError):

        return None





def _ist_month_start(year: int, month: int) -> datetime:

    return datetime(year, month, 1, 0, 0, 0, tzinfo=IST)





def _ist_month_end(year: int, month: int) -> datetime:

    last = calendar.monthrange(year, month)[1]

    return datetime(year, month, last, 23, 59, 59, tzinfo=IST)





def _reported_date_range_ts(year: int, month: int | None) -> tuple[int, int] | None:

    """Inclusive unix range for reported earnings_release_date in IST."""

    if month is not None:

        start = _ist_month_start(year, month)

        end = _ist_month_end(year, month)

        return int(start.timestamp()), int(end.timestamp())

    start = _ist_month_start(year, 1)

    end = _ist_month_end(year, 12)

    return int(start.timestamp()), int(end.timestamp())


def _validate_calendar_month(month: int | None) -> int:

    m = int(month)  # type: ignore[arg-type]

    if m < 1 or m > 12:

        raise ValueError("month must be 1–12")

    return m


def _validate_month_range_order(
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> None:

    if (from_year, from_month) > (to_year, to_month):

        raise ValueError("From month must not be after To month")


def _reported_month_range_ts(
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> tuple[int, int]:

    """Inclusive IST range from first day of from_month through last day of to_month."""

    _validate_month_range_order(from_year, from_month, to_year, to_month)

    start = _ist_month_start(from_year, from_month)

    end = _ist_month_end(to_year, to_month)

    return int(start.timestamp()), int(end.timestamp())


def _ist_week_range_ts(week_offset: int = 0) -> tuple[int, int]:

    """

    Monday 00:00:00 through Sunday 23:59:59 IST.

    week_offset 0 = current week, -1 = previous calendar week.

    """

    now = datetime.now(IST)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    monday = today_start - timedelta(days=now.weekday())

    monday = monday + timedelta(weeks=week_offset)

    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return int(monday.timestamp()), int(sunday.timestamp())


ReportWindow = Literal["this_week", "prev_week", "month_range", "rolling_10_days"]


def resolve_reported_date_range(
    *,
    year: int | None = None,
    month: int | None = None,
    report_window: str | None = None,
    range_from_year: int | None = None,
    range_from_month: int | None = None,
    range_to_year: int | None = None,
    range_to_month: int | None = None,
) -> tuple[tuple[int, int], str]:
    """
    Returns (unix_start, unix_end) and a short cache-key token for reported mode.
    """
    rw = (report_window or "").strip().lower()

    if rw == "this_week":

        return _ist_week_range_ts(0), "w:0"

    if rw in ("prev_week", "previous_week"):

        return _ist_week_range_ts(-1), "w:-1"

    if rw == "month_range":

        fy = clamp_report_year(range_from_year)

        ty = clamp_report_year(range_to_year)

        fm = _validate_calendar_month(range_from_month)

        tm = _validate_calendar_month(range_to_month)

        return _reported_month_range_ts(fy, fm, ty, tm), f"r:{fy}:{fm}:{ty}:{tm}"

    if rw == "rolling_10_days":

        now = datetime.now(IST)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        start = today_start - timedelta(days=10)

        end = today_start + timedelta(hours=23, minutes=59, seconds=59)

        return (int(start.timestamp()), int(end.timestamp())), "rw:10"

    yr = clamp_report_year(year)

    mo = resolve_report_month(month)

    mo_key = mo if mo is not None else 0

    return _reported_date_range_ts(yr, mo), f"y:{yr}:{mo_key}"


def _period_date_range_ts(period: Period) -> tuple[int, int]:

    now = datetime.now(IST)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)



    if period == "coming_week":

        end = today_start + timedelta(days=7, hours=23, minutes=59, seconds=59)

        return int(today_start.timestamp()), int(end.timestamp())



    if period == "rolling_30_days":

        end = today_start + timedelta(days=30, hours=23, minutes=59, seconds=59)

        return int(today_start.timestamp()), int(end.timestamp())



    if period == "rolling_20_days":

        end = today_start + timedelta(days=20, hours=23, minutes=59, seconds=59)

        return int(today_start.timestamp()), int(end.timestamp())



    if period == "this_month":

        y, m = now.year, now.month

    elif period == "next_month":

        y, m = _shift_month(now.year, now.month, 1)

    else:  # month_after

        y, m = _shift_month(now.year, now.month, 2)



    start = _ist_month_start(y, m)

    end = _ist_month_end(y, m)

    return int(start.timestamp()), int(end.timestamp())





def _apply_mcap_filter(

    rows: list[dict[str, Any]],

    mcap_min: float | None,

    mcap_max: float | None,

) -> list[dict[str, Any]]:

    if mcap_min is None and mcap_max is None:

        return rows

    out: list[dict[str, Any]] = []

    for row in rows:

        mcap = _num(row.get("market_cap_basic"))

        if mcap is None:

            continue

        if mcap_min is not None and mcap < mcap_min:

            continue

        if mcap_max is not None and mcap > mcap_max:

            continue

        out.append(row)

    return out





def _normalize_symbol_list(symbols: list[str] | None) -> list[str]:
    if not symbols:
        return []
    out: list[str] = []
    for raw in symbols:
        s = str(raw or "").strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def _days_since_report_ist(ymd: str | None) -> int | None:
    """IST calendar days since earnings_release_date (0 = today)."""
    if not ymd:
        return None
    try:
        parts = str(ymd).strip().split("-")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        report_day = datetime(y, m, d, tzinfo=IST).date()
    except (ValueError, TypeError, IndexError):
        return None
    today = datetime.now(IST).date()
    return (today - report_day).days


def _report_window_max_age_days(report_window: str | None) -> int | None:
    rw = (report_window or "").strip().lower()
    if rw == "rolling_10_days":
        return 10
    return None


def _fetch_reported_rows_for_symbols(
    symbols: list[str],
    *,
    max_age_days: int | None,
    mcap_min: float | None,
    mcap_max: float | None,
    eps_surprise_min: float | None,
    eps_surprise_max: float | None,
    revenue_surprise_min: float | None,
    revenue_surprise_max: float | None,
    legacy_both_positive: bool,
) -> list[dict[str, Any]]:
    """
    Per-symbol TV lookup (portfolio/watchlist). Avoids market-wide scan row caps.
    Filters by earnings_release_date age in Python when max_age_days is set.
    """
    from tradingview_screener import col, stocks

    unique = _normalize_symbol_list(symbols)
    if not unique:
        return []

    parsed: list[dict[str, Any]] = []
    chunk_size = 80
    for i in range(0, len(unique), chunk_size):
        chunk = unique[i : i + chunk_size]
        where_parts: list[Any] = [col("name").isin(chunk)]
        if mcap_min is not None:
            where_parts.append(col("market_cap_basic") >= mcap_min)
        if mcap_max is not None:
            where_parts.append(col("market_cap_basic") <= mcap_max)

        q = (
            stocks("india")
            .select(
                "name",
                "earnings_per_share_fq",
                "earnings_per_share_forecast_fq",
                "eps_surprise_percent_fq",
                "total_revenue_fq",
                "revenue_forecast_fq",
                "revenue_surprise_percent_fq",
                "earnings_release_date",
                "market_cap_basic",
                "close",
                "change",
            )
            .where(*where_parts)
            .limit(max(len(chunk) * 3, 120))
        )
        _total, df = q.get_scanner_data()
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", ""))
            name = str(row.get("name", ""))
            item = _row_reported(ticker, name, row)
            if item is None:
                continue
            if max_age_days is not None:
                days = _days_since_report_ist(item.get("earnings_release_date"))
                if days is None or days < 0 or days > max_age_days:
                    continue
            if not row_passes_surprise_filters(
                item,
                eps_surprise_min=eps_surprise_min,
                eps_surprise_max=eps_surprise_max,
                revenue_surprise_min=revenue_surprise_min,
                revenue_surprise_max=revenue_surprise_max,
                legacy_both_positive=legacy_both_positive,
            ):
                continue
            parsed.append(item)
    return parsed


def fetch_upcoming_estimates_for_symbols(
    symbols: list[str],
    *,
    mcap_min: float | None = None,
    mcap_max: float | None = None,
) -> list[dict[str, Any]]:
    """
    Per-symbol TradingView upcoming-estimate lookup.
    Used by chart earnings markers when TradingView has estimates but has not yet
    published a complete reported surprise row for the same quarter.
    """
    from tradingview_screener import col, stocks

    unique = _normalize_symbol_list(symbols)
    if not unique:
        return []

    parsed: list[dict[str, Any]] = []
    chunk_size = 80
    for i in range(0, len(unique), chunk_size):
        chunk = unique[i : i + chunk_size]
        where_parts: list[Any] = [col("name").isin(chunk)]
        if mcap_min is not None:
            where_parts.append(col("market_cap_basic") >= mcap_min)
        if mcap_max is not None:
            where_parts.append(col("market_cap_basic") <= mcap_max)

        q = (
            stocks("india")
            .select(
                "name",
                "earnings_release_next_date",
                "earnings_per_share_forecast_next_fq",
                "revenue_forecast_next_fq",
                "earnings_per_share_forecast_fq",
                "revenue_forecast_fq",
                "market_cap_basic",
                "close",
                "change",
            )
            .where(*where_parts)
            .limit(max(len(chunk) * 3, 120))
        )
        _total, df = q.get_scanner_data()
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", ""))
            name = str(row.get("name", ""))
            item = _row_upcoming(ticker, name, row)
            if item is None:
                continue
            parsed.append(item)

    deduped = _dedupe_nse(parsed)
    if mcap_min is not None or mcap_max is not None:
        deduped = _apply_mcap_filter(deduped, mcap_min, mcap_max)
    deduped.sort(key=lambda r: r.get("earnings_release_next_date") or "")
    return deduped


def _row_reported(ticker: str, name: str, s: Any) -> dict[str, Any] | None:

    ex, sym = _parse_ticker(ticker)

    if not sym:

        return None



    eps_actual = _num(s.get("earnings_per_share_fq"))

    eps_est = _num(s.get("earnings_per_share_forecast_fq"))

    rev_actual = _num(s.get("total_revenue_fq"))

    rev_est = _num(s.get("revenue_forecast_fq"))

    eps_surp_pct = _surprise_pct_fq(
        eps_actual,
        eps_est,
        s.get("eps_surprise_percent_fq"),
    )

    rev_surp_pct = _surprise_pct_fq(
        rev_actual,
        rev_est,
        s.get("revenue_surprise_percent_fq"),
    )



    return {

        "ticker": ticker,

        "exchange": ex or None,

        "symbol": sym,

        "name": str(name or sym),

        "eps_actual": eps_actual,

        "eps_estimate": eps_est,

        "eps_surprise_pct": eps_surp_pct,

        "revenue_actual": rev_actual,

        "revenue_estimate": rev_est,

        "revenue_surprise_pct": rev_surp_pct,

        "earnings_release_date": _unix_to_ist_date_str(s.get("earnings_release_date")),

        "market_cap_basic": _num(s.get("market_cap_basic")),

        "price": _num(s.get("close")),

        "change_1d_pct": _num(s.get("change")),

    }





def _row_upcoming(ticker: str, name: str, s: Any) -> dict[str, Any] | None:

    ex, sym = _parse_ticker(ticker)

    if not sym:

        return None



    eps_est = _num(s.get("earnings_per_share_forecast_next_fq"))

    if eps_est is None:

        eps_est = _num(s.get("earnings_per_share_forecast_fq"))

    rev_est = _num(s.get("revenue_forecast_next_fq"))

    if rev_est is None:

        rev_est = _num(s.get("revenue_forecast_fq"))



    next_raw = s.get("earnings_release_next_date")

    if _unix_to_ts(next_raw) is None:

        return None



    return {

        "ticker": ticker,

        "exchange": ex or None,

        "symbol": sym,

        "name": str(name or sym),

        "eps_estimate": eps_est,

        "revenue_estimate": rev_est,

        "earnings_release_next_date": _unix_to_ist_date_str(next_raw),

        "market_cap_basic": _num(s.get("market_cap_basic")),

        "price": _num(s.get("close")),

        "change_1d_pct": _num(s.get("change")),

    }





def surprise_filters_active(
    eps_surprise_min: float | None,
    eps_surprise_max: float | None,
    revenue_surprise_min: float | None,
    revenue_surprise_max: float | None,
) -> bool:
    return any(
        x is not None
        for x in (
            eps_surprise_min,
            eps_surprise_max,
            revenue_surprise_min,
            revenue_surprise_max,
        )
    )


def row_passes_surprise_filters(
    item: dict[str, Any],
    *,
    eps_surprise_min: float | None,
    eps_surprise_max: float | None,
    revenue_surprise_min: float | None,
    revenue_surprise_max: float | None,
    legacy_both_positive: bool,
) -> bool:
    eps = item.get("eps_surprise_pct")
    rev = item.get("revenue_surprise_pct")
    if legacy_both_positive:
        return (
            _passes_surprise_bound(eps, min_val=0.0, max_val=None)
            and _passes_surprise_bound(rev, min_val=0.0, max_val=None)
        )
    if not _passes_surprise_bound(eps, min_val=eps_surprise_min, max_val=eps_surprise_max):
        return False
    if not _passes_surprise_bound(rev, min_val=revenue_surprise_min, max_val=revenue_surprise_max):
        return False
    return True


def _response_meta(

    *,

    mode: Mode,

    now: float,

    cached: bool,

    rows: list[dict[str, Any]],

    scanner_total: int | None = None,

    year: int | None = None,

    month: int | None = None,

    period: str | None = None,

    mcap_min: float | None = None,

    mcap_max: float | None = None,

    eps_surprise_min: float | None = None,

    eps_surprise_max: float | None = None,

    revenue_surprise_min: float | None = None,

    revenue_surprise_max: float | None = None,

    legacy_both_positive: bool = False,

    matched_symbols: int | None = None,

    row_limit: int | None = None,

) -> dict[str, Any]:

    truncated = (
        matched_symbols is not None
        and row_limit is not None
        and matched_symbols > len(rows)
    )

    return {

        "source": "tradingview_screener",

        "market": "india",

        "mode": mode,

        "cached": cached,

        "fetched_at": now,

        "scanner_total": scanner_total,

        "matched_symbols": matched_symbols if matched_symbols is not None else len(rows),

        "truncated": truncated,

        "row_limit": row_limit,

        "total_matches": len(rows),

        "count": len(rows),

        "rows": rows,

        "filters": {

            "year": year,

            "month": month,

            "period": period,

            "mcap_min": mcap_min,

            "mcap_max": mcap_max,

            "eps_surprise_min": eps_surprise_min,

            "eps_surprise_max": eps_surprise_max,

            "revenue_surprise_min": revenue_surprise_min,

            "revenue_surprise_max": revenue_surprise_max,

            "legacy_both_positive": legacy_both_positive,

        },

        "available_years": available_report_years(),

        "min_report_year": MIN_REPORT_YEAR,

        "max_report_year": current_year_ist(),

    }





def fetch_earnings_calendar(

    *,

    mode: Mode = "reported",

    year: int | None = None,

    month: int | None = None,

    period: str | None = "this_month",

    report_window: str | None = None,

    range_from_year: int | None = None,

    range_from_month: int | None = None,

    range_to_year: int | None = None,

    range_to_month: int | None = None,

    mcap_min: float | None = None,

    mcap_max: float | None = None,

    eps_surprise_min: float | None = None,

    eps_surprise_max: float | None = None,

    revenue_surprise_min: float | None = None,

    revenue_surprise_max: float | None = None,

    limit: int = 500,

    require_both: bool = False,

    use_cache: bool = True,

    symbols: list[str] | None = None,

) -> dict[str, Any]:

    """

    Reported: latest-quarter EPS/revenue surprise %, filtered by report month/year (IST).

    Upcoming: next earnings date in the chosen period window (IST), with estimates.

    Empty surprise bounds: no surprise filter (includes beats and misses).

    Set eps/revenue min/max and/or require_both=True for dual-beat-only lists.

    """

    limit = max(1, min(int(limit), 2000))

    symbol_list = _normalize_symbol_list(symbols)

    now = time.time()

    custom_surprise = surprise_filters_active(
        eps_surprise_min,
        eps_surprise_max,
        revenue_surprise_min,
        revenue_surprise_max,
    )
    legacy_both_positive = (not custom_surprise) and require_both



    if mode == "reported":

        period_val = None

        date_range, window_key = resolve_reported_date_range(
            year=year,
            month=month,
            report_window=report_window,
            range_from_year=range_from_year,
            range_from_month=range_from_month,
            range_to_year=range_to_year,
            range_to_month=range_to_month,
        )

        yr = clamp_report_year(year)

        mo = resolve_report_month(month)

        cache_key = (

            f"reported:tvclose:{window_key}:{mcap_min}:{mcap_max}:"
            f"{eps_surprise_min}:{eps_surprise_max}:"
            f"{revenue_surprise_min}:{revenue_surprise_max}:"
            f"{legacy_both_positive}:{limit}"

        )

        if symbol_list:
            sym_key = ",".join(symbol_list[:200])
            if len(symbol_list) > 200:
                sym_key += f"+{len(symbol_list)}"
            cache_key += f":sym:{sym_key}"

    else:

        yr = None

        mo = None

        period_val = validate_period(period)

        date_range = _period_date_range_ts(period_val)

        cache_key = f"upcoming:tvclose:{period_val}:{mcap_min}:{mcap_max}:{limit}"



    if use_cache and cache_key in _cache:

        rows, ts = _cache[cache_key]

        if now - ts < _CACHE_TTL_SEC:

            meta = _response_meta(

                mode=mode,

                now=ts,

                cached=True,

                rows=rows,

                year=yr,

                month=mo,

                period=period_val,

                mcap_min=mcap_min,

                mcap_max=mcap_max,

                eps_surprise_min=eps_surprise_min,

                eps_surprise_max=eps_surprise_max,

                revenue_surprise_min=revenue_surprise_min,

                revenue_surprise_max=revenue_surprise_max,

                legacy_both_positive=legacy_both_positive,

            )

            return meta



    try:

        from tradingview_screener import Query, col, stocks

    except ImportError as e:

        raise RuntimeError(

            "tradingview-screener is not installed. Run: pip install tradingview-screener"

        ) from e



    # Surprise % is applied in Python after _row_reported computes % from actual/estimate.
    # TradingView surprise columns are often null (e.g. GRASIM revenue beat) so TV where
    # clauses would drop rows that the UI would show as large beats.
    surprise_filtering = custom_surprise or legacy_both_positive
    scan_limit = (
        min(max(limit * 10, 1500), 5000)
        if surprise_filtering
        else min(max(limit * 5, 1000), 5000)
    )

    start_ts, end_ts = date_range

    parsed: list[dict[str, Any]] = []
    scanner_total = 0

    if mode == "reported" and symbol_list:
        max_age = _report_window_max_age_days(report_window)
        parsed = _fetch_reported_rows_for_symbols(
            symbol_list,
            max_age_days=max_age,
            mcap_min=mcap_min,
            mcap_max=mcap_max,
            eps_surprise_min=eps_surprise_min,
            eps_surprise_max=eps_surprise_max,
            revenue_surprise_min=revenue_surprise_min,
            revenue_surprise_max=revenue_surprise_max,
            legacy_both_positive=legacy_both_positive,
        )
        scanner_total = len(symbol_list)
    else:
        if mode == "reported":
            where_parts = [
                col("earnings_release_date") >= start_ts,
                col("earnings_release_date") <= end_ts,
            ]
            if mcap_min is not None:
                where_parts.append(col("market_cap_basic") >= mcap_min)
            if mcap_max is not None:
                where_parts.append(col("market_cap_basic") <= mcap_max)
            q = (
                stocks("india")
                .select(
                    "name",
                    "earnings_per_share_fq",
                    "earnings_per_share_forecast_fq",
                    "eps_surprise_percent_fq",
                    "total_revenue_fq",
                    "revenue_forecast_fq",
                    "revenue_surprise_percent_fq",
                    "earnings_release_date",
                    "market_cap_basic",
                    "close",
                    "change",
                )
                .where(*where_parts)
                .order_by("market_cap_basic", ascending=False)
                .limit(scan_limit)
            )
            parse_row = _row_reported
        else:
            where_parts = [
                col("earnings_release_next_date") >= start_ts,
                col("earnings_release_next_date") <= end_ts,
            ]
            if mcap_min is not None:
                where_parts.append(col("market_cap_basic") >= mcap_min)
            if mcap_max is not None:
                where_parts.append(col("market_cap_basic") <= mcap_max)
            q = (
                stocks("india")
                .select(
                    "name",
                    "earnings_release_next_date",
                    "earnings_per_share_forecast_next_fq",
                    "revenue_forecast_next_fq",
                    "earnings_per_share_forecast_fq",
                    "revenue_forecast_fq",
                    "market_cap_basic",
                    "close",
                    "change",
                )
                .where(*where_parts)
                .order_by("market_cap_basic", ascending=False)
                .limit(scan_limit)
            )
            parse_row = _row_upcoming

        total_raw, df = q.get_scanner_data()
        scanner_total = int(total_raw or 0)

        if df is None or df.empty:
            empty = _response_meta(
                mode=mode,
                now=now,
                cached=False,
                rows=[],
                scanner_total=scanner_total,
                year=yr,
                month=mo,
                period=period_val,
                mcap_min=mcap_min,
                mcap_max=mcap_max,
                eps_surprise_min=eps_surprise_min,
                eps_surprise_max=eps_surprise_max,
                revenue_surprise_min=revenue_surprise_min,
                revenue_surprise_max=revenue_surprise_max,
                legacy_both_positive=legacy_both_positive,
            )
            if use_cache:
                _cache[cache_key] = ([], now)
            return empty

        for _, row in df.iterrows():
            ticker = str(row.get("ticker", ""))
            name = str(row.get("name", ""))
            item = parse_row(ticker, name, row)
            if item is None:
                continue
            if mode == "reported" and not row_passes_surprise_filters(
                item,
                eps_surprise_min=eps_surprise_min,
                eps_surprise_max=eps_surprise_max,
                revenue_surprise_min=revenue_surprise_min,
                revenue_surprise_max=revenue_surprise_max,
                legacy_both_positive=legacy_both_positive,
            ):
                continue
            parsed.append(item)



    deduped = _dedupe_nse(parsed)

    if mcap_min is not None or mcap_max is not None:

        deduped = _apply_mcap_filter(deduped, mcap_min, mcap_max)



    if mode == "reported":

        deduped.sort(

            key=lambda r: (

                -(r.get("revenue_surprise_pct") or 0),

                -(r.get("eps_surprise_pct") or 0),

            ),

        )

    else:

        deduped.sort(

            key=lambda r: (

                r.get("earnings_release_next_date") or "",

                -(r.get("market_cap_basic") or 0),

            ),

        )



    matched_symbols = len(deduped)

    deduped = deduped[:limit]



    if use_cache:

        _cache[cache_key] = (deduped, now)



    return _response_meta(

        mode=mode,

        now=now,

        cached=False,

        rows=deduped,

        scanner_total=scanner_total,

        matched_symbols=matched_symbols,

        row_limit=limit,

        year=yr,

        month=mo,

        period=period_val,

        mcap_min=mcap_min,

        mcap_max=mcap_max,

        eps_surprise_min=eps_surprise_min,

        eps_surprise_max=eps_surprise_max,

        revenue_surprise_min=revenue_surprise_min,

        revenue_surprise_max=revenue_surprise_max,

        legacy_both_positive=legacy_both_positive,

    )





def fetch_earnings_beats(

    *,

    limit: int = 500,

    require_both: bool = True,

    use_cache: bool = True,

    year: int | None = None,

    month: int | None = None,

    mcap_min: float | None = None,

    mcap_max: float | None = None,

) -> dict[str, Any]:

    """Backward-compatible wrapper for reported beats."""

    return fetch_earnings_calendar(

        mode="reported",

        year=year,

        month=month,

        mcap_min=mcap_min,

        mcap_max=mcap_max,

        limit=limit,

        require_both=require_both,

        use_cache=use_cache,

    )


