"""Tests for corp actions on P&L ledger during import."""
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

from server.corp_actions import (  # noqa: E402
    apply_corp_action_to_ledger,
    apply_pending_corp_actions,
    load_corp_actions,
    pending_corp_actions,
)
from server.pnl_ledger import apply_bonus, symbol_open_qty  # noqa: E402
from server.zerodha_import import merge_zerodha_tradebook, run_zerodha_import_pipeline  # noqa: E402

FIXTURES = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"


def _empty_ledger():
    return {
        "positions": [],
        "closed_trades": [],
        "cycle_seq": {},
        "active_cycle": {},
        "import_meta": {"zerodha_trade_ids": []},
    }


class TestCorpActionsImport(unittest.TestCase):
    def test_trent_bonus_without_holdings(self):
        ledger = _empty_ledger()
        items: list = []
        tb = (FIXTURES / "tradebook_trent_partial.csv").read_text(encoding="utf-8")
        merge_zerodha_tradebook(ledger, items, tb, quote_map={})
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), 17)
        actions = load_corp_actions()
        trent_actions = [a for a in actions if a.get("symbol") == "TRENT"]
        self.assertTrue(trent_actions)
        applied = apply_pending_corp_actions(ledger, {"TRENT"}, actions, as_of="2026-06-10")
        self.assertEqual(len(applied), 1)
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), 25)

    def test_no_double_apply(self):
        ledger = _empty_ledger()
        items: list = []
        tb = (FIXTURES / "tradebook_trent_partial.csv").read_text(encoding="utf-8")
        merge_zerodha_tradebook(ledger, items, tb, quote_map={})
        actions = load_corp_actions()
        apply_pending_corp_actions(ledger, {"TRENT"}, actions, as_of="2026-06-10")
        qty_after_first = symbol_open_qty(ledger, "TRENT")
        apply_pending_corp_actions(ledger, {"TRENT"}, actions, as_of="2026-06-10")
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), qty_after_first)

    def test_split_1_5(self):
        ledger = {
            "positions": [{
                "id": "1", "symbol": "TEST", "entry_price": 1000, "qty": 10,
                "entry_date": "2026-01-01",
            }],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
        }
        from server.pnl_ledger import apply_split_to_open_lots
        result = apply_split_to_open_lots(ledger, "TEST", ratio=5.0, ex_date="2026-03-01")
        self.assertEqual(result["open_qty"], 50)
        self.assertAlmostEqual(ledger["positions"][0]["entry_price"], 200.0, places=2)

    def test_pipeline_corp_then_holdings(self):
        ledger = _empty_ledger()
        items: list = []
        tb = (FIXTURES / "tradebook_trent_partial.csv").read_text(encoding="utf-8")
        holdings = (FIXTURES / "holdings_trent.csv").read_text(encoding="utf-8")
        summary = run_zerodha_import_pipeline(
            ledger,
            items,
            csv_text=tb,
            holdings_csv=holdings,
            reconcile_holdings=True,
            apply_corp_actions=True,
            data_dir=ROOT / "data",
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), 25)


if __name__ == "__main__":
    unittest.main()
