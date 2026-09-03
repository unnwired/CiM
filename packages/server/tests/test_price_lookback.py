"""Multi-day price vs open/high/low must look back N trading sessions, not N calendar days."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from server import price_lookback as pl


class RollingLookbackSessionsTests(unittest.TestCase):
    def test_daily_multi_day_maps_to_sessions(self):
        self.assertEqual(pl.rolling_lookback_sessions("D", 3), 3)
        self.assertEqual(pl.rolling_lookback_sessions("D", 7), 7)

    def test_single_day_week_and_month_keep_chart_bar_path(self):
        # 1W/2W must match the chart weekly candle (red/green bar), not N*5 sessions.
        self.assertIsNone(pl.rolling_lookback_sessions("D", 1))
        self.assertIsNone(pl.rolling_lookback_sessions("W", 1))
        self.assertIsNone(pl.rolling_lookback_sessions("W", 2))
        self.assertIsNone(pl.rolling_lookback_sessions("M", 1))
        self.assertIsNone(pl.rolling_lookback_sessions("H", 4))

    def test_garbage_input_is_ignored(self):
        self.assertIsNone(pl.rolling_lookback_sessions("D", 0))
        self.assertIsNone(pl.rolling_lookback_sessions("D", None))


class WindowTargetTests(unittest.TestCase):
    # (open, high, low, close), oldest first
    BARS = [
        (100.0, 108.0, 96.0, 105.0),
        (105.0, 112.0, 99.0, 101.0),
        (101.0, 104.0, 92.0, 95.0),
        (95.0, 99.0, 90.0, 97.0),
    ]

    def test_open_is_first_bar_of_window(self):
        self.assertEqual(pl.window_target(self.BARS, 3, "open"), 105.0)
        self.assertEqual(pl.window_target(self.BARS, 4, "open"), 100.0)

    def test_high_and_low_span_the_window(self):
        self.assertEqual(pl.window_target(self.BARS, 3, "high"), 112.0)
        self.assertEqual(pl.window_target(self.BARS, 3, "low"), 90.0)

    def test_offset_shifts_the_window_back_one_bar(self):
        self.assertEqual(pl.window_target(self.BARS, 3, "open", offset=1), 100.0)

    def test_window_longer_than_history_returns_none(self):
        self.assertIsNone(pl.window_target(self.BARS, 9, "open"))


def _conn_with_bars(rows):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE screener (
            Symbol TEXT PRIMARY KEY, market_cap REAL, issued_shares REAL, price REAL
        );
        CREATE TABLE historical_data (
            Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL
        );
        """
    )
    conn.executemany("INSERT INTO historical_data VALUES (?,?,?,?,?,?)", rows)
    return conn


class FilterSymbolsTests(unittest.TestCase):
    # Up on the day, but well below where the 3-session stretch opened.
    BARS = [
        ("REBOUND", "2026-07-27", 100.0, 101.0, 99.0, 100.0),
        ("REBOUND", "2026-07-28", 100.0, 101.0, 96.0, 97.0),
        ("REBOUND", "2026-07-29", 97.0, 98.0, 93.0, 94.0),
        ("REBOUND", "2026-07-30", 94.0, 96.0, 93.0, 95.0),
        ("STEADY", "2026-07-27", 50.0, 51.0, 49.0, 50.0),
        ("STEADY", "2026-07-28", 50.0, 51.0, 49.0, 50.5),
        ("STEADY", "2026-07-29", 50.5, 51.5, 50.0, 51.0),
        ("STEADY", "2026-07-30", 51.0, 52.0, 50.5, 51.5),
    ]

    def test_below_open_by_pct_over_three_sessions(self):
        conn = _conn_with_bars(self.BARS)
        got = pl.filter_symbols(
            conn, ["REBOUND", "STEADY"], 3, "open", "below_pct", 1.0
        )
        self.assertEqual(got, ["REBOUND"])

    def test_same_stock_is_up_against_the_single_day_open(self):
        conn = _conn_with_bars(self.BARS)
        got = pl.filter_symbols(conn, ["REBOUND", "STEADY"], 1, "open", "above", 0.0)
        self.assertIn("REBOUND", got)

    def test_symbol_without_enough_history_is_skipped(self):
        conn = _conn_with_bars(self.BARS[:2])
        self.assertEqual(pl.filter_symbols(conn, ["REBOUND"], 3, "open", "below_pct", 1.0), [])

    def test_window_target_uses_extremes_not_last_bar(self):
        conn = _conn_with_bars(self.BARS)
        # 3-session low for REBOUND is 93.0; last close 95.0 is above it.
        self.assertEqual(pl.filter_symbols(conn, ["REBOUND"], 3, "low", "above", 0.0), ["REBOUND"])
        self.assertEqual(pl.filter_symbols(conn, ["REBOUND"], 3, "high", "above", 0.0), [])


