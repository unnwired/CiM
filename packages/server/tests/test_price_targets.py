"""Price-target store + watchlist absolute alert evaluation."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PACKAGES = Path(__file__).resolve().parents[2]
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from alert_evaluator import _evaluate_price_targets  # noqa: E402
from user_alerts_store import (  # noqa: E402
    load_alerts,
    load_settings,
    mark_price_target_triggered,
    normalize_price_target,
    set_price_target_armed,
    upsert_price_target,
)


class PriceTargetStoreTest(unittest.TestCase):
    def test_upsert_and_rearm_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            saved = upsert_price_target(
                base, symbol="RELIANCE", direction="above", level=2850
            )
            targets = saved["price_targets"]
            self.assertEqual(len(targets), 1)
            tid = targets[0]["id"]
            self.assertTrue(targets[0]["armed"])
            self.assertEqual(targets[0]["generation"], 0)

            mark_price_target_triggered(base, target_id=tid)
            after = load_settings(base)
            self.assertFalse(after["price_targets"][0]["armed"])

            rearmed = set_price_target_armed(base, target_id=tid, armed=True)
            self.assertTrue(rearmed["price_targets"][0]["armed"])
            self.assertEqual(rearmed["price_targets"][0]["generation"], 1)

    def test_normalize_rejects_bad(self):
        self.assertIsNone(normalize_price_target({"symbol": "X", "direction": "above", "level": 0}))
        self.assertIsNone(normalize_price_target({"symbol": "", "direction": "above", "level": 10}))


class PriceTargetEvalTest(unittest.TestCase):
    def test_fires_above_and_telegrams(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            upsert_price_target(base, symbol="RELIANCE", direction="above", level=2800)
            settings = load_settings(base)
            settings["telegram_enabled"] = True
            settings["browser_enabled"] = True
            stock_syms = {"RELIANCE"}
            sym_to_lists = {"RELIANCE": ["Key Stocks"]}

            with patch("alert_evaluator._is_nse_market_hours", return_value=True), patch(
                "alert_evaluator._session_price_quotes",
                return_value={"RELIANCE": {"price": 2850.5, "high": 2860.0, "low": 2800.0}},
            ), patch("alert_evaluator.telegram_notify.send_for_user", return_value={"ok": True}) as tg:
                n = _evaluate_price_targets(
                    base, None, settings, Path(tmp) / "nse_data.db", stock_syms, sym_to_lists
                )
            self.assertEqual(n, 1)
            self.assertTrue(tg.called)
            text = tg.call_args[0][2]
            self.assertIn("CiM Price Alert", text)
            self.assertIn("RELIANCE", text)

            doc = load_alerts(base)
            self.assertEqual(len(doc["alerts"]), 1)
            self.assertEqual(doc["alerts"][0]["kind"], "price_above")
            self.assertTrue(doc["alerts"][0].get("delivered_telegram"))

            after = load_settings(base)
            self.assertFalse(after["price_targets"][0]["armed"])

    def test_fires_above_via_session_high_when_ltp_below(self):
        """Regression: wick to target then reverse — LTP sample alone would miss."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            upsert_price_target(base, symbol="TATAPOWER", direction="above", level=379)
            settings = load_settings(base)
            stock_syms = {"TATAPOWER"}
            sym_to_lists = {"TATAPOWER": ["Key Stocks + Earnings"]}
            with patch("alert_evaluator._is_nse_market_hours", return_value=True), patch(
                "alert_evaluator._session_price_quotes",
                return_value={"TATAPOWER": {"price": 376.85, "high": 379.7, "low": 375.55}},
            ), patch("alert_evaluator.telegram_notify.send_for_user", return_value={"ok": True}):
                n = _evaluate_price_targets(
                    base, None, settings, Path(tmp) / "nse_data.db", stock_syms, sym_to_lists
                )
            self.assertEqual(n, 1)
            doc = load_alerts(base)
            self.assertEqual(doc["alerts"][0]["kind"], "price_above")
            self.assertEqual(doc["alerts"][0]["meta"].get("touch_price"), 379.7)
            self.assertFalse(load_settings(base)["price_targets"][0]["armed"])

    def test_skips_symbol_not_on_notified_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            upsert_price_target(base, symbol="RELIANCE", direction="above", level=2800)
            settings = load_settings(base)
            with patch("alert_evaluator._is_nse_market_hours", return_value=True), patch(
                "alert_evaluator._session_price_quotes",
                return_value={"RELIANCE": {"price": 2900, "high": 2910, "low": 2850}},
            ):
                n = _evaluate_price_targets(
                    base, None, settings, Path(tmp) / "x.db", set(), {}
                )
            self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
