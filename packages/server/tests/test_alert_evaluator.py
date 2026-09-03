"""Tests for alert evaluator filter mapping + earnings body formatting."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PACKAGES = Path(__file__).resolve().parents[2]
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from alert_evaluator import (  # noqa: E402
    build_earnings_fetch_kwargs,
    earnings_alert_fetch_kwargs,
    format_earnings_alert_body,
    _parse_mcap_value,
    _evaluate_earnings_page,
    _evaluate_portfolio,
    _evaluate_upcoming_symbol_watches,
    _evaluate_watchlists,
    _is_nse_market_hours,
    _is_session_fresh_quote_ts,
    _screener_day_changes,
)
from user_alerts_store import save_settings, load_alerts, set_upcoming_earnings_watch  # noqa: E402


class AlertEvaluatorHelpersTest(unittest.TestCase):
    def test_parse_mcap_abbrev(self):
        self.assertEqual(_parse_mcap_value("50B"), 50e9)
        self.assertEqual(_parse_mcap_value("500M"), 500e6)
        self.assertEqual(_parse_mcap_value(1.5e12), 1.5e12)
        self.assertIsNone(_parse_mcap_value("nope"))

    def test_build_kwargs_includes_earnings_plus_and_filters(self):
        kwargs = build_earnings_fetch_kwargs({
            "mode": "reported",
            "year": 2026,
            "month": 7,
            "earningsPlusFilter": "only",
            "mcapMin": "50B",
            "epsSurpriseMin": 0,
            "revenueSurpriseMin": 1,
        })
        self.assertIsNotNone(kwargs)
        self.assertEqual(kwargs["mode"], "reported")
        self.assertEqual(kwargs["year"], 2026)
        self.assertEqual(kwargs["month"], 7)
        self.assertEqual(kwargs["earnings_plus"], "only")
        self.assertEqual(kwargs["mcap_min"], 50e9)
        self.assertEqual(kwargs["eps_surprise_min"], 0.0)
        self.assertEqual(kwargs["revenue_surprise_min"], 1.0)

    def test_build_kwargs_accepts_tv_eps_rev_beat(self):
        kwargs = build_earnings_fetch_kwargs({
            "mode": "reported",
            "year": 2026,
            "month": 8,
            "earningsPlusFilter": "tv_eps_rev_beat",
        })
        self.assertIsNotNone(kwargs)
        self.assertEqual(kwargs["earnings_plus"], "tv_eps_rev_beat")

    def test_format_earnings_body_has_required_fields(self):
        body = format_earnings_alert_body({
            "symbol": "RELIANCE",
            "market_cap_basic": 12.34e12,
            "price": 2850.5,
            "change_1d_pct": 1.25,
            "earnings_release_date": "2026-07-20",
            "eps_estimate": 12.5,
            "eps_surprise_pct": 4.2,
            "revenue_estimate": 1.2e12,
            "revenue_surprise_pct": 2.1,
        })
        self.assertIn("Mcap:", body)
        self.assertIn("Price:", body)
        self.assertIn("1D:", body)
        self.assertIn("Report: 2026-07-20", body)
        self.assertIn("EPS est:", body)
        self.assertIn("EPS beat:", body)
        self.assertIn("Rev est:", body)
        self.assertIn("Rev beat:", body)
        self.assertNotIn("matches your Earnings page filters", body)

    def test_portfolio_up_move_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            data.mkdir()
            pf = data / "portfolio.json"
            pf.write_text(
                '{"items":[{"symbol":"AAA","type":"stock"},{"symbol":"BBB","type":"stock"}]}',
                encoding="utf-8",
            )
            save_settings(base, {
                "portfolio_notifications_enabled": True,
                "portfolio_day_move_pct": 3,
                "telegram_enabled": False,
                "browser_enabled": False,
            }, session=None)
            with patch("alert_evaluator._is_nse_market_hours", return_value=True), \
                 patch("alert_evaluator._day_move_changes", return_value={"AAA": 4.5, "BBB": -5.0}):
                n = _evaluate_portfolio(base, None, pf, data / "nse_data.db", {
                    "portfolio_notifications_enabled": True,
                    "portfolio_day_move_pct": 3,
                    "telegram_enabled": False,
                    "browser_enabled": False,
                })
            self.assertEqual(n, 1)
            alerts = load_alerts(base, session=None)["alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["symbol"], "AAA")
            self.assertIn("+4.50%", alerts[0]["title"])

    def test_watchlist_up_move_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            data.mkdir()
            wl = data / "watchlists.json"
            wl.write_text(
                json.dumps([{
                    "name": "Main",
                    "notifications_enabled": True,
                    "items": [
                        {"symbol": "AAA", "type": "stock"},
                        {"symbol": "BBB", "type": "stock"},
                        {"symbol": "ORIENTELEC", "type": "stock"},
                    ],
                }]),
                encoding="utf-8",
            )
            settings = {
                "day_move_pct": 2,
                "telegram_enabled": False,
                "browser_enabled": False,
            }
            save_settings(base, settings, session=None)
            with patch("alert_evaluator._is_nse_market_hours", return_value=True), patch(
                "alert_evaluator._day_move_changes",
                return_value={"AAA": 2.5, "BBB": -5.0, "ORIENTELEC": -2.06},
            ):
                n = _evaluate_watchlists(
                    base, None, wl, data / "nse_data.db", settings,
                    fetch_earnings_fn=lambda **_kwargs: {"rows": []},
                )
            self.assertEqual(n, 1)
            alerts = load_alerts(base, session=None)["alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["symbol"], "AAA")
            self.assertEqual(alerts[0]["kind"], "day_move_up")
            self.assertNotIn("day_move_down", [a["kind"] for a in alerts])

    def test_portfolio_earnings_reported_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            data.mkdir()
            pf = data / "portfolio.json"
            pf.write_text(
                '{"items":[{"symbol":"NESTLEIND","type":"stock"},{"symbol":"TCS","type":"stock"}]}',
                encoding="utf-8",
            )
            settings = {
                "portfolio_notifications_enabled": True,
                "portfolio_day_move_pct": 99,
                "telegram_enabled": False,
                "browser_enabled": False,
            }
            save_settings(base, settings, session=None)
            today = __import__("datetime").datetime.now(
                __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
            ).date().isoformat()

            def fetch_earnings(**kwargs):
                self.assertEqual(kwargs.get("mode"), "reported")
                self.assertEqual(set(kwargs.get("symbols") or []), {"NESTLEIND", "TCS"})
                return {
                    "rows": [
                        {
                            "symbol": "NESTLEIND",
                            "earnings_release_date": today,
                            "eps_surprise_pct": 3.1,
                            "revenue_surprise_pct": 1.2,
                            "price": 2500,
                        },
                        {
                            "symbol": "INFY",
                            "earnings_release_date": today,
                            "eps_surprise_pct": 5.0,
                        },
                    ]
                }

            with patch("alert_evaluator._day_move_changes", return_value={}):
                n = _evaluate_portfolio(
                    base, None, pf, data / "nse_data.db", settings,
                    fetch_earnings_fn=fetch_earnings,
                )
            self.assertEqual(n, 1)
            alerts = load_alerts(base, session=None)["alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["kind"], "portfolio_earnings_reported")
            self.assertEqual(alerts[0]["symbol"], "NESTLEIND")
            self.assertTrue(str(alerts[0]["title"]).startswith("Portfolio Update"))

    def test_earnings_alert_kwargs_locks_to_current_month_reported(self):
        today = __import__("datetime").datetime.now(
            __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
        ).date()
        # UI on upcoming + a past month must still fetch reported / current month.
        kwargs = earnings_alert_fetch_kwargs({
            "mode": "upcoming",
            "period": "next_month",
            "year": 2024,
            "month": 1,
            "epsSurpriseMin": 2,
            "mcapMin": "50B",
            "earningsPlusFilter": "only",
        })
        self.assertIsNotNone(kwargs)
        self.assertEqual(kwargs["mode"], "reported")
        self.assertEqual(kwargs["year"], today.year)
        self.assertEqual(kwargs["month"], today.month)
        self.assertEqual(kwargs["eps_surprise_min"], 2.0)
        self.assertEqual(kwargs["mcap_min"], 50e9)
        self.assertEqual(kwargs["earnings_plus"], "only")

    def test_portfolio_upcoming_earnings_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            data.mkdir()
            pf = data / "portfolio.json"
            pf.write_text(
                '{"items":[{"symbol":"RELIANCE","type":"stock"},{"symbol":"INFY","type":"stock"}]}',
                encoding="utf-8",
            )
            settings = {
                "portfolio_notifications_enabled": True,
                "portfolio_day_move_pct": 99,
                "telegram_enabled": False,
                "browser_enabled": False,
            }
            save_settings(base, settings, session=None)

            def fetch_earnings(**kwargs):
                if kwargs.get("mode") == "upcoming":
                    self.fail("upcoming earnings fetch must not run")
                return {"rows": []}

            with patch("alert_evaluator._day_move_changes", return_value={}):
                n = _evaluate_portfolio(
                    base, None, pf, data / "nse_data.db", settings,
                    fetch_earnings_fn=fetch_earnings,
                )
            self.assertEqual(n, 0)
            alerts = load_alerts(base, session=None)["alerts"]
            self.assertEqual(alerts, [])

    def test_earnings_page_ignores_ui_past_month_and_upcoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            data.mkdir()
            today = __import__("datetime").datetime.now(
                __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
            ).date()
            this_month = today.replace(day=min(15, today.day)).isoformat()
            # Force a prior-month date for the "should not alert" row
            if today.month == 1:
                past = today.replace(year=today.year - 1, month=12, day=15).isoformat()
            else:
                past = today.replace(month=today.month - 1, day=15).isoformat()

            settings = {
                "earnings_notifications_enabled": True,
                "telegram_enabled": False,
                "browser_enabled": False,
                "earnings_filter_snapshot": {
                    "mode": "upcoming",
                    "year": 2024,
                    "month": 3,
                    "period": "this_month",
                    "epsSurpriseMin": 0,
                },
            }
            save_settings(base, settings, session=None)
            seen = {}

            def fetch_earnings(**kwargs):
                seen.update(kwargs)
                self.assertEqual(kwargs.get("mode"), "reported")
                self.assertEqual(kwargs.get("year"), today.year)
                self.assertEqual(kwargs.get("month"), today.month)
                return {
                    "rows": [
                        {
                            "symbol": "GOOD",
                            "earnings_release_date": this_month,
                            "eps_surprise_pct": 5,
                            "revenue_surprise_pct": 2,
                        },
                        {
                            "symbol": "OLD",
                            "earnings_release_date": past,
                            "eps_surprise_pct": 9,
                            "revenue_surprise_pct": 9,
                        },
                    ]
                }

            n = _evaluate_earnings_page(base, None, settings, fetch_earnings)
            self.assertEqual(n, 1)
            alerts = load_alerts(base, session=None)["alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["symbol"], "GOOD")
            self.assertEqual(alerts[0]["kind"], "earnings_page_reported")
            self.assertNotIn("upcoming", [a["kind"] for a in alerts])

    def test_upcoming_symbol_watch_alerts_t0_and_t1_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            today = __import__("datetime").datetime.now(
                __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
            ).date()
            tomorrow = (today + __import__("datetime").timedelta(days=1)).isoformat()
            far = (today + __import__("datetime").timedelta(days=10)).isoformat()
            set_upcoming_earnings_watch(
                base, symbol="NEAR", release_date=tomorrow, enabled=True, session=None,
            )
            set_upcoming_earnings_watch(
                base, symbol="FAR", release_date=far, enabled=True, session=None,
            )
            settings = {
                "telegram_enabled": False,
                "browser_enabled": False,
                "upcoming_earnings_watches": [
                    {"symbol": "NEAR", "release_date": tomorrow, "enabled": True},
                    {"symbol": "FAR", "release_date": far, "enabled": True},
                ],
            }

            def fetch_earnings(**kwargs):
                self.assertEqual(kwargs.get("mode"), "upcoming")
                return {
                    "rows": [
                        {"symbol": "NEAR", "earnings_release_next_date": tomorrow, "price": 100},
                        {"symbol": "FAR", "earnings_release_next_date": far, "price": 200},
                    ]
                }

            n = _evaluate_upcoming_symbol_watches(base, None, settings, fetch_earnings)
            self.assertEqual(n, 1)
            alerts = load_alerts(base, session=None)["alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["symbol"], "NEAR")
            self.assertEqual(alerts[0]["kind"], "earnings_symbol_upcoming")

    def test_no_day_move_alerts_on_non_trading_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            data.mkdir()
            wl = data / "watchlists.json"
            wl.write_text(
                json.dumps([{
                    "name": "Main",
                    "notifications_enabled": True,
                    "items": [{"symbol": "AAA", "type": "stock"}],
                }]),
                encoding="utf-8",
            )
            pf = data / "portfolio.json"
            pf.write_text(
                '{"items":[{"symbol":"BBB","type":"stock"}]}',
                encoding="utf-8",
            )
            settings = {
                "day_move_pct": 1,
                "portfolio_notifications_enabled": True,
                "portfolio_day_move_pct": 1,
                "telegram_enabled": False,
                "browser_enabled": False,
            }
            save_settings(base, settings, session=None)
            with patch("alert_evaluator._is_nse_market_hours", return_value=False), \
                 patch(
                     "alert_evaluator._day_move_changes",
                     return_value={"AAA": 5.0, "BBB": 6.0},
                 ) as mock_chg:
                n_wl = _evaluate_watchlists(
                    base, None, wl, data / "nse_data.db", settings,
                    fetch_earnings_fn=lambda **_kwargs: {"rows": []},
                )
                n_pf = _evaluate_portfolio(
                    base, None, pf, data / "nse_data.db", settings,
                )
            self.assertEqual(n_wl, 0)
            self.assertEqual(n_pf, 0)
            mock_chg.assert_not_called()
            self.assertEqual(load_alerts(base, session=None)["alerts"], [])

    def test_no_day_move_alerts_at_midnight_even_on_trading_day(self):
        """Regression: IST day rollover must not re-fire yesterday's % moves."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        # Monday midnight IST — trading day, but not market hours.
        midnight = datetime(2026, 7, 27, 0, 5, tzinfo=ist)
        with patch("alert_evaluator._is_nse_trading_day", return_value=True):
            self.assertFalse(_is_nse_market_hours(midnight))
        # During cash session
        lunch = datetime(2026, 7, 27, 12, 0, tzinfo=ist)
        with patch("alert_evaluator._is_nse_trading_day", return_value=True):
            self.assertTrue(_is_nse_market_hours(lunch))
        # After close
        evening = datetime(2026, 7, 27, 16, 0, tzinfo=ist)
        with patch("alert_evaluator._is_nse_trading_day", return_value=True):
            self.assertFalse(_is_nse_market_hours(evening))

    def test_session_fresh_quote_ts_rejects_prior_session_and_preopen(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        now = datetime(2026, 7, 27, 13, 0, tzinfo=ist)
        self.assertFalse(_is_session_fresh_quote_ts("2026-07-26 16:14:15", now=now))
        self.assertFalse(_is_session_fresh_quote_ts("2026-07-27 00:05:00", now=now))
        self.assertFalse(_is_session_fresh_quote_ts("2026-07-27 09:14:00", now=now))
        self.assertTrue(_is_session_fresh_quote_ts("2026-07-27 09:15:00", now=now))
        self.assertTrue(_is_session_fresh_quote_ts("2026-07-27 13:10:00", now=now))

    def test_screener_day_changes_skips_stale_price_updated_at(self):
        import sqlite3
        from datetime import datetime
        from zoneinfo import ZoneInfo

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nse_data.db"
            conn = sqlite3.connect(str(db))
            conn.execute(
                "CREATE TABLE screener (symbol TEXT PRIMARY KEY, change_percent REAL, price_updated_at TEXT)"
            )
            conn.execute(
                "INSERT INTO screener VALUES ('FRESH', 3.5, '2026-07-27 10:30:00')"
            )
            conn.execute(
                "INSERT INTO screener VALUES ('STALE', 5.0, '2026-07-26 16:14:15')"
            )
            conn.execute(
                "INSERT INTO screener VALUES ('PREOPEN', 4.0, '2026-07-27 00:01:00')"
            )
            conn.commit()
            conn.close()

            fixed_now = datetime(2026, 7, 27, 13, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
            real_fresh = _is_session_fresh_quote_ts

            def fresh_for_fixture(stamp, now=None):
                return real_fresh(stamp, now=fixed_now)

            with patch("alert_evaluator._is_session_fresh_quote_ts", side_effect=fresh_for_fixture):
                out = _screener_day_changes(db, {"FRESH", "STALE", "PREOPEN"})
            self.assertEqual(out, {"FRESH": 3.5})


if __name__ == "__main__":
    unittest.main()
