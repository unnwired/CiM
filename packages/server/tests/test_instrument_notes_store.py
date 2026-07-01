"""Tests for per-user instrument notes storage."""
from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "packages"))

from server import instrument_notes_store as ins


class InstrumentNotesStoreTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        base = Path(tmp)
        (base / "data").mkdir(parents=True, exist_ok=True)
        return base

    def _seed_legacy_db(self, base: Path, symbol: str, note: str, it: str = "stock") -> None:
        db = base / "data" / "nse_data.db"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS instrument_notes (
                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    note_text TEXT NOT NULL DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, instrument_type)
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO instrument_notes (symbol, instrument_type, note_text) VALUES (?, ?, ?)",
                (symbol, it, note),
            )
            conn.commit()
        finally:
            conn.close()

    def test_local_and_user_namespaces_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.instrument_notes_store._crypto.current_machine_code", return_value="MACH001"):
                ins.save_note(base, "RELIANCE", "stock", "local note", session=None)
                ins.save_note(
                    base,
                    "RELIANCE",
                    "stock",
                    "user note",
                    session={"email": "alice@example.com"},
                )
                local = ins.load_note(base, "RELIANCE", "stock", session=None)
                user = ins.load_note(
                    base, "RELIANCE", "stock", session={"email": "alice@example.com"}
                )
            self.assertEqual(local, "local note")
            self.assertEqual(user, "user note")

    def test_legacy_db_migrates_to_local_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            self._seed_legacy_db(base, "TCS", "legacy text")
            ins._legacy_migrated = False
            with mock.patch("server.instrument_notes_store._crypto.current_machine_code", return_value="MACH002"):
                note = ins.load_note(base, "TCS", "stock", session=None)
            self.assertEqual(note, "legacy text")
            conn = sqlite3.connect(str(base / "data" / "nse_data.db"))
            try:
                count = conn.execute("SELECT COUNT(*) FROM instrument_notes").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 0)
            notes_path = base / "data" / "users" / "_local" / "MACH002" / "instrument_notes.json"
            self.assertTrue(notes_path.is_file())

    def test_clear_instrument_notes_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            self._seed_legacy_db(base, "INFY", "export leak")
            db = base / "data" / "nse_data.db"
            removed = ins.clear_instrument_notes_table(db)
            self.assertEqual(removed, 1)
            conn = sqlite3.connect(str(db))
            try:
                count = conn.execute("SELECT COUNT(*) FROM instrument_notes").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 0)

    def test_save_empty_removes_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            with mock.patch("server.instrument_notes_store._crypto.current_machine_code", return_value="MACH003"):
                ins.save_note(base, "SBIN", "stock", "hello", session=None)
                self.assertTrue(ins.has_note(base, "SBIN", "stock", session=None))
                ins.save_note(base, "SBIN", "stock", "   ", session=None)
                self.assertFalse(ins.has_note(base, "SBIN", "stock", session=None))


if __name__ == "__main__":
    unittest.main()
