#!/usr/bin/env python3
"""Unit tests for index ∪ industry multi-tag Market Sectors."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "packages" / "server"
for p in (str(ROOT / "packages"), str(SERVER), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import index_industry_sectors as iis  # noqa: E402
import market_sectors as ms  # noqa: E402


class TestIndexIndustrySectors(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        cores = {label: set() for label in iis.SECTOR_TAG_ORDER}
        cores["Auto"] = {"MARUTI", "M&M", "BAJAJ-AUTO", "TMPV"}
        cores["Bank"] = {"HDFCBANK", "ICICIBANK", "SBIN"}
        cores["PSU Bank"] = {"SBIN", "BANKBARODA"}
        cores["Financial Services"] = {"HDFCBANK", "SBIN", "BAJFINANCE"}
        cores["Defence"] = {"BEL", "HAL"}
        cores["Energy"] = {"NTPC", "SCHNEIDER", "SUZLON"}
        cores["Consumption"] = {"TRENT", "PAGEIND"}
        cores["Chemicals"] = {"PIDILITIND", "SRF"}
        iis.save_index_cores(self.data_dir, cores)
        self.mapping = ms.load_mapping(self.data_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_canonical_includes_consumption_chemicals_telecom(self) -> None:
        canon = ms.canonical_sectors_for_ui()
        self.assertIn("Consumption", canon)
        self.assertIn("Chemicals", canon)
        self.assertIn("Telecom", canon)
        self.assertIn("Auto", canon)
        self.assertNotIn(ms.AUTOMOBILES, canon)

    def test_auto_industry_and_index(self) -> None:
        self.assertIn(
            "Auto",
            ms.resolve_market_sectors(
                "BOSCHLTD", "Automobile and Auto Components",
                "Automobile and Auto Components", self.mapping, data_dir=self.data_dir,
            ),
        )
        self.assertIn(
            "Auto",
            ms.resolve_market_sectors("TMPV", None, None, self.mapping, data_dir=self.data_dir),
        )
        self.assertIn(
            "Auto",
            ms.resolve_market_sectors(
                "ATULAUTO", None, "Industrials > Commercial Vehicles",
                self.mapping, data_dir=self.data_dir,
            ),
        )
        # Capital Goods exact label lands in Infra (not Unclassified).
        self.assertIn(
            "Infra",
            ms.resolve_market_sectors(
                "ACE", "Capital Goods", "Capital Goods",
                self.mapping, data_dir=self.data_dir,
            ),
        )

    def test_chemicals_fact(self) -> None:
        tags = ms.resolve_market_sectors(
            "FACT", None, "Chemicals", self.mapping, data_dir=self.data_dir,
        )
        self.assertIn("Chemicals", tags)

    def test_gujgas_slash_industry(self) -> None:
        tags = ms.resolve_market_sectors(
            "GUJGASLTD",
            None,
            "Energy > LPG/CNG/PNG/LNG Supplier",
            self.mapping,
            data_dir=self.data_dir,
        )
        self.assertIn("Energy", tags)
        self.assertIn("Oil & Gas", tags)

    def test_schneider_energy_core(self) -> None:
        tags = ms.resolve_market_sectors(
            "SCHNEIDER", "Capital Goods", "Capital Goods",
            self.mapping, data_dir=self.data_dir,
        )
        self.assertIn("Energy", tags)

    def test_waaree_renewable_keyword(self) -> None:
        # Capital Goods alone → Infra; solar/renewable text → Energy.
        tags = ms.resolve_market_sectors(
            "WAAREEENER", None, "Capital Goods - Solar", self.mapping, data_dir=self.data_dir,
        )
        self.assertTrue("Energy" in tags or "Infra" in tags)

    def test_consumption_textiles_retail(self) -> None:
        tags = ms.resolve_market_sectors(
            "PAGEIND", None, "Textiles", self.mapping, data_dir=self.data_dir,
        )
        self.assertIn("Consumption", tags)
        tags2 = ms.resolve_market_sectors(
            "SHOPERSTOP",
            None,
            "Consumer Discretionary > Diversified Retail",
            self.mapping,
            data_dir=self.data_dir,
        )
        self.assertIn("Consumption", tags2)

    def test_telecom(self) -> None:
        tags = ms.resolve_market_sectors(
            "IDEA", None, "Telecommunication", self.mapping, data_dir=self.data_dir,
        )
        self.assertIn("Telecom", tags)

    def test_construction_infra(self) -> None:
        tags = ms.resolve_market_sectors(
            "HCC", None, "Construction", self.mapping, data_dir=self.data_dir,
        )
        self.assertIn("Infra", tags)

    def test_bank_overlap(self) -> None:
        tags = ms.resolve_market_sectors(
            "SBIN", "Financial Services", "Financial Services",
            self.mapping, data_dir=self.data_dir,
        )
        self.assertIn("Bank", tags)
        self.assertIn("PSU Bank", tags)
        self.assertIn("Financial Services", tags)

    def test_symbol_set_filter_or(self) -> None:
        db = self.data_dir / "t.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE screener (symbol TEXT, nse_sector TEXT, nse_industry TEXT)"
        )
        conn.executemany(
            "INSERT INTO screener VALUES (?,?,?)",
            [
                ("BOSCHLTD", "Automobile and Auto Components", "Automobile and Auto Components"),
                ("FACT", None, "Chemicals"),
                ("TRENT", "Consumer Discretionary", "Retail Trade"),
            ],
        )
        conn.commit()
        conn.close()
        chem = ms.symbol_set_for_market_sectors(self.data_dir, db, ["Chemicals"])
        self.assertIn("FACT", chem)
        self.assertIn("PIDILITIND", chem)  # index core


if __name__ == "__main__":
    unittest.main()
