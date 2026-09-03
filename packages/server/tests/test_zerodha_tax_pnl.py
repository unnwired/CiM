"""Tests for Zerodha Tax P&L / Console P&L import as realized truth."""
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

from server.pnl_ledger import BROKER_PAYTM, BROKER_ZERODHA, infer_broker  # noqa: E402
from server.zerodha_tax_pnl import (  # noqa: E402
    parse_zerodha_tax_pnl_csv,
    preview_zerodha_tax_pnl,
    run_zerodha_tax_pnl_import,
)

FIXTURES = ROOT / "packages" / "server" / "tests" / "fixtures" / "zerodha"


def _ledger_with_junk():
    return {
        "positions": [
            {
                "id": "z1",
                "symbol": "TRENT",
                "qty": 10,
                "entry_price": 2700,
                "broker": BROKER_ZERODHA,
                "import_source": "zerodha",
            },
        ],
        "closed_trades": [
            {
                "id": "bad-trent",
                "symbol": "TRENT",
                "qty_sold": 2,
                "realized_pl": -3400,
                "broker": BROKER_ZERODHA,
                "import_source": "zerodha",
            },
            {
                "id": "paytm-keep",
                "symbol": "TRENT",
                "qty_sold": 1,
                "realized_pl": 100,
                "broker": BROKER_PAYTM,
                "import_source": "manual",
            },
            {
                "id": "other-sym",
                "symbol": "INFY",
                "qty_sold": 5,
                "realized_pl": 500,
                "broker": BROKER_ZERODHA,
                "import_source": "zerodha",
            },
        ],
        "cycle_seq": {},
        "active_cycle": {},
        "import_meta": {},
    }


