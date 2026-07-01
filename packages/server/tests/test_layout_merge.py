"""Layout API merge — index star tags and list orders persist per user."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server.routers import settings as settings_router  # noqa: E402


class TestLayoutMerge(unittest.TestCase):
    def test_save_layout_merges_index_star_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings_router.configure_layout(data_dir)
            path = data_dir / "layout.json"
            path.write_text(
                json.dumps({"indicesPaneWidth": 240}),
                encoding="utf-8",
            )
            payload = {
                "indexStarTags": {"NIFTY 50": "golden", "NIFTY BANK": "blue"},
                "layoutOrdersSavedAt": "2026-06-30T12:00:00.000Z",
            }
            class Req:
                pass

            settings_router.save_layout(Req(), payload)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["indicesPaneWidth"], 240)
            self.assertEqual(saved["indexStarTags"]["NIFTY 50"], "golden")
            self.assertEqual(saved["indexStarTags"]["NIFTY BANK"], "blue")

            settings_router.save_layout(Req(), {"indicesPaneWidth": 300})
            saved2 = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved2["indicesPaneWidth"], 300)
            self.assertEqual(saved2["indexStarTags"]["NIFTY 50"], "golden")


if __name__ == "__main__":
    unittest.main()
