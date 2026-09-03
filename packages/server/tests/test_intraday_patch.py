"""Intraday patch must force NSE refetch — not reuse stale prior-session cache."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from server import movers_live
from server.intraday_overlay import fetch_patch

IST = timezone(timedelta(hours=5, minutes=30))


class IntradayPatchTests(unittest.TestCase):
    def test_cache_quote_stale_rejects_yesterday(self):
        yesterday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
        snap = {"price": 100.0, "updated_at": f"{yesterday} 15:00:00 IST"}
        self.assertTrue(movers_live._cache_quote_stale(snap))
        self.assertFalse(movers_live.cache_quote_fresh(snap))

    def test_cache_quote_fresh_accepts_today(self):
        today = datetime.now(IST).strftime("%Y-%m-%d")
        snap = {"price": 101.5, "updated_at": f"{today} 10:30:00 IST"}
        self.assertFalse(movers_live._cache_quote_stale(snap))
        self.assertTrue(movers_live.cache_quote_fresh(snap))

    @patch("server.intraday_overlay.live_quote_providers.fetch_live_quotes")
    @patch("server.intraday_overlay.movers_live._merge_cache")
    @patch("server.intraday_overlay.movers_live.live_cache_snapshot")
    @patch("server.intraday_overlay.movers_live.cache_quote_fresh", return_value=True)
    def test_fetch_patch_uses_live_providers(self, _fresh, live_snap, _merge, fetch_live):
        fetch_live.return_value = (
            [{"symbol": "RELIANCE", "price": 2500.0, "previous_close": 2480.0, "change_pct": 0.81, "updated_at": movers_live._iso_now(), "source": "yfinance"}],
            None,
        )
        live_snap.return_value = {
            "RELIANCE": {
                "price": 2500.0,
                "previous_close": 2480.0,
                "change_pct": 0.81,
                "updated_at": movers_live._iso_now(),
                "source": "yfinance",
            }
        }
        result = fetch_patch(["RELIANCE", "TCS"])
        fetch_live.assert_called_once()
        self.assertEqual(result["returned"], 1)
        self.assertIn("RELIANCE", result["symbols"])

    def test_merge_daily_bars_rejects_zero_ohlc(self):
        bars = [
            {"time": "2026-06-04", "open": 770, "high": 775, "low": 768, "close": 772, "volume": 1e6},
        ]
        snap = {
            "price": 782.3,
            "open": 770.0,
            "high": 0,
            "low": 0,
            "previous_close": 772,
            "volume": 500000,
            "updated_at": movers_live._iso_now(),
        }
        with patch.object(movers_live, "get_symbol_live_snapshot", return_value=snap):
            with patch.object(movers_live, "_is_after_nse_cash_open", return_value=True):
                out, chg = movers_live.merge_live_into_daily_bars("HDFCBANK", bars, "1D")
        last = out[-1]
        self.assertTrue(last.get("live"))
        self.assertGreater(last["low"], 0)
        self.assertGreater(last["open"], 0)
        self.assertIsNotNone(chg)

    def test_merge_daily_bars_skips_before_cash_open(self):
        bars = [
            {"time": "2026-07-21", "open": 770, "high": 775, "low": 768, "close": 772, "volume": 1e6},
        ]
        snap = {
            "price": 782.3,
            "open": 770.0,
            "high": 785.0,
            "low": 768.0,
            "previous_close": 772,
            "volume": 500000,
            "updated_at": movers_live._iso_now(),
        }
        with patch.object(movers_live, "get_symbol_live_snapshot", return_value=snap):
            with patch.object(movers_live, "_is_after_nse_cash_open", return_value=False):
                out, chg = movers_live.merge_live_into_daily_bars("HDFCBANK", bars, "1D")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["time"], "2026-07-21")
        self.assertIsNone(chg)


if __name__ == "__main__":
    unittest.main()
