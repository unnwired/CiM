"""Tests for Upstox market-data integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from server import live_quote_providers as lqp
from server import upstox_client, upstox_config, upstox_instruments


class UpstoxConfigTests(unittest.TestCase):
    @patch.dict("os.environ", {"UPSTOX_ANALYTICS_TOKEN": "tok", "CIM_UPSTOX_DISABLED": ""}, clear=False)
    def test_market_data_enabled_with_token(self):
        self.assertTrue(upstox_config.market_data_enabled())

    @patch.dict("os.environ", {"UPSTOX_ANALYTICS_TOKEN": "tok", "CIM_UPSTOX_DISABLED": "1"}, clear=False)
    def test_market_data_disabled_flag(self):
        self.assertFalse(upstox_config.market_data_enabled())


class UpstoxInstrumentMapTests(unittest.TestCase):
    def test_build_map_from_sample_rows(self):
        rows = [
            {
                "segment": "NSE_EQ",
                "instrument_type": "EQ",
                "trading_symbol": "RELIANCE",
                "instrument_key": "NSE_EQ|INE002A01018",
            },
            {
                "segment": "NSE_EQ",
                "instrument_type": "BE",
                "trading_symbol": "MTARTECH",
                "instrument_key": "NSE_EQ|INE864I01014",
            },
            {
                "segment": "NSE_EQ",
                "instrument_type": "BZ",
                "trading_symbol": "SOMEBZ",
                "instrument_key": "NSE_EQ|INEBZ0000001",
            },
            {
                "segment": "NSE_EQ",
                "instrument_type": "GS",
                "trading_symbol": "GOVBOND",
                "instrument_key": "NSE_EQ|INEGS0000001",
            },
            {
                "segment": "NSE_INDEX",
                "name": "Nifty 50",
                "trading_symbol": "NIFTY",
                "instrument_key": "NSE_INDEX|Nifty 50",
            },
        ]
        meta = upstox_instruments._build_map_from_rows(rows)
        self.assertEqual(meta["symbols"]["RELIANCE"], "NSE_EQ|INE002A01018")
        self.assertEqual(meta["symbols"]["MTARTECH"], "NSE_EQ|INE864I01014")
        self.assertEqual(meta["symbols"]["SOMEBZ"], "NSE_EQ|INEBZ0000001")
        self.assertNotIn("GOVBOND", meta["symbols"])
        self.assertIn("BE", meta["included_equity_types"])
        self.assertEqual(meta["index_names"]["Nifty 50"], "NSE_INDEX|Nifty 50")

    def test_eq_preferred_over_be_duplicate(self):
        rows = [
            {
                "segment": "NSE_EQ",
                "instrument_type": "BE",
                "trading_symbol": "FOO",
                "instrument_key": "NSE_EQ|BEKEY",
            },
            {
                "segment": "NSE_EQ",
                "instrument_type": "EQ",
                "trading_symbol": "FOO",
                "instrument_key": "NSE_EQ|EQKEY",
            },
        ]
        meta = upstox_instruments._build_map_from_rows(rows)
        self.assertEqual(meta["symbols"]["FOO"], "NSE_EQ|EQKEY")

    def test_resolve_equity_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            upstox_instruments.configure_paths(data_dir=Path(tmp))
            meta = {
                "session_day": upstox_instruments._session_day_ist(),
                "symbols": {"RELIANCE": "NSE_EQ|INE002A01018"},
                "index_names": {"Nifty 50": "NSE_INDEX|Nifty 50"},
            }
            path = Path(tmp) / upstox_instruments.MAP_FILENAME
            path.write_text(json.dumps(meta), encoding="utf-8")
            self.assertEqual(upstox_instruments.resolve_equity_key("reliance"), "NSE_EQ|INE002A01018")
            self.assertEqual(
                upstox_instruments.resolve_index_key("^NSEI"),
                "NSE_INDEX|Nifty 50",
            )


class UpstoxClientTests(unittest.TestCase):
    def test_quote_entry_from_payload(self):
        payload = {
            "last_price": 1304.0,
            "net_change": 0.5,
            "volume": 1000,
            "ohlc": {"open": 1312.0, "high": 1312.0, "low": 1302.0, "close": 1304.0},
        }
        ent = upstox_client._quote_entry_from_payload("RELIANCE", payload)
        self.assertIsNotNone(ent)
        assert ent is not None
        self.assertEqual(ent["symbol"], "RELIANCE")
        self.assertEqual(ent["price"], 1304.0)
        self.assertEqual(ent["previous_close"], 1303.5)
        self.assertEqual(ent["source"], "upstox")

    @patch("server.upstox_config.analytics_token", return_value="test-token")
    @patch("server.upstox_client.requests.get")
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    @patch("server.upstox_instruments.resolve_instrument_keys")
    @patch("server.upstox_instruments.instrument_map")
    def test_fetch_quotes_batch(self, _imap, resolve, _enabled, mock_get, _tok):
        resolve.return_value = ({"RELIANCE": "NSE_EQ|INE002A01018"}, [])
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "status": "success",
            "data": {
                "NSE_EQ:RELIANCE": {
                    "instrument_token": "NSE_EQ|INE002A01018",
                    "symbol": "RELIANCE",
                    "last_price": 2500.0,
                    "net_change": 25.0,
                    "volume": 500,
                    "ohlc": {"open": 2480.0, "high": 2510.0, "low": 2475.0, "close": 2500.0},
                }
            },
        }
        mock_get.return_value = resp
        rows, err = upstox_client.fetch_quotes(["RELIANCE"])
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "RELIANCE")


class LiveQuoteUpstoxIntegrationTests(unittest.TestCase):
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    @patch("server.live_quote_providers.fetch_upstox_quotes")
    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    def test_equity_prefers_upstox(self, yf, ux, _enabled):
        ux.return_value = (
            [
                {
                    "symbol": "RELIANCE",
                    "price": 2500.0,
                    "previous_close": 2480.0,
                    "change_pct": 0.81,
                    "updated_at": "2026-06-15 10:00:00 IST",
                    "source": "upstox",
                }
            ],
            None,
        )
        rows, err = lqp.fetch_live_quotes(["RELIANCE"])
        self.assertIsNone(err)
        self.assertEqual(rows[0]["source"], "upstox")
        ux.assert_called_once()
        yf.assert_not_called()

    @patch("server.upstox_config.market_data_enabled", return_value=True)
    @patch("server.live_quote_providers.fetch_upstox_quotes")
    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    def test_primary_equity_no_yahoo_fallback(self, yf, ux, _enabled):
        ux.return_value = ([], "missing keys")
        yf.return_value = [
            {
                "symbol": "ZZZZZ",
                "price": 10.0,
                "updated_at": "2026-06-15 10:00:00 IST",
                "source": "yfinance",
            }
        ]
        rows = lqp.fetch_primary_equity_quotes(["ZZZZZ"])
        self.assertEqual(rows, [])
        yf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
