"""Per-browser session files for web host showcase mode."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto
from server.license_client import (
    SESSION_VERSION,
    _decrypt_session_payload,
    _encrypt_session_payload,
    device_id,
)

_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.I)


def sessions_dir(base_dir: Path) -> Path:
    return base_dir / "data" / "sessions"


def _session_file(base_dir: Path, session_id: str) -> Path:
    sid = str(session_id or "").strip().lower()
    if not _SESSION_ID_RE.match(sid):
        raise ValueError("invalid session id")
    return sessions_dir(base_dir) / f"{sid}.json"


def create_session(base_dir: Path, data: dict[str, Any]) -> str:
    session_id = uuid.uuid4().hex
    save_session_by_id(base_dir, session_id, data)
    return session_id


def load_session_by_id(base_dir: Path, session_id: str) -> Optional[dict[str, Any]]:
    if not session_id:
        return None
    path = _session_file(base_dir, session_id)
    if not path.is_file():
        return None
    try:
        blob = path.read_bytes()
        if blob.startswith(_crypto.MAGIC):
            plain = _decrypt_session_payload(blob, base_dir)
        else:
            plain = blob
        data = json.loads(plain.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_session_by_id(base_dir: Path, session_id: str, data: dict[str, Any]) -> None:
    path = _session_file(base_dir, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["version"] = SESSION_VERSION
    payload["device_id"] = device_id()
    plain = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    path.write_bytes(_encrypt_session_payload(plain, base_dir))


def delete_session_by_id(base_dir: Path, session_id: str) -> None:
    if not session_id:
        return
    try:
        path = _session_file(base_dir, session_id)
    except ValueError:
        return
    if path.is_file():
        path.unlink()


def clear_all_sessions(base_dir: Path) -> None:
    root = sessions_dir(base_dir)
    if not root.is_dir():
        return
    for path in root.glob("*.json"):
        try:
            path.unlink()
        except OSError:
            pass
