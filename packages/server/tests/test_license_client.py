"""Tests for online license session and access gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from server import app_code_crypto as crypto
from server import license_client as lc


class LicenseClientTests(unittest.TestCase):
    def test_device_id_matches_machine_code(self):
        mc = crypto.current_machine_code()
        self.assertEqual(lc.device_id(), mc)
        self.assertEqual(len(mc), 32)

    def test_session_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "data").mkdir()
            session = {
                "access_token": "test-token",
                "refresh_token": "refresh",
                "access_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "email": "user@example.com",
            }
            lc.save_session(base, session)
            loaded = lc.load_session(base)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["access_token"], "test-token")
            self.assertEqual(loaded["email"], "user@example.com")

    def test_access_token_valid_and_grace(self):
        now = datetime.now(timezone.utc)
        valid = {
            "access_expires_at": (now + timedelta(hours=1)).isoformat(),
            "offline_grace_until": (now + timedelta(days=7)).isoformat(),
        }
        self.assertTrue(lc.access_token_valid(valid))
        expired = {
            "access_expires_at": (now - timedelta(hours=1)).isoformat(),
            "offline_grace_until": (now + timedelta(days=1)).isoformat(),
        }
        self.assertFalse(lc.access_token_valid(expired))
        self.assertTrue(lc.within_offline_grace(expired))

    def test_access_granted_offline_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "server").mkdir()
            (base / "server" / "server.py").write_text("# dev\n", encoding="utf-8")
            self.assertTrue(crypto.access_granted(base))

    @patch.object(lc, "online_session_valid", return_value=True)
    @patch.object(crypto, "license_valid", return_value=False)
    @patch.object(crypto, "is_development_tree", return_value=False)
    def test_access_granted_online_session(self, *_mocks):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertTrue(crypto.access_granted(base))

    @patch.object(lc, "online_session_valid", return_value=False)
    @patch.object(crypto, "license_valid", return_value=True)
    @patch.object(crypto, "is_online_only_distribution", return_value=True)
    @patch.object(crypto, "is_development_tree", return_value=False)
    def test_access_granted_online_only_ignores_offline_key(self, *_mocks):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertFalse(crypto.access_granted(base))

    @patch("server.product_config.require_online_auth", return_value=False)
    @patch.object(crypto, "is_development_tree", return_value=True)
    @patch.object(crypto, "is_online_only_distribution", return_value=True)
    def test_license_status_web_dev_tree_includes_session_email(self, *_mocks):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            session = {
                "email": "sandeep@example.com",
                "access_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            }
            status = lc.license_status_for_client(base, session, host_mode="web")
            self.assertTrue(status["valid"])
            self.assertEqual(status["mode"], "online")
            self.assertEqual(status["email"], "sandeep@example.com")

    @patch("server.product_config.require_online_auth", return_value=False)
    @patch.object(crypto, "is_development_tree", return_value=True)
    def test_license_status_web_dev_tree_without_session_stays_dev(self, *_mocks):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            status = lc.license_status_for_client(base, None, host_mode="web")
            self.assertTrue(status["valid"])
            self.assertEqual(status["mode"], "dev")
            self.assertNotIn("email", status)


if __name__ == "__main__":
    unittest.main()
