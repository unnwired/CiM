from __future__ import annotations

import time
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.upstox_stream_proto import _feed_response_cls, decode_feed_response
from server.upstox_stream_worker import (
    MAX_MOVERS_LTPC,
    MAX_PORTFOLIO_LTPC,
    UpstoxStreamManager,
    _session_ohlc_from_minutes,
    combined_status,
    focus_manager,
    movers_manager,
)


class UpstoxStreamWorkerTests(unittest.TestCase):
    def test_dual_managers_roles(self):
        # Focus manager allows per-context mode (full for chart focus, ltpc for lists).
        self.assertIsNone(focus_manager.force_mode)
        self.assertEqual(movers_manager.force_mode, "ltpc")
        self.assertGreaterEqual(MAX_MOVERS_LTPC, 2000)
        st = combined_status()
        self.assertIn("focus", st)
        self.assertIn("movers", st)
        self.assertEqual(st.get("stream_mode"), "ltpc")

    def test_subscribe_caps_portfolio_and_resolves_symbols(self):
        mgr = UpstoxStreamManager()
        symbols = [f"SYM{i}" for i in range(MAX_PORTFOLIO_LTPC + 5)]
        resolved = {sym: f"NSE_EQ|{sym}" for sym in symbols[:MAX_PORTFOLIO_LTPC]}
        with patch("server.upstox_stream_worker.upstox_instruments.instrument_map", return_value={}), patch(
            "server.upstox_stream_worker.upstox_instruments.resolve_instrument_keys",
            return_value=(resolved, []),
        ), patch.object(mgr, "_ensure_thread"), patch.object(mgr, "_backfill_intraday"), patch.object(
            mgr, "_seed_session_quote"
        ):
            status = mgr.subscribe("portfolio", symbols, mode="ltpc")
        self.assertEqual(len(status["contexts"]["portfolio"]), MAX_PORTFOLIO_LTPC)
        self.assertTrue(all(mode == "ltpc" for mode in status["contexts"]["portfolio"].values()))

    def test_movers_manager_forces_ltpc_and_allows_large_universe(self):
        mgr = UpstoxStreamManager(name="movers", max_symbols=MAX_MOVERS_LTPC, force_mode="ltpc")
        symbols = [f"SYM{i}" for i in range(2500)]
        resolved = {sym: f"NSE_EQ|{sym}" for sym in symbols}
        with patch("server.upstox_stream_worker.upstox_instruments.instrument_map", return_value={}), patch(
            "server.upstox_stream_worker.upstox_instruments.resolve_instrument_keys",
            return_value=(resolved, []),
        ), patch.object(mgr, "_ensure_thread"), patch.object(mgr, "_backfill_intraday"), patch.object(
            mgr, "_seed_session_quote"
        ):
            status = mgr.subscribe("movers", symbols, mode="full")  # force_mode overrides to ltpc
        self.assertEqual(len(status["contexts"]["movers"]), 2500)
        self.assertTrue(all(mode == "ltpc" for mode in status["contexts"]["movers"].values()))
        self.assertEqual(status["ltpc_count"], 2500)
        self.assertEqual(status["full_count"], 0)

    def test_full_subscription_triggers_backfill(self):
        mgr = UpstoxStreamManager()
        with patch("server.upstox_stream_worker.upstox_instruments.instrument_map", return_value={}), patch(
            "server.upstox_stream_worker.upstox_instruments.resolve_instrument_keys",
            return_value=({"RELIANCE": "NSE_EQ|INE002A01018"}, []),
        ), patch.object(mgr, "_ensure_thread"), patch.object(mgr, "_backfill_intraday") as backfill:
            status = mgr.subscribe("chart", ["RELIANCE"], mode="full")
            # Backfill runs on a daemon thread so subscribe stays non-blocking.
            for _ in range(50):
                if backfill.called:
                    break
                time.sleep(0.02)
        self.assertEqual(status["full_count"], 1)
        backfill.assert_called_once_with("RELIANCE", "NSE_EQ|INE002A01018")

    def test_decode_feed_response_ltpc(self):
        cls = _feed_response_cls()
        msg = cls()
        msg.type = 1
        msg.currentTs = 1740729566039
        msg.feeds["NSE_EQ|INE002A01018"].ltpc.ltp = 2500.5
        msg.feeds["NSE_EQ|INE002A01018"].ltpc.cp = 2480.0
        decoded = decode_feed_response(msg.SerializeToString())
        feed = decoded["feeds"]["NSE_EQ|INE002A01018"]
        self.assertEqual(feed["ltpc"]["ltp"], 2500.5)
        self.assertEqual(feed["ltpc"]["cp"], 2480.0)

    def test_apply_feed_day_ohlc_and_running_high_low(self):
        mgr = UpstoxStreamManager(name="test-ohlc")
        feed = {
            "fullFeed": {
                "marketFF": {
                    "ltpc": {"ltp": 101.0, "cp": 100.0},
                    "marketOHLC": {
                        "ohlc": [
                            {"interval": "I1", "ts": 1740729566000, "open": 100.5, "high": 101.2, "low": 100.4, "close": 101.0, "vol": 10},
                            {"interval": "1d", "open": 99.5, "high": 102.0, "low": 99.0, "close": 101.0, "vol": 1000},
                        ]
                    },
                }
            }
        }
        mgr._apply_feed("RELIANCE", feed, 1740729566000)
        q1 = mgr._quotes["RELIANCE"]
        self.assertEqual(q1["price"], 101.0)
        self.assertEqual(q1["open"], 99.5)
        self.assertEqual(q1["high"], 102.0)
        self.assertEqual(q1["low"], 99.0)

        # LTP-only tick expands session high/low
        mgr._apply_feed(
            "RELIANCE",
            {"ltpc": {"ltp": 103.5, "cp": 100.0}},
            1740729626000,
        )
        q2 = mgr._quotes["RELIANCE"]
        self.assertEqual(q2["price"], 103.5)
        self.assertEqual(q2["open"], 99.5)
        self.assertEqual(q2["high"], 103.5)
        self.assertEqual(q2["low"], 99.0)

        mgr._apply_feed(
            "RELIANCE",
            {"ltpc": {"ltp": 98.5, "cp": 100.0}},
            1740729686000,
        )
        q3 = mgr._quotes["RELIANCE"]
        self.assertEqual(q3["low"], 98.5)
        self.assertEqual(q3["high"], 103.5)

    def test_session_ohlc_from_minutes_aggregates_full_body(self):
        candles = {
            "2026-07-13T09:15:00+05:30": {
                "time": "2026-07-13T09:15:00+05:30",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 10,
            },
            "2026-07-13T10:00:00+05:30": {
                "time": "2026-07-13T10:00:00+05:30",
                "open": 100.5,
                "high": 105.0,
                "low": 100.0,
                "close": 104.0,
                "volume": 20,
            },
            "2026-07-13T11:30:00+05:30": {
                "time": "2026-07-13T11:30:00+05:30",
                "open": 104.0,
                "high": 104.5,
                "low": 97.0,
                "close": 98.0,
                "volume": 30,
            },
        }
        out = _session_ohlc_from_minutes(candles)
        self.assertEqual(out["open"], 100.0)
        self.assertEqual(out["high"], 105.0)
        self.assertEqual(out["low"], 97.0)
        self.assertEqual(out["price"], 98.0)
        self.assertEqual(out["volume"], 60.0)

    def test_seed_session_quote_from_minutes_when_rest_empty(self):
        mgr = UpstoxStreamManager(name="test-seed")
        mgr._candles["INFY"] = {
            "2026-07-13T09:15:00+05:30": {
                "time": "2026-07-13T09:15:00+05:30",
                "open": 1500.0,
                "high": 1510.0,
                "low": 1495.0,
                "close": 1505.0,
                "volume": 100,
            },
            "2026-07-13T10:15:00+05:30": {
                "time": "2026-07-13T10:15:00+05:30",
                "open": 1505.0,
                "high": 1520.0,
                "low": 1480.0,
                "close": 1490.0,
                "volume": 200,
            },
        }
        with patch("server.upstox_stream_worker.upstox_client.fetch_quotes", return_value=([], None)):
            mgr._seed_session_quote("INFY")
        q = mgr._quotes["INFY"]
        self.assertEqual(q["open"], 1500.0)
        self.assertEqual(q["high"], 1520.0)
        self.assertEqual(q["low"], 1480.0)
        self.assertEqual(q["price"], 1490.0)
        self.assertEqual(q["source"], "upstox_session_seed")

    def test_seed_session_quote_prefers_rest_day_ohlc(self):
        mgr = UpstoxStreamManager(name="test-seed-rest")
        mgr._candles["TCS"] = {
            "2026-07-13T09:15:00+05:30": {
                "time": "2026-07-13T09:15:00+05:30",
                "open": 3000.0,
                "high": 3010.0,
                "low": 2990.0,
                "close": 3005.0,
                "volume": 10,
            },
        }
        rest = [{
            "symbol": "TCS",
            "price": 3050.0,
            "open": 2995.0,
            "high": 3060.0,
            "low": 2980.0,
            "previous_close": 2988.0,
            "change_pct": 2.07,
        }]
        with patch("server.upstox_stream_worker.upstox_client.fetch_quotes", return_value=(rest, None)):
            mgr._seed_session_quote("TCS")
        q = mgr._quotes["TCS"]
        self.assertEqual(q["open"], 2995.0)
        self.assertEqual(q["high"], 3060.0)
        self.assertEqual(q["low"], 2980.0)
        self.assertEqual(q["price"], 3050.0)
        self.assertEqual(q["previous_close"], 2988.0)

    def test_ltp_only_tick_without_seed_omits_open(self):
        mgr = UpstoxStreamManager(name="test-ltp-open")
        mgr._apply_feed(
            "RELIANCE",
            {"ltpc": {"ltp": 1300.0, "cp": 1290.0}},
            1740729566000,
        )
        q = mgr._quotes["RELIANCE"]
        self.assertEqual(q["price"], 1300.0)
        self.assertIsNone(q.get("open"))

    def test_ltpc_force_mode_preserves_seeded_open(self):
        mgr = UpstoxStreamManager(name="test-ltpc", force_mode="ltpc")
        with mgr._lock:
            mgr._quotes["RELIANCE"] = {
                "symbol": "RELIANCE",
                "open": 1285.0,
                "high": 1290.0,
                "low": 1280.0,
            }
        mgr._apply_feed(
            "RELIANCE",
            {"ltpc": {"ltp": 1300.0, "cp": 1290.0}},
            1740729566000,
        )
        q = mgr._quotes["RELIANCE"]
        self.assertEqual(q["open"], 1285.0)
        self.assertEqual(q["high"], 1300.0)
        self.assertEqual(q["low"], 1280.0)

    def test_ltpc_symbols_get_session_seed_on_backfill(self):
        mgr = UpstoxStreamManager()
        with patch("server.upstox_stream_worker.upstox_instruments.instrument_map", return_value={}), patch(
            "server.upstox_stream_worker.upstox_instruments.resolve_instrument_keys",
            return_value=({"RELIANCE": "NSE_EQ|INE002A01018"}, []),
        ), patch.object(mgr, "_ensure_thread"), patch.object(mgr, "_backfill_intraday") as backfill, patch.object(
            mgr, "_seed_session_quote"
        ) as seed:
            mgr.subscribe("dashboard", ["RELIANCE"], mode="ltpc")
            for _ in range(50):
                if seed.called:
                    break
                time.sleep(0.02)
        backfill.assert_not_called()
        seed.assert_called_once_with("RELIANCE")


if __name__ == "__main__":
    unittest.main()