class FilterPriceIntegrationTests(unittest.TestCase):
    """filter_price on a multi-day chip must take the rolling path, not the snapshot."""

    def _run(self, timeframe, condition, pct, target="open"):
        from server import server as srv

        conn = _conn_with_bars(FilterSymbolsTests.BARS)
        conn.execute("INSERT INTO screener (Symbol, market_cap) VALUES ('REBOUND', 1e12)")
        conn.execute("INSERT INTO screener (Symbol, market_cap) VALUES ('STEADY', 9e11)")

        class _Conn:
            def cursor(self_inner):
                return conn.cursor()

            def close(self_inner):
                pass

            def execute(self_inner, *a, **k):
                return conn.execute(*a, **k)

        with patch.object(srv, "get_db_connection", return_value=_Conn()), patch.object(
            srv, "get_filter_cache", return_value=None
        ), patch.object(srv, "set_filter_cache"), patch.object(
            srv, "_sector_allowed_symbols", return_value=None
        ), patch.object(
            srv, "_load_filter_snapshots"
        ) as snaps:
            result = srv.filter_price(
                {
                    "timeframe": timeframe,
                    "condition": condition,
                    "pct_value": pct,
                    "target": target,
                    "ema_period": 21,
                }
            )
            self.snapshots_used = snaps.called
        return result

    def test_three_day_open_uses_rolling_sessions(self):
        result = self._run("3D", "below_pct", 1.0)
        self.assertEqual(result["symbols"], ["REBOUND"])
        self.assertFalse(self.snapshots_used, "3D price vs open must not read snapshots")

    def test_ema_target_still_uses_the_bucket_path(self):
        from server import server as srv

        conn = _conn_with_bars(FilterSymbolsTests.BARS)
        conn.execute("INSERT INTO screener (Symbol, market_cap) VALUES ('REBOUND', 1e12)")

        class _Conn:
            def cursor(self_inner):
                return conn.cursor()

            def close(self_inner):
                pass

            def execute(self_inner, *a, **k):
                return conn.execute(*a, **k)

        with patch.object(srv, "get_db_connection", return_value=_Conn()), patch.object(
            srv, "get_filter_cache", return_value=None
        ), patch.object(srv, "set_filter_cache"), patch.object(
            srv, "_sector_allowed_symbols", return_value=None
        ), patch.object(
            srv, "_load_filter_snapshots", return_value=[]
        ) as snaps:
            srv.filter_price(
                {
                    "timeframe": "3D",
                    "condition": "above",
                    "pct_value": 0,
                    "target": "ema",
                    "ema_period": 21,
                }
            )
        self.assertTrue(snaps.called, "EMA targets still need aggregated snapshot bars")

    def test_one_week_open_uses_weekly_snapshot_not_rolling(self):
        """Price < Open (1W) must use the chart weekly candle, not last-5-sessions."""
        from server import server as srv

        # Green weekly bar: close > open → must NOT match below_pct 1%.
        green = {
            "symbol": "MANKIND",
            "open_curr": 2458.0,
            "close_curr": 2483.0,
            "open_prev": 2513.0,
            "close_prev": 2469.6,
            "high_curr": 2497.9,
            "low_curr": 2442.2,
            "high_prev": 2613.5,
            "low_prev": 2422.0,
        }
        # Red weekly bar, down >1% from week open.
        red = {
            "symbol": "REDBAR",
            "open_curr": 100.0,
            "close_curr": 97.0,
            "open_prev": 102.0,
            "close_prev": 100.0,
            "high_curr": 101.0,
            "low_curr": 96.0,
            "high_prev": 103.0,
            "low_prev": 99.0,
        }
        conn = _conn_with_bars([])
        conn.execute("INSERT INTO screener (Symbol, market_cap) VALUES ('MANKIND', 1e12)")
        conn.execute("INSERT INTO screener (Symbol, market_cap) VALUES ('REDBAR', 9e11)")

        class _Conn:
            def cursor(self_inner):
                return conn.cursor()

            def close(self_inner):
                pass

            def execute(self_inner, *a, **k):
                return conn.execute(*a, **k)

        with patch.object(srv, "get_db_connection", return_value=_Conn()), patch.object(
            srv, "get_filter_cache", return_value=None
        ), patch.object(srv, "set_filter_cache"), patch.object(
            srv, "_sector_allowed_symbols", return_value=None
        ), patch.object(
            srv, "_load_filter_snapshots", return_value=[green, red]
        ) as snaps:
            result = srv.filter_price(
                {
                    "timeframe": "1W",
                    "condition": "below_pct",
                    "pct_value": 1.0,
                    "target": "open",
                    "ema_period": 21,
                }
            )
        self.assertTrue(snaps.called, "1W price vs open must use weekly snapshots")
        self.assertEqual(result["symbols"], ["REDBAR"])
        self.assertNotIn("MANKIND", result["symbols"])


if __name__ == "__main__":
    unittest.main()
