"""Tests for scrape_4h worklist-only incremental path."""
from __future__ import annotations

import sys
import sqlite3
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

import scrape_4h  # noqa: E402
from server.bars_4h import (  # noqa: E402
    META_BACKFILL_COMPLETE,
    ensure_bars_4h_table,
    ensure_updater_meta_table,
    set_meta,
)


class TestScrape4hIncremental(unittest.TestCase):
    def test_skips_when_all_current(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        ensure_updater_meta_table(conn)
        set_meta(conn, META_BACKFILL_COMPLETE, "1")
        latest = "2026-07-10"
        for sym in ("AAA", "BBB"):
            for i in range(25):
                sd = latest if i == 24 else f"2026-06-{i + 1:02d}"
                conn.execute(
                    "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                    "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                    (sym, f"{sd}T09:15:00+05:30", sd),
                )
        conn.commit()

        messages = []
        build_calls = []

        def fake_build(conn_arg, symbols, base_dir, **kwargs):
            build_calls.append(list(symbols))
            return {"updated": 0, "failed": 0, "skipped": 0, "processed": 0, "sources": {}}

        with patch.object(scrape_4h, "connect_db", return_value=conn):
            with patch("server.bars_4h.build_bars_4h_for_symbols", side_effect=fake_build):
                with patch(
                    "server.bars_4h.recent_completed_4h_session_dates",
                    return_value=[date(2026, 7, 10)],
                ):
                    with patch(
                        "server.bars_4h.load_nse_calendar",
                        return_value={"holidays": set(), "special_sessions": set()},
                    ):
                        totals = scrape_4h.run(
                            symbols=["AAA", "BBB"],
                            backfill=False,
                            message_callback=messages.append,
                        )

        self.assertEqual(build_calls, [])
        self.assertIn("already current", " ".join(messages).lower())
        self.assertEqual(totals.get("skipped_current"), 2)

    def test_does_not_full_universe_when_partial_stale(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        ensure_updater_meta_table(conn)
        set_meta(conn, META_BACKFILL_COMPLETE, "1")
        latest = "2026-07-10"
        for i in range(25):
            sd = f"2026-06-{i + 1:02d}" if i < 24 else latest
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("AAA", f"{sd}T09:15:00+05:30", sd),
            )
        for i in range(25):
            sd = f"2026-06-{i + 1:02d}"
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("BBB", f"{sd}T09:15:00+05:30", sd),
            )
        conn.commit()

        build_calls = []

        def fake_build(conn_arg, symbols, base_dir, **kwargs):
            build_calls.append({"symbols": list(symbols), "backfill": kwargs.get("backfill")})
            return {
                "updated": len(symbols),
                "failed": 0,
                "skipped": 0,
                "processed": len(symbols),
                "sources": {"upstox": len(symbols)},
            }

        with patch.object(scrape_4h, "connect_db", return_value=conn):
            with patch("server.bars_4h.build_bars_4h_for_symbols", side_effect=fake_build):
                with patch(
                    "server.bars_4h.recent_completed_4h_session_dates",
                    return_value=[date(2026, 7, 10)],
                ):
                    with patch(
                        "server.bars_4h.load_nse_calendar",
                        return_value={"holidays": set(), "special_sessions": set()},
                    ):
                        scrape_4h.run(symbols=["AAA", "BBB", "CCC"], backfill=False)

        # CCC needs depth backfill; BBB missing latest only — never full [AAA,BBB,CCC] incremental.
        all_syms = [tuple(c["symbols"]) for c in build_calls]
        self.assertTrue(build_calls)
        self.assertNotIn(("AAA", "BBB", "CCC"), all_syms)
        for c in build_calls:
            self.assertNotIn("AAA", c["symbols"])

    def test_meta_unset_does_not_force_universe_90d(self):
        """backfill=False must stay incremental even when META is unset."""
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        ensure_updater_meta_table(conn)
        # Meta intentionally unset (not "1").
        latest = "2026-07-10"
        for i in range(25):
            sd = f"2026-06-{i + 1:02d}" if i < 24 else latest
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("AAA", f"{sd}T09:15:00+05:30", sd),
            )
        for i in range(25):
            sd = f"2026-06-{i + 1:02d}"
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("BBB", f"{sd}T09:15:00+05:30", sd),
            )
        conn.commit()

        build_calls = []

        def fake_build(conn_arg, symbols, base_dir, **kwargs):
            build_calls.append({"symbols": list(symbols), "backfill": kwargs.get("backfill")})
            return {
                "updated": len(symbols),
                "failed": 0,
                "skipped": 0,
                "processed": len(symbols),
                "sources": {"upstox": len(symbols)},
            }

        with patch.object(scrape_4h, "connect_db", return_value=conn):
            with patch("server.bars_4h.build_bars_4h_for_symbols", side_effect=fake_build):
                with patch(
                    "server.bars_4h.recent_completed_4h_session_dates",
                    return_value=[date(2026, 7, 10)],
                ):
                    with patch(
                        "server.bars_4h.load_nse_calendar",
                        return_value={"holidays": set(), "special_sessions": set()},
                    ):
                        scrape_4h.run(symbols=["AAA", "BBB"], backfill=False)

        self.assertTrue(build_calls)
        self.assertFalse(any(c["backfill"] is True for c in build_calls))
        self.assertEqual(build_calls[0]["symbols"], ["BBB"])

    def test_shallow_symbols_scoped_depth_without_clearing_meta(self):
        conn = sqlite3.connect(":memory:")
        ensure_bars_4h_table(conn)
        ensure_updater_meta_table(conn)
        set_meta(conn, META_BACKFILL_COMPLETE, "1")
        latest = "2026-07-10"
        for i in range(25):
            sd = f"2026-06-{i + 1:02d}" if i < 24 else latest
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("AAA", f"{sd}T09:15:00+05:30", sd),
            )
        # BBB is shallow (2 sessions only).
        for i in range(2):
            sd = f"2026-06-{10 + i}"
            conn.execute(
                "INSERT INTO bars_4h (Symbol, BarStart, SessionDate, Bucket, Open, High, Low, Close, Volume) "
                "VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1)",
                ("BBB", f"{sd}T09:15:00+05:30", sd),
            )
        conn.commit()

        build_calls = []
        meta_during = []

        def fake_build(conn_arg, symbols, base_dir, **kwargs):
            build_calls.append({"symbols": list(symbols), "backfill": kwargs.get("backfill")})
            meta_during.append(
                conn_arg.execute(
                    "SELECT value FROM updater_meta WHERE key=?",
                    (META_BACKFILL_COMPLETE,),
                ).fetchone()[0]
            )
            return {
                "updated": len(symbols),
                "failed": 0,
                "skipped": 0,
                "processed": len(symbols),
                "sources": {"upstox": len(symbols)},
            }

        with patch.object(scrape_4h, "connect_db", return_value=conn):
            with patch("server.bars_4h.build_bars_4h_for_symbols", side_effect=fake_build):
                with patch(
                    "server.bars_4h.recent_completed_4h_session_dates",
                    return_value=[date(2026, 7, 10)],
                ):
                    with patch(
                        "server.bars_4h.load_nse_calendar",
                        return_value={"holidays": set(), "special_sessions": set()},
                    ):
                        scrape_4h.run(symbols=["AAA", "BBB"], backfill=False)

        self.assertTrue(meta_during)
        self.assertTrue(all(v == "1" for v in meta_during))
        depth_calls = [c for c in build_calls if c["backfill"] is True]
        self.assertEqual(len(depth_calls), 1)
        self.assertEqual(depth_calls[0]["symbols"], ["BBB"])
        self.assertNotIn("AAA", depth_calls[0]["symbols"])


if __name__ == "__main__":
    unittest.main()
