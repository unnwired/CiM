"""Tests for avg_volume_filter."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

SERVER_PKG = ROOT / "packages" / "server"
if str(SERVER_PKG) not in sys.path:
    sys.path.insert(0, str(SERVER_PKG))

from avg_volume_filter import normalize_avg_volume_params, query_avg_volume_symbols  # noqa: E402


class AvgVolumeFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Volume REAL)"
        )
        rows = []
        for day in range(1, 11):
            rows.append(("THIN", f"2026-06-{day:02d}", 50_000.0))
        for day in range(1, 11):
            rows.append(("LIQUID", f"2026-06-{day:02d}", 2_000_000.0))
        conn.executemany(
            "INSERT INTO historical_data (Symbol, Date, Volume) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_above_min_volume(self):
        conn = sqlite3.connect(str(self.db_path))
        filt = {"period": 10, "condition": "above", "min_volume": 500_000}
        syms = query_avg_volume_symbols(conn, filt)
        conn.close()
        self.assertEqual(syms, ["LIQUID"])

    def test_normalize_defaults(self):
        p = normalize_avg_volume_params({"period": 10, "min_volume": 1e6})
        self.assertEqual(p["period"], 10)
        self.assertEqual(p["condition"], "above")


if __name__ == "__main__":
    unittest.main()
