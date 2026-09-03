"""Daily Update path is Upstox-only (no Yahoo fallback)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from unittest.mock import patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestScrapeDailyUpstoxOnly(unittest.TestCase):
    @patch("server.upstox_config.market_data_enabled", return_value=True)
    @patch("server.upstox_history.fetch_daily_batch")
    def test_fetch_batch_does_not_call_yahoo(self, mock_ux, _enabled):
        import scrape_daily as sd

        mock_ux.return_value = (
            {"RELIANCE": [("2026-06-15 00:00:00+05:30", 1, 2, 0.5, 1.5, 10)]},
            {"upstox": 1, "failed": 0},
        )
        with patch.object(sd, "_fetch_batch_yfinance") as mock_yf:
            result, status = sd.fetch_batch(
                ["RELIANCE", "MISSING"],
                date(2026, 6, 1),
                date(2026, 6, 15),
            )
            self.assertEqual(status, "ok")
            self.assertIn("RELIANCE", result)
            self.assertNotIn("MISSING", result)
            mock_yf.assert_not_called()
            stats = getattr(sd.fetch_batch, "last_stats", {})
            self.assertEqual(stats.get("upstox"), 1)
            self.assertEqual(stats.get("yahoo_fallback"), 0)
            self.assertEqual(stats.get("failed"), 1)


if __name__ == "__main__":
    unittest.main()
