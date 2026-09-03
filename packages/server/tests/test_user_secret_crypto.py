"""Tests for AES-GCM user secret crypto + per-user Telegram credential storage."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVER = Path(__file__).resolve().parents[1]
PACKAGES = SERVER.parent
for p in (str(PACKAGES), str(SERVER)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["CIM_TELEGRAM_KEK"] = "unit-test-telegram-kek-not-for-prod"

from user_alerts_store import (  # noqa: E402
    clear_telegram_credentials,
    resolve_telegram_credentials,
    save_telegram_credentials,
    telegram_credentials_status,
)
from user_secret_crypto import decrypt_secret, encrypt_secret  # noqa: E402


class UserSecretCryptoTest(unittest.TestCase):
    def test_roundtrip(self):
        session = {"email": "alice@example.com"}
        with mock.patch("user_secret_crypto._crypto.current_machine_code", return_value="TESTMACHINE"):
            blob = encrypt_secret("123456:AA-secret-token", session=session, base_dir=None)
            self.assertNotIn("AA-secret-token", blob)
            self.assertEqual(
                decrypt_secret(blob, session=session, base_dir=None),
                "123456:AA-secret-token",
            )

    def test_aad_binds_to_account(self):
        with mock.patch("user_secret_crypto._crypto.current_machine_code", return_value="TESTMACHINE"):
            blob = encrypt_secret(
                "123456:AA-secret-token",
                session={"email": "alice@example.com"},
                base_dir=None,
            )
            with self.assertRaises(Exception):
                decrypt_secret(
                    blob,
                    session={"email": "bob@example.com"},
                    base_dir=None,
                )


class TelegramCredentialsStoreTest(unittest.TestCase):
    def test_save_status_never_returns_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            session = {"email": "alice@example.com"}
            with mock.patch("server.app_code_crypto.current_machine_code", return_value="TESTMACHINE"):
                with mock.patch("user_secret_crypto._crypto.current_machine_code", return_value="TESTMACHINE"):
                    with mock.patch(
                        "server.telegram_notify.get_me",
                        return_value={"ok": True, "username": "@TestCiMBot", "name": "Test CiM Bot"},
                    ):
                        status = save_telegram_credentials(
                            base,
                            bot_token="123456789:AA-test-bot-token-value",
                            chat_id="987654321",
                            session=session,
                        )
                    self.assertTrue(status["configured"])
                    self.assertTrue(status["connected"])
                    self.assertEqual(status["source"], "user")
                    self.assertEqual(status["chat_id_hint"], "…4321")
                    self.assertEqual(status["bot_username"], "@TestCiMBot")
                    self.assertEqual(status["bot_name"], "Test CiM Bot")

                    secrets_path = (
                        base / "data" / "users" / "alice_at_example.com" / "TESTMACHINE" / "telegram_secrets.json"
                    )
                    self.assertTrue(secrets_path.is_file())
                    raw = secrets_path.read_text(encoding="utf-8")
                    self.assertNotIn("AA-test-bot-token-value", raw)
                    self.assertNotIn("987654321", raw)
                    self.assertIn("bot_token_enc", raw)
                    self.assertIn("@TestCiMBot", raw)

                    creds = resolve_telegram_credentials(base, session=session)
                    self.assertTrue(creds["ok"])
                    self.assertEqual(creds["bot_token"], "123456789:AA-test-bot-token-value")
                    self.assertEqual(creds["chat_id"], "987654321")

                    pub = telegram_credentials_status(base, session=session)
                    dumped = str(pub)
                    self.assertNotIn("AA-test-bot-token-value", dumped)
                    self.assertNotIn("987654321", dumped)

                    cleared = clear_telegram_credentials(base, session=session)
                    self.assertFalse(cleared["configured"])
                    self.assertFalse(resolve_telegram_credentials(base, session=session)["ok"])


if __name__ == "__main__":
    unittest.main()
