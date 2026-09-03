"""Earnings chip scope: reported, upcoming, or both."""
from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _rows(*symbols):
    return {"rows": [{"symbol": s} for s in symbols]}


class FilterEarningsScopeTests(unittest.TestCase):
    BODY = {
        "report_window": "month_range",
        "from_year": 2026,
        "from_month": 7,
        "to_year": 2026,
        "to_month": 8,
    }

    def _run(self, body):
        from server import server as srv

        calls = []

        def fake_fetch(**kwargs):
            calls.append(kwargs)
            if kwargs["mode"] == "reported":
                return _rows("TCS", "INFY")
            return _rows("INFY", "MTARTECH")

        with patch.object(srv, "get_filter_cache", return_value=None), patch.object(
            srv, "set_filter_cache"
        ), patch.object(srv, "_sector_allowed_symbols", return_value=None), patch.object(
            srv, "fetch_earnings_calendar", side_effect=fake_fetch
        ):
            result = srv.filter_earnings(body)
        return result, calls

    def test_default_scope_is_reported(self):
        result, calls = self._run(dict(self.BODY))
        self.assertEqual([c["mode"] for c in calls], ["reported"])
        self.assertEqual(result["symbols"], ["TCS", "INFY"])

    def test_upcoming_scope_queries_next_release_only(self):
        result, calls = self._run({**self.BODY, "earnings_scope": "upcoming"})
        self.assertEqual([c["mode"] for c in calls], ["upcoming"])
        self.assertEqual(result["symbols"], ["INFY", "MTARTECH"])

    def test_both_unions_and_dedupes(self):
        result, calls = self._run({**self.BODY, "earnings_scope": "both"})
        self.assertEqual([c["mode"] for c in calls], ["reported", "upcoming"])
        self.assertEqual(result["symbols"], ["TCS", "INFY", "MTARTECH"])
        self.assertEqual(result["count"], 3)

    def test_surprise_bounds_reach_reported_leg_only(self):
        _, calls = self._run(
            {**self.BODY, "earnings_scope": "both", "eps_surprise_min": 5}
        )
        reported = next(c for c in calls if c["mode"] == "reported")
        upcoming = next(c for c in calls if c["mode"] == "upcoming")
        self.assertEqual(reported["eps_surprise_min"], 5.0)
        self.assertNotIn("eps_surprise_min", upcoming)

    def test_window_is_shared_by_both_legs(self):
        _, calls = self._run({**self.BODY, "earnings_scope": "both"})
        for c in calls:
            self.assertEqual(c["report_window"], "month_range")
            self.assertEqual(c["range_from_month"], 7)
            self.assertEqual(c["range_to_month"], 8)

    def test_unknown_scope_falls_back_to_reported(self):
        _, calls = self._run({**self.BODY, "earnings_scope": "sideways"})
        self.assertEqual([c["mode"] for c in calls], ["reported"])

    def test_sector_restriction_applies_to_both_legs(self):
        from server import server as srv

        def fake_fetch(**kwargs):
            return _rows("TCS") if kwargs["mode"] == "reported" else _rows("MTARTECH")

        with patch.object(srv, "get_filter_cache", return_value=None), patch.object(
            srv, "set_filter_cache"
        ), patch.object(srv, "_sector_allowed_symbols", return_value={"TCS"}), patch.object(
            srv, "fetch_earnings_calendar", side_effect=fake_fetch
        ):
            result = srv.filter_earnings({**self.BODY, "earnings_scope": "both"})
        self.assertEqual(result["symbols"], ["TCS"])


class _FakeCol:
    def __init__(self, name):
        self.name = name

    def __ge__(self, other):
        return (self.name, ">=", other)

    def __le__(self, other):
        return (self.name, "<=", other)


class _FakeQuery:
    def __init__(self, sink):
        self.sink = sink

    def select(self, *a, **k):
        return self

    def where(self, *clauses):
        self.sink.extend(clauses)
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def get_scanner_data(self):
        return 0, None


class UpcomingWindowTests(unittest.TestCase):
    """Upcoming mode must accept the same month-range window reported mode takes."""

    def _scan_clauses(self, **kwargs):
        import tradingview_earnings as tve

        clauses: list = []
        fake_mod = types.ModuleType("tradingview_screener")
        fake_mod.Query = object
        fake_mod.col = _FakeCol
        fake_mod.stocks = lambda market: _FakeQuery(clauses)

        with patch.dict(sys.modules, {"tradingview_screener": fake_mod}):
            tve.fetch_earnings_calendar(use_cache=False, **kwargs)
        return clauses

    def test_month_range_bounds_the_next_release_date(self):
        clauses = self._scan_clauses(
            mode="upcoming",
            report_window="month_range",
            range_from_year=2026,
            range_from_month=7,
            range_to_year=2026,
            range_to_month=8,
        )
        bounds = {c[1]: c[2] for c in clauses if c[0] == "earnings_release_next_date"}
        self.assertEqual(len(bounds), 2)
        start = datetime.fromtimestamp(bounds[">="], IST)
        end = datetime.fromtimestamp(bounds["<="], IST)
        self.assertEqual((start.year, start.month, start.day), (2026, 7, 1))
        self.assertEqual((end.year, end.month, end.day), (2026, 8, 31))

    def test_period_enum_still_works_without_a_window(self):
        clauses = self._scan_clauses(mode="upcoming", period="this_month")
        names = {c[0] for c in clauses}
        self.assertIn("earnings_release_next_date", names)

    def test_reported_window_untouched(self):
        clauses = self._scan_clauses(
            mode="reported",
            report_window="month_range",
            range_from_year=2026,
            range_from_month=7,
            range_to_year=2026,
            range_to_month=8,
        )
        names = {c[0] for c in clauses}
        self.assertIn("earnings_release_date", names)
        self.assertNotIn("earnings_release_next_date", names)


if __name__ == "__main__":
    unittest.main()
