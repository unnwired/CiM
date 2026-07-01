"""Tests for Zerodha holdings CSV parse and reconcile."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.pnl_ledger import compute_symbol_avg_entry, symbol_open_qty  # noqa: E402
from server.zerodha_holdings import (  # noqa: E402
    compare_ledger_to_holdings,
    parse_zerodha_holdings_csv,
    reconcile_open_to_holdings,
)
from server.zerodha_import import merge_zerodha_tradebook  # noqa: E402

FIXTURES = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"


def _empty_ledger():
    return {
        "positions": [],
        "closed_trades": [{"symbol": "OLD", "import_source": "manual", "qty_sold": 5}],
        "cycle_seq": {},
        "active_cycle": {},
        "import_meta": {"zerodha_trade_ids": []},
    }


class TestZerodhaHoldings(unittest.TestCase):
    def test_parse_kite_holdings_avg_cost_column(self):
        text = (FIXTURES / "holdings_kite_format.csv").read_text(encoding="utf-8")
        rows, errors = parse_zerodha_holdings_csv(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "TRENT")
        self.assertAlmostEqual(rows[0]["average_price"], 2894.11, places=2)

    def test_parse_holdings_trent(self):
        text = (FIXTURES / "holdings_trent.csv").read_text(encoding="utf-8")
        rows, errors = parse_zerodha_holdings_csv(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "TRENT")
        self.assertEqual(rows[0]["quantity"], 25)
        self.assertAlmostEqual(rows[0]["average_price"], 2894.11, places=2)

    def test_tradebook_only_mismatch(self):
        ledger = _empty_ledger()
        items: list = []
        tb = (FIXTURES / "tradebook_trent_partial.csv").read_text(encoding="utf-8")
        merge_zerodha_tradebook(ledger, items, tb, quote_map={})
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), 17)
        holdings = parse_zerodha_holdings_csv(
            (FIXTURES / "holdings_trent.csv").read_text(encoding="utf-8"),
        )[0]
        mismatches = compare_ledger_to_holdings(ledger, holdings)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["ledger_qty"], 17)
        self.assertEqual(mismatches[0]["holdings_qty"], 25)

    def test_reconcile_to_holdings_qty_25(self):
        ledger = _empty_ledger()
        items: list = []
        tb = (FIXTURES / "tradebook_trent_partial.csv").read_text(encoding="utf-8")
        merge_zerodha_tradebook(ledger, items, tb, quote_map={})
        holdings = parse_zerodha_holdings_csv(
            (FIXTURES / "holdings_trent.csv").read_text(encoding="utf-8"),
        )[0]
        rec = reconcile_open_to_holdings(ledger, holdings, dry_run=False)
        self.assertEqual(len(rec["reconciled"]), 1)
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), 25)
        self.assertAlmostEqual(compute_symbol_avg_entry(ledger, "TRENT"), 2894.11, places=2)
        self.assertEqual(len(ledger["closed_trades"]), 1)

    def test_reconcile_preserves_closed(self):
        ledger = _empty_ledger()
        closed_before = len(ledger["closed_trades"])
        holdings = parse_zerodha_holdings_csv(
            (FIXTURES / "holdings_trent.csv").read_text(encoding="utf-8"),
        )[0]
        reconcile_open_to_holdings(ledger, holdings, dry_run=False)
        self.assertEqual(len(ledger["closed_trades"]), closed_before)


if __name__ == "__main__":
    unittest.main()
