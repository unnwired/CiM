"""Regression: Yahoo single-symbol leftover must parse MultiIndex OHLCV."""
from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

import scrape_daily as sd


class YahooSingleTickerFallbackTests(unittest.TestCase):
    def test_yfinance_symbol_frame_group_by_ticker_single(self):
        idx = pd.to_datetime(["2026-07-15", "2026-07-16"])
        cols = pd.MultiIndex.from_product([["MTARTECH.NS"], ["Open", "High", "Low", "Close", "Volume"]])
        df = pd.DataFrame(
            [
                [100.0, 110.0, 90.0, 105.0, 1000.0],
                [105.0, 115.0, 100.0, 110.0, 2000.0],
            ],
            index=idx,
            columns=cols,
        )
        frame = sd._yfinance_symbol_frame(df, "MTARTECH.NS", single=True)
        self.assertIsNotNone(frame)
        self.assertIn("Close", frame.columns)
        self.assertEqual(len(frame), 2)

    @patch("yfinance.download")
    def test_fetch_batch_yfinance_single_symbol_ok(self, mock_dl):
        idx = pd.to_datetime(["2026-07-15", "2026-07-16"])
        cols = pd.MultiIndex.from_product([["MTARTECH.NS"], ["Open", "High", "Low", "Close", "Volume"]])
        mock_dl.return_value = pd.DataFrame(
            [
                [100.0, 110.0, 90.0, 105.0, 1000.0],
                [105.0, 115.0, 100.0, 110.0, 2000.0],
            ],
            index=idx,
            columns=cols,
        )
        result, status = sd._fetch_batch_yfinance(
            ["MTARTECH"],
            datetime(2026, 7, 15),
            datetime(2026, 7, 16),
        )
        self.assertEqual(status, "ok")
        self.assertIn("MTARTECH", result)
        self.assertEqual(len(result["MTARTECH"]), 2)


if __name__ == "__main__":
    unittest.main()
