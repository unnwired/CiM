"""Tests for market_data_version publish / refresh bumps."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from server import market_data_version as mdv


class MarketDataVersionTests(unittest.TestCase):
    def test_record_data_refresh_bumps_published_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(str(db))
            try:
                mdv.ensure_table(conn)
                conn.commit()
            finally:
                conn.close()

            first = mdv.record_data_refresh(db, bars=100)
            second = mdv.record_data_refresh(db, bars=50)

            self.assertIsNotNone(first.get("published_at"))
            self.assertIsNotNone(second.get("published_at"))
            self.assertNotEqual(first["published_at"], second["published_at"])
            self.assertGreaterEqual(int(second.get("bars_reconciled") or 0), 100)


if __name__ == "__main__":
    unittest.main()
