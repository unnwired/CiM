"""API E2E tests for full Zerodha P&L import pipeline."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

FIXTURES = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"


class PnlImportE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = ROOT / "data" / "nse_data.db"
        if not cls.db_path.exists():
            raise unittest.SkipTest("nse_data.db missing — run dev_setup first")

        import server.server as srv

        cls._srv = srv
        cls._orig_base = srv.BASE_DIR
        cls._orig_data = srv.DATA_DIR
        cls._orig_db = srv.DB_PATH

        cls._tmpdir = tempfile.mkdtemp(prefix="cim-pnl-e2e-")
        cls._base = Path(cls._tmpdir)
        cls._data = cls._base / "data"
        cls._data.mkdir(parents=True)
        shutil.copy2(cls.db_path, cls._data / "nse_data.db")
        shutil.copy2(ROOT / "data" / "corp_actions.json", cls._data / "corp_actions.json")

        srv.BASE_DIR = cls._base
        srv.DATA_DIR = cls._data
        srv.DB_PATH = cls._data / "nse_data.db"

        from fastapi.testclient import TestClient

        cls.client = TestClient(srv.app)

    @classmethod
    def tearDownClass(cls):
        cls._srv.BASE_DIR = cls._orig_base
        cls._srv.DATA_DIR = cls._orig_data
        cls._srv.DB_PATH = cls._orig_db
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _reset_ledger(self):
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        portfolio = {"items": []}
        ledger_path = self._data / "pnl_ledger.json"
        portfolio_path = self._data / "portfolio.json"
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        portfolio_path.write_text(json.dumps(portfolio), encoding="utf-8")

    def _fixture(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def test_tradebook_only_preview_trent_17(self):
        self._reset_ledger()
        r = self.client.post("/api/pnl/import/zerodha/preview", json={
            "csv": self._fixture("tradebook_trent_partial.csv"),
            "apply_corp_actions": False,
            "reconcile_holdings": False,
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("open_qty_after", {}).get("TRENT"), 17)

    def test_holdings_reconcile_trent_25(self):
        self._reset_ledger()
        payload = {
            "csv": self._fixture("tradebook_trent_partial.csv"),
            "holdings_csv": self._fixture("holdings_trent.csv"),
            "reconcile_holdings": True,
            "apply_corp_actions": False,
        }
        r = self.client.post("/api/pnl/import/zerodha", json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        open_r = self.client.get("/api/pnl/open")
        self.assertEqual(open_r.status_code, 200)
        rows = open_r.json().get("data") or []
        trent = [x for x in rows if x.get("symbol") == "TRENT"]
        total_qty = sum(int(x.get("qty") or 0) for x in trent)
        self.assertEqual(total_qty, 25)

    def test_corp_action_trent_25_without_holdings(self):
        self._reset_ledger()
        r = self.client.post("/api/pnl/import/zerodha", json={
            "csv": self._fixture("tradebook_trent_partial.csv"),
            "apply_corp_actions": True,
            "reconcile_holdings": False,
        })
        self.assertEqual(r.status_code, 200, r.text)
        open_r = self.client.get("/api/pnl/open")
        rows = open_r.json().get("data") or []
        trent = [x for x in rows if x.get("symbol") == "TRENT"]
        total_qty = sum(int(x.get("qty") or 0) for x in trent)
        self.assertEqual(total_qty, 25)

    def test_holdings_only_import(self):
        self._reset_ledger()
        r = self.client.post("/api/pnl/import/zerodha", json={
            "holdings_csv": self._fixture("holdings_trent.csv"),
            "reconcile_holdings": True,
            "apply_corp_actions": False,
        })
        self.assertEqual(r.status_code, 200, r.text)
        open_r = self.client.get("/api/pnl/open")
        rows = open_r.json().get("data") or []
        trent = [x for x in rows if x.get("symbol") == "TRENT"]
        total_qty = sum(int(x.get("qty") or 0) for x in trent)
        self.assertEqual(total_qty, 25)

    @patch("server.zerodha_positions.today_sale_date_ist", return_value="2026-06-27")
    def test_today_positions_paras_sell(self, _mock_today):
        self._reset_ledger()
        self.client.post("/api/pnl/import/zerodha", json={
            "csv": self._fixture("tradebook_paras_open.csv"),
            "apply_corp_actions": False,
        })
        r = self.client.post("/api/pnl/import/zerodha", json={
            "csv": self._fixture("tradebook_paras_open.csv"),
            "positions_csv": self._fixture("positions_today_sells.csv"),
            "import_todays_positions": True,
            "apply_corp_actions": False,
        })
        self.assertEqual(r.status_code, 200, r.text)
        closed = self.client.get("/api/pnl/closed").json()
        all_closed = (closed.get("profit") or []) + (closed.get("loss") or [])
        paras = [t for t in all_closed if t.get("symbol") == "PARAS"]
        self.assertTrue(paras)
        self.assertEqual(paras[0].get("qty_sold"), 18)
        self.assertEqual(str(paras[0].get("sale_date", ""))[:10], "2026-06-27")

    @patch("server.zerodha_positions.today_sale_date_ist", return_value="2026-06-27")
    def test_positions_dedupe_on_reimport(self, _mock_today):
        self._reset_ledger()
        base = {
            "csv": self._fixture("tradebook_paras_open.csv"),
            "positions_csv": self._fixture("positions_today_sells.csv"),
            "import_todays_positions": True,
        }
        self.client.post("/api/pnl/import/zerodha", json=base)
        closed1 = self.client.get("/api/pnl/closed").json()
        n1 = len((closed1.get("profit") or []) + (closed1.get("loss") or []))
        self.client.post("/api/pnl/import/zerodha", json=base)
        closed2 = self.client.get("/api/pnl/closed").json()
        n2 = len((closed2.get("profit") or []) + (closed2.get("loss") or []))
        self.assertEqual(n1, n2)


if __name__ == "__main__":
    unittest.main()
