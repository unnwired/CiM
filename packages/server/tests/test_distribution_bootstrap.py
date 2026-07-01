"""Regression tests for distribution bootstrap (blank Electron shell)."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import uuid
import unittest
from pathlib import Path

from server import app_code_crypto as crypto


class DistributionTreeDetectionTest(unittest.TestCase):
    def test_distribution_with_embedded_secret_is_not_dev_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server").mkdir()
            (root / "server" / "server.pyc.enc").write_bytes(b"enc")
            (root / "server" / "_cim_dist_embedded.py").write_text(
                'def distribution_secret_bytes() -> bytes:\n    return b"test-secret"\n',
                encoding="utf-8",
            )
            self.assertFalse(crypto.is_development_tree(root))

    def test_distribution_with_profile_and_encrypted_server_is_not_dev_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "server").mkdir()
            (root / "data").mkdir()
            (root / "config" / ".fx-dist.cfg").write_text("test-secret", encoding="utf-8")
            (root / "server" / "server.pyc.enc").write_bytes(b"enc")
            self.assertFalse(crypto.is_development_tree(root))

    def test_dev_repo_with_stray_encrypt_artifacts_stays_dev_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "server").mkdir()
            (root / "config" / ".fx-dist.cfg").write_text("test-secret", encoding="utf-8")
            (root / "server" / "server.py").write_text("# dev", encoding="utf-8")
            (root / "server" / "server.pyc.enc").write_bytes(b"enc")
            self.assertTrue(crypto.is_development_tree(root))
            self.assertEqual(crypto.product_display_name(root), "Charts In Motion Dev")

    def test_flowx_dev_does_not_override_client_distribution_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "server").mkdir()
            (root / "config" / ".fx-dist.cfg").write_text("test-secret", encoding="utf-8")
            (root / "server" / "server.pyc.enc").write_bytes(b"enc")
            prev = os.environ.get("CIM_DEV")
            try:
                os.environ["CIM_DEV"] = "1"
                self.assertFalse(crypto.is_development_tree(root))
            finally:
                if prev is None:
                    os.environ.pop("CIM_DEV", None)
                else:
                    os.environ["CIM_DEV"] = prev

    def test_repo_with_server_py_and_no_profile_is_dev_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server").mkdir()
            (root / "server" / "server.py").write_text("# dev", encoding="utf-8")
            self.assertTrue(crypto.is_development_tree(root))

    def test_plaintext_distribution_with_server_py_is_not_dev_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "server").mkdir()
            (root / "server" / "server.py").write_text("# dist", encoding="utf-8")
            (root / "server" / "_cim_dist_embedded.py").write_text(
                'def distribution_secret_bytes() -> bytes:\n    return b"test-secret"\n',
                encoding="utf-8",
            )
            (root / "config" / ".cim-plaintext-dist").write_text("plaintext\n", encoding="utf-8")
            self.assertTrue(crypto.is_plaintext_distribution(root))
            self.assertFalse(crypto.is_development_tree(root))
            self.assertTrue(crypto.needs_distribution_bootstrap(root))

    def test_product_display_name_dev_vs_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "server").mkdir()
            (root / "config" / ".fx-dist.cfg").write_text("test-secret", encoding="utf-8")
            (root / "server" / "server.pyc.enc").write_bytes(b"enc")
            self.assertEqual(crypto.product_display_name(root), "Charts In Motion")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server").mkdir()
            (root / "server" / "server.py").write_text("# dev", encoding="utf-8")
            self.assertEqual(crypto.product_display_name(root), "Charts In Motion Dev")

    def test_stale_app_cache_invalid_when_index_js_hash_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "server").mkdir()
            (root / "data").mkdir()
            (root / "frontend" / "build" / "static" / "js").mkdir(parents=True)
            (root / "frontend" / "build" / "static" / "css").mkdir(parents=True)
            (root / "config" / ".fx-dist.cfg").write_text("test-secret", encoding="utf-8")
            (root / "version.txt").write_text(f"9.9.8-{uuid.uuid4().hex[:8]}", encoding="utf-8")
            (root / "frontend" / "build" / "index.html").write_text(
                '<script src="/static/js/main.oldhash.js"></script>', encoding="utf-8"
            )
            (root / "frontend" / "build" / "static" / "js" / "main.newhash.js.enc").write_bytes(b"enc")
            (root / "frontend" / "build" / "static" / "css" / "main.css").write_text("x", encoding="utf-8")
            cache_dir = crypto.app_cache_root(root)
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            cache_js = cache_dir / "frontend" / "build" / "static" / "js"
            cache_css = cache_dir / "frontend" / "build" / "static" / "css"
            cache_js.mkdir(parents=True)
            cache_css.mkdir(parents=True)
            (cache_js / "main.newhash.js").write_text("console.log('wrong');", encoding="utf-8")
            (cache_css / "main.css").write_text("x", encoding="utf-8")
            (cache_dir / ".ready").write_text("ok", encoding="utf-8")
            self.assertFalse(crypto.cache_is_current(root, cache_dir))


if __name__ == "__main__":
    unittest.main()
