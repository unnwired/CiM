"""Tests for per-account universal notes storage (tabbed notepad)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "packages"))

from server import user_notes_store as uns


class UserNotesStoreTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        base = Path(tmp)
        (base / "data").mkdir(parents=True, exist_ok=True)
        return base

    def test_roundtrip_and_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.user_notes_store._crypto.current_machine_code", return_value="MACH001"):
                doc = {
                    "tabs": [
                        {"id": "a", "title": "Ideas", "text": "buy the dip", "archived": False},
                        {"title": "  Watch  ", "text": "TRENT breakout", "archived": True},
                    ],
                    "junk_key": "dropped",
                }
                saved = uns.save_doc(base, doc, session={"email": "alice@example.com"})
                self.assertEqual(len(saved["tabs"]), 2)
                self.assertEqual(saved["tabs"][1]["title"], "Watch")
                self.assertTrue(saved["tabs"][1]["id"])
                self.assertNotIn("junk_key", saved)

                loaded = uns.load_doc(base, session={"email": "alice@example.com"})
                self.assertEqual(loaded["tabs"][0]["text"], "buy the dip")
                self.assertTrue(loaded["tabs"][1]["archived"])

    def test_accounts_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.user_notes_store._crypto.current_machine_code", return_value="MACH001"):
                uns.save_doc(base, {"tabs": [{"title": "A", "text": "alice"}]}, session={"email": "alice@example.com"})
                uns.save_doc(base, {"tabs": [{"title": "B", "text": "bob"}]}, session={"email": "bob@example.com"})
                uns.save_doc(base, {"tabs": [{"title": "L", "text": "local"}]}, session=None)

                alice = uns.load_doc(base, session={"email": "alice@example.com"})
                bob = uns.load_doc(base, session={"email": "bob@example.com"})
                local = uns.load_doc(base, session=None)
                self.assertEqual(alice["tabs"][0]["text"], "alice")
                self.assertEqual(bob["tabs"][0]["text"], "bob")
                self.assertEqual(local["tabs"][0]["text"], "local")

    def test_rejects_bad_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.user_notes_store._crypto.current_machine_code", return_value="MACH001"):
                with self.assertRaises(ValueError):
                    uns.save_doc(base, ["not", "a", "dict"], session=None)
                with self.assertRaises(ValueError):
                    uns.save_doc(base, {"tabs": "nope"}, session=None)
                with self.assertRaises(ValueError):
                    uns.save_doc(
                        base,
                        {"tabs": [{"title": "big", "text": "x" * (uns.MAX_TEXT_LEN + 1)}]},
                        session=None,
                    )

    def test_missing_file_returns_empty_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.user_notes_store._crypto.current_machine_code", return_value="MACH001"):
                doc = uns.load_doc(base, session={"email": "nobody@example.com"})
                self.assertEqual(doc, {"tabs": []})


if __name__ == "__main__":
    unittest.main()
