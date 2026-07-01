"""Tests for showcase host gating and market-data contracts."""
from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as _ROOT
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server import market_data_version as mdv
from server.product_config import is_showcase_host, showcase_host_allowed_for_request
from server.showcase_host_gate import path_requires_showcase_host

from starlette.requests import Request


def _request(*, client_host: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [],
        "scheme": "http",
        "path": "/",
        "server": (client_host, 8001),
        "client": (client_host, 0),
    }
    return Request(scope)


class ShowcaseHostMarkerTests(unittest.TestCase):
    def test_is_showcase_host_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertFalse(is_showcase_host(base))
            (base / "config").mkdir()
            (base / "config" / ".cim-showcase-host").write_text("", encoding="utf-8")
            self.assertTrue(is_showcase_host(base))

    def test_loopback_allowed_without_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req = _request(client_host="127.0.0.1")
            self.assertTrue(showcase_host_allowed_for_request(req, base))

    def test_remote_not_allowed_without_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req = _request(client_host="203.0.113.10")
            self.assertFalse(showcase_host_allowed_for_request(req, base))

    def test_remote_not_allowed_with_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            (base / "config" / ".cim-showcase-host").write_text("", encoding="utf-8")
            (base / "config" / ".cim-web-host").write_text("", encoding="utf-8")
            req = _request(client_host="203.0.113.10")
            self.assertFalse(showcase_host_allowed_for_request(req, base))


class ShowcaseHostGatePathTests(unittest.TestCase):
    def test_admin_requires_host(self):
        self.assertTrue(path_requires_showcase_host("/api/admin/fetch-ohlcv", "POST"))

    def test_stocks_read_ok(self):
        self.assertFalse(path_requires_showcase_host("/api/stocks", "GET"))

    def test_screener_lazy_fetch_allowed_for_clients(self):
        self.assertFalse(
            path_requires_showcase_host(
                "/api/screener-quarters/RELIANCE",
                "GET",
                "fetch_if_missing=true",
            )
        )

    def test_screener_cache_read_allowed_for_remote(self):
        self.assertFalse(
            path_requires_showcase_host("/api/screener-quarters/RELIANCE", "GET")
        )
        self.assertFalse(
            path_requires_showcase_host(
                "/api/screener-quarters/RELIANCE",
                "GET",
                "basis=consolidated",
            )
        )

    def test_screener_refresh_requires_host(self):
        self.assertTrue(
            path_requires_showcase_host(
                "/api/screener-quarters/RELIANCE/refresh",
                "POST",
            )
        )

    def test_intraday_patch_allowed(self):
        self.assertFalse(path_requires_showcase_host("/api/intraday-patch", "GET"))


class MarketDataVersionTests(unittest.TestCase):
    def test_record_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nse_data.db"
            conn = sqlite3.connect(str(db))
            mdv.ensure_table(conn)
            conn.commit()
            conn.close()
            mdv.record_eod_publish(db, bars=123, trade_date="2026-06-05")
            ver = mdv.get_version(db)
            self.assertEqual(ver["eod_trade_date"], "2026-06-05")
            self.assertEqual(ver["bars_reconciled"], 123)
            self.assertEqual(ver["status"], "complete")


if __name__ == "__main__":
    unittest.main()
