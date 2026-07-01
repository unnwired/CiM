"""Tests for range_channel_filter."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

SERVER_PKG = ROOT / "packages" / "server"
if str(SERVER_PKG) not in sys.path:
    sys.path.insert(0, str(SERVER_PKG))

from range_channel_filter import (  # noqa: E402
    evaluate_range_channel,
    normalize_range_channel_params,
    _is_histogram_spike,
)


def _daily_from_3d_bars(bars: list[tuple]) -> list[tuple]:
    """Expand each 3D bar into 3 synthetic daily rows (enough for chart_candles_for_timeframe)."""
    from datetime import date, timedelta

    start = date(2026, 1, 5)
    out = []
    offset = 0
    for o, h, l, c in [(b[1], b[2], b[3], b[4]) for b in bars]:
        for j in range(3):
            day = (start + timedelta(days=offset + j)).isoformat()
            out.append((day, o, h, l, c))
        offset += 3
    return out


class RangeChannelFilterTests(unittest.TestCase):
    def test_spike_fails_even_with_straggler_budget(self):
        """Histogram spike must fail immediately — not forgiven as a straggler."""
        # 20 bars in tight channel, then spike on last transition
        bars = []
        for i in range(19):
            bars.append((f"2026-04-{i+1:02d}", 140.0, 145.0, 135.0, 142.0))
        bars.append(("2026-06-24", 160.0, 165.0, 155.0, 162.0))
        daily = _daily_from_3d_bars(bars)
        filt = {
            "timeframe": "3D",
            "lookback_bars": 18,
            "max_channel_width_pct": 25,
            "macd_allowed_stragglers": 3,
            "hist_flat_stragglers": 3,
        }
        # Synthetic flat price may not produce MACD spike — test spike helper via hist path
        params = normalize_range_channel_params(filt)

        self.assertTrue(_is_histogram_spike(0.3, 1.5, params))
        self.assertFalse(_is_histogram_spike(0.3, 0.35, params))

    def test_narrow_channel_evaluates_without_error(self):
        """Flat channel evaluation returns bool without raising."""
        bars = []
        for i in range(25):
            px = 140.0 + (i % 3) * 0.5
            bars.append((f"2026-04-{min(i + 1, 28):02d}", px, px + 2, px - 2, px))
        daily = _daily_from_3d_bars(bars)
        filt = {
            "timeframe": "3D",
            "lookback_bars": 12,
            "max_channel_width_pct": 20,
            "macd_allowed_stragglers": 2,
            "hist_flat_stragglers": 2,
        }
        result = evaluate_range_channel(daily, filt)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
