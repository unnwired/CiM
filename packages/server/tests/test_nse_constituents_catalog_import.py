"""Regression: bare nse_constituents import must still resolve full catalog (e.g. FMCG)."""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


class NseConstituentsCatalogImportTests(unittest.TestCase):
    def test_bare_module_includes_fmcg(self):
        server_dir = Path(__file__).resolve().parents[1]
        # Simulate showcase flat path: server/ on sys.path, import as bare module.
        sys.path.insert(0, str(server_dir))
        try:
            # Force a fresh load under the bare name.
            for name in list(sys.modules):
                if name == "nse_constituents" or name.startswith("nse_constituents."):
                    del sys.modules[name]
            nc = importlib.import_module("nse_constituents")
            self.assertIn("^CNXFMCG", nc.NSE_INDEX_MAP)
            self.assertEqual(nc.NSE_INDEX_MAP["^CNXFMCG"], "NIFTY FMCG")
            self.assertIn("^CNXFMCG", nc.INDEX_ARCHIVE_CSV)
            self.assertGreaterEqual(len(nc.NSE_INDEX_MAP), 40)
        finally:
            if sys.path and sys.path[0] == str(server_dir):
                sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
