"""Tests for portfolio entry price and P/L % helpers."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.portfolio_entry import compute_pl_pct, parse_entry_price  # noqa: E402


class TestPortfolioEntryHelpers(unittest.TestCase):
    def test_parse_entry_price(self):
        self.assertEqual(parse_entry_price(100.5), 100.5)
        self.assertIsNone(parse_entry_price(0))
        self.assertIsNone(parse_entry_price(-1))
        self.assertIsNone(parse_entry_price("bad"))

    def test_compute_pl_pct(self):
        self.assertEqual(compute_pl_pct(110, 100), 10.0)
        self.assertEqual(compute_pl_pct(88, 100), -12.0)
        self.assertIsNone(compute_pl_pct(None, 100))
        self.assertIsNone(compute_pl_pct(100, None))
        self.assertIsNone(compute_pl_pct(100, 0))


class TestPortfolioLoadSaveEntry(unittest.TestCase):
    def test_load_preserves_entry_price(self):
        import server.server as srv

        with tempfile.TemporaryDirectory() as tmp:
            prefs = Path(tmp)
            pf = prefs / "portfolio.json"
            pf.write_text(
                json.dumps(
                    {
                        "items": [
                            {"symbol": "RELIANCE", "type": "stock", "entry_price": 2450.5},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(srv, "_portfolio_path", return_value=pf):
                data = srv._load_portfolio()
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(data["items"][0]["entry_price"], 2450.5)


if __name__ == "__main__":
    unittest.main()
