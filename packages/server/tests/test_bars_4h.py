"""Tests for NSE session-aligned 4H bar aggregation."""
from __future__ import annotations

import sys
import sqlite3
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

from server.bars_4h import (  # noqa: E402
    BARS_4H_INCREMENTAL_SESSION_DAYS,
    META_BACKFILL_COMPLETE,
    aggregate_intraday_to_4h,
    assign_session_bucket,
    bucket_bar_start,
    build_bars_4h_for_symbols,
    ensure_bars_4h_table,
    ensure_updater_meta_table,
    latest_completed_4h_session_date,
    pick_live_session_4h_catchup,
    reconcile_4h_backfill_meta,
    set_meta,
    should_defer_bars_4h_build,
    symbols_needing_4h_backfill,
    symbols_needing_4h_refresh,
    try_mark_universe_backfill_complete,
    yahoo_ticker_for_symbol,
)

IST = ZoneInfo("Asia/Kolkata")
HOLIDAYS: set[str] = set()
SPECIAL: set[str] = set()


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


class TestBars4h(unittest.TestCase):
    def test_assign_session_bucket_boundaries(self):
        self.assertIsNone(assign_session_bucket(_ist(2026, 6, 16, 9, 14)))
        self.assertEqual(assign_session_bucket(_ist(2026, 6, 16, 9, 15)), 1)
        self.assertEqual(assign_session_bucket(_ist(2026, 6, 16, 13, 14)), 1)
        self.assertEqual(assign_session_bucket(_ist(2026, 6, 16, 13, 15)), 2)
        self.assertEqual(assign_session_bucket(_ist(2026, 6, 16, 15, 30)), 2)
        self.assertIsNone(assign_session_bucket(_ist(2026, 6, 16, 15, 31)))

    def test_bucket_bar_start(self):
        d = date(2026, 6, 16)
        self.assertEqual(bucket_bar_start(d, 1), _ist(2026, 6, 16, 9, 15))
        self.assertEqual(bucket_bar_start(d, 2), _ist(2026, 6, 16, 13, 15))

    def test_yahoo_ticker_for_symbol(self):
        self.assertEqual(yahoo_ticker_for_symbol("RELIANCE"), "RELIANCE.NS")
        self.assertEqual(yahoo_ticker_for_symbol("^NSEI"), "^NSEI")
        self.assertEqual(yahoo_ticker_for_symbol("GC=F"), "GC=F")

    def test_aggregate_intraday_to_4h_ohlcv(self):
        rows = [
            (_ist(2026, 6, 16, 9, 20), 100.0, 101.0, 99.5, 100.5, 1000.0),
            (_ist(2026, 6, 16, 12, 0), 100.5, 103.0, 100.0, 102.0, 2000.0),
            (_ist(2026, 6, 16, 13, 20), 102.0, 104.0, 101.5, 103.0, 500.0),
            (_ist(2026, 6, 16, 15, 25), 103.0, 105.0, 102.5, 104.0, 800.0),
        ]
        bars = aggregate_intraday_to_4h("RELIANCE", rows, HOLIDAYS, SPECIAL)
        self.assertEqual(len(bars), 2)
        b1, b2 = bars
        self.assertEqual(b1.bucket, 1)
        self.assertEqual(b1.open, 100.0)
        self.assertEqual(b1.high, 103.0)
        self.assertEqual(b1.low, 99.5)
        self.assertEqual(b1.close, 102.0)
        self.assertEqual(b1.volume, 3000.0)
        self.assertEqual(b2.bucket, 2)
        self.assertEqual(b2.open, 102.0)
        self.assertEqual(b2.close, 104.0)
        self.assertEqual(b2.volume, 1300.0)

    def test_aggregate_skips_weekend_without_special(self):
        rows = [
            (_ist(2026, 6, 14, 10, 0), 100.0, 101.0, 99.0, 100.5, 100.0),
        ]
        bars = aggregate_intraday_to_4h("RELIANCE", rows, HOLIDAYS, SPECIAL)
        self.assertEqual(bars, [])

    def test_symbols_needing_4h_backfill(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        for i in range(2):
            sd = f"2026-06-{10 + i}"
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("OFSS", f"{sd}T09:15:00+05:30", sd),
            )
        for i in range(25):
            sd = f"2026-04-{(i % 28) + 1:02d}"
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("RELIANCE", f"{sd}T09:15:00+05:30", sd),
            )
        conn.commit()
        needing = symbols_needing_4h_backfill(conn, ["OFSS", "RELIANCE", "TATACONSUM"])
        self.assertIn("OFSS", needing)
        self.assertIn("TATACONSUM", needing)
        self.assertNotIn("RELIANCE", needing)

    def test_reconcile_keeps_backfill_complete_with_shallow_symbols(self):
        """Shallow symbols must not clear meta (avoids auto full-universe 90d)."""
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        ensure_updater_meta_table(conn)
        set_meta(conn, META_BACKFILL_COMPLETE, "1")
        reconcile_4h_backfill_meta(conn, ["OFSS", "RELIANCE"])
        self.assertEqual(
            conn.execute(
                "SELECT value FROM updater_meta WHERE key=?",
                (META_BACKFILL_COMPLETE,),
            ).fetchone()[0],
            "1",
        )

    def test_try_mark_universe_backfill_complete(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        ensure_updater_meta_table(conn)
        for sym in ("OFSS", "RELIANCE"):
            for i in range(25):
                sd = f"2026-04-{(i % 28) + 1:02d}"
                conn.execute(
                    "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                    "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                    (sym, f"{sd}T09:15:00+05:30", sd),
                )
        conn.commit()
        try_mark_universe_backfill_complete(conn, ["OFSS", "RELIANCE"])
        row = conn.execute(
            "SELECT value FROM updater_meta WHERE key=?",
            (META_BACKFILL_COMPLETE,),
        ).fetchone()
        self.assertEqual(row[0], "1")

    def test_pick_live_session_4h_catchup_prefers_zero(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        for i in range(2):
            sd = f"2026-06-{10 + i}"
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("OFSS", f"{sd}T09:15:00+05:30", sd),
            )
        conn.commit()
        picked = pick_live_session_4h_catchup(
            conn, ["OFSS", "RELIANCE", "TATACONSUM"], max_symbols=2
        )
        self.assertEqual(len(picked), 2)
        self.assertEqual(picked[0], "RELIANCE")
        self.assertEqual(picked[1], "TATACONSUM")

    @patch("server.bars_4h.datetime")
    @patch.dict("os.environ", {}, clear=False)
    def test_should_defer_bars_4h_during_session(self, mock_dt):
        import os

        os.environ.pop("CIM_BARS_4H_DURING_SESSION", None)
        mock_dt.now.return_value = datetime(2026, 7, 10, 11, 0, tzinfo=IST)

        with patch(
            "server.bars_4h.load_nse_calendar",
            return_value={"holidays": set(), "special_sessions": set()},
        ):
            with patch("server.bars_4h.is_nse_session_day", return_value=True):
                defer, reason = should_defer_bars_4h_build(ROOT)
        self.assertTrue(defer)
        self.assertIn("live session", reason)
        self.assertIn("15:30", reason)

    @patch("server.bars_4h.datetime")
    @patch.dict("os.environ", {}, clear=False)
    def test_should_not_defer_after_1530(self, mock_dt):
        import os

        os.environ.pop("CIM_BARS_4H_DURING_SESSION", None)
        mock_dt.now.return_value = datetime(2026, 7, 10, 15, 30, tzinfo=IST)

        with patch(
            "server.bars_4h.load_nse_calendar",
            return_value={"holidays": set(), "special_sessions": set()},
        ):
            with patch("server.bars_4h.is_nse_session_day", return_value=True):
                defer, reason = should_defer_bars_4h_build(ROOT)
        self.assertFalse(defer)
        self.assertIn("post-close", reason)

    @patch.dict("os.environ", {"CIM_BARS_4H_DURING_SESSION": "1"}, clear=False)
    def test_should_defer_forced_off(self):
        defer, reason = should_defer_bars_4h_build(ROOT)
        self.assertFalse(defer)
        self.assertIn("forced", reason.lower())

    def test_latest_completed_4h_session_before_close(self):
        now = datetime(2026, 7, 10, 14, 0, tzinfo=IST)  # Friday mid-session
        latest = latest_completed_4h_session_date(
            now=now,
            holidays=set(),
            special_sessions=set(),
        )
        self.assertEqual(latest, date(2026, 7, 9))

    def test_latest_completed_4h_session_at_close(self):
        now = datetime(2026, 7, 10, 15, 30, tzinfo=IST)
        latest = latest_completed_4h_session_date(
            now=now,
            holidays=set(),
            special_sessions=set(),
        )
        self.assertEqual(latest, date(2026, 7, 10))

    def test_symbols_needing_4h_refresh(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        sd = "2026-07-10"
        conn.execute(
            "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
            "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
            ("RELIANCE", f"{sd}T09:15:00+05:30", sd),
        )
        conn.commit()
        needing = symbols_needing_4h_refresh(
            conn, ["RELIANCE", "TCS", "INFY"], date(2026, 7, 10)
        )
        self.assertEqual(needing, ["TCS", "INFY"])

    def test_symbols_needing_4h_refresh_detects_mid_window_hole(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        for sd in ("2026-07-13", "2026-07-15"):
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("BAJAJCON", f"{sd}T09:15:00+05:30", sd),
            )
        conn.commit()
        needing = symbols_needing_4h_refresh(
            conn,
            ["BAJAJCON", "RELIANCE"],
            [date(2026, 7, 15), date(2026, 7, 14), date(2026, 7, 13)],
        )
        self.assertEqual(needing, ["BAJAJCON", "RELIANCE"])
        conn.execute(
            "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
            "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
            ("BAJAJCON", "2026-07-14T09:15:00+05:30", "2026-07-14"),
        )
        conn.commit()
        needing2 = symbols_needing_4h_refresh(
            conn,
            ["BAJAJCON"],
            [date(2026, 7, 15), date(2026, 7, 14), date(2026, 7, 13)],
        )
        self.assertEqual(needing2, [])

    def test_incremental_session_days_covers_recent_window(self):
        self.assertGreaterEqual(BARS_4H_INCREMENTAL_SESSION_DAYS, 3)

    def test_incremental_build_fetches_and_upserts_latest_session_only(self):
        from server.bars_4h import Fetch5mResult

        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        target = date(2026, 7, 10)
        captured = {}

        def fake_fetch(symbols, windows, base_dir):
            captured["windows"] = list(windows)
            rows = [
                (_ist(2026, 7, 9, 10, 0), 90.0, 91.0, 89.0, 90.5, 100.0),
                (_ist(2026, 7, 10, 10, 0), 100.0, 101.0, 99.0, 100.5, 200.0),
                (_ist(2026, 7, 10, 14, 0), 100.5, 102.0, 100.0, 101.0, 300.0),
            ]
            return {s: Fetch5mResult(rows=rows, source="upstox") for s in symbols}

        with patch(
            "server.bars_4h.load_nse_calendar",
            return_value={"holidays": set(), "special_sessions": set()},
        ):
            with patch(
                "server.bars_4h.recent_completed_4h_session_dates",
                return_value=[target],
            ):
                with patch("server.bars_4h.fetch_5m_with_fallback", side_effect=fake_fetch):
                    with patch(
                        "server.upstox_config.market_data_enabled",
                        return_value=False,
                    ):
                        build_bars_4h_for_symbols(
                            conn, ["RELIANCE"], ROOT, backfill=False
                        )

        self.assertEqual(len(captured["windows"]), 1)
        w_start, w_end = captured["windows"][0]
        self.assertEqual(w_start.date(), target)
        self.assertEqual(w_start.hour, 9)
        self.assertEqual(w_start.minute, 15)
        self.assertEqual(w_end.date(), target)

        rows = conn.execute(
            "SELECT SessionDate, COUNT(*) FROM bars_4h WHERE Symbol=? GROUP BY SessionDate",
            ("RELIANCE",),
        ).fetchall()
        self.assertEqual(rows, [("2026-07-10", 2)])


if __name__ == "__main__":
    unittest.main()
