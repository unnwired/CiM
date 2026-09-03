"""Indicator snapshots that predate the newest bar must not drive screener filters."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch


class _NoCache:
    def get_snapshot_coverage(self, timeframe):
        return None

    def set_snapshot_coverage(self, timeframe, ok):
        return None


def _db(*, snapshot_day, last_bar_day, timeframe="1D", symbols=10, covered=10):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE screener (Symbol TEXT PRIMARY KEY);
        CREATE TABLE indicator_snapshots (symbol TEXT, timeframe TEXT, updated_at TEXT);
        CREATE TABLE historical_data (Symbol TEXT, Date TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO screener VALUES (?)", [(f"SYM{i}",) for i in range(symbols)]
    )
    conn.executemany(
        "INSERT INTO indicator_snapshots VALUES (?,?,?)",
        [(f"SYM{i}", timeframe, f"{snapshot_day} 18:05:11") for i in range(covered)],
    )
    conn.execute("INSERT INTO historical_data VALUES ('SYM0', ?)", (last_bar_day,))
    return conn


class SnapshotFreshnessTests(unittest.TestCase):
    def _cover(self, conn, timeframe="1D"):
        from server import server as srv

        class _Conn:
            def cursor(self_inner):
                return conn.cursor()

            def close(self_inner):
                pass

        with patch.object(srv, "get_db_connection", return_value=_Conn()), patch.object(
            srv, "_app_caches", _NoCache()
        ), patch.object(type(srv.DB_PATH), "exists", lambda _self: True):
            return srv._indicator_snapshots_cover_universe(timeframe)

    def test_same_day_snapshot_is_used(self):
        conn = _db(snapshot_day="2026-07-31", last_bar_day="2026-07-31")
        self.assertTrue(self._cover(conn))

    def test_snapshot_rebuilt_after_the_last_bar_is_used(self):
        conn = _db(snapshot_day="2026-08-01", last_bar_day="2026-07-31")
        self.assertTrue(self._cover(conn))

    def test_snapshot_behind_the_last_bar_is_rejected(self):
        conn = _db(snapshot_day="2026-07-20", last_bar_day="2026-07-31")
        self.assertFalse(self._cover(conn))

    def test_partial_coverage_still_rejected(self):
        conn = _db(
            snapshot_day="2026-07-31", last_bar_day="2026-07-31", symbols=100, covered=10
        )
        self.assertFalse(self._cover(conn))

    def test_monthly_timeframe_keeps_coverage_only_check(self):
        conn = _db(snapshot_day="2026-06-26", last_bar_day="2026-07-31", timeframe="1M")
        self.assertTrue(self._cover(conn, "1M"))

    def test_missing_updated_at_is_treated_as_stale(self):
        conn = _db(snapshot_day="2026-07-31", last_bar_day="2026-07-31")
        conn.execute("UPDATE indicator_snapshots SET updated_at = NULL")
        self.assertFalse(self._cover(conn))


if __name__ == "__main__":
    unittest.main()
