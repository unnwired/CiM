#!/usr/bin/env python3
"""
E2E: MACD filter Level crosses_up Signal on 2W must match chart-parity MACD math.

Verifies indicator_snapshots rows (after chart-parity rebuild) agree with
snapshot_bars.macd_crosses_up_level_signal on the same historical_data.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages"
SERVER_PKG = ROOT / "packages" / "server"
TESTS_PKG = SERVER_PKG / "tests"
for p in (str(PKG), str(SERVER_PKG), str(TESTS_PKG), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from repo_paths import REPO_ROOT  # noqa: E402

import importlib.util

_sb_spec = importlib.util.spec_from_file_location(
    "snapshot_bars",
    REPO_ROOT / "packages" / "server" / "snapshot_bars.py",
)
_snapshot_bars = importlib.util.module_from_spec(_sb_spec)
_sb_spec.loader.exec_module(_snapshot_bars)
chart_candles_for_timeframe = _snapshot_bars.chart_candles_for_timeframe
macd_crosses_up_level_signal = _snapshot_bars.macd_crosses_up_level_signal


def find_db() -> Path | None:
    for raw in (
        os.environ.get("CIM_DB_PATH"),
        REPO_ROOT / "data" / "nse_data.db",
        Path(r"D:\CiM\Client_Test\data\nse_data.db"),
    ):
        if not raw:
            continue
        p = Path(raw)
        if p.is_file():
            return p
    return None


def chart_crosses_up(conn: sqlite3.Connection, symbol: str) -> bool | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT SUBSTR(Date,1,10), Open, High, Low, Close
        FROM historical_data WHERE Symbol = ? ORDER BY Date ASC
        """,
        (symbol,),
    )
    rows = cur.fetchall()
    if len(rows) < 40:
        return None
    candles = chart_candles_for_timeframe(rows, "2W")
    if len(candles) < 37:
        return None
    closes = [float(c[4]) for c in candles]
    return macd_crosses_up_level_signal(closes)


def snapshot_crosses_up(row: dict) -> bool:
    m = row.get("macd")
    mp = row.get("macd_prev")
    s = row.get("macd_signal")
    sp = row.get("macd_signal_prev")
    if m is None or s is None or mp is None or sp is None:
        return False
    return mp <= sp and m > s


def build_fresh_snapshot_row(conn: sqlite3.Connection, symbol: str) -> dict | None:
    """Recompute 2W snapshot row using scrape_daily chart-parity path."""
    import importlib.util

    scrape_path = REPO_ROOT / "scrape_daily.py"
    spec = importlib.util.spec_from_file_location("nse_pulse_scrape_daily_test", scrape_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT SUBSTR(Date,1,10), Open, High, Low, Close
        FROM historical_data WHERE Symbol = ? ORDER BY Date ASC
        """,
        (symbol,),
    )
    candles = [(r[0], r[1], r[2], r[3], r[4]) for r in cur.fetchall()]
    rows = mod._build_snapshot_rows_for_symbol(symbol, candles, allowed_timeframes=("2W",))
    for row in rows:
        if row.get("timeframe") == "2W":
            return row
    return None


class MacdFilter2WCrossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = find_db()
        if cls.db is None:
            raise unittest.SkipTest("nse_data.db not found")
        cls.conn = sqlite3.connect(str(cls.db))
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_reliance_chart_matches_fresh_snapshot_cross(self):
        sym = "RELIANCE"
        chart = chart_crosses_up(self.conn, sym)
        if chart is None:
            self.skipTest(f"insufficient history for {sym}")
        fresh = build_fresh_snapshot_row(self.conn, sym)
        self.assertIsNotNone(fresh, "fresh snapshot row")
        snap_cross = snapshot_crosses_up(fresh)
        self.assertEqual(
            chart,
            snap_cross,
            f"{sym} 2W crosses_up: chart={chart} snapshot={snap_cross} "
            f"macd={fresh['macd']} signal={fresh['macd_signal']} "
            f"prev macd={fresh['macd_prev']} prev signal={fresh['macd_signal_prev']}",
        )

    def test_filter_macd_api_matches_chart_for_sample(self):
        """filter_macd on 2W crosses_up should match chart-parity recompute for sample symbols."""
        cur = self.conn.cursor()
        cur.execute("SELECT symbol FROM screener ORDER BY symbol ASC LIMIT 200")
        symbols = [str(r[0]).upper() for r in cur.fetchall() if r[0]]

        mismatches = []
        checked = 0
        for sym in symbols:
            chart = chart_crosses_up(self.conn, sym)
            if chart is None:
                continue
            fresh = build_fresh_snapshot_row(self.conn, sym)
            if fresh is None:
                continue
            snap = snapshot_crosses_up(fresh)
            checked += 1
            if chart != snap:
                mismatches.append((sym, chart, snap))

        self.assertGreater(checked, 10, "need enough symbols with 2W MACD history")
        self.assertEqual(
            mismatches,
            [],
            f"chart vs fresh-snapshot crosses_up mismatches: {mismatches[:15]}",
        )

    def test_stored_snapshots_match_chart_when_present(self):
        """DB indicator_snapshots 2W rows should match chart after parity rebuild."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT s.symbol, i.macd, i.macd_prev, i.macd_signal, i.macd_signal_prev
            FROM indicator_snapshots i
            JOIN screener s ON s.symbol = i.symbol
            WHERE i.timeframe = '2W'
            LIMIT 150
            """
        )
        rows = cur.fetchall()
        if not rows:
            self.skipTest("no 2W indicator_snapshots rows — run full rebuild first")

        mismatches = []
        for row in rows:
            sym = str(row[0]).upper()
            chart = chart_crosses_up(self.conn, sym)
            if chart is None:
                continue
            snap_row = {
                "macd": row[1],
                "macd_prev": row[2],
                "macd_signal": row[3],
                "macd_signal_prev": row[4],
            }
            snap = snapshot_crosses_up(snap_row)
            if chart != snap:
                mismatches.append((sym, chart, snap, snap_row))

        if mismatches:
            self.fail(
                "stored snapshot vs chart crosses_up mismatches (rebuild snapshots): "
                + repr(mismatches[:10])
            )


if __name__ == "__main__":
    unittest.main()
