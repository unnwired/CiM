"""Regression tests for index 1D % alignment, Update summary, and dashboard live % guards."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "nse_data.db"
SCRAPE_INDICES_PATH = ROOT / "scrape_indices.py"


def _import_server():
    path = Path(__file__).resolve().parent.parent / "server.py"
    spec = importlib.util.spec_from_file_location("nse_pulse_server_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _import_scrape_indices():
    spec = importlib.util.spec_from_file_location("scrape_indices_test", SCRAPE_INDICES_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _build_update_finish_summary(stocks_n: int, total_idx, index_ohlcv_error) -> str:
    """Mirror run_fetch_ohlcv finish line (server.py)."""
    if index_ohlcv_error:
        idx_part = f"index OHLCV failed ({index_ohlcv_error})"
    elif total_idx is None:
        idx_part = "index OHLCV not run"
    else:
        idx_part = f"{total_idx} index candles added"
    summary = (
        f"Chart data updated. {stocks_n} stock symbols, {idx_part}. "
        "Change % recalculated."
    )
    if total_idx == 0 and not index_ohlcv_error:
        summary += (
            " No new index bars were written — Indices charts may still "
            "show the last stored session."
        )
    return summary


class IndexPctAlignmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = _import_server()
        if not DB_PATH.is_file():
            raise unittest.SkipTest(f"DB not found: {DB_PATH}")

    def test_equity_indices_list_matches_history_day_pct(self):
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT symbol FROM indices WHERE category = 'equity' ORDER BY symbol"
            )
            symbols = [r[0] for r in cur.fetchall()]
            live_map = self.srv._index_live_day_change_map(conn, symbols)
            mismatches = []
            for sym in symbols:
                lk = live_map.get(str(sym).strip())
                if lk is None:
                    continue
                single = self.srv._index_day_change_pct_single(sym, conn)
                if single is None:
                    continue
                if abs(float(lk) - float(single)) > 0.011:
                    mismatches.append((sym, lk, single))
            self.assertEqual(
                mismatches,
                [],
                f"live_map vs single mismatch: {mismatches[:5]}",
            )
        finally:
            conn.close()

    def test_cnxit_history_pct_consistent(self):
        sym = "^CNXIT"
        conn = sqlite3.connect(DB_PATH)
        try:
            pct = self.srv._index_day_change_pct_single(sym, conn)
            self.assertIsNotNone(pct)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT Close FROM index_history WHERE Symbol=? ORDER BY Date DESC LIMIT 2
                """,
                (sym,),
            )
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            calc = round((float(rows[0][0]) - float(rows[1][0])) / float(rows[1][0]) * 100, 2)
            self.assertAlmostEqual(float(pct), calc, places=2)
        finally:
            conn.close()


class UpdateFinishSummaryTest(unittest.TestCase):
    def test_success_with_candles(self):
        s = _build_update_finish_summary(10, 42, None)
        self.assertIn("10 stock symbols", s)
        self.assertIn("42 index candles added", s)
        self.assertNotIn("failed", s)

    def test_zero_candles_warning(self):
        s = _build_update_finish_summary(1, 0, None)
        self.assertIn("0 index candles added", s)
        self.assertIn("No new index bars were written", s)

    def test_index_failure_explicit(self):
        s = _build_update_finish_summary(5, None, "charmap codec")
        self.assertIn("index OHLCV failed (charmap codec)", s)
        self.assertNotIn("index candles added", s)


class LiveDayChangeGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = _import_server()

    def test_stale_zero_live_not_applied(self):
        self.assertFalse(self.srv._should_apply_live_day_change(2.5, 0.0))
        self.assertFalse(self.srv._should_apply_live_day_change(-1.2, 0.0))

    def test_real_live_applied(self):
        self.assertTrue(self.srv._should_apply_live_day_change(2.5, 2.8))


class ScrapeIndicesLogTest(unittest.TestCase):
    def test_nifty_india_defence_in_equity_catalog(self):
        scrape = _import_scrape_indices()
        symbols = [s for s, _n, c in scrape.INDICES if c == "equity"]
        self.assertIn("^CNXINDDEF", symbols)
        self.assertEqual(scrape.NSE_NAME_MAP.get("^CNXINDDEF"), "NIFTY INDIA DEFENCE")

    def test_log_replaces_unicode_checkmarks(self):
        scrape = _import_scrape_indices()
        buf = []
        orig = sys.stdout

        class _Capture:
            def write(self, s):
                buf.append(s)

            def flush(self):
                pass

        try:
            sys.stdout = _Capture()
            scrape._log("done \u2713 ok")
        finally:
            sys.stdout = orig
        out = "".join(buf)
        self.assertIn("[OK]", out)
        self.assertNotIn("\u2713", out)


if __name__ == "__main__":
    unittest.main()
