"""Regression tests for Market Movers day-change ranking (stale screener / live guards)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from server import movers_data as md


def _row(
    symbol: str,
    *,
    change_pct: float,
    eod_close: float,
    screener_price: float | None = None,
    screener_change_pct: float | None = None,
    as_of_date: str = "2026-06-08",
) -> dict:
    return {
        "symbol": symbol,
        "change_pct": change_pct,
        "eod_close": eod_close,
        "eod_prev_close": eod_close * 0.95,
        "price": eod_close,
        "screener_price": screener_price if screener_price is not None else eod_close,
        "screener_change_pct": screener_change_pct,
        "as_of_date": as_of_date,
        "market_cap": 1e9,
        "volume_today": 1000,
        "volume_prior": 900,
        "volume_change_pct": 11.0,
        "avg_volume_20d": 1000,
        "rvol_20d": 1.0,
        "pe": 10,
        "issued_shares": 1e6,
    }


class MoversDayChangeTests(unittest.TestCase):
    def test_screener_price_moved_materially(self):
        self.assertFalse(md.screener_price_moved_materially(100.0, 100.0))
        self.assertTrue(md.screener_price_moved_materially(101.0, 100.0))

    def test_should_apply_live_day_change_rejects_stale_zero(self):
        self.assertFalse(md.should_apply_live_day_change(11.68, 0.0))
        self.assertFalse(md.should_apply_live_day_change(-2.23, 0.0))
        self.assertTrue(md.should_apply_live_day_change(11.68, 12.1))

    def test_session_adjustment_keeps_historical_when_screener_stale(self):
        df = pd.DataFrame([
            _row("ZAGGLE", change_pct=-2.23, eod_close=196.33, screener_price=196.33),
            _row("TCIFINANCE", change_pct=19.96, eod_close=17.43, screener_price=17.43),
        ])
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            out = md.apply_session_day_adjustment(df)
        self.assertEqual(float(out.loc[out["symbol"] == "ZAGGLE", "change_pct"].iloc[0]), -2.23)
        self.assertEqual(float(out.loc[out["symbol"] == "TCIFINANCE", "change_pct"].iloc[0]), 19.96)

    def test_session_adjustment_uses_fresh_screener_when_material(self):
        df = pd.DataFrame([
            _row("EXCEL", change_pct=0.0, eod_close=0.88, screener_price=1.07),
        ])
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            out = md.apply_session_day_adjustment(df)
        chg = float(out.loc[0, "change_pct"])
        self.assertGreater(chg, 20.0)

    def test_filter_day_change_by_side_excludes_zeros_from_gainers(self):
        df = pd.DataFrame([
            _row("A", change_pct=5.0, eod_close=10),
            _row("B", change_pct=0.0, eod_close=10),
            _row("C", change_pct=-1.0, eod_close=10),
        ])
        gainers = md.filter_day_change_by_side(df, "gainers")
        self.assertEqual(list(gainers["symbol"]), ["A"])
        losers = md.filter_day_change_by_side(df, "losers")
        self.assertEqual(list(losers["symbol"]), ["C"])

    def test_gainers_top_list_has_no_zero_after_session_adjustment(self):
        df = pd.DataFrame([
            _row("EXCEL", change_pct=0.0, eod_close=0.88, screener_price=1.07),
            _row("ZAGGLE", change_pct=-2.23, eod_close=196.33, screener_price=196.33),
            _row("TCIFINANCE", change_pct=19.96, eod_close=17.43, screener_price=17.43),
            _row("OMKARCHEM", change_pct=0.0, eod_close=3.41, screener_price=4.06),
        ])
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            adj = md.apply_session_day_adjustment(df)
        adj = adj[adj["change_pct"].notna()]
        adj = md.filter_day_change_by_side(adj, "gainers")
        adj = adj.sort_values("change_pct", ascending=False)
        top = adj.head(10)
        self.assertTrue((top["change_pct"] > 0).all())
        symbols = list(top["symbol"])
        self.assertIn("TCIFINANCE", symbols)
        self.assertNotIn("ZAGGLE", symbols)


if __name__ == "__main__":
    unittest.main()
