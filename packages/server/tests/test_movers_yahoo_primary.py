"""Movers live: Yahoo-primary fetch order on testbed installs."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from server import movers_live


class MoversYahooPrimaryTests(unittest.TestCase):
    @patch.object(movers_live, "_yahoo_primary_enabled", return_value=True)
    @patch.object(movers_live, "_merge_cache")
    @patch("server.live_quote_providers.fetch_yfinance_quotes")
    @patch.object(movers_live, "_make_session")
    @patch.object(movers_live, "_fetch_quote_equity")
    @patch.object(movers_live, "_symbol_needs_live_quote", return_value=True)
    def test_yahoo_first_on_demand(
        self,
        _needs,
        mock_quote_equity,
        mock_session,
        mock_yahoo,
        mock_merge,
        _yahoo_flag,
    ):
        mock_yahoo.return_value = [
            {"symbol": "RELIANCE", "price": 2500.0, "previous_close": 2480.0, "source": "yfinance"},
            {"symbol": "TCS", "price": 3500.0, "previous_close": 3480.0, "source": "yfinance"},
        ]
        n = movers_live._fetch_missing_quote_symbols(["RELIANCE", "TCS"])
        self.assertGreaterEqual(n, 1)
        mock_yahoo.assert_called_once()
        mock_quote_equity.assert_not_called()
        mock_session.assert_not_called()

    @patch.object(movers_live, "_yahoo_primary_enabled", return_value=False)
    @patch.object(movers_live, "_merge_cache")
    @patch("server.live_quote_providers.fetch_live_quotes")
    @patch.object(movers_live, "_make_session")
    @patch.object(movers_live, "_fetch_quote_equity", return_value=None)
    @patch.object(movers_live, "_symbol_needs_live_quote", return_value=True)
    def test_legacy_nse_first(
        self,
        _needs,
        mock_quote_equity,
        mock_session,
        mock_fetch_live,
        mock_merge,
        _yahoo_flag,
    ):
        mock_fetch_live.return_value = ([], None)
        movers_live._fetch_missing_quote_symbols(["RELIANCE"])
        mock_session.assert_called()
        mock_quote_equity.assert_called()


if __name__ == "__main__":
    unittest.main()
