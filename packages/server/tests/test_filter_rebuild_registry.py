"""Tests for filter rebuild registry."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[1]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from filter_rebuild_registry import (  # noqa: E402
    indicator_families_for_keys,
    keys_for_engine,
    public_options_payload,
    registry_by_key,
    resolve_keys,
)


class TestFilterRebuildRegistry(unittest.TestCase):
    def test_public_options_lists_all_keys(self):
        payload = public_options_payload()
        keys = {it["key"] for it in payload["items"]}
        self.assertIn("ema", keys)
        self.assertIn("avg_volume", keys)
        self.assertIn("range_channel", keys)
        self.assertIn("snapshot_timeframes", payload)

    def test_resolve_keys_subset(self):
        entries = resolve_keys(["ema", "avg_volume", "missing"])
        self.assertEqual(len(entries), 2)
        self.assertEqual({e["key"] for e in entries}, {"ema", "avg_volume"})

    def test_indicator_families_mapping(self):
        fam = indicator_families_for_keys(["ema", "macd", "avg_volume"])
        self.assertEqual(fam, frozenset({"ema", "macd"}))

    def test_keys_for_engine(self):
        by_key = registry_by_key()
        self.assertIn("volume_stats", by_key["avg_volume"]["engine"])
        vol = keys_for_engine(["ema", "avg_volume"], "volume_stats")
        self.assertEqual(vol, ["avg_volume"])


if __name__ == "__main__":
    unittest.main()
