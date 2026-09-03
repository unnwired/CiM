"""Live quote provider: Upstox only (no Yahoo / NSE mix on regular path)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from server import live_quote_providers as lqp


class LiveQuoteProviderTests(unittest.TestCase):
    @patch("server.upstox_config.market_data_enabled", return_value=False)
    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    def test_fetch_live_quotes_equity_no_yahoo_when_upstox_off(self, yf, _ux):
        yf.return_value = [
            {
                "symbol": "RELIANCE",
                "price": 2500.0,
                "previous_close": 2480.0,
                "change_pct": 0.81,
                "updated_at": "2026-06-15 10:00:00 IST",
                "source": "yfinance",
            }
        ]
        rows, err = lqp.fetch_live_quotes(["RELIANCE"])
        self.assertEqual(rows, [])
        self.assertIsNotNone(err)
        yf.assert_not_called()

    @patch("server.upstox_config.market_data_enabled", return_value=True)
    @patch("server.live_quote_providers.fetch_upstox_quotes")
    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    @patch("server.live_quote_providers.fetch_nse_all_indices")
    def test_fetch_live_quotes_index_upstox_only(self, nse_idx, yf, ux, _enabled):
        ux.return_value = (
            [
                {
                    "symbol": "^NSEI",
                    "price": 24100.0,
                    "change_pct": 0.5,
                    "updated_at": "2026-06-15 10:00:00 IST",
                    "source": "upstox",
                }
            ],
            None,
        )
        rows, _err = lqp.fetch_live_quotes(["^NSEI"], index_names={"^NSEI": "NIFTY 50"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "^NSEI")
        self.assertEqual(rows[0]["source"], "upstox")
        nse_idx.assert_not_called()
        yf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
