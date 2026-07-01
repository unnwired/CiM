"""Tests for P&L available-cash ledger."""
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

from server.pnl_cash import (  # noqa: E402
    get_available_cash,
    record_bank_deposit,
    record_bank_withdrawal,
    record_buy_cost,
    record_sell_proceeds,
    set_available_cash_balance,
)
from server.pnl_ledger import (  # noqa: E402
    _default_ledger,
    add_position,
    book_position,
    load_ledger,
    save_ledger,
)


PORTFOLIO = {
    "items": [
        {"symbol": "LICI", "type": "stock", "entry_price": 900},
    ]
}


def _empty_ledger() -> dict:
    return _default_ledger()


class TestPnlCash(unittest.TestCase):
    def test_buy_debits_and_sell_credits(self):
        ledger = _empty_ledger()
        items = [dict(x) for x in PORTFOLIO["items"]]
        record_bank_deposit(ledger, 100_000, note="seed")
        add_position(ledger, symbol="LICI", entry_price=900, qty=10, portfolio_items=items)
        self.assertEqual(get_available_cash(ledger), 91_000.0)
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
        self.assertEqual(get_available_cash(ledger), 95_600.0)

    def test_sell_dedupes_by_trade_id(self):
        ledger = _empty_ledger()
        record_sell_proceeds(
            ledger, qty_sold=10, exit_price=100, trade_id="t1", symbol="LICI"
        )
        record_sell_proceeds(
            ledger, qty_sold=10, exit_price=100, trade_id="t1", symbol="LICI"
        )
        self.assertEqual(get_available_cash(ledger), 1000.0)

    def test_buy_dedupes_by_ref(self):
        ledger = _empty_ledger()
        record_buy_cost(
            ledger,
            qty=5,
            entry_price=200,
            position_id="p1",
            symbol="LICI",
            ref_key="buy:test:1",
        )
        record_buy_cost(
            ledger,
            qty=5,
            entry_price=200,
            position_id="p1",
            symbol="LICI",
            ref_key="buy:test:1",
        )
        self.assertEqual(get_available_cash(ledger), -1000.0)

    def test_bank_deposit_and_withdraw(self):
        ledger = _empty_ledger()
        record_bank_deposit(ledger, 50_000)
        record_bank_withdrawal(ledger, 12_500)
        self.assertEqual(get_available_cash(ledger), 37_500.0)

    def test_manual_balance_set(self):
        ledger = _empty_ledger()
        record_bank_deposit(ledger, 10_000)
        set_available_cash_balance(ledger, 12_345.67)
        self.assertEqual(get_available_cash(ledger), 12_345.67)

    def test_load_ledger_preserves_cash(self):
        import tempfile

        ledger = _empty_ledger()
        record_bank_deposit(ledger, 1_234.56)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            save_ledger(path, ledger)
            loaded = load_ledger(path)
            self.assertEqual(loaded.get("available_cash"), 1_234.56)
            self.assertTrue(loaded.get("cash_log"))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
