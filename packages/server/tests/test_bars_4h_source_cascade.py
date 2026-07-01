"""Tests for Yahoo -> NSE 4H intraday source cascade."""
from __future__ import annotations

import sys
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.bars_4h import (  # noqa: E402
    fetch_5m_with_fallback,
    format_4h_missing_detail,
    get_bars_4h_source,
    set_bars_4h_source,
    ensure_updater_meta_table,
)

IST = ZoneInfo("Asia/Kolkata")


class TestBars4hSourceCascade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        cfg = self.base / "config"
        cfg.mkdir()
        (cfg / "nse_index_chart_tokens.json").write_text(
            json.dumps({"^CNXINDDEF": {"token": "26085", "chartSymbol": "NIFTY IND DEFENCE"}}),
            encoding="utf-8",
        )
        self.start = datetime(2026, 6, 23, 9, 15, tzinfo=IST)
        self.end = datetime(2026, 6, 25, 15, 30, tzinfo=IST)
        self.windows = [(self.start, self.end)]

    def tearDown(self):
        self.tmp.cleanup()

    @patch("server.bars_4h.fetch_5m_for_symbols")
    @patch("server.nse_charting_intraday.fetch_nse_charting_5m")
    def test_yahoo_hit_skips_nse(self, mock_nse, mock_yahoo):
        row = (self.start, 100.0, 101.0, 99.0, 100.5, 10.0)
        mock_yahoo.return_value = {"^NSEI": [row]}
        out = fetch_5m_with_fallback(["^NSEI"], self.windows, self.base)
        self.assertEqual(out["^NSEI"].source, "yahoo")
        self.assertEqual(len(out["^NSEI"].rows), 1)
        mock_nse.assert_not_called()

    @patch("server.bars_4h.fetch_5m_for_symbols")
    @patch("server.nse_charting_intraday.fetch_nse_charting_5m")
    def test_yahoo_miss_uses_nse_when_token_exists(self, mock_nse, mock_yahoo):
        mock_yahoo.return_value = {}
        row = (self.start, 9000.0, 9010.0, 8990.0, 9005.0, 0.0)
        mock_nse.return_value = [row]
        out = fetch_5m_with_fallback(["^CNXINDDEF"], self.windows, self.base)
        self.assertEqual(out["^CNXINDDEF"].source, "nse_charting")
        self.assertEqual(len(out["^CNXINDDEF"].rows), 1)
        mock_nse.assert_called()

    @patch("server.bars_4h.fetch_5m_for_symbols")
    @patch("server.nse_charting_intraday.fetch_nse_charting_5m")
    def test_both_miss_returns_none(self, mock_nse, mock_yahoo):
        mock_yahoo.return_value = {}
        mock_nse.return_value = []
        out = fetch_5m_with_fallback(["^CNXINDDEF"], self.windows, self.base)
        self.assertEqual(out["^CNXINDDEF"].source, "none")
        self.assertEqual(out["^CNXINDDEF"].rows, [])

    @patch("server.bars_4h.fetch_5m_for_symbols")
    @patch("server.nse_charting_intraday.fetch_nse_charting_5m")
    def test_no_token_skips_nse(self, mock_nse, mock_yahoo):
        mock_yahoo.return_value = {}
        out = fetch_5m_with_fallback(["UNKNOWN"], self.windows, self.base)
        self.assertEqual(out["UNKNOWN"].source, "none")
        mock_nse.assert_not_called()

    def test_source_metadata_roundtrip(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        ensure_updater_meta_table(conn)
        set_bars_4h_source(conn, "^CNXINDDEF", "nse_charting")
        self.assertEqual(get_bars_4h_source(conn, "^CNXINDDEF"), "nse_charting")

    def test_format_4h_missing_detail_after_failed_sources(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        ensure_updater_meta_table(conn)
        set_bars_4h_source(conn, "^CNXINDDEF", "none")
        msg = format_4h_missing_detail("^CNXINDDEF", conn, is_index=True)
        self.assertIn("No 4H intraday source available", msg)


if __name__ == "__main__":
    unittest.main()
