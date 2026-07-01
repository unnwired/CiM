"""Tests for issued share count Yahoo → Screener → NSE cascade."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.admin_job_control import JobCancelled, request_cancel, sleep_interruptible, clear_cancel
from server.issued_shares_fetch import (
    IssuedSharesCascadeState,
    fetch_issued_shares_cascade,
    process_symbol_batch,
    set_issued_shares_source,
)


class TestIssuedSharesCascade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("server.issued_shares_fetch.fetch_nse_issued_shares")
    @patch("server.issued_shares_fetch.fetch_screener_issued_shares")
    @patch("server.issued_shares_fetch.fetch_yahoo_issued_shares")
    def test_yahoo_hit_skips_lower_tiers(self, mock_yahoo, mock_screener, mock_nse):
        mock_yahoo.return_value = 1_000_000
        state = IssuedSharesCascadeState(allow_nse=True)
        res = fetch_issued_shares_cascade(
            "RELIANCE",
            data_dir=self.data_dir,
            price=2500.0,
            state=state,
            nse_session=MagicMock(),
        )
        self.assertEqual(res.source, "yahoo")
        self.assertEqual(res.issued_shares, 1_000_000)
        mock_screener.assert_not_called()
        mock_nse.assert_not_called()

    @patch("server.issued_shares_fetch.fetch_nse_issued_shares")
    @patch("server.issued_shares_fetch.fetch_screener_issued_shares")
    @patch("server.issued_shares_fetch.fetch_yahoo_issued_shares")
    def test_screener_fallback_when_yahoo_misses(self, mock_yahoo, mock_screener, mock_nse):
        mock_yahoo.return_value = None
        mock_screener.return_value = 500_000
        state = IssuedSharesCascadeState(allow_nse=True)
        res = fetch_issued_shares_cascade(
            "TCS",
            data_dir=self.data_dir,
            price=3500.0,
            state=state,
            nse_session=MagicMock(),
        )
        self.assertEqual(res.source, "screener")
        self.assertEqual(res.issued_shares, 500_000)
        mock_nse.assert_not_called()

    @patch("server.issued_shares_fetch.fetch_nse_issued_shares")
    @patch("server.issued_shares_fetch.fetch_screener_issued_shares")
    @patch("server.issued_shares_fetch.fetch_yahoo_issued_shares")
    def test_showcase_skips_nse_tier(self, mock_yahoo, mock_screener, mock_nse):
        mock_yahoo.return_value = None
        mock_screener.return_value = None
        state = IssuedSharesCascadeState(allow_nse=False)
        res = fetch_issued_shares_cascade(
            "INFY",
            data_dir=self.data_dir,
            price=1500.0,
            state=state,
            nse_session=MagicMock(),
        )
        self.assertEqual(res.source, "none")
        self.assertIsNone(res.issued_shares)
        mock_nse.assert_not_called()

    @patch("server.issued_shares_fetch.fetch_nse_issued_shares")
    @patch("server.issued_shares_fetch.fetch_screener_issued_shares")
    @patch("server.issued_shares_fetch.fetch_yahoo_issued_shares")
    def test_nse_block_sets_fast_fail_flag(self, mock_yahoo, mock_screener, mock_nse):
        mock_yahoo.return_value = None
        mock_screener.return_value = None
        mock_nse.return_value = (None, "blocked")
        state = IssuedSharesCascadeState(allow_nse=True)
        session = MagicMock()
        res = fetch_issued_shares_cascade(
            "HDFCBANK",
            data_dir=self.data_dir,
            price=1600.0,
            state=state,
            nse_session=session,
        )
        self.assertTrue(state.nse_blocked)
        self.assertEqual(res.nse_status, "blocked")

        mock_nse.reset_mock()
        res2 = fetch_issued_shares_cascade(
            "ICICIBANK",
            data_dir=self.data_dir,
            price=1100.0,
            state=state,
            nse_session=session,
        )
        self.assertIsNone(res2.issued_shares)
        mock_nse.assert_not_called()

    @patch("server.issued_shares_fetch.fetch_yahoo_batch")
    def test_process_batch_cancel_during_loop(self, mock_batch):
        mock_batch.return_value = {}
        cancel_after = {"n": 0}

        def cancel_check():
            cancel_after["n"] += 1
            return cancel_after["n"] > 1

        with patch("server.issued_shares_fetch.fetch_screener_issued_shares", return_value=None):
            with self.assertRaises(JobCancelled):
                process_symbol_batch(
                    ["A", "B", "C"],
                    {"A": 100.0, "B": 100.0, "C": 100.0},
                    data_dir=self.data_dir,
                    state=IssuedSharesCascadeState(allow_nse=False),
                    nse_session=None,
                    cancel_check=cancel_check,
                )

    def test_sleep_interruptible_raises_on_cancel(self):
        clear_cancel()
        request_cancel()
        with self.assertRaises(JobCancelled):
            sleep_interruptible(60.0)

    def test_source_metadata_roundtrip(self):
        conn = sqlite3.connect(":memory:")
        from server.bars_4h import ensure_updater_meta_table

        ensure_updater_meta_table(conn)
        set_issued_shares_source(conn, "RELIANCE", "yahoo")
        row = conn.execute(
            "SELECT value FROM updater_meta WHERE key=?",
            ("issued_shares_source:RELIANCE",),
        ).fetchone()
        self.assertEqual(row[0], "yahoo")


if __name__ == "__main__":
    unittest.main()
