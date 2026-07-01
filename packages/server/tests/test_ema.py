"""Tests for EMA calculation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.server import calculate_ema  # noqa: E402


class EmaTests(unittest.TestCase):
    def test_ema_constant_series(self):
        closes = [100.0] * 50
        emas = calculate_ema(closes, period=9)
        self.assertAlmostEqual(emas[-1], 100.0, places=1)

    def test_ema_short_series(self):
        closes = [1.0, 2.0, 3.0]
        emas = calculate_ema(closes, period=9)
        self.assertTrue(all(v is None for v in emas))


if __name__ == "__main__":
    unittest.main()
