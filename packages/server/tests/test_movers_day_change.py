"""Regression tests for Market Movers day-change ranking (stale screener / live guards)."""

from __future__ import annotations

import unittest
from datetime import datetime
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

    def test_session_adjustment_flat_when_screener_matches_eod_on_stale_bar(self):
        """When latest DB bar is before today and screener equals EOD, today is flat — not 2-bar hist %."""
        df = pd.DataFrame([
            _row("ZAGGLE", change_pct=-2.23, eod_close=196.33, screener_price=196.33),
            _row("TCIFINANCE", change_pct=19.96, eod_close=17.43, screener_price=17.43),
        ])
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            out = md.apply_session_day_adjustment(df)
        self.assertAlmostEqual(float(out.loc[out["symbol"] == "ZAGGLE", "change_pct"].iloc[0]), 0.0, places=2)
        self.assertAlmostEqual(float(out.loc[out["symbol"] == "TCIFINANCE", "change_pct"].iloc[0]), 0.0, places=2)

    def test_stale_screener_price_not_used_for_coffeeday_style_row(self):
        """Stale screener.price vs EOD must not produce +20% when change_percent says ~2%."""
        df = pd.DataFrame([
            {
                **_row("COFFEEDAY", change_pct=-3.34, eod_close=33.6, screener_price=40.45, screener_change_pct=2.12),
                "eod_prev_close": 34.76,
                "as_of_date": "2026-06-10",
            },
        ])
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            out = md.apply_session_day_adjustment(df)
        chg = float(out.loc[0, "change_pct"])
        self.assertNotAlmostEqual(chg, 20.39, places=1)
        self.assertAlmostEqual(chg, 2.12, places=2)

    def test_screener_day_change_inconsistent_with_eod(self):
        self.assertTrue(md.screener_day_change_inconsistent_with_eod(40.45, 33.6, 2.12))
        self.assertFalse(md.screener_day_change_inconsistent_with_eod(33.6, 33.6, 2.12))
        self.assertFalse(md.screener_day_change_inconsistent_with_eod(1.07, 0.88, None))

    def test_session_adjustment_uses_fresh_screener_when_material(self):
        today_s = datetime.now(md.IST).strftime("%Y-%m-%d")
        df = pd.DataFrame([
            {
                **_row("EXCEL", change_pct=0.0, eod_close=0.88, screener_price=1.07),
                "screener_change_pct": 21.59,
                "price_updated_at": f"{today_s} 10:00:00",
            },
        ])
        df = md.apply_fresh_screener_quotes(df)
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

    def test_session_adjustment_refreshes_when_todays_bar_exists_and_screener_moved(self):
        today_s = datetime.now(md.IST).strftime("%Y-%m-%d")
        df = pd.DataFrame([
            _row(
                "TCIFINANCE",
                change_pct=10.0,
                eod_close=23.0,
                screener_price=24.5,
                screener_change_pct=10.0,
                as_of_date=today_s,
            ),
        ])
        df["eod_prev_close"] = 20.91
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            out = md.apply_session_day_adjustment(df)
        chg = float(out.loc[0, "change_pct"])
        self.assertGreater(chg, 10.0)
        self.assertAlmostEqual(float(out.loc[0, "price"]), 24.5, places=2)

    def test_gainers_top_list_has_no_zero_after_session_adjustment(self):
        today_s = datetime.now(md.IST).strftime("%Y-%m-%d")
        df = pd.DataFrame([
            {
                **_row("EXCEL", change_pct=0.0, eod_close=0.88, screener_price=1.07),
                "screener_change_pct": 21.59,
                "price_updated_at": f"{today_s} 10:00:00",
            },
            _row("ZAGGLE", change_pct=-2.23, eod_close=196.33, screener_price=196.33),
            _row("TCIFINANCE", change_pct=19.96, eod_close=17.43, screener_price=17.43),
            {
                **_row("OMKARCHEM", change_pct=0.0, eod_close=3.41, screener_price=4.06),
                "screener_change_pct": 19.06,
                "price_updated_at": f"{today_s} 10:00:00",
            },
        ])
        df = md.apply_fresh_screener_quotes(df)
        with patch.object(md, "_session_day_intraday_active", return_value=True):
            adj = md.apply_session_day_adjustment(df)
        adj = adj[adj["change_pct"].notna()]
        adj = md.filter_day_change_by_side(adj, "gainers")
        adj = adj.sort_values("change_pct", ascending=False)
        top = adj.head(10)
        self.assertTrue((top["change_pct"] > 0).all())
        symbols = list(top["symbol"])
        self.assertIn("EXCEL", symbols)
        self.assertIn("OMKARCHEM", symbols)
        self.assertNotIn("ZAGGLE", symbols)


if __name__ == "__main__":
    unittest.main()
