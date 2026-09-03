"""Tests for chartable index catalog."""

from __future__ import annotations

import unittest

from server.cim_index_catalog import (
    CHARTABLE_INDICES,
    archive_csv_map,
    is_cim_index_symbol,
    nse_name_map,
    scrape_indices_tuples,
    upstox_name_map,
)


class CimIndexCatalogTests(unittest.TestCase):
    def test_catalog_sizes(self):
        self.assertGreaterEqual(len(CHARTABLE_INDICES), 60)
        self.assertEqual(len(upstox_name_map()), len(CHARTABLE_INDICES))
        self.assertEqual(len(nse_name_map()), len(CHARTABLE_INDICES))
        self.assertGreaterEqual(len(archive_csv_map()), 40)

    def test_required_high_value_present(self):
        syms = {r.symbol for r in CHARTABLE_INDICES}
        for need in (
            "NIFTY_MIDCAP_150",
            "NIFTY_FIN_SERVICE",
            "NIFTY_PVT_BANK",
            "NIFTY_OIL_GAS",
            "INDIA_VIX",
            "^NSEI",
        ):
            self.assertIn(need, syms)

    def test_scrape_tuples_include_commodities(self):
        rows = scrape_indices_tuples()
        cats = {c for _, _, c in rows}
        self.assertIn("equity", cats)
        self.assertIn("commodity", cats)

    def test_is_cim_index_symbol(self):
        self.assertTrue(is_cim_index_symbol("^NSEI"))
        self.assertTrue(is_cim_index_symbol("NIFTY_MIDCAP_150"))
        self.assertTrue(is_cim_index_symbol("INDIA_VIX"))
        self.assertFalse(is_cim_index_symbol("RELIANCE"))


if __name__ == "__main__":
    unittest.main()
