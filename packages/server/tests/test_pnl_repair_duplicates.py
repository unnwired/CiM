"""Tests for closed-trade duplicate repair (Trent-style double books)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from server.pnl_repair_duplicates import repair_duplicate_closed_trades  # noqa: E402


class TestRepairDuplicateCloses(unittest.TestCase):
    def test_trent_keeps_post_bonus_profit(self):
        ledger = {
            "closed_trades": [
                {
                    "id": "a",
                    "symbol": "TRENT",
                    "qty_sold": 3,
                    "entry_price": 2700.13,
                    "exit_price": 3272.6,
                    "realized_pl": 1717.41,
                    "sale_date": "2026-06-30",
                    "broker": "manual",
                },
                {
                    "id": "b",
                    "symbol": "TRENT",
                    "qty_sold": 3,
                    "entry_price": 4316.4,
                    "exit_price": 3272.6,
                    "realized_pl": -3131.4,
                    "sale_date": "2026-06-30",
                    "import_source": "zerodha",
                    "broker": "zerodha",
                },
                {
                    "id": "c",
                    "symbol": "TRENT",
                    "qty_sold": 8,
                    "entry_price": 2700.13,
                    "exit_price": 3333.0,
                    "realized_pl": 5062.96,
                    "sale_date": "2026-07-03",
                    "import_source": "zerodha_positions_today",
                    "broker": "manual",
                },
                {
                    "id": "d",
                    "symbol": "TRENT",
                    "qty_sold": 8,
                    "entry_price": 4316.0,
                    "exit_price": 3333.0,
                    "realized_pl": -7800.0,
                    "sale_date": "2026-07-03",
                    "import_source": "zerodha",
                    "broker": "zerodha",
                },
                {
                    "id": "e",
                    "symbol": "TRENT",
                    "qty_sold": 6,
                    "entry_price": 4103.0,
                    "exit_price": 3005.8,
                    "realized_pl": -6583.0,
                    "sale_date": "2026-07-07",
                    "import_source": "zerodha",
                    "broker": "zerodha",
                },
            ],
        }
        summary = repair_duplicate_closed_trades(ledger)
        self.assertEqual(len(ledger["closed_trades"]), 2)
        pl = sum(float(t["realized_pl"]) for t in ledger["closed_trades"])
        self.assertAlmostEqual(pl, 1717.41 + 5062.96, places=2)
        self.assertGreater(summary["removed_count"], 0)

    def test_exact_duplicate_pair(self):
        ledger = {
            "closed_trades": [
                {
                    "symbol": "PARAS",
                    "qty_sold": 5,
                    "entry_price": 100,
                    "exit_price": 200,
                    "realized_pl": 500,
                    "sale_date": "2026-06-29",
                    "broker": "manual",
                },
                {
                    "symbol": "PARAS",
                    "qty_sold": 5,
                    "entry_price": 100,
                    "exit_price": 200,
                    "realized_pl": 500,
                    "sale_date": "2026-06-29",
                    "import_source": "zerodha",
                    "broker": "zerodha",
                },
            ],
        }
        repair_duplicate_closed_trades(ledger)
        self.assertEqual(len(ledger["closed_trades"]), 1)
        self.assertEqual(ledger["closed_trades"][0].get("broker"), "manual")


if __name__ == "__main__":
    unittest.main()
