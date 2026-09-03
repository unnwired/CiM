"""Tests for Zerodha tradebook CSV import."""
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

from server.pnl_ledger import (  # noqa: E402
    add_position,
    consolidate_open_lots,
    symbol_open_qty,
)
from server.zerodha_import import (  # noqa: E402
    aggregate_zerodha_fills,
    known_zerodha_trade_ids,
    merge_zerodha_tradebook,
    parse_zerodha_tradebook_csv,
    preview_zerodha_merge,
)

SAMPLE_CSV = """symbol\tisin\ttrade_date\texchange\tsegment\tseries\ttrade_type\tauction\tquantity\tprice\ttrade_id\torder_id\torder_execution_time
MAZDOCK\tINE249Z01020\t13-03-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t16\t2434\t400113437\t1.2E+15\t2026-03-13T09:15:33
LUPIN\tINE326A01037\t08-04-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t2\t2295\t409365265\t1.2E+15\t2026-04-08T15:20:01
LUPIN\tINE326A01037\t08-04-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t2\t2295\t409367744\t1.2E+15\t2026-04-08T15:20:01
LUPIN\tINE326A01037\t08-04-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t8\t2295\t409361467\t1.2E+15\t2026-04-08T15:20:01
LUPIN\tINE326A01037\t10-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t1\t2326.800049\t405588225\t1.2E+15\t2026-04-10T13:26:55
LUPIN\tINE326A01037\t10-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t1\t2326.800049\t405588553\t1.2E+15\t2026-04-10T13:26:55
LUPIN\tINE326A01037\t10-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t1\t2326.800049\t405588986\t1.2E+15\t2026-04-10T13:26:55
LUPIN\tINE326A01037\t10-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t1\t2326.800049\t405589500\t1.2E+15\t2026-04-10T13:26:55
LUPIN\tINE326A01037\t10-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t2\t2326.800049\t405589483\t1.2E+15\t2026-04-10T13:26:55
LUPIN\tINE326A01037\t10-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t6\t2326.800049\t405588441\t1.2E+15\t2026-04-10T13:26:55
M&MFIN\tINE774D01024\t27-04-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t200\t321.950012\t403402875\t1.2E+15\t2026-04-27T11:21:12
M&MFIN\tINE774D01024\t27-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t136\t322.200012\t405021938\t1.2E+15\t2026-04-27T13:15:29
M&MFIN\tINE774D01024\t27-04-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t2\t322.200012\t405021121\t1.2E+15\t2026-04-27T13:15:29
"""


