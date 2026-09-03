"""Per-account mutual fund favorites (scheme codes)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto
from server.user_data_paths import email_safe, user_lock

FAVORITES_FILENAME = "mf_favorites.json"
MAX_FAVORITES = 500


def resolve_mf_favorites_namespace(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    email = str((session or {}).get("email") or "").strip()
    machine = _crypto.current_machine_code().strip().upper()
    segment = email_safe(email) if email else "_local"
    ns = base_dir / "data" / "users" / segment / machine
    ns.mkdir(parents=True, exist_ok=True)
    return ns


def _path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_mf_favorites_namespace(base_dir, session) / FAVORITES_FILENAME


def _normalize_codes(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("scheme_codes must be a list")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        code = str(item or "").strip()
        if not code or not code.isdigit() or code in seen:
            continue
        seen.add(code)
        out.append(code)
        if len(out) >= MAX_FAVORITES:
            break
    return out


def load_favorites(base_dir: Path, session: Optional[dict[str, Any]] = None) -> list[str]:
    with user_lock(base_dir, session):
        p = _path(base_dir, session)
        if not p.exists():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(raw, dict):
            return _normalize_codes(raw.get("scheme_codes"))
        return _normalize_codes(raw)


def save_favorites(
    base_dir: Path,
    scheme_codes: Any,
    session: Optional[dict[str, Any]] = None,
) -> list[str]:
    codes = _normalize_codes(scheme_codes)
    with user_lock(base_dir, session):
        p = _path(base_dir, session)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"scheme_codes": codes}, indent=2),
            encoding="utf-8",
        )
    return codes
