"""

TradingView India screener — earnings beats (reported) and upcoming releases.

Uses TradingView's scanner API (same data family as Financials → Earnings).

"""



from __future__ import annotations



import calendar
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MIN_REPORT_YEAR = 2024

_CACHE_TTL_SEC = 300  # 5 minutes
# Recent-report re-sync window (TV often corrects FQ fields 1–2 days after print).
RECENT_RESYNC_LOOKBACK_DAYS = 4

# In-memory cache: cache_key -> (rows, fetched_at)
_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}
# Cache: IST date YYYY-MM-DD -> (frozenset symbols, fetched_at)
_earnings_today_cache: dict[str, tuple[frozenset[str], float]] = {}
_EARNINGS_TODAY_TTL_SEC = 300
# Single-flight: concurrent identical TV scans share one fetch (avoids stampede).
_inflight_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}


def clear_earnings_calendar_cache() -> None:
    """Drop in-memory TV calendar caches so the next fetch hits TradingView."""
    _cache.clear()
    _earnings_today_cache.clear()


def _parse_rolling_past_days(window_key: str) -> int | None:
    """Parse ``rolling_N_days`` → N (past calendar days including today)."""
    rw = (window_key or "").strip().lower()
    if not (rw.startswith("rolling_") and rw.endswith("_days")):
        return None
    mid = rw[len("rolling_") : -len("_days")]
    if not mid.isdigit():
        return None
    n = int(mid)
    if n < 1 or n > 30:
        return None
    return n


