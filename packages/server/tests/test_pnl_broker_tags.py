"""Broker tags: migrate, strip/rebuild preserve Paytm, holdings Zerodha-scoped."""
from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from server.pnl_ledger import (  # noqa: E402
    BROKER_MANUAL,
    BROKER_PAYTM,
    BROKER_ZERODHA,
    book_fifo,
    ensure_broker_tags,
    infer_broker,
    set_symbol_broker,
    set_symbol_open_snapshot,
    symbol_open_qty,
)
from server.zerodha_holdings import (  # noqa: E402
    compare_ledger_to_holdings,
    reconcile_open_to_holdings,
)
from server.zerodha_import import (  # noqa: E402
    _strip_symbol_ledger_state,
    merge_zerodha_tradebook,
)


SAMPLE_CSV = """symbol\tisin\ttrade_date\texchange\tsegment\tseries\ttrade_type\tauction\tquantity\tprice\ttrade_id\torder_id\torder_execution_time
MAZDOCK\tINE249Z01020\t13-03-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t16\t2434\t400113437\t1.2E+15\t2026-03-13T09:15:33
"""


class TestBrokerTags(unittest.TestCase):
    def test_infer_zerodha_from_import_source(self):
        self.assertEqual(infer_broker({"import_source": "zerodha"}), BROKER_ZERODHA)
        self.assertEqual(infer_broker({"zerodha_trade_id": "x"}), BROKER_ZERODHA)
        self.assertEqual(infer_broker({"broker": "paytm"}), BROKER_PAYTM)
        self.assertEqual(infer_broker({}), BROKER_MANUAL)

    def test_ensure_broker_tags_backfills(self):
        ledger = {
            "positions": [
                {"id": "1", "symbol": "A", "qty": 1, "entry_price": 10, "import_source": "zerodha"},
                {"id": "2", "symbol": "B", "qty": 1, "entry_price": 10},
            ],
            "closed_trades": [
                {"id": "c1", "symbol": "A", "import_source": "zerodha"},
            ],
        }
        n = ensure_broker_tags(ledger)
        self.assertGreaterEqual(n, 2)
        self.assertEqual(ledger["positions"][0]["broker"], BROKER_ZERODHA)
        self.assertEqual(ledger["positions"][1]["broker"], BROKER_MANUAL)
        self.assertEqual(ledger["closed_trades"][0]["broker"], BROKER_ZERODHA)

    def test_strip_preserves_paytm_lots(self):
        ledger = {
            "positions": [
                {
                    "id": "z1",
                    "symbol": "ZENSARTECH",
                    "qty": 10,
                    "entry_price": 100,
                    "broker": BROKER_ZERODHA,
                    "import_source": "zerodha",
                },
                {
                    "id": "p1",
                    "symbol": "ZENSARTECH",
                    "qty": 50,
                    "entry_price": 90,
                    "broker": BROKER_PAYTM,
                },
            ],
            "closed_trades": [
                {
                    "id": "cz",
                    "symbol": "ZENSARTECH",
                    "broker": BROKER_ZERODHA,
                    "import_source": "zerodha",
                },
                {
                    "id": "cp",
                    "symbol": "ZENSARTECH",
                    "broker": BROKER_PAYTM,
                },
            ],
            "active_cycle": {"ZENSARTECH": 1},
            "cycle_seq": {"ZENSARTECH": 1},
        }
        counts = _strip_symbol_ledger_state(ledger, {"ZENSARTECH"})
        self.assertEqual(counts["positions_removed"], 1)
        self.assertEqual(counts["positions_kept_other_broker"], 1)
        self.assertEqual(counts["closed_removed"], 1)
        self.assertEqual(len(ledger["positions"]), 1)
        self.assertEqual(ledger["positions"][0]["broker"], BROKER_PAYTM)
        self.assertEqual(len(ledger["closed_trades"]), 1)
        self.assertEqual(ledger["closed_trades"][0]["broker"], BROKER_PAYTM)
        self.assertEqual(symbol_open_qty(ledger, "ZENSARTECH"), 50)
        self.assertIn("ZENSARTECH", ledger["active_cycle"])

    def test_holdings_reconcile_only_replaces_zerodha(self):
        ledger = {
            "positions": [
                {
                    "id": "z1",
                    "symbol": "TRENT",
                    "qty": 10,
                    "entry_price": 1000,
                    "broker": BROKER_ZERODHA,
                    "import_source": "zerodha",
                },
                {
                    "id": "p1",
                    "symbol": "TRENT",
                    "qty": 5,
                    "entry_price": 900,
                    "broker": BROKER_PAYTM,
                },
            ],
            "closed_trades": [],
        }
        holdings = [{"symbol": "TRENT", "quantity": 25, "average_price": 1100.0}]
        mm = compare_ledger_to_holdings(ledger, holdings)
        self.assertEqual(len(mm), 1)
        self.assertEqual(mm[0]["ledger_qty"], 10)
        self.assertEqual(mm[0]["holdings_qty"], 25)

        reconcile_open_to_holdings(ledger, holdings, dry_run=False)
        self.assertEqual(symbol_open_qty(ledger, "TRENT", brokers=(BROKER_ZERODHA,)), 25)
        self.assertEqual(symbol_open_qty(ledger, "TRENT", brokers=(BROKER_PAYTM,)), 5)
        self.assertEqual(symbol_open_qty(ledger, "TRENT"), 30)

    def test_zerodha_sell_skips_paytm_lots(self):
        ledger = {
            "positions": [
                {
                    "id": "p1",
                    "symbol": "PARAS",
                    "qty": 20,
                    "entry_price": 100,
                    "entry_date": "2026-01-01",
                    "broker": BROKER_PAYTM,
                },
                {
                    "id": "z1",
                    "symbol": "PARAS",
                    "qty": 5,
                    "entry_price": 110,
                    "entry_date": "2026-02-01",
                    "broker": BROKER_ZERODHA,
                    "import_source": "zerodha",
                },
            ],
            "closed_trades": [],
            "active_cycle": {"PARAS": 1},
            "cycle_seq": {"PARAS": 1},
        }
        items = [{"symbol": "PARAS", "type": "stock"}]
        trades = book_fifo(
            ledger,
            symbol="PARAS",
            exit_price=120,
            qty_sold=5,
            sale_date="2026-03-01",
            quote_snapshot={},
            portfolio_items=items,
            brokers=(BROKER_ZERODHA,),
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["broker"], BROKER_ZERODHA)
        self.assertEqual(symbol_open_qty(ledger, "PARAS", brokers=(BROKER_PAYTM,)), 20)
        self.assertEqual(symbol_open_qty(ledger, "PARAS", brokers=(BROKER_ZERODHA,)), 0)

        with self.assertRaises(ValueError):
            book_fifo(
                ledger,
                symbol="PARAS",
                exit_price=120,
                qty_sold=1,
                sale_date="2026-03-02",
                quote_snapshot={},
                portfolio_items=items,
                brokers=(BROKER_ZERODHA,),
            )

    def test_sell_promotes_manual_then_books(self):
        ledger = {
            "positions": [
                {
                    "id": "m1",
                    "symbol": "PARAS",
                    "qty": 44,
                    "entry_price": 100,
                    "entry_date": "2026-01-01",
                    "broker": BROKER_MANUAL,
                },
            ],
            "closed_trades": [],
            "active_cycle": {"PARAS": 1},
            "cycle_seq": {"PARAS": 1},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items = [{"symbol": "PARAS", "type": "stock"}]
        csv = (
            "symbol\tisin\ttrade_date\texchange\tsegment\tseries\ttrade_type\tauction\tquantity\tprice\ttrade_id\torder_id\torder_execution_time\n"
            "PARAS\tINE\t10-07-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t10\t120\tzsell1\to1\t2026-07-10T10:00:00\n"
        )
        summary = merge_zerodha_tradebook(ledger, items, csv, quote_map={})
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["sells_applied"], 1)
        self.assertEqual(summary["manual_promoted_qty"], 10)
        # Only the sold slice was promoted; remainder stays Manual.
        self.assertEqual(symbol_open_qty(ledger, "PARAS"), 34)
        self.assertEqual(symbol_open_qty(ledger, "PARAS", brokers=(BROKER_ZERODHA,)), 0)
        self.assertEqual(symbol_open_qty(ledger, "PARAS", brokers=(BROKER_MANUAL,)), 34)

    def test_sell_gap_seeds_when_no_open_zerodha(self):
        ledger = {
            "positions": [
                {
                    "id": "p1",
                    "symbol": "ZENSARTECH",
                    "qty": 50,
                    "entry_price": 90,
                    "entry_date": "2026-01-01",
                    "broker": BROKER_PAYTM,
                },
            ],
            "closed_trades": [],
            "active_cycle": {"ZENSARTECH": 1},
            "cycle_seq": {"ZENSARTECH": 1},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items = [{"symbol": "ZENSARTECH", "type": "stock"}]
        csv = (
            "symbol\tisin\ttrade_date\texchange\tsegment\tseries\ttrade_type\tauction\tquantity\tprice\ttrade_id\torder_id\torder_execution_time\n"
            "ZENSARTECH\tINE\t10-07-2026\tNSE\tEQ\tEQ\tsell\tFALSE\t5\t100\tzs1\to1\t2026-07-10T10:00:00\n"
        )
        summary = merge_zerodha_tradebook(ledger, items, csv, quote_map={})
        self.assertTrue(summary["ok"], summary.get("errors"))
        self.assertEqual(summary["gap_seed_qty"], 5)
        self.assertEqual(symbol_open_qty(ledger, "ZENSARTECH", brokers=(BROKER_PAYTM,)), 50)
        self.assertEqual(symbol_open_qty(ledger, "ZENSARTECH", brokers=(BROKER_ZERODHA,)), 0)
        self.assertEqual(len(ledger["closed_trades"]), 1)
        self.assertEqual(ledger["closed_trades"][0]["broker"], BROKER_ZERODHA)

    def test_append_does_not_wipe_manual_lots(self):
        ledger = {
            "positions": [
                {
                    "id": "m1",
                    "symbol": "MARUTI",
                    "qty": 3,
                    "entry_price": 10000,
                    "broker": BROKER_MANUAL,
                },
            ],
            "closed_trades": [],
            "import_meta": {"zerodha_trade_ids": []},
            "active_cycle": {},
            "cycle_seq": {},
        }
        items: list = []
        csv = (
            "symbol\tisin\ttrade_date\texchange\tsegment\tseries\ttrade_type\tauction\tquantity\tprice\ttrade_id\torder_id\torder_execution_time\n"
            "MARUTI\tINE\t10-07-2026\tNSE\tEQ\tEQ\tbuy\tFALSE\t1\t12000\tzb1\to1\t2026-07-10T10:00:00\n"
        )
        summary = merge_zerodha_tradebook(ledger, items, csv, quote_map={})
        self.assertTrue(summary["ok"])
        self.assertEqual(summary.get("manual_lots_removed", 0), 0)
        self.assertEqual(symbol_open_qty(ledger, "MARUTI", brokers=(BROKER_MANUAL,)), 3)
        self.assertEqual(symbol_open_qty(ledger, "MARUTI", brokers=(BROKER_ZERODHA,)), 1)

    def test_rebuild_does_not_wipe_paytm(self):
        ledger = {
            "positions": [
                {
                    "id": str(uuid.uuid4()),
                    "symbol": "MAZDOCK",
                    "qty": 40,
                    "entry_price": 1800,
                    "broker": BROKER_PAYTM,
                },
            ],
            "closed_trades": [],
            "cycle_seq": {},
            "active_cycle": {},
            "import_meta": {"zerodha_trade_ids": []},
        }
        items: list = []
        summary = merge_zerodha_tradebook(
            ledger, items, SAMPLE_CSV, quote_map={}, rebuild=True,
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK", brokers=(BROKER_PAYTM,)), 40)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK", brokers=(BROKER_ZERODHA,)), 16)
        self.assertEqual(symbol_open_qty(ledger, "MAZDOCK"), 56)


if __name__ == "__main__":
    unittest.main()
