"""API e2e: broker tag endpoints (POST-only paths used by the PnL UI)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))


class PnlBrokerApiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server.server as srv

        cls._srv = srv
        cls._orig_base = srv.BASE_DIR
        cls._orig_data = srv.DATA_DIR
        cls._orig_db = srv.DB_PATH

        cls._tmpdir = tempfile.mkdtemp(prefix="cim-pnl-broker-e2e-")
        cls._base = Path(cls._tmpdir)
        cls._data = cls._base / "data"
        cls._data.mkdir(parents=True)

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

    def _write_state(self, positions, items=None):
        ledger = {
            "positions": positions,
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        portfolio = {"items": items or []}
        (self._data / "pnl_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (self._data / "portfolio.json").write_text(json.dumps(portfolio), encoding="utf-8")

    def test_post_positions_id_is_405_but_broker_position_works(self):
        pid = str(uuid.uuid4())
        self._write_state(
            [{
                "id": pid,
                "symbol": "PARAS",
                "qty": 10,
                "entry_price": 100,
                "entry_date": "2026-01-01",
                "broker": "manual",
            }],
            items=[{"symbol": "PARAS", "type": "stock", "pnl_tracked": True}],
        )

        bad = self.client.post(f"/api/pnl/positions/{pid}", json={"broker": "zerodha"})
        self.assertEqual(bad.status_code, 405, bad.text)
        self.assertEqual(bad.json().get("detail"), "Method Not Allowed")

        ok = self.client.post("/api/pnl/broker/position", json={
            "position_id": pid,
            "broker": "zerodha",
        })
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["position"]["broker"], "zerodha")

        ledger = json.loads((self._data / "pnl_ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["positions"][0]["broker"], "zerodha")

    def test_post_broker_symbol_tags_all_lots(self):
        p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
        self._write_state(
            [
                {"id": p1, "symbol": "TRENT", "qty": 1, "entry_price": 1, "broker": "manual"},
                {"id": p2, "symbol": "TRENT", "qty": 2, "entry_price": 2, "broker": "manual"},
                {"id": str(uuid.uuid4()), "symbol": "OTHER", "qty": 1, "entry_price": 1, "broker": "manual"},
            ],
            items=[
                {"symbol": "TRENT", "type": "stock"},
                {"symbol": "OTHER", "type": "stock"},
            ],
        )
        r = self.client.post("/api/pnl/broker/symbol", json={
            "symbol": "TRENT",
            "broker": "paytm",
            "scope": "open",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["open_updated"], 2)

        ledger = json.loads((self._data / "pnl_ledger.json").read_text(encoding="utf-8"))
        by_id = {p["id"]: p for p in ledger["positions"]}
        self.assertEqual(by_id[p1]["broker"], "paytm")
        self.assertEqual(by_id[p2]["broker"], "paytm")

    def test_patch_position_broker_still_works(self):
        pid = str(uuid.uuid4())
        self._write_state(
            [{
                "id": pid,
                "symbol": "LUPIN",
                "qty": 3,
                "entry_price": 50,
                "broker": "manual",
            }],
            items=[{"symbol": "LUPIN", "type": "stock"}],
        )
        r = self.client.patch(f"/api/pnl/positions/{pid}", json={"broker": "zerodha"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["position"]["broker"], "zerodha")


if __name__ == "__main__":
    unittest.main()
