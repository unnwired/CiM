"""Tests for focus-only /api/live subscribe rules."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.live_routes import _merge_live_quote_layers, _needs_rest_ohlc


class LiveQuoteMergeTests(unittest.TestCase):
    def test_merge_keeps_focus_session_high_over_ltpc_cache(self):
        merged = _merge_live_quote_layers(
            {
                "symbol": "FEDFINA",
                "price": 163.0,
                "high": 163.0,
                "low": 160.0,
                "open": 161.0,
                "previous_close": 157.0,
                "change_pct": 3.82,
                "source": "upstox_stream",
            },
            None,
            {
                "symbol": "FEDFINA",
                "price": 163.0,
                "high": 174.0,
                "low": 160.0,
                "open": 161.0,
                "previous_close": 157.0,
                "change_pct": 3.82,
                "source": "upstox_session_seed",
            },
        )
        self.assertIsNotNone(merged)
        self.assertEqual(merged["high"], 174.0)
        self.assertEqual(merged["price"], 163.0)

    def test_needs_rest_ohlc_for_ltpc_stub(self):
        self.assertTrue(_needs_rest_ohlc({"price": 100, "high": 100, "source": "upstox_stream"}))
        self.assertFalse(_needs_rest_ohlc({"price": 100, "high": 105, "open": 99, "source": "upstox"}))


class LiveRoutesFocusTests(unittest.TestCase):
    def test_focus_subscribe_keeps_one_symbol_full(self):
        with patch("server.live_routes.stream_manager") as mgr:
            mgr.subscribe.return_value = {
                "configured": True,
                "contexts": {"focus": {"RELIANCE": "full"}},
                "subscription_count": 1,
            }
            from server.live_routes import router
            from fastapi import FastAPI

            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)
            res = client.post(
                "/api/live/subscribe",
                json={"context": "focus", "symbols": ["RELIANCE", "TCS", "INFY"], "mode": "ltpc"},
            )
            self.assertEqual(res.status_code, 200)
            mgr.subscribe.assert_called_once_with("focus", ["RELIANCE"], mode="full")
            mgr.seed_session_quotes_sync.assert_called_once_with(["RELIANCE"])

    def test_live_quotes_merges_ohlc_layers(self):
        with patch("server.live_routes._enrich_session_ohlc"), patch(
            "server.live_routes.movers_live", create=True
        ), patch("server.live_routes.focus_manager") as focus, patch(
            "server.live_routes.movers_manager"
        ) as movers:
            focus.quotes.return_value = {
                "symbols": {
                    "FEDFINA": {
                        "symbol": "FEDFINA",
                        "price": 163.0,
                        "high": 174.0,
                        "source": "upstox_session_seed",
                    }
                }
            }
            movers.quotes.return_value = {"symbols": {}}
            with patch("server.movers_live.live_cache_snapshot") as snap:
                snap.return_value = {
                    "FEDFINA": {
                        "symbol": "FEDFINA",
                        "price": 163.0,
                        "high": 163.0,
                        "source": "upstox_stream",
                    }
                }
                from server.live_routes import router
                from fastapi import FastAPI

                app = FastAPI()
                app.include_router(router)
                client = TestClient(app)
                res = client.get("/api/live/quotes", params={"symbols": "FEDFINA"})
                self.assertEqual(res.status_code, 200)
                q = res.json()["symbols"]["FEDFINA"]
                self.assertEqual(q["high"], 174.0)


if __name__ == "__main__":
    unittest.main()
