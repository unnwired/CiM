import json
import sqlite3
import unittest

from earnings_plus_lookup import attach_earnings_plus_flags, read_qualified_symbols


class TestEarningsPlusLookup(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE earnings_plus_cache (
                symbol TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                basis_used TEXT,
                latest_period TEXT,
                latest_period_date_key TEXT,
                previous_period TEXT,
                previous_year_period TEXT,
                note TEXT,
                source_fetched_at TEXT,
                computed_at TEXT NOT NULL,
                refresh_after TEXT NOT NULL,
                last_error TEXT
            )
            """
        )
        self.conn.execute(
            "INSERT INTO earnings_plus_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("RELIANCE", "qualified", "c", "Q1", "2025-03", None, None, "ok", "t", "t", "t", None),
        )
        self.conn.execute(
            "INSERT INTO earnings_plus_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("FAILCO", "not_qualified", "c", "Q1", "2025-03", None, None, None, "t", "t", "t", None),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_read_qualified_symbols(self):
        q = read_qualified_symbols(self.conn, ["RELIANCE", "FAILCO", "MISSING"])
        self.assertEqual(q, {"RELIANCE"})

    def test_attach_flags(self):
        rows = [{"symbol": "RELIANCE"}, {"symbol": "FAILCO"}]
        attach_earnings_plus_flags(self.conn, rows)
        self.assertTrue(rows[0]["earnings_plus"])
        self.assertFalse(rows[1]["earnings_plus"])

    def test_period_mismatch_excludes_stale_qualified(self):
        self.conn.execute(
            """
            CREATE TABLE screener_quarterly (
                symbol TEXT NOT NULL,
                basis TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at TEXT,
                source_url TEXT,
                PRIMARY KEY (symbol, basis)
            )
            """
        )
        payload = {
            "periods": [
                {"period": "Mar 2026", "date_key": "2026-03-31"},
                {"period": "Jun 2026", "date_key": "2026-06-30"},
            ]
        }
        self.conn.execute(
            "INSERT INTO screener_quarterly VALUES (?,?,?,?,?)",
            ("RELIANCE", "consolidated", json.dumps(payload), "t", None),
        )
        self.conn.commit()
        q = read_qualified_symbols(self.conn, ["RELIANCE"])
        self.assertEqual(q, set())


if __name__ == "__main__":
    unittest.main()
