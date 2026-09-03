"""Tests for Yahoo-primary pipeline gating (testbed vs live)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.product_config import yahoo_primary_pipeline


class YahooPrimaryPipelineTests(unittest.TestCase):
    def test_testbed_role_enables_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = base / "config"
            cfg.mkdir()
            (cfg / "showcase_host.json").write_text(
                json.dumps({"port": 8002, "role": "testbed"}),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(yahoo_primary_pipeline(base))

    def test_live_role_uses_yahoo_primary_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = base / "config"
            cfg.mkdir()
            (cfg / "showcase_host.json").write_text(
                json.dumps({"port": 8001, "role": "live"}),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(yahoo_primary_pipeline(base))

    def test_explicit_json_false_opts_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = base / "config"
            cfg.mkdir()
            (cfg / "showcase_host.json").write_text(
                json.dumps({"port": 8001, "role": "live", "yahooPrimaryPipeline": False}),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                self.assertFalse(yahoo_primary_pipeline(base))

    def test_explicit_json_true_on_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = base / "config"
            cfg.mkdir()
            (cfg / "showcase_host.json").write_text(
                json.dumps({"port": 8001, "role": "live", "yahooPrimaryPipeline": True}),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(yahoo_primary_pipeline(base))

    def test_env_var_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = base / "config"
            cfg.mkdir()
            (cfg / "showcase_host.json").write_text(
                json.dumps({"port": 8002, "role": "testbed"}),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"CIM_YAHOO_PRIMARY_PIPELINE": "0"}, clear=True):
                self.assertFalse(yahoo_primary_pipeline(base))

    def test_desktop_default_skips_nse_bulk(self):
        """No showcase_host.json (desktop install) must still skip NSE universe scrape."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(yahoo_primary_pipeline(base))


if __name__ == "__main__":
    unittest.main()
