"""Unit tests for TV-aligned earnings date windows (CTD / weekends / weeks)."""
from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from server import tradingview_earnings as te

IST = ZoneInfo("Asia/Kolkata")


def _iso_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, IST).date().isoformat()


class NormalizeAliasesTests(unittest.TestCase):
    def test_legacy_aliases(self):
        self.assertEqual(te.normalize_earnings_window_key("today"), "current_trading_day")
        self.assertEqual(te.normalize_earnings_window_key("yesterday"), "previous_day")
        self.assertEqual(te.normalize_earnings_window_key("today_yesterday"), "current_trading_day")
        self.assertEqual(te.normalize_earnings_window_key("previous_week"), "prev_week")
        self.assertEqual(te.normalize_earnings_window_key("current_trading_day"), "current_trading_day")


class CurrentTradingDayTests(unittest.TestCase):
    def test_tuesday_session_is_single_day(self):
        # 2026-08-04 is a Tuesday (session day).
        fixed = datetime(2026, 8, 4, 15, 30, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt, patch.object(te, "_nse_session_day", side_effect=lambda d: d.weekday() < 5):
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            start, end = te._current_trading_day_range_ts()
            _, key = te.resolve_reported_date_range(report_window="current_trading_day")
            legacy, legacy_key = te.resolve_reported_date_range(report_window="today")
        self.assertEqual(_iso_date(start), "2026-08-04")
        self.assertEqual(_iso_date(end), "2026-08-04")
        self.assertEqual(key, "rw:ctd")
        self.assertEqual(legacy, (start, end))
        self.assertEqual(legacy_key, "rw:ctd")

    def test_saturday_spans_friday_through_saturday(self):
        # Sat 2026-08-08 → CTD = Fri 08-07 → Sat 08-08
        fixed = datetime(2026, 8, 8, 11, 0, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt, patch.object(te, "_nse_session_day", side_effect=lambda d: d.weekday() < 5):
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            start, end = te._current_trading_day_range_ts()
            prev_start, prev_end = te._previous_day_range_ts()
            next_start, next_end = te._next_day_range_ts()
        self.assertEqual(_iso_date(start), "2026-08-07")
        self.assertEqual(_iso_date(end), "2026-08-08")
        # Previous day = 1 calendar day before Friday anchor → Thursday
        self.assertEqual(_iso_date(prev_start), "2026-08-06")
        self.assertEqual(_iso_date(prev_end), "2026-08-06")
        # Next day = 1 calendar day after Friday anchor → Saturday
        self.assertEqual(_iso_date(next_start), "2026-08-08")
        self.assertEqual(_iso_date(next_end), "2026-08-08")

    def test_sunday_spans_friday_through_sunday(self):
        fixed = datetime(2026, 8, 9, 10, 0, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt, patch.object(te, "_nse_session_day", side_effect=lambda d: d.weekday() < 5):
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            start, end = te._current_trading_day_range_ts()
            prev_start, _ = te._previous_day_range_ts()
            next_start, _ = te._next_day_range_ts()
        self.assertEqual(_iso_date(start), "2026-08-07")
        self.assertEqual(_iso_date(end), "2026-08-09")
        self.assertEqual(_iso_date(prev_start), "2026-08-06")
        self.assertEqual(_iso_date(next_start), "2026-08-08")


class FiveDayAndWeekTests(unittest.TestCase):
    def test_previous_and_next_5_days_from_anchor(self):
        # Tuesday session: anchor = Aug 4 → prev 5 = Jul 30–Aug 3; next 5 = Aug 5–9
        fixed = datetime(2026, 8, 4, 12, 0, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt, patch.object(te, "_nse_session_day", side_effect=lambda d: d.weekday() < 5):
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            p5 = te._previous_5_days_range_ts()
            n5 = te._next_5_days_range_ts()
            _, p5_key = te.resolve_reported_date_range(report_window="previous_5_days")
            _, n5_key = te.resolve_reported_date_range(report_window="next_5_days")
        self.assertEqual(_iso_date(p5[0]), "2026-07-30")
        self.assertEqual(_iso_date(p5[1]), "2026-08-03")
        self.assertEqual(_iso_date(n5[0]), "2026-08-05")
        self.assertEqual(_iso_date(n5[1]), "2026-08-09")
        self.assertEqual(p5_key, "rw:prev_5")
        self.assertEqual(n5_key, "rw:next_5")

    def test_saturday_previous_5_days_from_friday_anchor(self):
        fixed = datetime(2026, 8, 8, 12, 0, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt, patch.object(te, "_nse_session_day", side_effect=lambda d: d.weekday() < 5):
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            p5 = te._previous_5_days_range_ts()
        # Anchor Fri Aug 7 → Jul 2–Aug 6
        self.assertEqual(_iso_date(p5[0]), "2026-08-02")
        self.assertEqual(_iso_date(p5[1]), "2026-08-06")

    def test_next_week_is_following_mon_sun(self):
        # Tue Aug 4 2026 → this week Mon Aug 3–Sun Aug 9; next week Aug 10–16
        fixed = datetime(2026, 8, 4, 9, 0, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            this_w = te._ist_week_range_ts(0)
            next_w = te._ist_week_range_ts(1)
            _, key = te.resolve_reported_date_range(report_window="next_week")
            period_range = te._period_date_range_ts("next_week")
        self.assertEqual(_iso_date(this_w[0]), "2026-08-03")
        self.assertEqual(_iso_date(this_w[1]), "2026-08-09")
        self.assertEqual(_iso_date(next_w[0]), "2026-08-10")
        self.assertEqual(_iso_date(next_w[1]), "2026-08-16")
        self.assertEqual(key, "w:1")
        self.assertEqual(period_range, next_w)

    def test_yesterday_alias_uses_previous_day_not_calendar_yesterday_on_sunday(self):
        # Sunday: calendar yesterday = Sat; TV previous_day = Thu (day before Fri anchor)
        fixed = datetime(2026, 8, 9, 10, 0, tzinfo=IST)
        with patch.object(te, "datetime") as mock_dt, patch.object(te, "_nse_session_day", side_effect=lambda d: d.weekday() < 5):
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            rng, key = te.resolve_reported_date_range(report_window="yesterday")
        self.assertEqual(key, "rw:prev_day")
        self.assertEqual(_iso_date(rng[0]), "2026-08-06")


class AnchorHelperTests(unittest.TestCase):
    def test_anchor_on_holiday_falls_back(self):
        # Force today non-session even if weekday, ensure walk-back works.
        today = date(2026, 8, 5)  # Wednesday
        with patch.object(te, "_nse_session_day", side_effect=lambda d: d == date(2026, 8, 4)):
            self.assertEqual(te._current_trading_day_anchor(today), date(2026, 8, 4))


if __name__ == "__main__":
    unittest.main()