class TestZerodhaTaxPnl(unittest.TestCase):
    def test_parse_capital_gains_csv(self):
        text = (FIXTURES / "tax_pnl_capital_gains.csv").read_text(encoding="utf-8")
        closed, open_rows, errors = parse_zerodha_tax_pnl_csv(text)
        self.assertEqual(errors, [])
        self.assertEqual(open_rows, [])
        self.assertEqual(len(closed), 3)
        trent = next(r for r in closed if r["symbol"] == "TRENT")
        self.assertEqual(trent["quantity"], 2)
        self.assertAlmostEqual(trent["realized_pl"], 6780.0)
        self.assertAlmostEqual(trent["entry_price"], 4300.0)  # 8600/2
        self.assertAlmostEqual(trent["exit_price"], 7690.0)  # 15380/2
        self.assertEqual(trent["sale_date"], "2025-01-15")

    def test_parse_console_combined(self):
        text = (FIXTURES / "console_pnl_combined.csv").read_text(encoding="utf-8")
        closed, open_rows, errors = parse_zerodha_tax_pnl_csv(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(closed), 2)
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0]["symbol"], "TRENT")
        self.assertEqual(open_rows[0]["quantity"], 10)
        # Unrealized column must not be mistaken for realized
        trent = next(r for r in closed if r["symbol"] == "TRENT")
        self.assertAlmostEqual(trent["realized_pl"], 6780.0)

    def test_apply_replaces_entire_zerodha_broker(self):
        ledger = _ledger_with_junk()
        # No open Zerodha lots — capital-gains-only replace is safe.
        ledger["positions"] = [{
            "id": "paytm-open-keep",
            "symbol": "TRENT",
            "qty": 3,
            "entry_price": 2800,
            "broker": BROKER_PAYTM,
            "import_source": "manual",
        }]
        ledger["import_meta"] = {"zerodha_trade_ids": ["stale-z-id"]}
        items = []
        text = (FIXTURES / "tax_pnl_capital_gains.csv").read_text(encoding="utf-8")
        summary = run_zerodha_tax_pnl_import(ledger, items, text)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["closed_replaced"], 2)
        self.assertEqual(summary["open_replaced"], 0)
        self.assertEqual(summary["trade_ids_cleared"], 1)
        self.assertEqual(summary["broker"], BROKER_ZERODHA)
        self.assertEqual(summary["replace_scope"], "broker")
        # All pre-existing Zerodha rows are gone; Paytm rows remain.
        symbols_closed = [t["symbol"] for t in ledger["closed_trades"]]
        self.assertNotIn("INFY", symbols_closed)
        paytm = [t for t in ledger["closed_trades"] if t.get("id") == "paytm-keep"]
        self.assertEqual(len(paytm), 1)
        paytm_open = [p for p in ledger["positions"] if p.get("id") == "paytm-open-keep"]
        self.assertEqual(len(paytm_open), 1)
        self.assertFalse(any(infer_broker(p) == BROKER_ZERODHA for p in ledger["positions"]))
        self.assertEqual(ledger["import_meta"]["zerodha_trade_ids"], [])
        trent_z = [
            t for t in ledger["closed_trades"]
            if t["symbol"] == "TRENT" and infer_broker(t) == BROKER_ZERODHA
        ]
        self.assertEqual(len(trent_z), 1)
        self.assertAlmostEqual(trent_z[0]["realized_pl"], 6780.0)
        self.assertEqual(trent_z[0]["import_source"], "zerodha_tax_pnl")
        self.assertAlmostEqual(summary["by_symbol"]["TRENT"], 6780.0)
        self.assertAlmostEqual(summary["cim_realized_before"]["TRENT"], -3400.0)

    def test_capital_gains_without_open_source_is_blocked(self):
        ledger = _ledger_with_junk()
        text = (FIXTURES / "tax_pnl_capital_gains.csv").read_text(encoding="utf-8")
        summary = run_zerodha_tax_pnl_import(ledger, [], text)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["open_replaced"], 1)
        self.assertTrue(any(infer_broker(p) == BROKER_ZERODHA for p in ledger["positions"]))
        self.assertEqual(len(ledger["closed_trades"]), 3)
        self.assertIn("Holdings CSV", summary["errors"][0]["message"])

    def test_full_replace_rebuilds_open_from_combined_file(self):
        ledger = _ledger_with_junk()
        items = []
        text = (FIXTURES / "console_pnl_combined.csv").read_text(encoding="utf-8")
        summary = run_zerodha_tax_pnl_import(ledger, items, text)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["open_replaced"], 1)
        self.assertEqual(summary["open_synced"], 1)
        trent_open = [
            p for p in ledger["positions"]
            if p["symbol"] == "TRENT" and infer_broker(p) == BROKER_ZERODHA
        ]
        self.assertEqual(len(trent_open), 1)
        self.assertEqual(trent_open[0]["qty"], 10)

    def test_parse_error_does_not_destroy_existing_zerodha_rows(self):
        ledger = _ledger_with_junk()
        before_positions = [dict(p) for p in ledger["positions"]]
        before_closed = [dict(t) for t in ledger["closed_trades"]]
        summary = run_zerodha_tax_pnl_import(
            ledger,
            [],
            "Symbol,Quantity,Realised P&L\nPARAS,not-a-number,100\n",
        )
        self.assertFalse(summary["ok"])
        self.assertEqual(ledger["positions"], before_positions)
        self.assertEqual(ledger["closed_trades"], before_closed)

    def test_preview_compare(self):
        ledger = _ledger_with_junk()
        # Remove Zerodha opens so capital-gains preview can run.
        ledger["positions"] = []
        text = (FIXTURES / "tax_pnl_capital_gains.csv").read_text(encoding="utf-8")
        preview = preview_zerodha_tax_pnl(ledger, [], text)
        self.assertTrue(preview["ok"])
        # dry-run must not mutate
        self.assertEqual(preview["closed_replaced"], 2)
        self.assertEqual(preview["open_replaced"], 0)
        self.assertEqual(preview["replace_scope"], "broker")
        self.assertEqual(len(ledger["positions"]), 0)
        self.assertEqual(len(ledger["closed_trades"]), 3)
        cmp_trent = next(c for c in preview["compare"] if c["symbol"] == "TRENT")
        self.assertAlmostEqual(cmp_trent["cim_realized"], -3400.0)
        self.assertAlmostEqual(cmp_trent["tax_realized"], 6780.0)
        self.assertAlmostEqual(cmp_trent["delta"], 10180.0)

    def test_consolidate_does_not_merge_across_brokers(self):
        from server.pnl_ledger import consolidate_open_lots

        ledger = {
            "positions": [
                {
                    "id": "z1",
                    "symbol": "TRENT",
                    "qty": 10,
                    "entry_price": 2700,
                    "entry_date": None,
                    "broker": BROKER_ZERODHA,
                },
                {
                    "id": "p1",
                    "symbol": "TRENT",
                    "qty": 3,
                    "entry_price": 2700,
                    "entry_date": None,
                    "broker": BROKER_PAYTM,
                },
            ],
            "closed_trades": [],
            "import_meta": {"zerodha_trade_ids": []},
        }
        removed = consolidate_open_lots(ledger)
        self.assertEqual(removed, 0)
        self.assertEqual(len(ledger["positions"]), 2)

    def test_excel_xlsx_to_tax_pnl(self):
        from server.excel_table import excel_upload_to_csv_text, resolve_tax_pnl_csv_from_payload
        import base64

        path = FIXTURES / "tax_pnl_sample.xlsx"
        data = path.read_bytes()
        csv_text, sheet = excel_upload_to_csv_text(raw=data, filename=path.name)
        self.assertIn("Equity", sheet)
        closed, _, errors = parse_zerodha_tax_pnl_csv(csv_text)
        self.assertEqual(errors, [])
        self.assertEqual(len(closed), 2)
        b64 = base64.b64encode(data).decode("ascii")
        resolved = resolve_tax_pnl_csv_from_payload({
            "excel_base64": b64,
            "filename": "tax_pnl_sample.xlsx",
        })
        closed2, _, _ = parse_zerodha_tax_pnl_csv(resolved)
        self.assertEqual(len(closed2), 2)

    def test_html_disguised_as_xls(self):
        from server.excel_table import excel_upload_to_csv_text, _sniff_format

        html = b"""<html><body><table>
        <tr><td>Symbol</td><td>Quantity</td><td>Buy value</td><td>Sell value</td><td>Realised P&L</td></tr>
        <tr><td>TRENT</td><td>2</td><td>8600</td><td>15380</td><td>6780</td></tr>
        </table></body></html>"""
        self.assertEqual(_sniff_format(html, "tax_pnl.xls"), "html")
        csv_text, sheet = excel_upload_to_csv_text(raw=html, filename="tax_pnl.xls")
        closed, _, errors = parse_zerodha_tax_pnl_csv(csv_text)
        self.assertEqual(errors, [])
        self.assertEqual(len(closed), 1)
        self.assertAlmostEqual(closed[0]["realized_pl"], 6780.0)


if __name__ == "__main__":
    unittest.main()
