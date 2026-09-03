"""
Encrypt user secrets at rest (Telegram bot tokens, chat IDs).

Ciphertext is AES-256-GCM with a random nonce. The key encryption key (KEK) is
derived from CIM_TELEGRAM_KEK when set, otherwise from the install distribution
secret with a dedicated salt — so a dump of user JSON alone is not enough to
recover tokens. Associated data binds ciphertext to the account (email + machine),
preventing cut-and-paste of secrets across user namespaces.

Threat model: protects stolen on-disk user files without the host KEK.
A full host compromise (attacker reads process memory / .env KEK) can still
decrypt — that is true of any server-held secret.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover
    AESGCM = None  # type: ignore

from server import app_code_crypto as _crypto

MAGIC = b"CIMTG1\x00"
NONCE_LEN = 12
TELEGRAM_KEK_SALT = b"cim-user-telegram-v1"


def _aad_for_session(session: Optional[dict[str, Any]]) -> bytes:
    email = str((session or {}).get("email") or "").strip().lower()
    machine = _crypto.current_machine_code().strip().upper()
    return f"{email}|{machine}".encode("utf-8")


def telegram_kek(base_dir: Optional[Path] = None) -> bytes:
    """
    32-byte AES key for Telegram credential encryption.

    Prefer a dedicated CIM_TELEGRAM_KEK so Telegram secrets are independent of
    the distribution/license secret. Fall back to a salted hash of the
    distribution secret for installs that have not set a dedicated KEK yet.
    """
    dedicated = os.getenv("CIM_TELEGRAM_KEK", "").strip()
    if dedicated:
        return hashlib.sha256(dedicated.encode("utf-8") + TELEGRAM_KEK_SALT).digest()
    dist = _crypto.distribution_secret(base_dir)
    return hashlib.sha256(dist + TELEGRAM_KEK_SALT).digest()


def encrypt_secret(
    plaintext: str,
    *,
    session: Optional[dict[str, Any]] = None,
    base_dir: Optional[Path] = None,
) -> str:
    if AESGCM is None:
        raise RuntimeError("cryptography package required for Telegram secret storage")
    text = str(plaintext or "")
    if not text:
        raise ValueError("empty secret")
    key = telegram_kek(base_dir)
    nonce = os.urandom(NONCE_LEN)
    aead = AESGCM(key)
    ct = aead.encrypt(nonce, text.encode("utf-8"), _aad_for_session(session))
    blob = MAGIC + nonce + ct
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_secret(
    blob_b64: str,
    *,
    session: Optional[dict[str, Any]] = None,
    base_dir: Optional[Path] = None,
) -> str:
    if AESGCM is None:
        raise RuntimeError("cryptography package required for Telegram secret storage")
    raw = base64.urlsafe_b64decode(str(blob_b64 or "").encode("ascii"))
    if len(raw) < len(MAGIC) + NONCE_LEN + 16 or not raw.startswith(MAGIC):
        raise ValueError("invalid ciphertext")
    nonce = raw[len(MAGIC) : len(MAGIC) + NONCE_LEN]
    ct = raw[len(MAGIC) + NONCE_LEN :]
    aead = AESGCM(telegram_kek(base_dir))
    pt = aead.decrypt(nonce, ct, _aad_for_session(session))
    return pt.decode("utf-8")
