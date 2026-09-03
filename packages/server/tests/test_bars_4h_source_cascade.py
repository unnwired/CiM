"""Tests for Upstox-only 4H intraday source (no Yahoo / NSE mix)."""
from __future__ import annotations

import sys
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
        self.start = datetime(2026, 6, 23, 9, 15, tzinfo=IST)
        self.end = datetime(2026, 6, 25, 15, 30, tzinfo=IST)
        self.windows = [(self.start, self.end)]

    def tearDown(self):
        self.tmp.cleanup()

    @patch("server.bars_4h._fetch_5m_upstox", return_value={})
    @patch("server.bars_4h.fetch_5m_for_symbols")
    def test_upstox_miss_does_not_call_yahoo(self, mock_yahoo, _ux):
        out = fetch_5m_with_fallback(["^NSEI"], self.windows, self.base)
        self.assertEqual(out["^NSEI"].source, "none")
        self.assertEqual(out["^NSEI"].rows, [])
        mock_yahoo.assert_not_called()

    @patch("server.bars_4h._fetch_5m_upstox", return_value={})
    @patch("server.bars_4h.fetch_5m_for_symbols", return_value={})
    def test_both_miss_returns_none(self, _yahoo, _ux):
        out = fetch_5m_with_fallback(["^CNXINDDEF"], self.windows, self.base)
        self.assertEqual(out["^CNXINDDEF"].source, "none")
        self.assertEqual(out["^CNXINDDEF"].rows, [])

    @patch("server.bars_4h._fetch_5m_upstox")
    @patch("server.bars_4h.fetch_5m_for_symbols")
    def test_upstox_hit_skips_yahoo(self, mock_yahoo, mock_ux):
        row = (self.start, 100.0, 101.0, 99.0, 100.5, 10.0)
        mock_ux.return_value = {"^NSEI": [row]}
        out = fetch_5m_with_fallback(["^NSEI"], self.windows, self.base)
        self.assertEqual(out["^NSEI"].source, "upstox")
        mock_yahoo.assert_not_called()

    def test_source_metadata_roundtrip(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        ensure_updater_meta_table(conn)
        set_bars_4h_source(conn, "^CNXINDDEF", "none")
        self.assertEqual(get_bars_4h_source(conn, "^CNXINDDEF"), "none")

    def test_format_4h_missing_detail_after_failed_sources(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        ensure_updater_meta_table(conn)
        set_bars_4h_source(conn, "^CNXINDDEF", "none")
        msg = format_4h_missing_detail("^CNXINDDEF", conn, is_index=True)
        self.assertIn("No 4H intraday source available", msg)
        self.assertIn("Upstox", msg)
        self.assertNotIn("Yahoo", msg)


if __name__ == "__main__":
    unittest.main()
