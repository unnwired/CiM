#!/usr/bin/env python3
"""Unit tests for screener universe expand from market sets."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "packages" / "server"
for p in (str(ROOT / "packages"), str(SERVER), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import screener_universe_expand as sue  # noqa: E402


class TestScreenerUniverseExpand(unittest.TestCase):
    def test_inserts_nse_listed_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db_path = data_dir / "nse_data.db"
            (data_dir / "screener_market_sets.json").write_text(
                json.dumps({
                    "sets": {
                        sue.AUTO_AND_AUTO_COMPONENTS: ["GOODYEAR", "NOTNSE"],
                        sue.AUTOMOBILES: ["MERCURYEV"],
                    },
                }),
                encoding="utf-8",
            )
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE screener (symbol TEXT PRIMARY KEY, nse_sector TEXT, nse_industry TEXT)"
            )
            conn.execute("INSERT INTO screener (symbol) VALUES ('MARUTI')")
            conn.commit()
            conn.close()

            fake_nse = {"GOODYEAR": "EQ", "MERCURYEV": "BE", "MARUTI": "EQ"}
            with patch.object(sue, "fetch_nse_equity_symbols", return_value=fake_nse):
                result = sue.expand_screener_from_market_sets(data_dir, db_path)

            self.assertEqual(result["inserted"], 2)
            self.assertIn("NOTNSE", result["skipped_not_nse"])

            conn = sqlite3.connect(db_path)
            rows = {
                r[0]: (r[1], r[2])
                for r in conn.execute(
                    "SELECT symbol, nse_industry, nse_sector FROM screener ORDER BY symbol"
                )
            }
            conn.close()
            self.assertEqual(rows["GOODYEAR"][0], "Auto Components")
            self.assertEqual(rows["MERCURYEV"][0], "Automobiles")


if __name__ == "__main__":
    unittest.main()