def _rolling_past_days_range_ts(days: int) -> tuple[int, int]:
    now = datetime.now(IST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today_start - timedelta(days=max(1, int(days)))
    end = today_start + timedelta(hours=23, minutes=59, seconds=59)
    return int(start.timestamp()), int(end.timestamp())



Mode = Literal["reported", "upcoming"]

Period = Literal[
    "this_month",
    "next_month",
    "month_after",
    "coming_week",
    "rolling_30_days",
    "rolling_20_days",
    "today",  # legacy alias → current_trading_day
    "current_trading_day",
    "next_day",
    "next_5_days",
    "this_week",
    "next_week",
]


def lookup_tv_close_prices(symbols: list[str]) -> dict[str, float]:
    """TradingView last close for symbols missing from local screener (NSE preferred)."""
    return {s: m["price"] for s, m in lookup_tv_market_metrics(symbols).items() if m.get("price")}


def lookup_tv_market_metrics(symbols: list[str]) -> dict[str, dict[str, float | None]]:
    """TradingView close, 1D %, 1M %, and P/E (TTM) for symbols missing from local screener."""
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
                .select("name", "close", "change", "change|1M", "price_earnings_ttm")
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
            chg_1m = _num(rec.get("change|1M"))
            pe = _num(rec.get("price_earnings_ttm"))
            out[sym] = {
                "price": round(px, 2) if px is not None and px > 0 else None,
                "change_1d_pct": round(chg, 2) if chg is not None else None,
                "change_1m_pct": round(chg_1m, 2) if chg_1m is not None else None,
                "price_earnings_ttm": round(pe, 2) if pe is not None else None,
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





def normalize_earnings_window_key(key: str | None) -> str:
    """Map legacy UI/API keys onto the TV-aligned vocabulary."""
    k = (key or "").strip().lower()
    aliases = {
        "today": "current_trading_day",
        "yesterday": "previous_day",
        "today_yesterday": "current_trading_day",
        "today_and_yesterday": "current_trading_day",
        "previous_week": "prev_week",
    }
    return aliases.get(k, k)


def validate_period(period: str | None) -> Period:
    p = normalize_earnings_window_key(period or "this_month")
    allowed = (
        "this_month",
        "next_month",
        "month_after",
        "coming_week",
        "rolling_30_days",
        "rolling_20_days",
        "current_trading_day",
        "next_day",
        "next_5_days",
        "this_week",
        "next_week",
    )
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


# When TV's absolute actual and surprise % disagree (common right after results),
# prefer estimate + surprise → implied actual. Matches TradingView earnings calendar.
_SURPRISE_ACTUAL_MISMATCH_PP = 0.5


def _implied_actual_from_surprise(
    estimate: float | None,
    surprise_pct: float | None,
) -> float | None:
    e = _num(estimate)
    s = _num(surprise_pct)
    if e is None or s is None:
        return None
    return e * (1.0 + s / 100.0)


def _computed_surprise_pct(actual: float | None, estimate: float | None) -> float | None:
    a = _num(actual)
    e = _num(estimate)
    if a is None or e is None:
        return None
    if e == 0:
        if a == 0:
            return 0.0
        return 100.0 if a > 0 else -100.0
    return ((a - e) / abs(e)) * 100.0


def _reconcile_actual_vs_tv_surprise(
    actual: float | None,
    estimate: float | None,
    tv_surprise_pct: float | None,
    *,
    allow_rewrite_actual: bool = True,
) -> tuple[float | None, float | None]:
    """
    Return (actual, surprise_pct) reconciled for display/filters.

    When TV surprise contradicts actual vs estimate:
    - Revenue (allow_rewrite_actual=True): replace stale actual with the value
      implied by estimate + TV surprise (DEEPAKNTR-style scanner lag).
    - EPS (allow_rewrite_actual=False): keep scanner actual and recompute surprise
      so a stale surprise % cannot turn a real beat into a fake miss (Pidilite).
    """
    a = _num(actual)
    e = _num(estimate)
    tv = _num(tv_surprise_pct)
    if tv is None:
        return a, _computed_surprise_pct(a, e)
    if a is None or e is None or e == 0:
        return a, tv
    computed = _computed_surprise_pct(a, e)
    if computed is None:
        return a, tv
    if abs(computed - tv) <= _SURPRISE_ACTUAL_MISMATCH_PP:
        return a, tv
    if not allow_rewrite_actual:
        return a, computed
    implied = _implied_actual_from_surprise(e, tv)
    if implied is None:
        return a, tv
    return implied, tv


def _round_surprise_pct_display(value: float) -> float:
    """
    Round surprise % to 2 decimals (half-up), matching the Earnings table.
    Uses Decimal so 0.995 → 1.00 (binary float formatting alone would keep 0.99).
    """
    from decimal import Decimal, ROUND_HALF_UP

    return float(
        Decimal(str(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _passes_surprise_bound(
    value: float | None,
    *,
    min_val: float | None,
    max_val: float | None,
) -> bool:
    """
    Inclusive surprise % bounds (what the Earnings tab inputs mean):
      min N → value >= N
      max N → value <= N
    Compared at 2-decimal display precision so a row showing +1.00% passes min=1.
    """
    if min_val is None and max_val is None:
        return True
    if value is None:
        return False
    display = _round_surprise_pct_display(value)
    if min_val is not None and display < _round_surprise_pct_display(min_val):
        return False
    if max_val is not None and display > _round_surprise_pct_display(max_val):
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

    week_offset 0 = current week, -1 = previous calendar week, +1 = next.

    """

    now = datetime.now(IST)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    monday = today_start - timedelta(days=now.weekday())

    monday = monday + timedelta(weeks=week_offset)

    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return int(monday.timestamp()), int(sunday.timestamp())


ReportWindow = Literal[
    "this_week",
    "prev_week",
    "next_week",
    "month_range",
    "rolling_10_days",
    "rolling_4_days",
    "today",  # legacy → current_trading_day
    "yesterday",  # legacy → previous_day
    "today_yesterday",  # legacy → current_trading_day
    "current_trading_day",
    "previous_day",
    "previous_5_days",
    "next_day",
    "next_5_days",
]


def _nse_session_day(d: date) -> bool:
    """True if `d` is an NSE session day (uses nse_calendar holidays when available)."""
    try:
        from server.movers_data import _is_nse_session_day as _check
        return bool(_check(d))
    except Exception:
        try:
            from movers_data import _is_nse_session_day as _check  # type: ignore
            return bool(_check(d))
        except Exception:
            return d.weekday() < 5


def _current_trading_day_anchor(today: date | None = None) -> date:
    """Last/current NSE session day on or before `today` (IST)."""
    d = today or datetime.now(IST).date()
    if _nse_session_day(d):
        return d
    for i in range(1, 15):
        prev = d - timedelta(days=i)
        if _nse_session_day(prev):
            return prev
    return d


def _inclusive_date_range_ts(start_d: date, end_d: date) -> tuple[int, int]:
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    start = datetime(start_d.year, start_d.month, start_d.day, 0, 0, 0, tzinfo=IST)
    end = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59, tzinfo=IST)
    return int(start.timestamp()), int(end.timestamp())


def _day_bounds_ts(d: date) -> tuple[int, int]:
    return _inclusive_date_range_ts(d, d)


def _current_trading_day_range_ts() -> tuple[int, int]:
    """Session day = that day; non-session = last session through today (Fri–Sun on weekends)."""
    today = datetime.now(IST).date()
    anchor = _current_trading_day_anchor(today)
    return _inclusive_date_range_ts(anchor, today)


def _previous_day_range_ts() -> tuple[int, int]:
    """One calendar day before the current/last trading-day anchor."""
    today = datetime.now(IST).date()
    anchor = _current_trading_day_anchor(today)
    return _day_bounds_ts(anchor - timedelta(days=1))


def _previous_5_days_range_ts() -> tuple[int, int]:
    """Five calendar days prior to the current trading-day anchor (excludes anchor)."""
    today = datetime.now(IST).date()
    anchor = _current_trading_day_anchor(today)
    return _inclusive_date_range_ts(anchor - timedelta(days=5), anchor - timedelta(days=1))


def _next_day_range_ts() -> tuple[int, int]:
    """Next calendar day after the current/last trading-day anchor."""
    today = datetime.now(IST).date()
    anchor = _current_trading_day_anchor(today)
    return _day_bounds_ts(anchor + timedelta(days=1))


def _next_5_days_range_ts() -> tuple[int, int]:
    """Five calendar days after the current trading-day anchor (excludes anchor)."""
    today = datetime.now(IST).date()
    anchor = _current_trading_day_anchor(today)
    return _inclusive_date_range_ts(anchor + timedelta(days=1), anchor + timedelta(days=5))


def _ist_calendar_day_span_ts(start_offset_days: int, end_offset_days: int = 0) -> tuple[int, int]:
    """Inclusive IST calendar-day span relative to today (legacy helper)."""
    now = datetime.now(IST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today_start + timedelta(days=int(start_offset_days))
    end = today_start + timedelta(days=int(end_offset_days), hours=23, minutes=59, seconds=59)
    if end < start:
        start, end = end.replace(hour=0, minute=0, second=0, microsecond=0), start.replace(
            hour=23, minute=59, second=59, microsecond=0
        )
    return int(start.timestamp()), int(end.timestamp())


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
    rw = normalize_earnings_window_key(report_window)

    if rw == "this_week":
        return _ist_week_range_ts(0), "w:0"

    if rw == "prev_week":
        return _ist_week_range_ts(-1), "w:-1"

    if rw == "next_week":
        return _ist_week_range_ts(1), "w:1"

    if rw == "month_range":
        fy = clamp_report_year(range_from_year)
        ty = clamp_report_year(range_to_year)
        fm = _validate_calendar_month(range_from_month)
        tm = _validate_calendar_month(range_to_month)
        return _reported_month_range_ts(fy, fm, ty, tm), f"r:{fy}:{fm}:{ty}:{tm}"

    if rw == "current_trading_day":
        return _current_trading_day_range_ts(), "rw:ctd"

    if rw == "previous_day":
        return _previous_day_range_ts(), "rw:prev_day"

    if rw == "previous_5_days":
        return _previous_5_days_range_ts(), "rw:prev_5"

    if rw == "next_day":
        return _next_day_range_ts(), "rw:next_day"

    if rw == "next_5_days":
        return _next_5_days_range_ts(), "rw:next_5"

    rolling_days = _parse_rolling_past_days(rw)
    if rolling_days is not None:
        return _rolling_past_days_range_ts(rolling_days), f"rw:{rolling_days}"

    yr = clamp_report_year(year)
    mo = resolve_report_month(month)
    mo_key = mo if mo is not None else 0
    return _reported_date_range_ts(yr, mo), f"y:{yr}:{mo_key}"


def _period_date_range_ts(period: Period) -> tuple[int, int]:
    now = datetime.now(IST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    p = normalize_earnings_window_key(period)

    if p == "current_trading_day":
        return _current_trading_day_range_ts()

    if p == "next_day":
        return _next_day_range_ts()

    if p == "next_5_days":
        return _next_5_days_range_ts()

    if p == "this_week":
        return _ist_week_range_ts(0)

    if p == "next_week":
        return _ist_week_range_ts(1)

    if p == "coming_week":
        end = today_start + timedelta(days=7, hours=23, minutes=59, seconds=59)
        return int(today_start.timestamp()), int(end.timestamp())

    if p == "rolling_30_days":
        end = today_start + timedelta(days=30, hours=23, minutes=59, seconds=59)
        return int(today_start.timestamp()), int(end.timestamp())

    if p == "rolling_20_days":
        end = today_start + timedelta(days=20, hours=23, minutes=59, seconds=59)
        return int(today_start.timestamp()), int(end.timestamp())

    if p == "this_month":
        y, m = now.year, now.month
    elif p == "next_month":
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
    rolling_days = _parse_rolling_past_days(rw)
    if rolling_days is not None:
        return rolling_days
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
                "change|1M",
                "price_earnings_ttm",
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
                "change|1M",
                "price_earnings_ttm",
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

    eps_actual, eps_surp_pct = _reconcile_actual_vs_tv_surprise(
        eps_actual,
        eps_est,
        _num(s.get("eps_surprise_percent_fq")),
        allow_rewrite_actual=False,
    )

    rev_actual, rev_surp_pct = _reconcile_actual_vs_tv_surprise(
        rev_actual,
        rev_est,
        _num(s.get("revenue_surprise_percent_fq")),
        allow_rewrite_actual=True,
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

        "change_1m_pct": _num(s.get("change|1M")),

        "price_earnings_ttm": _num(s.get("price_earnings_ttm")),

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

        "change_1m_pct": _num(s.get("change|1M")),

        "price_earnings_ttm": _num(s.get("price_earnings_ttm")),

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


def _metric_passes_with_sibling_fallback(
    value: float | None,
    *,
    min_val: float | None,
    max_val: float | None,
    sibling: float | None,
) -> bool:
    """
    Apply min/max on one surprise metric.
    If that metric is null (company did not publish vs estimate) but the sibling
    surprise is available for the same quarter, do not fail this dimension.
    If both are null, fail when a bound is set.
    """
    if min_val is None and max_val is None:
        return True
    if value is None:
        return sibling is not None
    return _passes_surprise_bound(value, min_val=min_val, max_val=max_val)


def is_beat_report_row(row: dict[str, Any]) -> bool:
    """
    Beat when every measurable surprise dimension is >= 0.
    If TV omits an estimate, that dimension is not measurable; a beat on the
    sibling surprise also requires reported actual for the missing-estimate metric.
    """
    eps_surp = _num(row.get("eps_surprise_pct"))
    rev_surp = _num(row.get("revenue_surprise_pct"))
    eps_actual = _num(row.get("eps_actual"))
    rev_actual = _num(row.get("revenue_actual"))

    if eps_surp is not None and eps_surp < 0:
        return False
    if rev_surp is not None and rev_surp < 0:
        return False

    eps_measurable = eps_surp is not None
    rev_measurable = rev_surp is not None

    if eps_measurable and rev_measurable:
        if (
            eps_actual is None
            and rev_actual is None
            and eps_surp == 0
            and rev_surp == 0
        ):
            return False
        return eps_surp >= 0 and rev_surp >= 0

    if rev_measurable and not eps_measurable:
        return rev_surp >= 0 and eps_actual is not None

    if eps_measurable and not rev_measurable:
        return eps_surp >= 0 and rev_actual is not None

    return False


def is_tv_eps_rev_beat_row(row: dict[str, Any]) -> bool:
    """
    Strict TradingView dual beat: reported EPS > estimate AND reported revenue > estimate.
    Both act/est pairs must be present (no sibling-null fallback).
    """
    eps_a = _num(row.get("eps_actual"))
    eps_e = _num(row.get("eps_estimate"))
    rev_a = _num(row.get("revenue_actual"))
    rev_e = _num(row.get("revenue_estimate"))
    if eps_a is None or eps_e is None or rev_a is None or rev_e is None:
        return False
    return eps_a > eps_e and rev_a > rev_e


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
    if not _metric_passes_with_sibling_fallback(
        eps,
        min_val=eps_surprise_min,
        max_val=eps_surprise_max,
        sibling=rev,
    ):
        return False
    if not _metric_passes_with_sibling_fallback(
        rev,
        min_val=revenue_surprise_min,
        max_val=revenue_surprise_max,
        sibling=eps,
    ):
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

    Upcoming: next earnings date in the chosen window (IST), with estimates. Takes either
    a period enum or, when report_window is set, the same windows reported mode accepts.

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

        if (report_window or "").strip():

            # Upcoming accepts the reported window vocabulary too, so one screener chip
            # can ask "earnings in July-August" against either release date.

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

        else:

            period_val = validate_period(period)

            date_range = _period_date_range_ts(period_val)

            window_key = f"p:{period_val}"

        cache_key = f"upcoming:tvclose:{window_key}:{mcap_min}:{mcap_max}:{limit}"



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

    # Coalesce concurrent cache-miss fetches for the same key (portfolio/watchlist stampede).
    waiter: threading.Event | None = None
    leader = False
    with _inflight_lock:
        existing = _inflight.get(cache_key)
        if existing is not None:
            waiter = existing
        else:
            waiter = threading.Event()
            _inflight[cache_key] = waiter
            leader = True
    if not leader and waiter is not None:
        waiter.wait(timeout=120)
        if use_cache and cache_key in _cache:
            rows, ts = _cache[cache_key]
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

    def _release_inflight() -> None:
        if not leader:
            return
        with _inflight_lock:
            ev = _inflight.pop(cache_key, None)
        if ev is not None:
            ev.set()

    try:

        from tradingview_screener import Query, col, stocks

    except ImportError as e:
        _release_inflight()
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
        try:
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
        except Exception:
            _release_inflight()
            raise
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
                    "change|1M",
                    "price_earnings_ttm",
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
                    "change|1M",
                    "price_earnings_ttm",
                )
                .where(*where_parts)
                .order_by("market_cap_basic", ascending=False)
                .limit(scan_limit)
            )
            parse_row = _row_upcoming

        try:
            total_raw, df = q.get_scanner_data()
        except Exception:
            _release_inflight()
            raise
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
            _release_inflight()
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

    meta = _response_meta(
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
    _release_inflight()
    return meta





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








# Cache: IST date YYYY-MM-DD -> (frozenset symbols, fetched_at)
# (_earnings_today_cache / _EARNINGS_TODAY_TTL_SEC declared near module top)



def symbols_with_earnings_today(*, use_cache: bool = True) -> set[str]:
    """
    NSE symbols with earnings releasing today (IST calendar day).

    Includes:
      - upcoming: earnings_release_next_date == today
      - reported: earnings_release_date == today (already out)
    """
    today = datetime.now(IST).date().isoformat()
    now = time.time()
    if use_cache:
        hit = _earnings_today_cache.get(today)
        if hit and (now - hit[1]) < _EARNINGS_TODAY_TTL_SEC:
            return set(hit[0])

    symbols: set[str] = set()

    try:
        upcoming = fetch_earnings_calendar(
            mode="upcoming",
            period="today",
            limit=2000,
            use_cache=use_cache,
        )
        for row in upcoming.get("rows") or []:
            if str(row.get("earnings_release_next_date") or "")[:10] != today:
                continue
            sym = str(row.get("symbol") or "").strip().upper()
            if sym:
                symbols.add(sym)
    except Exception as exc:
        print(f"[earnings_today] upcoming scan failed: {exc}")

    try:
        reported = fetch_earnings_calendar(
            mode="reported",
            report_window="today",
            limit=2000,
            use_cache=use_cache,
        )
        for row in reported.get("rows") or []:
            if str(row.get("earnings_release_date") or "")[:10] != today:
                continue
            sym = str(row.get("symbol") or "").strip().upper()
            if sym:
                symbols.add(sym)
    except Exception as exc:
        print(f"[earnings_today] reported scan failed: {exc}")

    _earnings_today_cache[today] = (frozenset(symbols), now)
    for key in list(_earnings_today_cache.keys()):
        if key != today:
            _earnings_today_cache.pop(key, None)
    return symbols


def fetch_recent_reported_for_resync(
    *,
    lookback_days: int | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    """
    Force-refresh TradingView reported rows for the recent release window.

    One market scan (not per-symbol). Clears the in-memory calendar cache first so
    TV corrections from the last day or two replace stale rows.
    """
    days = int(lookback_days) if lookback_days is not None else RECENT_RESYNC_LOOKBACK_DAYS
    days = max(1, min(14, days))
    clear_earnings_calendar_cache()
    payload = fetch_earnings_calendar(
        mode="reported",
        report_window=f"rolling_{days}_days",
        limit=max(1, min(2000, int(limit))),
        use_cache=False,
    )
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["resync_lookback_days"] = days
    return payload
