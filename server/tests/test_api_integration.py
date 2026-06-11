"""API integration tests using FastAPI TestClient."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = ROOT / "data" / "nse_data.db"
        if not cls.db_path.exists():
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "dev_setup",
                ROOT / "scripts" / "dev_setup.py",
            )
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            mod.run_setup(force=False)

        import server.server as srv

        cls._orig_db = srv.DB_PATH
        srv.DB_PATH = cls.db_path
        cls.app = srv.app

        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        import server.server as srv

        srv.DB_PATH = cls._orig_db

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("status"), "ok")
        self.assertTrue(body.get("db_exists"))

    def test_stocks_list(self):
        r = self.client.get("/api/stocks?pageSize=10")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(data.get("total", 0), 1)
        self.assertTrue(data.get("data"))

    def test_chart_data_reliance(self):
        r = self.client.get("/api/chart-data/RELIANCE?timeframe=1D&bars_limit=100")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("bars", body)
        self.assertGreater(len(body["bars"]), 0)

    def test_chart_unknown_symbol(self):
        r = self.client.get("/api/chart-data/FAKESYM999?timeframe=1D&bars_limit=100")
        self.assertIn(r.status_code, (404, 400))

    def test_indices(self):
        r = self.client.get("/api/indices")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data", r.json())


if __name__ == "__main__":
    unittest.main()
