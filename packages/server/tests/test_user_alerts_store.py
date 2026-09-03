"""Tests for user alerts store + telegram helper status."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

PACKAGES = Path(__file__).resolve().parents[2]
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from user_alerts_store import (  # noqa: E402
    append_alert,
    dedup_key,
    delete_alerts,
    earnings_dedup_day,
    has_release_dedup,
    load_alerts,
    load_settings,
    mark_alerts,
    normalize_upcoming_watches,
    prune_expired_upcoming_watches,
    save_settings,
    set_upcoming_earnings_watch,
    unread_count,
)
import telegram_notify  # noqa: E402


class UserAlertsStoreTest(unittest.TestCase):
    def test_append_dedup_and_unread(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a1, ok1 = append_alert(base, {
                "symbol": "RELIANCE",
                "kind": "day_move_up",
                "source": "watchlist",
                "title": "RELIANCE +3%",
                "body": "test",
                "dedup_key": dedup_key("RELIANCE", "day_move_up", "2026-07-24"),
            }, session=None)
            self.assertTrue(ok1)
            self.assertIsNotNone(a1)
            _, ok2 = append_alert(base, {
                "symbol": "RELIANCE",
                "kind": "day_move_up",
                "source": "watchlist",
                "title": "RELIANCE +4%",
                "body": "test2",
                "dedup_key": dedup_key("RELIANCE", "day_move_up", "2026-07-24"),
            }, session=None)
            self.assertFalse(ok2)
            doc = load_alerts(base, session=None)
            self.assertEqual(len(doc["alerts"]), 1)
            self.assertEqual(unread_count(doc), 1)
            mark_alerts(base, mark_all_read=True, session=None)
            doc2 = load_alerts(base, session=None)
            self.assertEqual(unread_count(doc2), 0)

    def test_earnings_release_dedup_not_daily(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, ok1 = append_alert(base, {
                "symbol": "HINDZINC",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "HINDZINC earnings",
                "body": "first",
                "dedup_key": dedup_key("HINDZINC", "earnings_page_reported", "2026-07-24"),
                "meta": {"date": "2026-07-18"},
            }, session=None)
            self.assertTrue(ok1)
            # Same release, new calendar-day style key — must not insert again.
            _, ok2 = append_alert(base, {
                "symbol": "HINDZINC",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "HINDZINC earnings",
                "body": "again",
                "dedup_key": dedup_key("HINDZINC", "earnings_page_reported", "2026-07-25"),
                "meta": {"date": "2026-07-18"},
            }, session=None)
            self.assertFalse(ok2)
            # Same release with stable release-date key — still blocked.
            _, ok3 = append_alert(base, {
                "symbol": "HINDZINC",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "HINDZINC earnings",
                "body": "stable",
                "dedup_key": dedup_key("HINDZINC", "earnings_page_reported", "2026-07-18"),
                "meta": {"date": "2026-07-18"},
            }, session=None)
            self.assertFalse(ok3)
            # Different release date → new alert allowed.
            _, ok4 = append_alert(base, {
                "symbol": "HINDZINC",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "HINDZINC earnings",
                "body": "next quarter",
                "dedup_key": dedup_key("HINDZINC", "earnings_page_reported", "2026-10-20"),
                "meta": {"date": "2026-10-20"},
            }, session=None)
            self.assertTrue(ok4)
            self.assertEqual(len(load_alerts(base, session=None)["alerts"]), 2)
            self.assertTrue(has_release_dedup(
                load_alerts(base, session=None)["alerts"],
                symbol="HINDZINC",
                kind="earnings_page_reported",
                release_date="2026-07-18",
                eps_ready=False,
                revenue_ready=False,
            ))

    def test_earnings_realert_when_missing_surprise_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rel = "2026-07-18"
            # Nestle: revenue in, EPS still missing.
            _, ok1 = append_alert(base, {
                "symbol": "NESTLEIND",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "NESTLEIND earnings",
                "body": "rev only",
                "dedup_key": dedup_key(
                    "NESTLEIND",
                    "earnings_page_reported",
                    earnings_dedup_day(rel, False, True),
                ),
                "meta": {
                    "date": rel,
                    "eps_surprise_pct": None,
                    "revenue_surprise_pct": 2.5,
                    "eps_ready": False,
                    "revenue_ready": True,
                },
            }, session=None)
            self.assertTrue(ok1)
            # Same incomplete snapshot next day — no spam.
            _, ok2 = append_alert(base, {
                "symbol": "NESTLEIND",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "NESTLEIND earnings",
                "body": "rev only again",
                "dedup_key": dedup_key(
                    "NESTLEIND",
                    "earnings_page_reported",
                    earnings_dedup_day(rel, False, True),
                ),
                "meta": {
                    "date": rel,
                    "eps_surprise_pct": None,
                    "revenue_surprise_pct": 2.5,
                    "eps_ready": False,
                    "revenue_ready": True,
                },
            }, session=None)
            self.assertFalse(ok2)
            # EPS fills in → allow one update alert.
            _, ok3 = append_alert(base, {
                "symbol": "NESTLEIND",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "NESTLEIND earnings",
                "body": "eps filled",
                "dedup_key": dedup_key(
                    "NESTLEIND",
                    "earnings_page_reported",
                    earnings_dedup_day(rel, True, True),
                ),
                "meta": {
                    "date": rel,
                    "eps_surprise_pct": 1.2,
                    "revenue_surprise_pct": 2.5,
                    "eps_ready": True,
                    "revenue_ready": True,
                },
            }, session=None)
            self.assertTrue(ok3)
            # Full data again → blocked.
            _, ok4 = append_alert(base, {
                "symbol": "NESTLEIND",
                "kind": "earnings_page_reported",
                "source": "earnings",
                "title": "NESTLEIND earnings",
                "body": "full again",
                "dedup_key": dedup_key(
                    "NESTLEIND",
                    "earnings_page_reported",
                    earnings_dedup_day(rel, True, True),
                ),
                "meta": {
                    "date": rel,
                    "eps_surprise_pct": 1.3,
                    "revenue_surprise_pct": 2.6,
                    "eps_ready": True,
                    "revenue_ready": True,
                },
            }, session=None)
            self.assertFalse(ok4)
            self.assertEqual(len(load_alerts(base, session=None)["alerts"]), 2)

    def test_delete_one_and_clear_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a1, _ = append_alert(base, {
                "symbol": "TCS",
                "kind": "earnings_today",
                "source": "watchlist",
                "title": "TCS earnings",
                "body": "today",
                "dedup_key": dedup_key("TCS", "earnings_today", "2026-07-24"),
            }, session=None)
            a2, _ = append_alert(base, {
                "symbol": "INFY",
                "kind": "day_move_up",
                "source": "watchlist",
                "title": "INFY +3%",
                "body": "move",
                "dedup_key": dedup_key("INFY", "day_move_up", "2026-07-24"),
            }, session=None)
            self.assertEqual(len(load_alerts(base, session=None)["alerts"]), 2)
            delete_alerts(base, ids=[a1["id"]], session=None)
            left = load_alerts(base, session=None)["alerts"]
            self.assertEqual(len(left), 1)
            self.assertEqual(left[0]["id"], a2["id"])
            delete_alerts(base, clear_all=True, session=None)
            self.assertEqual(load_alerts(base, session=None)["alerts"], [])

    def test_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            saved = save_settings(base, {
                "telegram_enabled": False,
                "browser_enabled": True,
                "earnings_notifications_enabled": True,
                "day_move_pct": 5,
                "earnings_filter_snapshot": {"mode": "reported", "year": 2026, "month": 7},
            }, session=None)
            self.assertFalse(saved["telegram_enabled"])
            self.assertEqual(saved["day_move_pct"], 5.0)
            loaded = load_settings(base, session=None)
            self.assertTrue(loaded["earnings_notifications_enabled"])
            self.assertEqual(loaded["earnings_filter_snapshot"]["month"], 7)
            self.assertEqual(loaded.get("upcoming_earnings_watches"), [])

    def test_upcoming_earnings_watch_toggle_and_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            saved = set_upcoming_earnings_watch(
                base, symbol="reliance", release_date="2026-08-15", enabled=True, session=None,
            )
            self.assertEqual(len(saved["upcoming_earnings_watches"]), 1)
            self.assertEqual(saved["upcoming_earnings_watches"][0]["symbol"], "RELIANCE")
            # One per symbol — update date
            saved = set_upcoming_earnings_watch(
                base, symbol="RELIANCE", release_date="2026-09-01", enabled=True, session=None,
            )
            self.assertEqual(len(saved["upcoming_earnings_watches"]), 1)
            self.assertEqual(saved["upcoming_earnings_watches"][0]["release_date"], "2026-09-01")
            saved = set_upcoming_earnings_watch(
                base, symbol="RELIANCE", release_date="2026-09-01", enabled=False, session=None,
            )
            self.assertEqual(saved["upcoming_earnings_watches"], [])

            set_upcoming_earnings_watch(
                base, symbol="TCS", release_date="2026-01-01", enabled=True, session=None,
            )
            set_upcoming_earnings_watch(
                base, symbol="INFY", release_date="2026-12-01", enabled=True, session=None,
            )
            pruned = prune_expired_upcoming_watches(base, session=None, today="2026-06-01")
            syms = [w["symbol"] for w in pruned["upcoming_earnings_watches"]]
            self.assertEqual(syms, ["INFY"])

    def test_normalize_upcoming_watches_rejects_bad(self):
        self.assertEqual(normalize_upcoming_watches([None, {"symbol": "X"}, {"symbol": "A", "release_date": "bad"}]), [])
        ok = normalize_upcoming_watches([{"symbol": "a", "release_date": "2026-07-01", "enabled": 1}])
        self.assertEqual(ok[0]["symbol"], "A")
        self.assertTrue(ok[0]["enabled"])


class TelegramNotifyTest(unittest.TestCase):
    def test_send_without_env(self):
        with patch.dict("os.environ", {}, clear=True):
            telegram_notify._DOTENV_LOADED = True
            result = telegram_notify.send_message("hi")
            self.assertFalse(result["ok"])
            self.assertIn("not configured", result["error"])


if __name__ == "__main__":
    unittest.main()
