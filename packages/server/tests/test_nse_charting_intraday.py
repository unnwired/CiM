"""Tests for NSE charting 5m parse helpers."""
from __future__ import annotations

import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.bars_4h import assign_session_bucket  # noqa: E402
from server.nse_charting_intraday import (  # noqa: E402
    get_nse_chart_token,
    load_nse_chart_token_map,
    parse_nse_charting_candles,
)

IST = ZoneInfo("Asia/Kolkata")


class TestNseChartingIntraday(unittest.TestCase):
    def test_parse_nse_charting_candles(self):
        # NSE sends UTC epoch where UTC wall clock == intended IST session time.
        ts_ms = int(datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
        rows = parse_nse_charting_candles(
            [{"time": ts_ms, "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 0}]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0].hour, 10)
        self.assertEqual(rows[0][0].tzinfo, IST)
        self.assertEqual(assign_session_bucket(rows[0][0]), 1)
        self.assertEqual(rows[0][1], 100.0)
        self.assertEqual(rows[0][4], 100.5)

    def test_load_token_map_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "config"
            cfg_dir.mkdir()
            (cfg_dir / "nse_index_chart_tokens.json").write_text(
                json.dumps({"^CNXINDDEF": {"token": "26085", "chartSymbol": "NIFTY IND DEFENCE"}}),
                encoding="utf-8",
            )
            m = load_nse_chart_token_map(Path(tmp))
            self.assertIn("^CNXINDDEF", m)
            self.assertEqual(m["^CNXINDDEF"]["token"], "26085")
            tok = get_nse_chart_token("^CNXINDDEF", Path(tmp))
            self.assertIsNotNone(tok)
            assert tok is not None
            self.assertEqual(tok["token"], "26085")

    def test_nse_timestamps_produce_both_session_buckets(self):
        """Regression: NSE UTC-wall-clock skew must not collapse 4H to afternoon-only."""
        from server.bars_4h import aggregate_intraday_to_4h

        base_am = datetime(2026, 6, 25, 9, 15, tzinfo=timezone.utc)
        base_pm = datetime(2026, 6, 25, 13, 15, tzinfo=timezone.utc)
        candles = []
        for i in range(16):
            t = base_am + timedelta(minutes=5 * i)
            candles.append(
                {
                    "time": int(t.timestamp() * 1000),
                    "open": 9400 + i,
                    "high": 9410 + i,
                    "low": 9390 + i,
                    "close": 9405 + i,
                    "volume": 0,
                }
            )
        for i in range(16):
            t = base_pm + timedelta(minutes=5 * i)
            candles.append(
                {
                    "time": int(t.timestamp() * 1000),
                    "open": 9500 + i,
                    "high": 9510 + i,
                    "low": 9490 + i,
                    "close": 9505 + i,
                    "volume": 0,
                }
            )
        rows = parse_nse_charting_candles(candles)
        bars = aggregate_intraday_to_4h("^CNXINDDEF", rows, set(), set())
        buckets = {b.bucket for b in bars}
        self.assertIn(1, buckets)
        self.assertIn(2, buckets)


if __name__ == "__main__":
    unittest.main()
