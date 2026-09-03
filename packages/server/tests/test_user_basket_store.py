"""Tests for per-account interest basket storage."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "packages"))

from server import user_basket_store as ubs


class UserBasketStoreTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        base = Path(tmp)
        (base / "data").mkdir(parents=True, exist_ok=True)
        return base

    def test_roundtrip_dedupe_and_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.user_basket_store._crypto.current_machine_code", return_value="MACH001"):
                session = {"email": "alice@example.com"}
                saved = ubs.save_doc(
                    base,
                    {
                        "symbols": [
                            {"symbol": "reliance", "kind": "stock"},
                            "RELIANCE",
                            {"symbol": "NIFTY", "kind": "index"},
                            {"symbol": "bad", "kind": " Mutual"},
                        ],
                    },
                    session=session,
                )
                self.assertEqual(len(saved["symbols"]), 3)
                self.assertEqual(saved["symbols"][0]["symbol"], "RELIANCE")
                self.assertEqual(saved["symbols"][0]["kind"], "stock")
                self.assertEqual(saved["symbols"][1]["symbol"], "NIFTY")
                self.assertEqual(saved["symbols"][1]["kind"], "index")
                self.assertEqual(saved["symbols"][2]["kind"], "stock")

                loaded = ubs.load_doc(base, session=session)
                self.assertEqual(len(loaded["symbols"]), 3)

                again = ubs.add_symbol(base, "RELIANCE", kind="stock", session=session)
                self.assertEqual(len(again["symbols"]), 3)

                removed = ubs.remove_symbol(base, "NIFTY", kind="index", session=session)
                self.assertEqual([e["symbol"] for e in removed["symbols"]], ["RELIANCE", "BAD"])


if __name__ == "__main__":
    unittest.main()
