"""Tests for NSE session-aligned 30m bar aggregation and parse wiring."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.bars_30m import (  # noqa: E402
    aggregate_intraday_to_30m,
    assign_30m_bucket,
    bucket_30m_bar_start,
    ensure_bars_30m_table,
    load_bars_30m_candles_batch,
    should_defer_bars_30m_build,
    upsert_bars_30m,
)

IST = ZoneInfo("Asia/Kolkata")
HOLIDAYS: set[str] = set()
SPECIAL: set[str] = set()


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


class TestBars30m(unittest.TestCase):
    def test_assign_30m_bucket_edges(self):
        self.assertIsNone(assign_30m_bucket(_ist(2026, 6, 16, 9, 14)))
        self.assertEqual(assign_30m_bucket(_ist(2026, 6, 16, 9, 15)), 0)
        self.assertEqual(assign_30m_bucket(_ist(2026, 6, 16, 9, 44)), 0)
        self.assertEqual(assign_30m_bucket(_ist(2026, 6, 16, 9, 45)), 1)
        self.assertEqual(assign_30m_bucket(_ist(2026, 6, 16, 15, 0)), 11)
        self.assertEqual(assign_30m_bucket(_ist(2026, 6, 16, 15, 15)), 12)
        self.assertEqual(assign_30m_bucket(_ist(2026, 6, 16, 15, 30)), 12)
        self.assertIsNone(assign_30m_bucket(_ist(2026, 6, 16, 15, 31)))

    def test_bucket_30m_bar_start(self):
        d = date(2026, 6, 16)
        self.assertEqual(bucket_30m_bar_start(d, 0), _ist(2026, 6, 16, 9, 15))
        self.assertEqual(bucket_30m_bar_start(d, 1), _ist(2026, 6, 16, 9, 45))
        self.assertEqual(bucket_30m_bar_start(d, 12), _ist(2026, 6, 16, 15, 15))

    def test_aggregate_intraday_to_30m_ohlcv(self):
        rows = [
            (_ist(2026, 6, 16, 9, 15), 100.0, 101.0, 99.5, 100.5, 1000.0),
            (_ist(2026, 6, 16, 9, 20), 100.5, 102.0, 100.0, 101.0, 500.0),
            (_ist(2026, 6, 16, 9, 45), 101.0, 103.0, 100.5, 102.5, 800.0),
            (_ist(2026, 6, 16, 15, 15), 110.0, 111.0, 109.0, 110.5, 200.0),
            (_ist(2026, 6, 16, 15, 25), 110.5, 112.0, 110.0, 111.0, 300.0),
        ]
        bars = aggregate_intraday_to_30m("RELIANCE", rows, HOLIDAYS, SPECIAL)
        by_bucket = {b.bucket: b for b in bars}
        self.assertIn(0, by_bucket)
        self.assertIn(1, by_bucket)
        self.assertIn(12, by_bucket)
        b0 = by_bucket[0]
        self.assertEqual(b0.open, 100.0)
        self.assertEqual(b0.high, 102.0)
        self.assertEqual(b0.low, 99.5)
        self.assertEqual(b0.close, 101.0)
        self.assertEqual(b0.volume, 1500.0)
        b12 = by_bucket[12]
        self.assertEqual(b12.open, 110.0)
        self.assertEqual(b12.close, 111.0)
        self.assertEqual(b12.volume, 500.0)

    def test_aggregate_skips_weekend(self):
        rows = [(_ist(2026, 6, 14, 10, 0), 100.0, 101.0, 99.0, 100.5, 100.0)]
        self.assertEqual(aggregate_intraday_to_30m("RELIANCE", rows, HOLIDAYS, SPECIAL), [])

    def test_should_defer_mirrors_4h_window(self):
        with patch("server.bars_30m.datetime") as mock_dt:
            mock_dt.now.return_value = _ist(2026, 6, 16, 12, 0)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            # Patch helpers used inside should_defer via bars_4h calendar
            with patch("server.bars_30m.load_nse_calendar", return_value={"holidays": set(), "special_sessions": set()}):
                with patch("server.bars_30m.is_nse_session_day", return_value=True):
                    defer, reason = should_defer_bars_30m_build()
                    self.assertTrue(defer)
                    self.assertIn("15:30", reason)

    def test_upsert_and_load_batch(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_30m_table(conn)
        rows = [
            (_ist(2026, 6, 16, 9, 15), 100.0, 101.0, 99.0, 100.5, 1000.0),
            (_ist(2026, 6, 16, 9, 45), 100.5, 102.0, 100.0, 101.5, 500.0),
        ]
        bars = aggregate_intraday_to_30m("RELIANCE", rows, HOLIDAYS, SPECIAL)
        upsert_bars_30m(conn, "RELIANCE", bars)
        loaded = load_bars_30m_candles_batch(conn, ["RELIANCE", "MISSING"])
        self.assertEqual(len(loaded["RELIANCE"]), 2)
        self.assertEqual(loaded["MISSING"], [])
        first = loaded["RELIANCE"][0]
        self.assertEqual(first[1], 100.0)
        self.assertEqual(first[4], 100.5)


class TestParseTimeframe30m(unittest.TestCase):
    def test_parse_and_snapshot_key(self):
        from server import server as srv

        self.assertEqual(srv.parse_timeframe("30m"), ("m", 30))
        self.assertEqual(srv.parse_timeframe("30M"), ("m", 30))
        self.assertEqual(srv._snapshot_timeframe_key("m", 30), "30m")
        # Months still work; 3M must not become minutes.
        self.assertEqual(srv.parse_timeframe("3M"), ("M", 3))
        self.assertEqual(srv.parse_timeframe("1M"), ("M", 1))
        # Legacy other minute tokens still map to daily.
        self.assertEqual(srv.parse_timeframe("15m"), ("D", 1))

    def test_snapshot_lists_include_30m(self):
        from server import server as srv

        self.assertIn("30m", srv.SNAPSHOT_TIMEFRAMES)
        self.assertIn("30m", srv.SNAPSHOT_LIGHT_TIMEFRAMES)
        self.assertNotIn("30m", srv.SNAPSHOT_FRESHNESS_TIMEFRAMES)
        self.assertEqual(srv.TIMEFRAME_CONFIG["30m"]["anchor"], "session_30m")


class TestSnapshotRebuildUsesBars30m(unittest.TestCase):
    def test_build_rows_reads_30m_series(self):
        import scrape_daily as sd

        # Minimal daily candles so non-30m TFs are skipped via allowed list.
        daily = [
            ("2026-06-10", 1, 1, 1, 1),
            ("2026-06-11", 1, 1, 1, 1),
            ("2026-06-12", 1, 1, 1, 1),
        ]
        bars_30m = [
            ("2026-06-16T09:15:00+05:30", 100.0, 101.0, 99.0, 100.5),
            ("2026-06-16T09:45:00+05:30", 100.5, 102.0, 100.0, 101.0),
            ("2026-06-16T10:15:00+05:30", 101.0, 103.0, 100.5, 102.0),
        ]
        with patch.object(sd, "build_snapshot_payload", return_value={"symbol": "RELIANCE", "timeframe": "30m"}):
            rows = sd._build_snapshot_rows_for_symbol(
                "RELIANCE",
                daily,
                allowed_timeframes=["30m"],
                bars_30m_series=bars_30m,
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timeframe"], "30m")


if __name__ == "__main__":
    unittest.main()
