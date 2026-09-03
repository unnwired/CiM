"""Tests for Upstox history + split/bonus adjustment."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from server import upstox_adjust


class UpstoxAdjustTests(unittest.TestCase):
    def test_bonus_factor_before_ex_date(self):
        actions = [
            {
                "symbol": "TRENT",
                "action_type": "bonus",
                "record_date": "2026-06-04",
                "ratio_num": 1,
                "ratio_den": 2,
                "_ex_date": date(2026, 6, 4),
                "_price_mult": 2.0 / 3.0,
            }
        ]
        before = upstox_adjust.cumulative_price_factor(date(2026, 6, 3), actions)
        after = upstox_adjust.cumulative_price_factor(date(2026, 6, 4), actions)
        self.assertAlmostEqual(before, 2.0 / 3.0, places=6)
        self.assertAlmostEqual(after, 1.0, places=6)

    def test_split_factor(self):
        actions = [
            {
                "symbol": "FOO",
                "action_type": "split",
                "record_date": "2025-01-10",
                "ratio": 5,
                "_ex_date": date(2025, 1, 10),
                "_price_mult": 0.2,
            }
        ]
        self.assertAlmostEqual(
            upstox_adjust.cumulative_price_factor(date(2025, 1, 1), actions),
            0.2,
            places=6,
        )

    def test_adjust_ohlcv_rows(self):
        actions = [
            {
                "symbol": "FOO",
                "action_type": "split",
                "record_date": "2025-01-10",
                "ratio": 2,
                "_ex_date": date(2025, 1, 10),
                "_price_mult": 0.5,
            }
        ]
        rows = [
            ("2025-01-01 00:00:00+05:30", 100.0, 110.0, 90.0, 105.0, 1000.0),
            ("2025-01-11 00:00:00+05:30", 50.0, 55.0, 45.0, 52.0, 2000.0),
        ]
        out = upstox_adjust.adjust_ohlcv_rows("FOO", rows, actions=actions)
        self.assertEqual(out[0][4], 52.5)  # 105 * 0.5
        self.assertEqual(out[1][4], 52.0)  # unchanged after ex


class UpstoxHistoryBatchTests(unittest.TestCase):
    @patch("server.upstox_history.fetch_daily_for_symbol")
    @patch("server.upstox_instruments.instrument_map")
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    def test_fetch_daily_batch_counts(self, _en, _map, fetch_one):
        from server import upstox_history

        def _side(sym, *_a, **_k):
            if sym == "RELIANCE":
                return [("2026-01-01 00:00:00+05:30", 1, 1, 1, 1, 1)], None
            return [], "No Upstox instrument key for ZZZ"

        fetch_one.side_effect = _side
        result, stats = upstox_history.fetch_daily_batch(
            ["RELIANCE", "ZZZ"],
            date(2026, 1, 1),
            date(2026, 1, 2),
            adjust=False,
        )
        self.assertIn("RELIANCE", result)
        self.assertEqual(stats["upstox"], 1)
        self.assertGreaterEqual(stats["failed"], 1)

    @patch("server.upstox_history._is_after_nse_cash_open", return_value=True)
    @patch("server.upstox_history._ist_today", return_value=date(2026, 7, 14))
    @patch("server.upstox_client.fetch_quotes")
    @patch("server.upstox_instruments.instrument_map")
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    def test_today_only_uses_quotes_not_historical(self, _en, _map, quotes, _today, _after_open):
        from server import upstox_history

        quotes.return_value = (
            [
                {
                    "symbol": "RELIANCE",
                    "price": 1400.5,
                    "open": 1390.0,
                    "high": 1410.0,
                    "low": 1385.0,
                    "volume": 1000,
                }
            ],
            None,
        )
        with patch.object(upstox_history, "fetch_daily_for_symbol") as fetch_one:
            result, stats = upstox_history.fetch_daily_batch(
                ["RELIANCE"],
                date(2026, 7, 14),
                date(2026, 7, 14),
                adjust=False,
            )
            fetch_one.assert_not_called()
        self.assertIn("RELIANCE", result)
        self.assertEqual(stats["upstox"], 1)
        self.assertEqual(stats["today_quote"], 1)
        self.assertEqual(result["RELIANCE"][0][4], 1400.5)

    @patch("server.upstox_history._is_after_nse_cash_open", return_value=False)
    @patch("server.upstox_history._ist_today", return_value=date(2026, 7, 22))  # Wednesday
    @patch("server.upstox_client.fetch_quotes")
    @patch("server.upstox_instruments.instrument_map")
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    def test_pre_open_today_quote_not_merged(self, _en, _map, quotes, _today, _after_open):
        """Regression: before 09:15 IST, pre-open quotes must not stamp today's OHLC."""
        from server import upstox_history

        quotes.return_value = (
            [
                {
                    "symbol": "RELIANCE",
                    "price": 1400.5,
                    "open": 1390.0,
                    "high": 1410.0,
                    "low": 1385.0,
                    "volume": 1000,
                }
            ],
            None,
        )
        with patch.object(upstox_history, "fetch_daily_for_symbol") as fetch_one:
            result, stats = upstox_history.fetch_daily_batch(
                ["RELIANCE"],
                date(2026, 7, 22),
                date(2026, 7, 22),
                adjust=False,
            )
            fetch_one.assert_not_called()
        quotes.assert_not_called()
        self.assertEqual(result, {})
        self.assertEqual(int(stats.get("today_quote") or 0), 0)

    @patch("server.upstox_history._ist_today", return_value=date(2026, 7, 18))  # Saturday
    @patch("server.upstox_client.fetch_quotes")
    @patch("server.upstox_instruments.instrument_map")
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    def test_weekend_today_quote_not_merged(self, _en, _map, quotes, _today):
        """Regression: Sat/Sun must not get Friday's OHLC stamped as today."""
        from server import upstox_history

        quotes.return_value = (
            [
                {
                    "symbol": "^NSEI",
                    "price": 24334.3,
                    "open": 24127.6,
                    "high": 24367.3,
                    "low": 24099.05,
                    "volume": 0,
                }
            ],
            None,
        )
        with patch.object(upstox_history, "fetch_daily_for_symbol") as fetch_one:
            result, stats = upstox_history.fetch_daily_batch(
                ["^NSEI"],
                date(2026, 7, 18),
                date(2026, 7, 18),
                adjust=False,
            )
            fetch_one.assert_not_called()
        quotes.assert_not_called()
        self.assertEqual(result, {})
        self.assertEqual(int(stats.get("today_quote") or 0), 0)

    def test_filter_session_day_bars_drops_weekend(self):
        from server import upstox_history

        rows = [
            ("2026-07-17 00:00:00+05:30", 1, 1, 1, 1, 1),  # Fri
            ("2026-07-18 00:00:00+05:30", 1, 1, 1, 1, 0),  # Sat
            ("2026-07-19 00:00:00+05:30", 1, 1, 1, 1, 0),  # Sun
            ("2026-07-20 00:00:00+05:30", 1, 1, 1, 1, 1),  # Mon
        ]
        out = upstox_history._filter_session_day_bars(rows)
        self.assertEqual([str(r[0])[:10] for r in out], ["2026-07-17", "2026-07-20"])


if __name__ == "__main__":
    unittest.main()
