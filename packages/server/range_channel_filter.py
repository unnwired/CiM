"""Horizontal price channel + sustained MACD-above-signal filter (chart-parity 3D bars)."""
from __future__ import annotations

from typing import Any, Sequence

from snapshot_bars import calculate_macd, chart_candles_for_timeframe


def normalize_range_channel_params(filter_def: dict[str, Any]) -> dict[str, Any]:
    lookback_bars = max(4, min(40, int(filter_def.get("lookback_bars", 18) or 18)))
    max_channel_width_pct = max(5.0, min(60.0, float(filter_def.get("max_channel_width_pct", 20) or 20)))
    macd_allowed_stragglers = max(0, min(3, int(filter_def.get("macd_allowed_stragglers", 2) or 2)))
    hist_flat_stragglers = max(0, min(5, int(filter_def.get("hist_flat_stragglers", 2) or 2)))
    spike_ratio = max(1.2, min(5.0, float(filter_def.get("spike_ratio", 1.8) or 1.8)))
    spike_min_delta = max(0.1, min(20.0, float(filter_def.get("spike_min_delta", 0.8) or 0.8)))
    return {
        "timeframe": str(filter_def.get("timeframe", "3D") or "3D").strip().upper(),
        "lookback_bars": lookback_bars,
        "max_channel_width_pct": max_channel_width_pct,
        "macd_allowed_stragglers": macd_allowed_stragglers,
        "hist_flat_stragglers": hist_flat_stragglers,
        "spike_ratio": spike_ratio,
        "spike_min_delta": spike_min_delta,
    }


def bars_needed_for_range_channel(filter_def: dict[str, Any]) -> int:
    p = normalize_range_channel_params(filter_def)
    # MACD warm-up (26+9) plus lookback window.
    return 26 + 9 + p["lookback_bars"] + 2


def _is_histogram_spike(prev_hist: float, curr_hist: float, params: dict[str, Any]) -> bool:
    """Breakout signature — never forgiven as a straggler."""
    if prev_hist is None or curr_hist is None:  # type: ignore[comparison-overlap]
        return False
    if curr_hist <= prev_hist:
        return False
    delta = curr_hist - prev_hist
    if delta >= params["spike_min_delta"]:
        return True
    if prev_hist > 0 and curr_hist >= prev_hist * params["spike_ratio"]:
        return True
    return False


def _hist_flat_violation(prev_hist: float, curr_hist: float) -> bool:
    """Positive histogram should recede or stay flat while price consolidates."""
    if prev_hist is None or curr_hist is None:  # type: ignore[comparison-overlap]
        return False
    if prev_hist <= 0:
        return False
    # Small upticks below spike thresholds count as stragglers only.
    return curr_hist > prev_hist + 1e-9


def evaluate_range_channel(
    daily_candles: Sequence[Sequence],
    filter_def: dict[str, Any],
) -> bool:
    """
    Match stocks in a horizontal channel with MACD line above signal, no histogram spikes.
    Spikes immediately fail — they are never counted toward straggler allowances.
    """
    params = normalize_range_channel_params(filter_def)
    timeframe = params["timeframe"]
    lookback = params["lookback_bars"]

    bars = chart_candles_for_timeframe(daily_candles, timeframe)
    if len(bars) < lookback:
        return False

    window = bars[-lookback:]
    highs = [float(c[2]) for c in window]
    lows = [float(c[3]) for c in window]
    hi, lo = max(highs), min(lows)
    if hi <= 0 or lo <= 0:
        return False
    mid = (hi + lo) / 2.0
    if mid <= 0:
        return False
    width_pct = (hi - lo) / mid * 100.0
    if width_pct > params["max_channel_width_pct"]:
        return False

    closes = [float(c[4]) for c in bars]
    macd_data = calculate_macd(closes)
    hist_all = macd_data["histogram"]
    start_idx = len(bars) - lookback
    hist_window = hist_all[start_idx:]

    macd_violations = 0
    hist_violations = 0

    for i in range(1, len(hist_window)):
        prev_h = hist_window[i - 1]
        curr_h = hist_window[i]
        if prev_h is None or curr_h is None:
            return False

        if _is_histogram_spike(prev_h, curr_h, params):
            return False

        if curr_h <= 0:
            macd_violations += 1
            if macd_violations > params["macd_allowed_stragglers"]:
                return False

        if _hist_flat_violation(prev_h, curr_h):
            hist_violations += 1
            if hist_violations > params["hist_flat_stragglers"]:
                return False

    # First bar in window must also be MACD-above-signal unless straggler budget covers it.
    h0 = hist_window[0]
    if h0 is None:
        return False
    if h0 <= 0:
        macd_violations += 1
        if macd_violations > params["macd_allowed_stragglers"]:
            return False

    return True
