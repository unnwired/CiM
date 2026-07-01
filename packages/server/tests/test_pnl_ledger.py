"""Tests for P&L ledger helpers."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.pnl_ledger import (  # noqa: E402
    add_position,
    add_stock,
    book_fifo,
    book_position,
    build_closed_rows,
    build_open_rows,
    compute_symbol_avg_entry,
    ensure_position_from_placeholder,
    finalize_symbol_after_book,
    load_ledger,
    parse_sale_date,
    patch_placeholder_or_position,
    purge_dead_positions,
    reconcile_pnl_portfolio_sync,
    remove_symbol_from_portfolio_items,
    save_ledger,
    sync_portfolio_entry_from_pnl,
    symbol_open_qty,
)


PORTFOLIO = {
    "items": [
        {"symbol": "LICI", "type": "stock", "entry_price": 900},
        {"symbol": "RELIANCE", "type": "stock"},
    ]
}


class TestPnlLedger(unittest.TestCase):
    def test_placeholder_prefills_portfolio_entry(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        rows = build_open_rows(PORTFOLIO["items"], ledger, {"LICI": {"price": 950, "change_1d": 1.0}})
        lic = [r for r in rows if r["symbol"] == "LICI"][0]
        self.assertTrue(lic["is_placeholder"])
        self.assertEqual(lic["entry_price"], 900.0)
        self.assertIsNone(lic["qty"])
        self.assertNotIn("lifetime_qty_sold", lic)

    def test_add_and_book_partial_profit(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        trade = book_position(
            ledger,
            position_id=pos_id,
            exit_price=920,
            qty_sold=5,
            sale_date="2026-01-10",
            entry_price_override=None,
            quote_snapshot={"market_cap": 1e12, "as_of_date": "2026-06-21"},
            portfolio_items=items,
        )
        self.assertEqual(trade["realized_pl"], 100.0)
        self.assertEqual(trade["sale_date"], "2026-01-10")
        self.assertEqual(trade["cycle_id"], 1)
        self.assertEqual(ledger["positions"][0]["qty"], 5)
        split = build_closed_rows(ledger["closed_trades"])
        self.assertEqual(len(split["profit"]), 1)
        self.assertEqual(len(split["loss"]), 0)

    def test_two_partial_books_same_cycle(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=62, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=915,
            qty_sold=32,
            sale_date="2026-01-10",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=925,
            qty_sold=30,
            sale_date="2026-01-12",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        self.assertEqual(len(ledger["closed_trades"]), 2)
        self.assertEqual(ledger["closed_trades"][0]["cycle_id"], 1)
        self.assertEqual(ledger["closed_trades"][1]["cycle_id"], 1)
        self.assertEqual(symbol_open_qty(ledger, "LICI"), 0)
        self.assertNotIn("LICI", ledger.get("active_cycle", {}))

    def test_full_close_clears_active_cycle(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=920,
            qty_sold=10,
            sale_date="2026-01-10",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        self.assertEqual(symbol_open_qty(ledger, "LICI"), 0)
        self.assertNotIn("LICI", ledger["active_cycle"])

    def test_rebuy_gets_new_cycle_id(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=920,
            qty_sold=10,
            sale_date="2026-01-10",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        add_position(ledger, symbol="LICI", entry_price=880, qty=20, portfolio_items=items)
        pos_id2 = ledger["positions"][0]["id"]
        trade2 = book_position(
            ledger,
            position_id=pos_id2,
            exit_price=900,
            qty_sold=20,
            sale_date="2026-03-05",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        self.assertEqual(trade2["cycle_id"], 2)

    def test_book_loss(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="RELIANCE", entry_price=2500, qty=4, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=2400,
            qty_sold=4,
            sale_date="2026-02-01",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        split = build_closed_rows(ledger["closed_trades"])
        self.assertEqual(len(split["profit"]), 0)
        self.assertEqual(len(split["loss"]), 1)
        self.assertEqual(split["loss"][0]["realized_pl"], -400.0)
        self.assertEqual(split["loss"][0]["sale_date"], "2026-02-01")

    def test_multi_lot_same_symbol(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=5, portfolio_items=items)
        add_position(ledger, symbol="LICI", entry_price=950, qty=30, portfolio_items=items)
        rows = build_open_rows(items, ledger, {})
        lic_rows = [r for r in rows if r["symbol"] == "LICI" and not r["is_placeholder"]]
        self.assertEqual(len(lic_rows), 2)

    def test_multi_lot_partial_book_keeps_symbol_open(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=5, portfolio_items=items)
        add_position(ledger, symbol="LICI", entry_price=950, qty=30, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=920,
            qty_sold=5,
            sale_date="2026-01-10",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        self.assertEqual(symbol_open_qty(ledger, "LICI"), 30)

    def test_placeholder_partial_entry_then_qty(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "RELIANCE", "type": "stock"}]
        pos = patch_placeholder_or_position(
            ledger,
            "placeholder-RELIANCE",
            entry_price=2450,
            qty=None,
            portfolio_items=items,
        )
        self.assertTrue(pos["is_placeholder"])
        self.assertEqual(pos["entry_price"], 2450.0)
        self.assertIsNone(pos["qty"])
        self.assertEqual(len(ledger["positions"]), 0)
        pos = patch_placeholder_or_position(
            ledger,
            "placeholder-RELIANCE",
            entry_price=None,
            qty=10,
            portfolio_items=items,
        )
        self.assertFalse(pos.get("is_placeholder", False))
        self.assertEqual(pos["qty"], 10)
        self.assertEqual(len(ledger["positions"]), 1)

    def test_placeholder_to_position(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        pos = ensure_position_from_placeholder(
            ledger, symbol="RELIANCE", entry_price=2450, qty=10, portfolio_items=items
        )
        self.assertEqual(pos["qty"], 10)
        self.assertEqual(len(ledger["positions"]), 1)
        self.assertEqual(ledger["active_cycle"]["RELIANCE"], 1)

    def test_add_stock_adds_portfolio_and_position(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = []
        pos = add_stock(
            ledger,
            symbol="LICI",
            entry_price=900,
            qty=15,
            portfolio_items=items,
        )
        self.assertEqual(pos["symbol"], "LICI")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "LICI")

    def test_remove_symbol_from_portfolio(self):
        items = [dict(x) for x in PORTFOLIO["items"]]
        removed = remove_symbol_from_portfolio_items(items, "LICI")
        self.assertTrue(removed)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "RELIANCE")

    def test_parse_sale_date(self):
        self.assertEqual(parse_sale_date("2026-06-27"), "2026-06-27")
        self.assertIsNone(parse_sale_date("2026-02-30"))
        self.assertIsNone(parse_sale_date("bad"))

    def test_load_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pnl_ledger.json"
            data = {
                "positions": [{"id": "a", "symbol": "X", "entry_price": 1, "qty": 2}],
                "closed_trades": [],
                "cycle_seq": {"X": 1},
                "active_cycle": {"X": 1},
            }
            save_ledger(path, data)
            loaded = load_ledger(path)
            self.assertEqual(loaded["positions"][0]["symbol"], "X")
            self.assertEqual(loaded["cycle_seq"]["X"], 1)

    def test_entry_date_on_add_position(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        pos = add_position(
            ledger,
            symbol="LICI",
            entry_price=900,
            qty=30,
            portfolio_items=items,
            entry_date="2026-06-20",
        )
        self.assertEqual(pos["entry_date"], "2026-06-20")
        rows = build_open_rows(items, ledger, {})
        lic = [r for r in rows if r["symbol"] == "LICI"][0]
        self.assertEqual(lic["entry_date"], "2026-06-20")

    def test_fifo_sell_spans_two_lots(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(
            ledger, symbol="LICI", entry_price=900, qty=30,
            portfolio_items=items, entry_date="2026-06-10",
        )
        add_position(
            ledger, symbol="LICI", entry_price=950, qty=30,
            portfolio_items=items, entry_date="2026-06-27",
        )
        trades = book_fifo(
            ledger,
            symbol="LICI",
            exit_price=980,
            qty_sold=40,
            sale_date="2026-06-27",
            quote_snapshot={},
            portfolio_items=items,
        )
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["qty_sold"], 30)
        self.assertEqual(trades[0]["entry_price"], 900.0)
        self.assertEqual(trades[0]["entry_date"], "2026-06-10")
        self.assertEqual(trades[1]["qty_sold"], 10)
        self.assertEqual(trades[1]["entry_price"], 950.0)
        self.assertEqual(trades[1]["entry_date"], "2026-06-27")
        self.assertEqual(symbol_open_qty(ledger, "LICI"), 20)
        self.assertEqual(ledger["positions"][0]["qty"], 20)

    def test_fifo_rejects_over_sell(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        with self.assertRaises(ValueError):
            book_fifo(
                ledger,
                symbol="LICI",
                exit_price=920,
                qty_sold=11,
                sale_date="2026-06-27",
                quote_snapshot={},
                portfolio_items=items,
            )

    def test_open_rows_sorted_by_entry_date(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [dict(x) for x in PORTFOLIO["items"]]
        add_position(
            ledger, symbol="LICI", entry_price=950, qty=10,
            portfolio_items=items, entry_date="2026-06-27",
        )
        add_position(
            ledger, symbol="LICI", entry_price=900, qty=10,
            portfolio_items=items, entry_date="2026-06-10",
        )
        rows = build_open_rows(items, ledger, {})
        lic_rows = [r for r in rows if r["symbol"] == "LICI"]
        self.assertEqual(lic_rows[0]["entry_date"], "2026-06-10")
        self.assertEqual(lic_rows[1]["entry_date"], "2026-06-27")

    def test_reconcile_removes_fully_closed_legacy_symbol(self):
        ledger = {
            "positions": [],
            "closed_trades": [{
                "id": "t1",
                "symbol": "SUPREMEIND",
                "entry_price": 4000,
                "exit_price": 3800,
                "qty_sold": 10,
                "realized_pl": -2000,
                "sale_date": "2026-06-20",
                "cycle_id": 1,
            }],
            "cycle_seq": {"SUPREMEIND": 1},
            "active_cycle": {},
        }
        items = [{"symbol": "SUPREMEIND", "type": "stock"}]
        sync = reconcile_pnl_portfolio_sync(items, ledger)
        self.assertTrue(sync["portfolio_changed"])
        self.assertIn("SUPREMEIND", sync["removed_symbols"])
        self.assertEqual(items, [])
        rows = build_open_rows(items, ledger, {})
        self.assertEqual(rows, [])

    def test_reconcile_keeps_portfolio_only_without_closed_trades(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "RELIANCE", "type": "stock"}]
        sync = reconcile_pnl_portfolio_sync(items, ledger)
        self.assertFalse(sync["portfolio_changed"])
        rows = build_open_rows(items, ledger, {})
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_placeholder"])

    def test_finalize_after_full_book_removes_pnl_tracked(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "LICI", "type": "stock", "pnl_tracked": True}]
        add_position(ledger, symbol="LICI", entry_price=900, qty=5, portfolio_items=items)
        pos_id = ledger["positions"][0]["id"]
        book_position(
            ledger,
            position_id=pos_id,
            exit_price=920,
            qty_sold=5,
            sale_date="2026-06-27",
            entry_price_override=None,
            quote_snapshot={},
            portfolio_items=items,
        )
        removed = finalize_symbol_after_book(ledger, items, "LICI")
        self.assertTrue(removed)
        self.assertEqual(items, [])

    def test_purge_dead_positions(self):
        ledger = {
            "positions": [
                {"id": "a", "symbol": "X", "entry_price": 1, "qty": 0},
                {"id": "b", "symbol": "Y", "entry_price": 2, "qty": 3},
            ],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
        }
        self.assertTrue(purge_dead_positions(ledger))
        self.assertEqual(len(ledger["positions"]), 1)
        self.assertEqual(ledger["positions"][0]["symbol"], "Y")

    def test_add_position_overwrites_portfolio_entry(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "LICI", "type": "stock", "entry_price": 800}]
        add_position(ledger, symbol="LICI", entry_price=920, qty=10, portfolio_items=items)
        self.assertEqual(items[0]["entry_price"], 920.0)

    def test_multi_lot_weighted_avg_syncs_portfolio(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "LICI", "type": "stock", "entry_price": 800}]
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        add_position(ledger, symbol="LICI", entry_price=950, qty=30, portfolio_items=items)
        self.assertEqual(compute_symbol_avg_entry(ledger, "LICI"), 937.5)
        self.assertEqual(items[0]["entry_price"], 937.5)

    def test_reconcile_syncs_stale_portfolio_entry(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "LICI", "type": "stock", "entry_price": 800}]
        add_position(ledger, symbol="LICI", entry_price=910, qty=5, portfolio_items=items)
        items[0]["entry_price"] = 800
        sync = reconcile_pnl_portfolio_sync(items, ledger)
        self.assertTrue(sync["entries_synced"])
        self.assertEqual(items[0]["entry_price"], 910.0)

    def test_reconcile_adds_portfolio_for_ledger_open_without_row(self):
        from server.pnl_ledger import set_symbol_open_snapshot

        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items: list[dict] = []
        set_symbol_open_snapshot(
            ledger,
            "TRENT",
            qty=25,
            entry_price=2894.11,
            import_source="holdings_reconcile",
        )
        sync = reconcile_pnl_portfolio_sync(items, ledger)
        self.assertTrue(sync["portfolio_changed"])
        self.assertIn("TRENT", sync["added_symbols"])
        rows = build_open_rows(items, ledger, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "TRENT")
        self.assertEqual(rows[0]["qty"], 25)

    def test_partial_book_updates_weighted_avg_on_portfolio(self):
        ledger = {"positions": [], "closed_trades": [], "cycle_seq": {}, "active_cycle": {}}
        items = [{"symbol": "LICI", "type": "stock"}]
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        add_position(ledger, symbol="LICI", entry_price=950, qty=30, portfolio_items=items)
        self.assertEqual(items[0]["entry_price"], 937.5)
        book_fifo(
            ledger,
            symbol="LICI",
            exit_price=960,
            qty_sold=10,
            sale_date="2026-06-27",
            quote_snapshot={},
            portfolio_items=items,
        )
        self.assertEqual(items[0]["entry_price"], 950.0)


if __name__ == "__main__":
    unittest.main()
