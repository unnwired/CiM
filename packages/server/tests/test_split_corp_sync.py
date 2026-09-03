import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from server.corp_actions import load_corp_actions, upsert_split_corp_action
from server.split_utils import history_has_split_discontinuity


class SplitCorpSyncTests(unittest.TestCase):
    def test_upsert_split_corp_action_writes_install_file(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            upsert_split_corp_action(
                data_dir,
                symbol="TDPOWERSYS",
                ex_date="2026-08-24",
                ratio=2.0,
                source="test",
            )
            actions = load_corp_actions(data_dir)
            splits = [a for a in actions if a.get("action_type") == "split"]
            self.assertEqual(len(splits), 1)
            self.assertEqual(splits[0]["symbol"], "TDPOWERSYS")
            self.assertEqual(splits[0]["ratio"], 2.0)
            raw = json.loads((data_dir / "corp_actions.json").read_text(encoding="utf-8"))
            self.assertIn("actions", raw)

    def test_history_has_split_discontinuity_detects_nominal_gap(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE historical_data (Symbol TEXT, Date TEXT, Close REAL)"
        )
        rows = [
            ("TDPOWERSYS", "2026-08-21 00:00:00+05:30", 1539.5),
            ("TDPOWERSYS", "2026-08-24 00:00:00+05:30", 782.5),
        ]
        conn.executemany(
            "INSERT INTO historical_data (Symbol, Date, Close) VALUES (?, ?, ?)",
            rows,
        )
        self.assertTrue(
            history_has_split_discontinuity(conn, "TDPOWERSYS", "2026-08-24", 2.0)
        )
        conn.execute(
            "UPDATE historical_data SET Close = 770.0 WHERE Date LIKE '2026-08-21%'"
        )
        self.assertFalse(
            history_has_split_discontinuity(conn, "TDPOWERSYS", "2026-08-24", 2.0)
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
