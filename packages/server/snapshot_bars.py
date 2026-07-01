"""
Chart-parity OHLC aggregation for indicator_snapshots rebuild.

Snapshots must use the same daily normalization, timeframe buckets, and MACD
math as /api/chart-data so filters match what users see on charts.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd

# Keep in sync with server.TIMEFRAME_CONFIG (snapshot-supported timeframes only).
TIMEFRAME_CONFIG = {
    "1D":  {"anchor": "day",   "days": 1},
    "2D":  {"anchor": "day",   "days": 2},
    "3D":  {"anchor": "day",   "days": 3},
    "4D":  {"anchor": "day",   "days": 4},
    "5D":  {"anchor": "day",   "days": 5},
    "6D":  {"anchor": "day",   "days": 6},
    "1W":  {"anchor": "week",  "weeks": 1},
    "2W":  {"anchor": "week",  "weeks": 2},
    "4W":  {"anchor": "week",  "weeks": 4},
    "1M":  {"anchor": "month", "months": 1},
}


def calculate_macd(
    closes: list,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """Same MACD as server.calculate_macd (12/26/9, 2dp rounding)."""
    n = len(closes)
    if n < slow + signal:
        return {
            "macd":      [None] * n,
            "signal":    [None] * n,
            "histogram": [None] * n,
        }

    def ema_full(data: list, period: int) -> list:
        k = 2.0 / (period + 1)
        ema = data[0]
        out = [ema]
        for p in data[1:]:
            ema = p * k + ema * (1 - k)
            out.append(ema)
        return out

    fast_ema = ema_full(closes, fast)
    slow_ema = ema_full(closes, slow)
    macd_raw = [round(f - s, 2) for f, s in zip(fast_ema, slow_ema)]

    sig_input = macd_raw[slow - 1:]
    sig_ema = ema_full(sig_input, signal)

    macd_out = [None] * (slow - 1) + macd_raw[slow - 1:]
    sig_out = [None] * (slow - 1 + signal - 1) + [round(v, 2) for v in sig_ema[signal - 1:]]
    hist_out = []
    for m, s in zip(macd_out, sig_out):
        if m is not None and s is not None:
            hist_out.append(round(m - s, 2))
        else:
            hist_out.append(None)

    return {"macd": macd_out, "signal": sig_out, "histogram": hist_out}


def _assign_period_key(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    cfg = TIMEFRAME_CONFIG.get(timeframe)
    if cfg is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_convert(None)
    df.sort_values("Date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    anchor = cfg["anchor"]
    if anchor == "day":
        n = cfg["days"]
        day_anchor = pd.Timestamp("1970-01-01")
        days_from_anchor = (df["Date"] - day_anchor).dt.days
        df["period_key"] = (days_from_anchor // n).astype(int)
    elif anchor == "week":
        weeks = cfg.get("weeks", 1)
        week_anchor = pd.Timestamp("1970-01-05")
        week_start = df["Date"] - pd.to_timedelta(df["Date"].dt.weekday, unit="D")
        weeks_from_anchor = ((week_start - week_anchor).dt.days // 7).astype(int)
        df["period_key"] = (weeks_from_anchor // weeks).astype(int)
    elif anchor == "month":
        months = cfg.get("months", 1)
        month_index = (df["Date"].dt.year * 12 + (df["Date"].dt.month - 1)).astype(int)
        df["period_key"] = (month_index // months).astype(int)

    return df


def normalize_daily_rows(
    candles: Sequence[Sequence],
) -> list[tuple[str, float, float, float, float]]:
    """
    Mirror /api/chart-data daily prep: numeric OHLC, dedupe by calendar day (last row wins).
    Input rows: (date, open, high, low, close) or with volume at index 5.
    """
    if not candles:
        return []

    rows = []
    for c in candles:
        if c[1] is None or c[2] is None or c[3] is None or c[4] is None:
            continue
        vol = float(c[5]) if len(c) > 5 and c[5] is not None else 0.0
        rows.append({
            "Date": str(c[0])[:10],
            "Open": round(float(c[1]), 2),
            "High": round(float(c[2]), 2),
            "Low": round(float(c[3]), 2),
            "Close": round(float(c[4]), 2),
            "Volume": vol,
        })

    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["_day"] = df["Date"].astype(str).str[:10]
    df["_vol"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
    df.sort_values(["_day", "_vol", "Date"], ascending=[True, False, True], inplace=True)
    df = df.groupby("_day", as_index=False).last()
    df.drop(columns=["_day", "_vol"], inplace=True, errors="ignore")

    out = []
    for _, row in df.iterrows():
        out.append((
            str(row["Date"])[:10],
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
        ))
    return out


def chart_candles_for_timeframe(
    daily_candles: Sequence[Sequence],
    timeframe: str,
) -> list[tuple[str, float, float, float, float]]:
    """Return OHLC tuples aggregated like aggregate_ohlcv in server.py."""
    normalized = normalize_daily_rows(daily_candles)
    if not normalized:
        return []

    if timeframe == "1D":
        return normalized

    df = pd.DataFrame(normalized, columns=["Date", "Open", "High", "Low", "Close"])
    df = _assign_period_key(df, timeframe)
    bars: list[tuple[str, float, float, float, float]] = []
    for _, group in df.groupby("period_key", sort=True):
        group = group.sort_values("Date")
        bars.append((
            str(group["Date"].iloc[0])[:10],
            round(float(group["Open"].iloc[0]), 2),
            round(float(group["High"].max()), 2),
            round(float(group["Low"].min()), 2),
            round(float(group["Close"].iloc[-1]), 2),
        ))
    return bars


def macd_crosses_up_level_signal(closes: list[float]) -> bool:
    """Level crosses up signal on the last bar (chart/snapshot semantics)."""
    macd_data = calculate_macd(closes)
    macd_line = macd_data["macd"]
    sig_line = macd_data["signal"]
    valid_m = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    valid_s = [(i, v) for i, v in enumerate(sig_line) if v is not None]
    if len(valid_m) < 2 or len(valid_s) < 2:
        return False
    m_prev, m_curr = valid_m[-2][1], valid_m[-1][1]
    s_prev, s_curr = valid_s[-2][1], valid_s[-1][1]
    return m_prev <= s_prev and m_curr > s_curr


def snapshot_macd_last_two(closes: list[float]) -> tuple:
    """(macd, macd_prev, signal, signal_prev) rounded to 4dp for DB storage."""
    macd_data = calculate_macd(closes)
    valid_m = [v for v in macd_data["macd"] if v is not None]
    valid_s = [v for v in macd_data["signal"] if v is not None]
    if len(valid_m) < 2 or len(valid_s) < 2:
        return None, None, None, None
    return (
        round(float(valid_m[-1]), 4),
        round(float(valid_m[-2]), 4),
        round(float(valid_s[-1]), 4),
        round(float(valid_s[-2]), 4),
    )
