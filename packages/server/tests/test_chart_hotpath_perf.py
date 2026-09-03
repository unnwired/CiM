"""Chart / screener hot-path: no sync 4H integrity; OHLC SQL is TTL-cached."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))


class TestChartHotpathPerf(unittest.TestCase):
    def test_schedule_4h_integrity_is_async_and_cooldown(self):
        from server import server as srv

        started = []

        def fake_thread(*, target=None, name=None, daemon=None):
            started.append(name)
            m = MagicMock()
            m.start = MagicMock()
            # Do not run target — we only assert scheduling.
            return m

        with patch.object(srv, "_4h_integrity_last_ts", {}):
            with patch.object(srv.threading, "Thread", side_effect=fake_thread):
                srv._schedule_4h_integrity_check("RELIANCE")
                srv._schedule_4h_integrity_check("RELIANCE")  # cooldown
                self.assertEqual(len(started), 1)
                self.assertTrue(started[0].startswith("4h-integrity-"))

    def test_get_stock_df_caches_ohlc_refresh(self):
        import pandas as pd
        from server import server as srv

        base = pd.DataFrame(
            {
                "Symbol": ["AAA", "BBB"],
                "Price": [1.0, 2.0],
                "Change %": [0.0, 0.0],
                "Monthly Change %": [0.0, 0.0],
                "Market Cap": [1e9, 2e9],
            }
        )
        calls = {"n": 0}

        def fake_ohlc(df, conn):
            calls["n"] += 1
            df["Change %"] = [1.0, 2.0]

        with patch.object(srv, "_stock_df", base.copy()):
            with patch.object(srv, "_stock_df_ohlc", None):
                with patch.object(srv, "_stock_df_ohlc_ts", 0.0):
                    with patch.object(srv, "get_db_connection", return_value=MagicMock()):
                        with patch.object(srv, "_apply_live_screener_ohlc", side_effect=fake_ohlc):
                            with patch.object(srv.market_cap_live, "apply_live_market_cap"):
                                with patch.object(srv, "_apply_movers_live_prices_only"):
                                    a = srv.get_stock_df()
                                    b = srv.get_stock_df()
        self.assertEqual(calls["n"], 1)
        self.assertEqual(list(a["Change %"]), [1.0, 2.0])
        self.assertEqual(list(b["Change %"]), [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
