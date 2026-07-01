"""Unit tests for NSE index history fallback (no network)."""

from __future__ import annotations

import importlib.util
import sqlite3
import unittest
from datetime import date
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT


def _import_nse_index_history():
    path = ROOT / "nse_index_history.py"
    spec = importlib.util.spec_from_file_location("nse_index_history_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class NseIndexHistoryParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_nse_index_history()

    def test_normalize_nse_history_row(self):
        row = {
            "EOD_INDEX_NAME": "NIFTY IND DEFENCE",
            "EOD_OPEN_INDEX_VAL": 8281.75,
            "EOD_HIGH_INDEX_VAL": 8285.45,
            "EOD_CLOSE_INDEX_VAL": 8116.4,
            "EOD_LOW_INDEX_VAL": 8109.05,
            "HIT_TRADED_QTY": 16735340,
            "EOD_TIMESTAMP": "21-NOV-2025",
        }
        norm = self.mod.normalize_nse_history_row(row)
        self.assertIsNotNone(norm)
        assert norm is not None
        self.assertEqual(norm["date"], "2025-11-21")
        self.assertEqual(norm["close"], 8116.4)

    def test_iter_date_chunks_respects_max_window(self):
        start = date(2024, 1, 1)
        end = date(2025, 6, 1)
        chunks = list(self.mod.iter_date_chunks(start, end, max_days=85))
        self.assertGreaterEqual(len(chunks), 4)
        for a, b in chunks:
            self.assertLessEqual((b - a).days, 85)

    def test_find_index_history_gaps(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE index_history (
                    Symbol TEXT, Date TEXT, Open REAL, High REAL,
                    Low REAL, Close REAL, Volume REAL,
                    PRIMARY KEY (Symbol, Date)
                )
                """
            )
            for d in ("2025-02-14", "2025-02-18", "2025-10-27", "2025-10-31"):
                conn.execute(
                    "INSERT INTO index_history VALUES (?, ?, 1, 1, 1, 1, 0)",
                    ("^CNXINDDEF", d),
                )
            conn.commit()
            gaps = self.mod.find_index_history_gaps(conn, "^CNXINDDEF")
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0][0].isoformat(), "2025-02-19")
            self.assertEqual(gaps[0][1].isoformat(), "2025-10-26")
        finally:
            conn.close()


class NseHistoryRefreshTargetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "scrape_indices_test", ROOT / "scrape_indices.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        cls.scrape = mod

    def test_defence_index_marked_nse_only(self):
        self.assertIn("^CNXINDDEF", self.scrape.NSE_ONLY_INDEX_SYMBOLS)

    def test_healthcare_index_marked_nse_only(self):
        self.assertIn("NIFTY_HEALTHCARE.NS", self.scrape.NSE_ONLY_INDEX_SYMBOLS)
        self.assertEqual(
            self.scrape.NSE_INDEX_HISTORY_START.get("NIFTY_HEALTHCARE.NS"),
            "2020-11-18",
        )

    def test_stale_defence_selected_for_refresh(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE indices (
                    symbol TEXT PRIMARY KEY, name TEXT, category TEXT,
                    last_price REAL, change_pct REAL, change_30d REAL,
                    change_1y REAL, updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE index_history (
                    Symbol TEXT, Date TEXT, Open REAL, High REAL,
                    Low REAL, Close REAL, Volume REAL,
                    PRIMARY KEY (Symbol, Date)
                )
                """
            )
            conn.execute(
                "INSERT INTO indices VALUES (?, ?, 'equity', 1, 0, 0, 0, 'x')",
                ("^CNXINDDEF", "Nifty India Defence"),
            )
            conn.execute(
                "INSERT INTO index_history VALUES (?, ?, 1, 1, 1, 1, 0)",
                ("^CNXINDDEF", "2020-01-02"),
            )
            conn.commit()
            targets = dict(
                self.scrape._nse_history_symbols_to_refresh(conn, max_lag_days=5)
            )
            self.assertIn("^CNXINDDEF", targets)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
