"""Tests for daily OHLCV skip-if-current vs latest NSE session date."""
from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scrape_daily as sd  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


class TestDailySessionTargetSkip(unittest.TestCase):
    def test_weekend_targets_friday(self):
        # Sunday 12 Jul 2026 → prior session Friday 10 Jul 2026
        now = datetime(2026, 7, 12, 18, 0, tzinfo=IST)
        target = sd.latest_target_ohlcv_session_date(now, set(), set())
        self.assertEqual(target, date(2026, 7, 10))

    def test_saturday_targets_friday(self):
        now = datetime(2026, 7, 11, 10, 0, tzinfo=IST)
        target = sd.latest_target_ohlcv_session_date(now, set(), set())
        self.assertEqual(target, date(2026, 7, 10))

    def test_holiday_monday_targets_friday(self):
        now = datetime(2026, 7, 13, 12, 0, tzinfo=IST)  # Monday
        holidays = {"2026-07-13"}
        target = sd.latest_target_ohlcv_session_date(now, holidays, set())
        self.assertEqual(target, date(2026, 7, 10))

    def test_session_day_targets_today(self):
        now = datetime(2026, 7, 10, 11, 0, tzinfo=IST)  # Friday mid-session
        target = sd.latest_target_ohlcv_session_date(now, set(), set())
        self.assertEqual(target, date(2026, 7, 10))

    def test_pre_open_targets_prior_session(self):
        # Monday 07:40 IST — cash not open; Upstox has no today candle yet
        now = datetime(2026, 7, 13, 7, 40, tzinfo=IST)
        target = sd.latest_target_ohlcv_session_date(now, set(), set())
        self.assertEqual(target, date(2026, 7, 10))  # prior Friday
        self.assertFalse(sd.session_refresh_enabled(True, now))

    def test_just_after_open_targets_today(self):
        now = datetime(2026, 7, 13, 9, 15, tzinfo=IST)
        target = sd.latest_target_ohlcv_session_date(now, set(), set())
        self.assertEqual(target, date(2026, 7, 13))
        self.assertTrue(sd.session_refresh_enabled(True, now))

    def test_pre_open_skips_when_prior_session_current(self):
        friday = date(2026, 7, 10)
        monday = date(2026, 7, 13)
        self.assertFalse(
            sd.symbol_needs_daily_ohlcv_update(
                friday,
                target_session=friday,
                today_ist=monday,
                session_day=True,
                refresh_today=False,
            )
        )

    def test_sunday_skips_when_friday_current(self):
        friday = date(2026, 7, 10)
        sunday = date(2026, 7, 12)
        self.assertFalse(
            sd.symbol_needs_daily_ohlcv_update(
                friday,
                target_session=friday,
                today_ist=sunday,
                session_day=False,
                refresh_today=False,
            )
        )

    def test_sunday_fetches_when_behind_friday(self):
        thursday = date(2026, 7, 9)
        friday = date(2026, 7, 10)
        sunday = date(2026, 7, 12)
        self.assertTrue(
            sd.symbol_needs_daily_ohlcv_update(
                thursday,
                target_session=friday,
                today_ist=sunday,
                session_day=False,
                refresh_today=False,
            )
        )

    def test_mid_session_refreshes_today_bar(self):
        today = date(2026, 7, 10)
        self.assertTrue(
            sd.symbol_needs_daily_ohlcv_update(
                today,
                target_session=today,
                today_ist=today,
                session_day=True,
                refresh_today=True,
            )
        )

    def test_post_close_skips_when_today_present(self):
        today = date(2026, 7, 10)
        self.assertFalse(
            sd.symbol_needs_daily_ohlcv_update(
                today,
                target_session=today,
                today_ist=today,
                session_day=True,
                refresh_today=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