class TestZerodhaImport(unittest.TestCase):
    def test_parse_sample_rows(self):
        rows, errors = parse_zerodha_tradebook_csv(SAMPLE_CSV)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[0]["symbol"], "MAZDOCK")
        self.assertEqual(rows[0]["trade_date"], "2026-03-13")

    def test_merge_into_empty_ledger(self):
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items: list = []
        summary = merge_zerodha_tradebook(ledger, items, SAMPLE_CSV, quote_map={})
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["buys_applied"], 3)
        self.assertEqual(summary["sells_applied"], 2)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK"), 16)
        self.assertEqual(symbol_open_qty(ledger, "LUPIN"), 0)
        self.assertEqual(symbol_open_qty(ledger, "M&MFIN"), 62)
        self.assertEqual(len(known_zerodha_trade_ids(ledger)), 13)
        self.assertEqual(len(ledger["positions"]), 2)

    def test_aggregate_partial_fills(self):
        rows, _ = parse_zerodha_tradebook_csv(SAMPLE_CSV)
        agg = aggregate_zerodha_fills(rows)
        self.assertEqual(len(agg), 5)
        lupin_buy = next(r for r in agg if r["symbol"] == "LUPIN" and r["trade_type"] == "buy")
        self.assertEqual(lupin_buy["quantity"], 12)
        self.assertEqual(len(lupin_buy["trade_ids"]), 3)

    def test_merge_skips_duplicate_trade_id(self):
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": ["400113437"]},
        }
        items: list = []
        summary = merge_zerodha_tradebook(ledger, items, SAMPLE_CSV, quote_map={})
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["skipped_duplicate"], 1)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK"), 0)

    def test_merge_with_existing_manual_lot(self):
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items = [{"symbol": "MAZDOCK", "type": "stock", "pnl_tracked": True}]
        add_position(
            ledger,
            symbol="MAZDOCK",
            entry_price=2400,
            qty=4,
            portfolio_items=items,
            entry_date="2026-01-01",
        )
        summary = merge_zerodha_tradebook(ledger, items, SAMPLE_CSV, quote_map={})
        self.assertTrue(summary["ok"])
        self.assertEqual(summary.get("manual_lots_removed", 0), 0)
        # Manual lot kept; Zerodha buy adds alongside it.
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK"), 20)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK", brokers=("manual",)), 4)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK", brokers=("zerodha",)), 16)

    def test_consolidate_open_lots(self):
        ledger = {
            "positions": [
                {"id": "a", "symbol": "PARAS", "entry_price": 100, "qty": 5, "entry_date": "2026-01-01"},
                {"id": "b", "symbol": "PARAS", "entry_price": 100, "qty": 7, "entry_date": "2026-01-01"},
            ],
            "closed_trades": [],
        }
        removed = consolidate_open_lots(ledger)
        self.assertEqual(removed, 1)
        self.assertEqual(len(ledger["positions"]), 1)
        self.assertEqual(ledger["positions"][0]["qty"], 12)

    def test_rebuild_fixes_double_counted_import(self):
        import uuid

        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items: list = []
        merge_zerodha_tradebook(ledger, items, SAMPLE_CSV, quote_map={})
        for p in list(ledger.get("positions", [])):
            if p.get("symbol") == "MAZDOCK":
                dup = dict(p)
                dup["id"] = str(uuid.uuid4())
                ledger["positions"].append(dup)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK"), 32)

        summary = merge_zerodha_tradebook(
            ledger, items, SAMPLE_CSV, quote_map={}, rebuild=True,
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK"), 16)
        self.assertEqual(symbol_open_qty(ledger, "LUPIN"), 0)
        self.assertEqual(symbol_open_qty(ledger, "M&MFIN"), 62)

    def test_preview_does_not_mutate(self):
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items: list = []
        preview = preview_zerodha_merge(ledger, items, SAMPLE_CSV)
        self.assertTrue(preview["ok"])
        self.assertEqual(len(ledger["positions"]), 0)

    def test_combined_preview_payload(self):
        from server.zerodha_import import preview_zerodha_import

        fixtures = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items: list = []
        tb = (fixtures / "tradebook_trent_partial.csv").read_text(encoding="utf-8")
        holdings = (fixtures / "holdings_trent.csv").read_text(encoding="utf-8")
        preview = preview_zerodha_import(
            ledger,
            items,
            csv_text=tb,
            holdings_csv=holdings,
            reconcile_holdings=True,
            apply_corp_actions=True,
            data_dir=ROOT / "data",
        )
        self.assertTrue(preview["ok"])
        self.assertEqual(preview.get("open_qty_after", {}).get("TRENT"), 25)
        self.assertTrue(preview.get("holdings_mismatches") is not None)

    def test_validate_requires_actionable_input(self):
        from server.zerodha_import import validate_zerodha_import_inputs

        self.assertIsNotNone(validate_zerodha_import_inputs("", None, None))
        self.assertIsNotNone(
            validate_zerodha_import_inputs("", "sym,qty\n", None, reconcile_holdings=False)
        )
        self.assertIsNotNone(
            validate_zerodha_import_inputs("", None, "sym,qty\n", import_todays_positions=False)
        )
        self.assertIsNone(
            validate_zerodha_import_inputs("", "holdings", None, reconcile_holdings=True)
        )
        self.assertIsNone(
            validate_zerodha_import_inputs("", None, "positions", import_todays_positions=True)
        )

    def test_holdings_only_preview(self):
        from server.zerodha_import import preview_zerodha_import

        fixtures = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"
        ledger = {
            "positions": [],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        holdings = (fixtures / "holdings_trent.csv").read_text(encoding="utf-8")
        preview = preview_zerodha_import(
            ledger,
            [],
            csv_text="",
            holdings_csv=holdings,
            reconcile_holdings=True,
            apply_corp_actions=False,
        )
        self.assertTrue(preview["ok"])
        self.assertTrue(preview.get("tradebook_skipped"))
        self.assertEqual(preview.get("open_qty_after", {}).get("TRENT"), 25)


if __name__ == "__main__":
    unittest.main()
