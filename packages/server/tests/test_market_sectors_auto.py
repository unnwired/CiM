#!/usr/bin/env python3
"""Unit tests for auto sector split under Consumer Discretionary."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "packages" / "server"
for p in (str(ROOT / "packages"), str(SERVER), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import market_sectors as ms  # noqa: E402


class TestAutoSectorSplit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        sets = {
            "version": 1,
            "sets": {
                ms.AUTO_AND_AUTO_COMPONENTS: ["BOSCHLTD", "UNOMINDA", "MARUTI"],
                ms.AUTOMOBILES: ["MARUTI", "M&M", "BAJAJ-AUTO"],
            },
        }
        p = self.data_dir / "screener_market_sets.json"
        p.write_text(json.dumps(sets), encoding="utf-8")
        self.mapping = ms.load_mapping(self.data_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_automobiles_subset_priority(self) -> None:
        sector = ms.resolve_market_sector(
            "MARUTI", "Consumer Discretionary", "Automobiles", self.mapping, data_dir=self.data_dir,
        )
        self.assertEqual(sector, ms.AUTOMOBILES)

    def test_auto_components_parent_only(self) -> None:
        sector = ms.resolve_market_sector(
            "BOSCHLTD", "Consumer Discretionary", "Auto Components", self.mapping, data_dir=self.data_dir,
        )
        self.assertEqual(sector, ms.AUTO_AND_AUTO_COMPONENTS)

    def test_keyword_fallback_automobiles(self) -> None:
        sector = ms.resolve_market_sector(
            "HEROMOTOCO", None, "Passenger Cars & Utility Vehicles", self.mapping, data_dir=self.data_dir,
        )
        self.assertEqual(sector, ms.AUTOMOBILES)

    def test_keyword_fallback_auto_components(self) -> None:
        sector = ms.resolve_market_sector(
            "MOTHERSON", None, "Auto Components", self.mapping, data_dir=self.data_dir,
        )
        self.assertEqual(sector, ms.AUTO_AND_AUTO_COMPONENTS)

    def test_consumer_discretionary_non_auto(self) -> None:
        sector = ms.resolve_market_sector(
            "TRENT", None, "Retail Trade", self.mapping, data_dir=self.data_dir,
        )
        self.assertEqual(sector, ms.CONSUMER_DISCRETIONARY)

    def test_canonical_sectors_include_auto_buckets(self) -> None:
        canon = ms.canonical_sectors_for_ui()
        self.assertIn(ms.AUTO_AND_AUTO_COMPONENTS, canon)
        self.assertIn(ms.AUTOMOBILES, canon)
        self.assertIn(ms.CONSUMER_DISCRETIONARY, canon)

    def test_sector_groups(self) -> None:
        groups = ms.sector_dropdown_groups_for_ui()
        self.assertTrue(groups)
        sectors = groups[0]["sectors"]
        self.assertIn(ms.AUTOMOBILES, sectors)
        self.assertIn(ms.AUTO_AND_AUTO_COMPONENTS, sectors)


if __name__ == "__main__":
    unittest.main()
