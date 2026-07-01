"""Live quote provider fallback when NSE quote-equity is blocked."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from server import live_quote_providers as lqp


class LiveQuoteProviderTests(unittest.TestCase):
    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    @patch("server.live_quote_providers.fetch_nse_all_indices")
    def test_fetch_live_quotes_equity_uses_yfinance(self, nse_idx, yf):
        nse_idx.return_value = {}
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
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "RELIANCE")
        yf.assert_called_once()

    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    @patch("server.live_quote_providers.fetch_nse_all_indices")
    def test_fetch_live_quotes_index_prefers_nse_all_indices(self, nse_idx, yf):
        nse_idx.return_value = {
            "NIFTY 50": {
                "symbol": "NIFTY 50",
                "price": 24000.0,
                "change_pct": 1.2,
                "updated_at": "2026-06-15 10:00:00 IST",
                "source": "nse_all_indices",
            }
        }
        rows, _err = lqp.fetch_live_quotes(["^NSEI"], index_names={"^NSEI": "NIFTY 50"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "^NSEI")
        yf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
