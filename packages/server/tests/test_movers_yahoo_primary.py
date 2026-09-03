"""Movers live: Upstox primary → Yahoo secondary on-demand quotes."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from server import movers_live


class MoversUpstoxPrimaryTests(unittest.TestCase):
    @patch.object(movers_live, "_merge_cache")
    @patch("server.live_quote_providers.fetch_primary_equity_quotes")
    @patch.object(movers_live, "_make_session")
    @patch.object(movers_live, "_fetch_quote_equity")
    @patch.object(movers_live, "_symbol_needs_live_quote", return_value=True)
    def test_upstox_yahoo_on_demand_no_nse(
        self,
        _needs,
        mock_quote_equity,
        mock_session,
        mock_primary,
        mock_merge,
    ):
        mock_primary.return_value = [
            {"symbol": "RELIANCE", "price": 2500.0, "previous_close": 2480.0, "source": "upstox"},
            {"symbol": "TCS", "price": 3500.0, "previous_close": 3480.0, "source": "upstox"},
        ]
        n = movers_live._fetch_missing_quote_symbols(["RELIANCE", "TCS"])
        self.assertGreaterEqual(n, 1)
        mock_primary.assert_called_once()
        mock_quote_equity.assert_not_called()
        mock_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
