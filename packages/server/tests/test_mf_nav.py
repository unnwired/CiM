"""AMFI NAVOpen parser + SQLite upsert + favorites store."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from server import mf_favorites_store as fav
from server import mf_nav

IST = ZoneInfo("Asia/Kolkata")

FIXTURE = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
  
Open Ended Schemes(Equity Scheme - Large Cap Fund)
  
Aditya Birla Sun Life Mutual Fund
  
119551;INF209KA12Z1;INF209KA13Z9;Aditya Birla Sun Life Frontline Equity Fund - DIRECT - IDCW;106.8611;28-Jul-2026
119550;INF209K01YN0;-;Aditya Birla Sun Life Frontline Equity Fund- Direct Plan-Growth;403.5701;28-Jul-2026
108273;INF209K01LV0;-;Aditya Birla Sun Life Frontline Equity Fund - Regular Plan-Growth;387.4356;28-Jul-2026
  
Open Ended Schemes(Debt Scheme - Liquid Fund)
  
Axis Mutual Fund
  
120438;INF846K01CR6;-;Axis Liquid Fund - Direct Plan - Growth Option;2890.2625;28-Jul-2026
"""


class TestMfNavParse(unittest.TestCase):
    def test_parse_categories_and_direct_growth(self):
        rows = mf_nav.parse_nav_open_text(FIXTURE)
        self.assertEqual(len(rows), 4)
        by_code = {r["scheme_code"]: r for r in rows}
        self.assertEqual(by_code["119550"]["plan_kind"], "direct_growth")
        self.assertEqual(by_code["120438"]["plan_kind"], "direct_growth")
        self.assertEqual(by_code["119551"]["plan_kind"], "other")
        self.assertEqual(by_code["108273"]["plan_kind"], "other")
        self.assertEqual(by_code["119550"]["category"], "Equity Scheme - Large Cap Fund")
        self.assertEqual(by_code["120438"]["category"], "Debt Scheme - Liquid Fund")
        self.assertEqual(by_code["119550"]["nav_date"], "2026-07-28")
        self.assertAlmostEqual(by_code["119550"]["last_nav"], 403.5701, places=4)

    def test_normalize_category_aliases(self):
        self.assertEqual(
            mf_nav.normalize_category("Equity Schemes - Flexi Cap Fund"),
            "Equity Scheme - Flexi Cap Fund",
        )

    def test_upsert_and_history(self):
        rows = mf_nav.parse_nav_open_text(FIXTURE)
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.db"
            conn = sqlite3.connect(str(db))
            try:
                stats = mf_nav.upsert_schemes_and_history(conn, rows)
                self.assertEqual(stats["schemes"], 4)
                n = conn.execute(
                    "SELECT COUNT(*) FROM mf_schemes WHERE plan_kind='direct_growth'"
                ).fetchone()[0]
                self.assertEqual(n, 2)
                hist = conn.execute(
                    "SELECT Close FROM mf_nav_history WHERE scheme_code='119550'"
                ).fetchone()
                self.assertAlmostEqual(float(hist[0]), 403.5701, places=4)
            finally:
                conn.close()


class TestMfFavorites(unittest.TestCase):
    def test_save_load(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            saved = fav.save_favorites(base, ["119550", "120438", "119550", "bad"])
            self.assertEqual(saved, ["119550", "120438"])
            loaded = fav.load_favorites(base)
            self.assertEqual(loaded, ["119550", "120438"])


class TestMfNavSessionGate(unittest.TestCase):
    def test_blocked_before_close_on_weekday(self):
        # Wednesday 2026-07-29 12:00 IST — mid-session
        now = datetime(2026, 7, 29, 12, 0, tzinfo=IST)
        ok, reason = mf_nav.mf_nav_refresh_allowed(now)
        self.assertFalse(ok)
        self.assertIn("15:30", reason)

    def test_allowed_at_close_on_weekday(self):
        now = datetime(2026, 7, 29, 15, 30, tzinfo=IST)
        ok, reason = mf_nav.mf_nav_refresh_allowed(now)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_allowed_weekend_morning(self):
        # Saturday morning — market already closed
        now = datetime(2026, 8, 1, 10, 0, tzinfo=IST)
        ok, _reason = mf_nav.mf_nav_refresh_allowed(now)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
