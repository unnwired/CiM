"""Tests for Zerodha positions CSV (today's session)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.pnl_ledger import symbol_open_qty, today_sale_date_ist  # noqa: E402
from server.zerodha_import import merge_zerodha_tradebook  # noqa: E402
from server.zerodha_positions import (  # noqa: E402
    apply_todays_positions,
    parse_zerodha_positions_csv,
    preview_todays_positions,
)

FIXTURES = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"


def _ledger_with_paras():
    ledger = {
        "positions": [],
        "closed_trades": [],
        "cycle_seq": {},
        "active_cycle": {},
        "import_meta": {"zerodha_trade_ids": []},
    }
    items = [{"symbol": "PARAS", "type": "stock", "pnl_tracked": True}]
    tb = (FIXTURES / "tradebook_paras_open.csv").read_text(encoding="utf-8")
    merge_zerodha_tradebook(ledger, items, tb, quote_map={})
    return ledger, items


class TestZerodhaPositions(unittest.TestCase):
    def test_parse_positions_screenshot_columns(self):
        text = (FIXTURES / "positions_today_sells.csv").read_text(encoding="utf-8")
        rows, errors = parse_zerodha_positions_csv(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 3)
        paras = next(r for r in rows if r["symbol"] == "PARAS")
        self.assertEqual(paras["side"], "sell")
        self.assertEqual(paras["qty"], 18)
        self.assertAlmostEqual(paras["avg"], 1176.05, places=2)
        self.assertEqual(paras["trade_date"], today_sale_date_ist())

    def test_negative_qty_is_sell(self):
        text = "Product,Instrument,Qty.,Avg.,LTP,P&L,Chg.\nCNC,PARAS,-18,1176.05,1182.9,-123.3,0.58\n"
        rows, _ = parse_zerodha_positions_csv(text)
        self.assertEqual(rows[0]["side"], "sell")

    @patch("server.zerodha_positions.today_sale_date_ist", return_value="2026-06-27")
    def test_apply_today_sell_paras(self, _mock_today):
        ledger, items = _ledger_with_paras()
        self.assertEqual(symbol_open_qty(ledger, "PARAS"), 30)
        pos_text = (FIXTURES / "positions_today_sells.csv").read_text(encoding="utf-8")
        rows, _ = parse_zerodha_positions_csv(pos_text)
        paras_rows = [r for r in rows if r["symbol"] == "PARAS"]
        result = apply_todays_positions(ledger, items, paras_rows, quote_map={})
        self.assertEqual(result["sells_applied"], 1)
        self.assertEqual(symbol_open_qty(ledger, "PARAS"), 12)
        closed = [t for t in ledger["closed_trades"] if t["symbol"] == "PARAS"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["qty_sold"], 18)
        self.assertEqual(closed[0]["sale_date"], "2026-06-27")

    @patch("server.zerodha_positions.today_sale_date_ist", return_value="2026-06-27")
    def test_dedupe_when_manual_fifo_already_booked_same_day(self, _mock_today):
        ledger, items = _ledger_with_paras()
        from server.pnl_ledger import book_fifo

        book_fifo(
            ledger,
            symbol="PARAS",
            exit_price=1176.05,
            qty_sold=13,
            sale_date="2026-06-27",
            quote_snapshot={},
            portfolio_items=items,
        )
        book_fifo(
            ledger,
            symbol="PARAS",
            exit_price=1176.05,
            qty_sold=5,
            sale_date="2026-06-27",
            quote_snapshot={},
            portfolio_items=items,
        )
        pos_text = (FIXTURES / "positions_today_sells.csv").read_text(encoding="utf-8")
        rows, _ = parse_zerodha_positions_csv(pos_text)
        paras_rows = [r for r in rows if r["symbol"] == "PARAS"]
        preview = preview_todays_positions(ledger, paras_rows)
        self.assertEqual(len(preview["positions_to_apply"]), 0)
        closed_count = len(ledger["closed_trades"])
        apply_todays_positions(ledger, items, paras_rows, quote_map={})
        self.assertEqual(len(ledger["closed_trades"]), closed_count)

    @patch("server.zerodha_positions.today_sale_date_ist", return_value="2026-06-27")
    def test_dedupe_second_import(self, _mock_today):
        ledger, items = _ledger_with_paras()
        pos_text = (FIXTURES / "positions_today_sells.csv").read_text(encoding="utf-8")
        rows, _ = parse_zerodha_positions_csv(pos_text)
        paras_rows = [r for r in rows if r["symbol"] == "PARAS"]
        apply_todays_positions(ledger, items, paras_rows, quote_map={})
        closed_count = len(ledger["closed_trades"])
        preview = preview_todays_positions(ledger, paras_rows)
        self.assertEqual(len(preview["positions_to_apply"]), 0)
        apply_todays_positions(ledger, items, paras_rows, quote_map={})
        self.assertEqual(len(ledger["closed_trades"]), closed_count)

    def test_preview_pnl_check(self):
        ledger, _ = _ledger_with_paras()
        pos_text = (FIXTURES / "positions_today_sells.csv").read_text(encoding="utf-8")
        rows, _ = parse_zerodha_positions_csv(pos_text)
        preview = preview_todays_positions(ledger, rows)
        paras = next(p for p in preview["positions_today"] if p["symbol"] == "PARAS")
        self.assertAlmostEqual(paras["broker_pnl"], -123.3, places=1)


if __name__ == "__main__":
    unittest.main()
