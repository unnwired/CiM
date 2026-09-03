"""Price filter vs open must use latest historical OHLC, not stale snapshots."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch


class TestPriceFilterVsOpenFreshOhlc(unittest.TestCase):
    def test_overlay_rejects_stale_snapshot_green_bar(self):
        """POWERINDIA-style: snapshot still on yesterday (+vs open), today closed below open."""
        from server import server as srv

        # Stale snapshot = yesterday green vs open
        stale = {
            "symbol": "POWERINDIA",
            "open_curr": 32695.0,
            "high_curr": 34080.0,
            "low_curr": 32650.0,
            "close_curr": 33980.0,
            "open_prev": 31550.0,
            "high_prev": 32585.0,
            "low_prev": 31300.0,
            "close_prev": 32345.0,
        }
        # Fresh hist = today red vs open (user's numbers)
        fresh = {
            "open_curr": 34190.0,
            "high_curr": 34215.0,
            "low_curr": 32890.0,
            "close_curr": 33545.0,
            "open_prev": 32695.0,
            "high_prev": 34080.0,
            "low_prev": 32650.0,
            "close_prev": 33980.0,
        }
        patched = srv._overlay_daily_ohlc_on_price_snapshot_row(stale, fresh)
        self.assertEqual(patched["open_curr"], 34190.0)
        self.assertEqual(patched["close_curr"], 33545.0)

        # above_pct 1% vs open: stale would match, fresh must not
        pct = 1.0
        stale_match = stale["close_curr"] > stale["open_curr"] * (1 + pct / 100)
        fresh_match = patched["close_curr"] > patched["open_curr"] * (1 + pct / 100)
        self.assertTrue(stale_match)
        self.assertFalse(fresh_match)

    def test_load_latest_two_daily_ohlc(self):
        from server import server as srv

        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE historical_data (
                Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO historical_data VALUES (?,?,?,?,?,?)",
            [
                ("GROWW", "2026-07-15", 205.0, 219.62, 201.67, 216.33),
                ("GROWW", "2026-07-16", 219.69, 220.98, 204.55, 205.64),
                ("CGPOWER", "2026-07-15", 918.4, 937.85, 915.1, 929.15),
                ("CGPOWER", "2026-07-16", 935.0, 954.9, 919.0, 921.95),
            ],
        )
        m = srv._load_latest_two_daily_ohlc(conn)
        self.assertAlmostEqual(m["GROWW"]["open_curr"], 219.69)
        self.assertAlmostEqual(m["GROWW"]["close_curr"], 205.64)
        self.assertAlmostEqual(m["GROWW"]["open_prev"], 205.0)
        self.assertAlmostEqual(m["CGPOWER"]["close_curr"], 921.95)
        # both below open today → above 1% must fail
        for sym in ("GROWW", "CGPOWER"):
            o = m[sym]["open_curr"]
            c = m[sym]["close_curr"]
            self.assertFalse(c > o * 1.01)

    def test_filter_price_1d_above_pct_open_uses_hist_not_stale_snap(self):
        from server import server as srv

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE screener (symbol TEXT PRIMARY KEY, market_cap REAL);
            INSERT INTO screener VALUES ('POWERINDIA', 1e12);
            CREATE TABLE historical_data (
                Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL
            );
            INSERT INTO historical_data VALUES
              ('POWERINDIA', '2026-07-15', 32695, 34080, 32650, 33980),
              ('POWERINDIA', '2026-07-16', 34190, 34215, 32890, 33545);
            CREATE TABLE indicator_snapshots (
                symbol TEXT, timeframe TEXT,
                close_curr REAL, close_prev REAL,
                open_curr REAL, open_prev REAL,
                high_curr REAL, high_prev REAL,
                low_curr REAL, low_prev REAL
            );
            -- Stale snapshot still on 15 Jul (would falsely match above 1% open)
            INSERT INTO indicator_snapshots VALUES (
                'POWERINDIA', '1D',
                33980, 32345,
                32695, 31550,
                34080, 32585,
                32650, 31300
            );
            """
        )

        class _Cur:
            def __init__(self, c):
                self._c = c

            def execute(self, *a, **k):
                return self._c.execute(*a, **k)

            def fetchall(self):
                return self._c.fetchall()

            def fetchone(self):
                return self._c.fetchone()

        class _Conn:
            def cursor(self):
                return conn.cursor()

            def close(self):
                pass

            def execute(self, *a, **k):
                return conn.execute(*a, **k)

        fake = _Conn()

        with patch.object(srv, "get_db_connection", return_value=fake), patch.object(
            srv, "get_filter_cache", return_value=None
        ), patch.object(srv, "set_filter_cache"), patch.object(
            srv, "_sector_allowed_symbols", return_value=None
        ), patch.object(
            srv, "_load_filter_snapshots",
            return_value=[dict(conn.execute("SELECT * FROM indicator_snapshots").fetchone())],
        ), patch.object(
            srv, "_indicator_snapshots_cover_universe", return_value=True
        ):
            # Direct call of overlay path logic via filter_price
            result = srv.filter_price(
                {
                    "timeframe": "1D",
                    "condition": "above_pct",
                    "pct_value": 1,
                    "target": "open",
                    "ema_period": 21,
                }
            )

        self.assertNotIn("POWERINDIA", result.get("symbols") or [])
        self.assertEqual(result.get("count"), 0)


if __name__ == "__main__":
    unittest.main()
