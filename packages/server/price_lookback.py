"""Rolling trading-session lookback for multi-day price vs open/high/low filters.

Multi-day chart bars (2D–6D) are calendar buckets anchored to the epoch, which is
correct for drawing a series but wrong for a screener lookback: the current bucket
is usually still forming, so on one date a 3D bucket holds three sessions and on
the next it holds one. "Price below open by 1% over 3D" then fires or vanishes for
reasons that have nothing to do with the market. Counting sessions keeps the
window the same size every day.

Weekly / monthly chart bars are real calendar periods the user reads on the chart
(this week's open→close is the red/green weekly candle). Those keep the bucket /
snapshot path in server.filter_price so "Price < Open (1W)" matches a red weekly
bar. EMA targets also stay on the bucket path.
"""
from __future__ import annotations

from typing import Optional

# Only bar-anchored targets are a lookback question; EMA is not.
ROLLING_TARGETS = frozenset({"open", "high", "low"})


def rolling_lookback_sessions(tf_unit: str, tf_num: int) -> Optional[int]:
    """Trading sessions a price-vs-OHL timeframe should look back over.

    Returns None for timeframes that keep calendar-bucket / chart-bar semantics
    (1D, weeks, months, hours).
    """
    try:
        n = int(tf_num)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    if tf_unit == "D" and n >= 2:
        return n
    return None


def load_recent_daily_bars(conn, symbols, sessions: int) -> dict:
    """Last `sessions` daily bars per symbol from historical_data, oldest first.

    Values are (open, high, low, close) tuples keyed by the uppercased symbol.
    Seeks once per symbol on the (Symbol, Date) index: a single window function
    over historical_data has to sort all 7M+ rows (~12s for the full universe)
    no matter how few bars it keeps, while the seeks cost about 0.1s.
    """
    limit = max(1, int(sessions))
    cur = conn.cursor()
    out: dict = {}
    for raw_sym in symbols:
        sym = str(raw_sym or "").strip().upper()
        if not sym or sym in out:
            continue
        cur.execute(
            "SELECT Open, High, Low, Close FROM historical_data "
            "WHERE Symbol = ? ORDER BY Date DESC LIMIT ?",
            (raw_sym, limit),
        )
        bars = []
        for o, h, l, c in reversed(cur.fetchall()):
            if o is None or h is None or l is None or c is None:
                continue
            try:
                bars.append((float(o), float(h), float(l), float(c)))
            except (TypeError, ValueError):
                continue
        if bars:
            out[sym] = bars
    return out


def window_target(bars: list, sessions: int, target: str, offset: int = 0):
    """open/high/low across the `sessions`-long window ending `offset` bars back."""
    end = len(bars) - offset
    start = end - sessions
    if start < 0 or end <= start:
        return None
    window = bars[start:end]
    if target == "open":
        return window[0][0]
    if target == "high":
        return max(b[1] for b in window)
    if target == "low":
        return min(b[2] for b in window)
    return None


def condition_matches(
    condition: str,
    price_curr,
    price_prev,
    tgt_curr,
    tgt_prev,
    pct_value: float,
) -> bool:
    """Shared comparison used by every price filter path."""
    if price_curr is None or tgt_curr is None:
        return False
    if condition == "above":
        return price_curr > tgt_curr
    if condition == "above_eq":
        return price_curr >= tgt_curr
    if condition == "below":
        return price_curr < tgt_curr
    if condition == "below_eq":
        return price_curr <= tgt_curr
    if condition == "crosses_up":
        if price_prev is None or tgt_prev is None:
            return False
        return price_prev <= tgt_prev and price_curr > tgt_curr
    if condition == "crosses_down":
        if price_prev is None or tgt_prev is None:
            return False
        return price_prev >= tgt_prev and price_curr < tgt_curr
    if condition == "above_pct":
        return tgt_curr != 0 and price_curr > tgt_curr * (1 + pct_value / 100)
    if condition == "below_pct":
        return tgt_curr != 0 and price_curr < tgt_curr * (1 - pct_value / 100)
    return False


def filter_symbols(
    conn,
    symbols: list,
    sessions: int,
    target: str,
    condition: str,
    pct_value: float,
) -> list:
    """Symbols whose last close meets `condition` vs the `sessions`-window target.

    `symbols` is the caller's ordered universe; result order is preserved.
    """
    bars_by_symbol = load_recent_daily_bars(conn, symbols, sessions + 1)
    results = []
    for raw_sym in symbols:
        sym = str(raw_sym or "").strip().upper()
        if not sym:
            continue
        bars = bars_by_symbol.get(sym) or []
        if len(bars) < sessions:
            continue
        tgt_curr = window_target(bars, sessions, target)
        price_curr = bars[-1][3]
        tgt_prev = window_target(bars, sessions, target, offset=1)
        price_prev = bars[-2][3] if len(bars) > sessions else None
        if condition_matches(
            condition, price_curr, price_prev, tgt_curr, tgt_prev, pct_value
        ):
            results.append(raw_sym)
    return results
