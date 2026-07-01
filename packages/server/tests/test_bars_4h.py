"""Tests for NSE session-aligned 4H bar aggregation."""
from __future__ import annotations

import sys
import sqlite3
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.bars_4h import (  # noqa: E402
    META_BACKFILL_COMPLETE,
    aggregate_intraday_to_4h,
    assign_session_bucket,
    bucket_bar_start,
    ensure_bars_4h_table,
    ensure_updater_meta_table,
    reconcile_4h_backfill_meta,
    set_meta,
    symbols_needing_4h_backfill,
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

    def test_reconcile_clears_stale_backfill_complete(self):
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
            "0",
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


if __name__ == "__main__":
    unittest.main()
