"""Unit tests for Earnings+ cache staleness and reported filter helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta


def _import_server():
    import sys
    from pathlib import Path

    packages = Path(__file__).resolve().parents[2]
    if str(packages) not in sys.path:
        sys.path.insert(0, str(packages))
    import server.server as mod
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
            "latest_period_date_key": "2026-03-31",
        }
        self.assertFalse(self.srv._earnings_plus_cache_is_stale(entry))
        self.assertFalse(
            self.srv._earnings_plus_cache_is_stale(entry, "2026-03-31")
        )

    def test_qualified_stale_when_local_screener_period_advances(self):
        entry = {
            "decision": "qualified",
            "refresh_after": "2026-06-09 18:00:00",
            "source_fetched_at": "2026-06-09 00:00:00",
            "latest_period_date_key": "2026-03-31",
        }
        self.assertTrue(
            self.srv._earnings_plus_cache_is_stale(entry, "2026-06-30")
        )
        self.assertTrue(
            self.srv._earnings_plus_cache_needs_refresh(
                entry, None, local_latest_period_date_key="2026-06-30"
            )
        )

    def test_evaluate_note_lists_failed_checks(self):
        payload = {
            "fetched_at": "2026-07-22 12:00:00",
            "periods": [
                {"period": "Jun 2025", "date_key": "2025-06-30"},
                {"period": "Sep 2025", "date_key": "2025-09-30"},
                {"period": "Dec 2025", "date_key": "2025-12-31"},
                {"period": "Mar 2026", "date_key": "2026-03-31"},
                {"period": "Jun 2026", "date_key": "2026-06-30"},
            ],
            "rows": [
                {"slug": "opm", "label": "OPM %", "values": ["12%", "15%", "15%", "26%", "15%"]},
                {"slug": "net_profit", "label": "Net Profit", "values": ["25", "44", "42", "144", "33"]},
                {"slug": "eps_in_rs", "label": "EPS in Rs", "values": ["4.10", "6.70", "6.50", "22.14", "5.14"]},
            ],
        }
        ev = self.srv._evaluate_earnings_plus_payload(payload, "consolidated")
        self.assertEqual(ev["decision"], "not_qualified")
        self.assertEqual(ev["latest_period"], "Jun 2026")
        self.assertIn("OPM 15% < QoQ Mar 2026 26%", ev["note"])
        self.assertIn("EPS 5.14 ≤ QoQ Mar 2026 22.14", ev["note"])

    def test_insufficient_data_stale_when_old_source(self):
        old = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "decision": "insufficient_data",
            "refresh_after": old,
            "source_fetched_at": old,
        }
        self.assertTrue(self.srv._earnings_plus_cache_is_stale(entry))

    def test_screener_synced_within_two_days_of_tv_release(self):
        entry = {
            "decision": "qualified",
            "source_fetched_at": "2026-07-17 10:00:00",
            "computed_at": "2026-07-17 10:00:00",
        }
        self.assertTrue(
            self.srv._earnings_plus_screener_synced_to_release(entry, "2026-07-16")
        )
        self.assertTrue(
            self.srv._earnings_plus_screener_synced_to_release(entry, "2026-07-18")
        )
        self.assertTrue(
            self.srv._earnings_plus_screener_synced_to_release(entry, "2026-07-15")
        )
        # Days after the print still counts as synced (post-print Screener data).
        late = {
            "decision": "qualified",
            "source_fetched_at": "2026-07-25 10:00:00",
            "computed_at": "2026-07-25 10:00:00",
        }
        self.assertTrue(
            self.srv._earnings_plus_screener_synced_to_release(late, "2026-07-10")
        )

    def test_screener_not_synced_when_fetch_weeks_before_tv_release(self):
        entry = {
            "decision": "qualified",
            "source_fetched_at": "2026-06-09 00:00:00",
            "computed_at": "2026-06-09 00:00:00",
        }
        self.assertFalse(
            self.srv._earnings_plus_screener_synced_to_release(entry, "2026-07-16")
        )
        self.assertTrue(
            self.srv._earnings_plus_cache_needs_refresh(
                entry, {"earnings_release_date": "2026-07-16"}
            )
        )

    def test_apply_is_read_only_and_queues_bg_sync(self):
        from unittest.mock import patch

        rows = [
            {"symbol": "KEEP", "earnings_release_date": "2026-07-16"},
            {"symbol": "STALEFETCH", "earnings_release_date": "2026-07-20"},
        ]
        entries = {
            "KEEP": {
                "decision": "qualified",
                "is_stale": False,
                "latest_period_date_key": "2026-03-31",
                "note": "KEEP Earnings+ note",
                "basis_used": "consolidated",
                "latest_period": "Mar 2026",
                "previous_period": "Dec 2025",
                "previous_year_period": "Mar 2025",
                "source_fetched_at": "2026-07-16 11:00:00",
                "computed_at": "2026-07-16 11:00:00",
            },
            "STALEFETCH": {
                "decision": "qualified",
                "is_stale": False,
                "latest_period_date_key": "2026-03-31",
                "note": "old fetch",
                "basis_used": "consolidated",
                "latest_period": "Mar 2026",
                "previous_period": "Dec 2025",
                "previous_year_period": "Mar 2025",
                "source_fetched_at": "2026-06-01 00:00:00",
                "computed_at": "2026-06-01 00:00:00",
            },
        }
        queued: list[str] = []

        with patch.object(self.srv, "_read_earnings_plus_cache_entries", return_value=entries), \
             patch.object(self.srv, "get_db_connection") as mock_conn, \
             patch.object(self.srv, "_enqueue_earnings_plus_screener_sync", side_effect=queued.extend), \
             patch.object(self.srv, "_heal_earnings_plus_entries_for_reported_rows") as mock_heal:
            mock_conn.return_value.close = lambda: None
            stamped, summary = self.srv._apply_reported_earnings_plus_filter(rows, "only")

        mock_heal.assert_not_called()
        self.assertEqual([r["symbol"] for r in stamped], ["KEEP", "STALEFETCH"])
        self.assertTrue(stamped[0]["earnings_plus"])
        self.assertTrue(stamped[1]["earnings_plus"])  # badge persists; bg will rescore
        self.assertEqual(queued, ["STALEFETCH"])
        self.assertEqual(summary["bg_sync_queued"], 1)

    def test_badge_persists_across_release_without_day_span_gate(self):
        """E+ stays until next print rescore — no 95/150d quarter-end lock."""
        entry = {
            "decision": "qualified",
            "is_stale": False,
            "latest_period_date_key": "2026-03-31",
            "source_fetched_at": "2026-07-16 12:00:00",
        }
        row = {"symbol": "BHEL", "earnings_release_date": "2026-07-16"}
        self.assertTrue(self.srv._earnings_plus_row_is_qualified(entry, row))
        # Even weeks later on the Earnings table, badge remains while not stale.
        later = {"symbol": "BHEL", "earnings_release_date": "2026-07-16"}
        self.assertTrue(self.srv._earnings_plus_row_is_qualified(entry, later))

    def test_badge_drops_when_stale_after_next_screener_quarter(self):
        entry = {
            "decision": "qualified",
            "is_stale": True,
            "latest_period_date_key": "2026-03-31",
        }
        row = {"symbol": "BHEL", "earnings_release_date": "2026-07-16"}
        self.assertFalse(self.srv._earnings_plus_row_is_qualified(entry, row))

    def test_badge_drops_when_next_print_not_qualified(self):
        entry = {
            "decision": "not_qualified",
            "is_stale": False,
            "latest_period_date_key": "2026-06-30",
            "source_fetched_at": "2026-07-20 09:00:00",
        }
        row = {"symbol": "DEMO", "earnings_release_date": "2026-07-20"}
        self.assertFalse(self.srv._earnings_plus_row_is_qualified(entry, row))

    def test_filter_excludes_stale_qualified(self):
        entry = {
            "decision": "qualified",
            "is_stale": True,
            "latest_period_date_key": "2026-03-31",
        }
        row = {"symbol": "TEST", "earnings_release_date": "2026-05-15"}
        self.assertFalse(self.srv._earnings_plus_row_is_qualified(entry, row))

    def test_pick_uses_standalone_when_consolidated_lags(self):
        sym = "JUSTDIAL"
        computed_at = "2026-07-25 12:00:00"
        c_ev = {
            "decision": "qualified",
            "basis_used": "consolidated",
            "latest_period": "Mar 2024",
            "latest_period_date_key": "2024-03-31",
            "previous_period": "Dec 2023",
            "previous_year_period": "Mar 2023",
            "note": "stale consol",
            "source_fetched_at": "2026-07-23 10:00:00",
        }
        s_ev = {
            "decision": "not_qualified",
            "basis_used": "standalone",
            "latest_period": "Jun 2026",
            "latest_period_date_key": "2026-06-30",
            "previous_period": "Mar 2026",
            "previous_year_period": "Jun 2025",
            "note": "current quarter",
            "source_fetched_at": "2026-07-23 10:00:00",
        }
        entry = self.srv._pick_best_earnings_plus_entry(
            sym,
            [("consolidated", c_ev, None, False), ("standalone", s_ev, None, False)],
            computed_at,
        )
        self.assertEqual(entry["decision"], "not_qualified")
        self.assertEqual(entry["basis_used"], "standalone")
        self.assertEqual(entry["latest_period_date_key"], "2026-06-30")

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

    def test_apply_stamps_badge_and_filters_without_day_span(self):
        from unittest.mock import patch

        rows = [
            {"symbol": "KEEP", "earnings_release_date": "2026-07-16"},
            {"symbol": "DROP", "earnings_release_date": "2026-07-20"},
            {"symbol": "NONE", "earnings_release_date": "2026-07-20"},
        ]
        entries = {
            "KEEP": {
                "decision": "qualified",
                "is_stale": False,
                "latest_period_date_key": "2026-03-31",
                "note": "KEEP Earnings+ note",
                "basis_used": "consolidated",
                "latest_period": "Mar 2026",
                "previous_period": "Dec 2025",
                "previous_year_period": "Mar 2025",
                "source_fetched_at": "2026-07-16 11:00:00",
                "computed_at": "2026-07-16 11:00:00",
            },
            "DROP": {
                "decision": "not_qualified",
                "is_stale": False,
                "latest_period_date_key": "2026-06-30",
                "note": "failed next print",
                "basis_used": "standalone",
                "latest_period": "Jun 2026",
                "previous_period": "Mar 2026",
                "previous_year_period": "Jun 2025",
                "source_fetched_at": "2026-07-20 09:00:00",
                "computed_at": "2026-07-20 09:00:00",
            },
        }

        with patch.object(self.srv, "_read_earnings_plus_cache_entries", return_value=entries), \
             patch.object(self.srv, "get_db_connection") as mock_conn, \
             patch.object(self.srv, "_enqueue_earnings_plus_screener_sync"):
            mock_conn.return_value.close = lambda: None
            stamped, summary = self.srv._apply_reported_earnings_plus_filter(rows, "all")

        by_sym = {r["symbol"]: r for r in stamped}
        self.assertTrue(by_sym["KEEP"]["earnings_plus"])
        self.assertIn("Earnings+", by_sym["KEEP"].get("earnings_plus_note") or "KEEP")
        self.assertFalse(by_sym["DROP"]["earnings_plus"])
        self.assertFalse(by_sym["NONE"]["earnings_plus"])
        self.assertEqual(summary["badge_qualified"], 1)

        with patch.object(self.srv, "_read_earnings_plus_cache_entries", return_value=entries), \
             patch.object(self.srv, "get_db_connection") as mock_conn, \
             patch.object(self.srv, "_enqueue_earnings_plus_screener_sync"):
            mock_conn.return_value.close = lambda: None
            only_rows, _ = self.srv._apply_reported_earnings_plus_filter(rows, "only")
            exclude_rows, _ = self.srv._apply_reported_earnings_plus_filter(rows, "exclude")

        self.assertEqual([r["symbol"] for r in only_rows], ["KEEP"])
        self.assertEqual([r["symbol"] for r in exclude_rows], ["DROP", "NONE"])

    def test_tv_eps_rev_beat_filter(self):
        from unittest.mock import patch

        rows = [
            {
                "symbol": "BEAT",
                "earnings_release_date": "2026-08-04",
                "eps_actual": 10.0,
                "eps_estimate": 8.0,
                "revenue_actual": 100.0,
                "revenue_estimate": 90.0,
            },
            {
                "symbol": "EPS_ONLY",
                "earnings_release_date": "2026-08-04",
                "eps_actual": 10.0,
                "eps_estimate": 8.0,
                "revenue_actual": 80.0,
                "revenue_estimate": 90.0,
            },
            {
                "symbol": "MEET",
                "earnings_release_date": "2026-08-04",
                "eps_actual": 8.0,
                "eps_estimate": 8.0,
                "revenue_actual": 90.0,
                "revenue_estimate": 90.0,
            },
            {
                "symbol": "MISSING",
                "earnings_release_date": "2026-08-04",
                "eps_actual": 10.0,
                "eps_estimate": None,
                "revenue_actual": 100.0,
                "revenue_estimate": 90.0,
            },
        ]
        with patch.object(self.srv, "_read_earnings_plus_cache_entries", return_value={}), \
             patch.object(self.srv, "get_db_connection") as mock_conn, \
             patch.object(self.srv, "_enqueue_earnings_plus_screener_sync"):
            mock_conn.return_value.close = lambda: None
            filtered, _ = self.srv._apply_reported_earnings_plus_filter(rows, "tv_eps_rev_beat")
        self.assertEqual([r["symbol"] for r in filtered], ["BEAT"])

    def test_upcoming_prescan_lead_constant(self):
        self.assertEqual(self.srv.EARNINGS_PLUS_UPCOMING_PRESCAN_LEAD_DAYS, 1)
        self.assertEqual(self.srv.EARNINGS_PLUS_REFRESH_WORKERS, 1)

    def test_upcoming_prescan_includes_tomorrow_release(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        tomorrow = (today + timedelta(days=1)).isoformat()
        later = (today + timedelta(days=4)).isoformat()
        today_s = today.isoformat()
        payload = {
            "rows": [
                {"symbol": "AAA", "earnings_release_next_date": tomorrow},
                {"symbol": "BBB", "earnings_release_next_date": later},
                {"symbol": "CCC", "earnings_release_next_date": today_s},
            ]
        }
        with patch.object(self.srv, "fetch_earnings_calendar", return_value=payload):
            rows = self.srv._upcoming_prescan_symbols(lead_days=1)

        syms = {r["symbol"] for r in rows}
        self.assertIn("AAA", syms)
        self.assertIn("CCC", syms)
        self.assertNotIn("BBB", syms)

    def test_no_release_period_max_days_constant_for_badges(self):
        self.assertFalse(hasattr(self.srv, "EARNINGS_PLUS_RELEASE_PERIOD_MAX_DAYS"))
        self.assertEqual(self.srv.EARNINGS_PLUS_SCREENER_SYNC_DAYS, 2)


if __name__ == "__main__":
    unittest.main()
