"""Tests for index_history_integrity gap scan and repair."""

from __future__ import annotations

import importlib.util
import sqlite3
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from repo_paths import REPO_ROOT as ROOT

PKG_SERVER = ROOT / "packages" / "server"
SERVER_PY = PKG_SERVER / "server.py"


def _import_integrity():
    path = PKG_SERVER / "index_history_integrity.py"
    spec = importlib.util.spec_from_file_location("index_history_integrity_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class InstallRootResolutionTest(unittest.TestCase):
    def test_install_root_finds_scrape_indices_in_repo_layout(self):
        mod = _import_integrity()
        root = mod._install_root()
        self.assertTrue((root / "scrape_indices.py").is_file(), root)
        self.assertTrue((root / "nse_index_history.py").is_file(), root)

    def test_install_root_deploy_layout_not_parent_of_client(self):
        """server/index_history_integrity.py under Client_Test -> Client_Test root, not D:\\CiM."""
        mod = _import_integrity()
        here = Path(mod.__file__).resolve()
        # Simulate export layout: .../Client_Test/server/index_history_integrity.py
        if here.name == "index_history_integrity.py" and here.parent.name == "server":
            install = here.parent.parent
            if (install / "scrape_indices.py").is_file():
                self.assertEqual(mod._install_root(), install)


class IndexHistoryIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_integrity()

    def _memory_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE index_history (
                Symbol TEXT, Date TEXT, Open REAL, High REAL,
                Low REAL, Close REAL, Volume REAL,
                PRIMARY KEY (Symbol, Date)
            )
            """
        )
        for d in ("2025-02-05", "2025-10-27"):
            conn.execute(
                "INSERT INTO index_history VALUES (?, ?, 1, 1, 1, 100, 0)",
                ("^CNXNXT50", d),
            )
        conn.commit()
        return conn

    def test_scan_detects_cnxnxt50_gap(self):
        conn = self._memory_conn()
        try:
            scan = self.mod.scan_index_history(conn, symbols=["^CNXNXT50"])
            self.assertEqual(scan["symbols_with_gaps"], 1)
            sym = scan["symbols"][0]
            self.assertEqual(sym["symbol"], "^CNXNXT50")
            self.assertEqual(sym["gap_count"], 1)
            self.assertGreater(sym["gaps"][0]["gap_calendar_days"], 200)
        finally:
            conn.close()

    def test_repair_invokes_scrape_history_for_equity_gaps(self):
        conn = self._memory_conn()
        scrape = MagicMock()
        scrape.INDICES = [("^CNXNXT50", "Nifty Next 50", "equity")]
        scrape.NSE_NAME_MAP = {"^CNXNXT50": "NIFTY NEXT 50"}
        scrape.NSE_INDEX_HISTORY_START = {}
        scrape.get_usd_inr.return_value = 86.0
        scrape.scrape_history.return_value = 42

        with patch.object(self.mod, "_load_scrape_indices", return_value=scrape):
            try:
                result = self.mod.repair_index_gaps(
                    conn, symbols=["^CNXNXT50"], log_fn=lambda _m: None
                )
                self.assertGreaterEqual(result["rows_inserted"], 42)
                scrape.scrape_history.assert_called()
                self.assertIn("^CNXNXT50", result["repaired_symbols"])
            finally:
                conn.close()

    def test_format_integrity_report_scan(self):
        report = self.mod.format_integrity_report(
            {
                "symbols_scanned": 1,
                "symbols_with_gaps": 1,
                "total_gap_ranges": 1,
                "symbols": [
                    {
                        "symbol": "^CNXNXT50",
                        "name": "Nifty Next 50",
                        "gap_count": 1,
                        "row_count": 2,
                        "first_date": "2025-02-05",
                        "last_date": "2025-10-27",
                        "gaps": [
                            {
                                "gap_start": "2025-02-06",
                                "gap_end": "2025-10-26",
                                "gap_calendar_days": 263,
                            }
                        ],
                    }
                ],
            }
        )
        self.assertIn("^CNXNXT50", report)
        self.assertIn("gap", report.lower())

    def test_purge_non_session_index_bars(self):
        conn = self._memory_conn()
        scrape = MagicMock()
        scrape.INDICES = [("^NSEI", "Nifty 50", "equity")]
        try:
            conn.execute(
                "INSERT INTO index_history VALUES ('^NSEI','2026-07-17',1,1,1,1,1)"
            )
            conn.execute(
                "INSERT INTO index_history VALUES ('^NSEI','2026-07-18',1,1,1,1,0)"
            )
            conn.execute(
                "INSERT INTO index_history VALUES ('^NSEI','2026-07-19',1,1,1,1,0)"
            )
            conn.execute(
                "INSERT INTO index_history VALUES ('^NSEI','2026-07-20',1,1,1,1,1)"
            )
            conn.commit()
            with patch.object(self.mod, "_load_scrape_indices", return_value=scrape):
                out = self.mod.purge_non_session_index_bars(conn, since="2026-07-01")
            self.assertEqual(out["deleted"], 2)
            self.assertEqual(sorted(out["dates"]), ["2026-07-18", "2026-07-19"])
            left = [
                r[0]
                for r in conn.execute(
                    "SELECT SUBSTR(Date,1,10) FROM index_history WHERE Symbol='^NSEI' ORDER BY Date"
                )
            ]
            self.assertEqual(left, ["2026-07-17", "2026-07-20"])
        finally:
            conn.close()


class RunFetchOhlcvRegressionTest(unittest.TestCase):
    def test_run_fetch_ohlcv_does_not_call_index_gap_repair(self):
        source = SERVER_PY.read_text(encoding="utf-8")
        start = source.index("def run_fetch_ohlcv")
        end = source.index("\ndef ", start + 1)
        body = source[start:end]
        self.assertNotIn("repair_index_gaps", body)
        self.assertNotIn("run_repair_index_chart_gaps", body)


class AdminRepairEndpointTest(unittest.TestCase):
    def test_admin_repair_endpoint_registered(self):
        source = SERVER_PY.read_text(encoding="utf-8")
        self.assertIn("/api/admin/repair-index-chart-gaps", source)
        self.assertIn("def run_repair_index_chart_gaps", source)


if __name__ == "__main__":
    unittest.main()
