"""Unit tests for focus tick candle engine (1m + 1D)."""
from __future__ import annotations

import unittest

from server.tick_candle_engine import (
    apply_tick_to_day,
    apply_tick_to_minute,
    focus_candle_bundle,
)


class TickCandleEngineTests(unittest.TestCase):
    def test_minute_locks_open_and_expands_range(self):
        a = apply_tick_to_minute(None, price=100.0, ts_ms=1_700_000_000_000)
        b = apply_tick_to_minute(a, price=105.0, ts_ms=1_700_000_000_000)
        c = apply_tick_to_minute(b, price=97.0, ts_ms=1_700_000_000_000)
        self.assertEqual(c["open"], 100.0)
        self.assertEqual(c["high"], 105.0)
        self.assertEqual(c["low"], 97.0)
        self.assertEqual(c["close"], 97.0)
        self.assertEqual(c["tf"], "1m")

    def test_day_does_not_invent_open_from_ltp(self):
        bar = apply_tick_to_day(None, price=1300.0, ts_ms=1_700_000_000_000)
        self.assertNotIn("open", bar)
        self.assertEqual(bar["close"], 1300.0)

    def test_day_locks_session_open(self):
        seeded = apply_tick_to_day(
            None, price=1290.0, session_open=1302.0, session_high=1304.0, session_low=1287.0
        )
        self.assertEqual(seeded["open"], 1302.0)
        later = apply_tick_to_day(seeded, price=1295.0)
        self.assertEqual(later["open"], 1302.0)
        self.assertEqual(later["close"], 1295.0)
        self.assertGreaterEqual(later["high"], 1304.0)

    def test_bundle_keys(self):
        m = apply_tick_to_minute(None, price=10.0)
        d = apply_tick_to_day(None, price=10.0, session_open=9.5)
        bundle = focus_candle_bundle(m, d)
        self.assertIn("1m", bundle)
        self.assertIn("1D", bundle)
        self.assertEqual(bundle["1D"]["open"], 9.5)


if __name__ == "__main__":
    unittest.main()
