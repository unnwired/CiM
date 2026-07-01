"""Per-user data directories for web host mode (email + host machine code)."""
from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto
from server.product_config import is_web_host_mode
from server.web_auth import get_request_session

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

_LEGACY_FILES = (
    "watchlists.json",
    "portfolio.json",
    "layout.json",
    "saved_filters.json",
)


def email_safe(email: str) -> str:
    raw = str(email or "").strip().lower()
    if not raw:
        return "unknown"
    out = raw.replace("@", "_at_")
    out = re.sub(r"[^a-z0-9._-]+", "_", out)
    return out[:120] or "unknown"


def user_namespace_dir(base_dir: Path, session: dict[str, Any]) -> Path:
    email = str(session.get("email") or "unknown")
    device = _crypto.current_machine_code().strip().upper()
    return base_dir / "data" / "users" / email_safe(email) / device


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def user_lock(base_dir: Path, session: Optional[dict[str, Any]] = None) -> threading.Lock:
    session = session or get_request_session()
    if session and is_web_host_mode(base_dir):
        return _lock_for(user_namespace_dir(base_dir, session))
    return _lock_for(base_dir / "data")


def resolve_user_dir(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    session = session or get_request_session()
    if session and is_web_host_mode(base_dir):
        return user_namespace_dir(base_dir, session)
    return base_dir / "data"


def user_file(base_dir: Path, name: str, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_user_dir(base_dir, session) / name


def maybe_migrate_legacy_user_files(base_dir: Path, session: dict[str, Any]) -> None:
    if not is_web_host_mode(base_dir):
        return
    user_dir = user_namespace_dir(base_dir, session)
    user_dir.mkdir(parents=True, exist_ok=True)
    legacy_dir = base_dir / "data"
    for name in _LEGACY_FILES:
        dst = user_dir / name
        if dst.exists():
            continue
        src = legacy_dir / name
        if src.is_file():
            try:
                shutil.copy2(src, dst)
            except OSError:
                pass


def purge_e2e_user_dirs(base_dir: Path) -> None:
    users_root = base_dir / "data" / "users"
    if not users_root.is_dir():
        return
    for email_dir in users_root.iterdir():
        if not email_dir.is_dir():
            continue
        if "cim-e2e" in email_dir.name or email_dir.name.endswith("_at_example.com"):
            shutil.rmtree(email_dir, ignore_errors=True)


def reset_global_user_json(base_dir: Path) -> None:
    data = base_dir / "data"
    defaults = {
        "watchlists.json": [],
        "portfolio.json": {"items": []},
        "layout.json": {},
        "saved_filters.json": [],
    }
    for name, content in defaults.items():
        path = data / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)
        except OSError:
            pass
