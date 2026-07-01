"""Unit tests for Earnings+ cache staleness and reported filter helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta


def _import_server():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "server.py"
    spec = importlib.util.spec_from_file_location("nse_pulse_server_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class EarningsPlusHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = _import_server()

    def test_qualified_not_time_stale(self):
        fresh = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "decision": "qualified",
            "refresh_after": fresh,
            "source_fetched_at": fresh,
        }
        self.assertFalse(self.srv._earnings_plus_cache_is_stale(entry))

    def test_insufficient_data_stale_when_old_source(self):
        old = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "decision": "insufficient_data",
            "refresh_after": old,
            "source_fetched_at": old,
        }
        self.assertTrue(self.srv._earnings_plus_cache_is_stale(entry))

    def test_filter_includes_qualified_matching_release(self):
        entry = {
            "decision": "qualified",
            "is_stale": False,
            "latest_period_date_key": "2026-03-31",
        }
        row = {"symbol": "TEST", "earnings_release_date": "2026-05-15"}
        self.assertTrue(self.srv._earnings_plus_entry_matches_report_row(entry, row))
        is_qualified = (
            bool(entry)
            and self.srv._earnings_plus_entry_matches_report_row(entry, row)
            and not entry.get("is_stale")
            and entry.get("decision") == "qualified"
        )
        self.assertTrue(is_qualified)

    def test_filter_excludes_stale_qualified(self):
        entry = {
            "decision": "qualified",
            "is_stale": True,
            "latest_period_date_key": "2026-03-31",
        }
        row = {"symbol": "TEST", "earnings_release_date": "2026-05-15"}
        is_qualified = (
            bool(entry)
            and self.srv._earnings_plus_entry_matches_report_row(entry, row)
            and not entry.get("is_stale")
            and entry.get("decision") == "qualified"
        )
        self.assertFalse(is_qualified)

    def test_pick_uses_consolidated_not_qualified_over_standalone_qualified(self):
        sym = "FINCABLES"
        computed_at = "2026-05-27 12:00:00"
        c_ev = {
            "decision": "not_qualified",
            "basis_used": "consolidated",
            "latest_period": "Mar 2026",
            "latest_period_date_key": "2026-03-31",
            "previous_period": "Dec 2025",
            "previous_year_period": "Mar 2025",
            "note": "consolidated fails",
            "source_fetched_at": "2026-05-27 10:00:00",
        }
        s_ev = {
            "decision": "qualified",
            "basis_used": "standalone",
            "latest_period": "Mar 2026",
            "latest_period_date_key": "2026-03-31",
            "previous_period": "Dec 2025",
            "previous_year_period": "Mar 2025",
            "note": "standalone passes",
            "source_fetched_at": "2026-05-27 10:00:00",
        }
        basis_results = [
            ("consolidated", c_ev, None, False),
            ("standalone", s_ev, None, False),
        ]
        entry = self.srv._pick_best_earnings_plus_entry(sym, basis_results, computed_at)
        self.assertEqual(entry["decision"], "not_qualified")
        self.assertEqual(entry["basis_used"], "consolidated")

    def test_pick_falls_back_to_standalone_when_consolidated_insufficient(self):
        sym = "DEMO"
        computed_at = "2026-05-27 12:00:00"
        c_ev = {
            "decision": "insufficient_data",
            "basis_used": "consolidated",
            "latest_period": None,
            "latest_period_date_key": None,
            "previous_period": None,
            "previous_year_period": None,
            "note": "no consolidated",
            "source_fetched_at": None,
        }
        s_ev = {
            "decision": "qualified",
            "basis_used": "standalone",
            "latest_period": "Mar 2026",
            "latest_period_date_key": "2026-03-31",
            "previous_period": "Dec 2025",
            "previous_year_period": "Mar 2025",
            "note": "standalone passes",
            "source_fetched_at": "2026-05-27 10:00:00",
        }
        basis_results = [
            ("consolidated", c_ev, None, False),
            ("standalone", s_ev, None, False),
        ]
        entry = self.srv._pick_best_earnings_plus_entry(sym, basis_results, computed_at)
        self.assertEqual(entry["decision"], "qualified")
        self.assertEqual(entry["basis_used"], "standalone")

    def test_pick_uses_consolidated_qualified_when_both_qualify(self):
        sym = "DEMO"
        computed_at = "2026-05-27 12:00:00"
        base = {
            "latest_period": "Mar 2026",
            "latest_period_date_key": "2026-03-31",
            "previous_period": "Dec 2025",
            "previous_year_period": "Mar 2025",
            "source_fetched_at": "2026-05-27 10:00:00",
        }
        c_ev = {"decision": "qualified", "basis_used": "consolidated", "note": "c", **base}
        s_ev = {"decision": "qualified", "basis_used": "standalone", "note": "s", **base}
        entry = self.srv._pick_best_earnings_plus_entry(
            sym,
            [("consolidated", c_ev, None, False), ("standalone", s_ev, None, False)],
            computed_at,
        )
        self.assertEqual(entry["decision"], "qualified")
        self.assertEqual(entry["basis_used"], "consolidated")


if __name__ == "__main__":
    unittest.main()
