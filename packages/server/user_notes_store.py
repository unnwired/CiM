"""Per-account universal notes (tabbed floating notepad; never in shared market DB)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto
from server.user_data_paths import email_safe, user_lock

NOTES_FILENAME = "user_notes.json"
MAX_TABS = 300
MAX_TITLE_LEN = 200
MAX_TEXT_LEN = 200_000


def resolve_user_notes_namespace(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    """Directory for this user+machine (or _local+machine when unsigned)."""
    email = str((session or {}).get("email") or "").strip()
    machine = _crypto.current_machine_code().strip().upper()
    segment = email_safe(email) if email else "_local"
    ns = base_dir / "data" / "users" / segment / machine
    ns.mkdir(parents=True, exist_ok=True)
    return ns


def _notes_path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_user_notes_namespace(base_dir, session) / NOTES_FILENAME


def _empty_doc() -> dict[str, Any]:
    return {"tabs": []}


def _normalize_tab(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    title = raw.get("title")
    text = raw.get("text")
    if title is not None and not isinstance(title, str):
        raise ValueError("tab title must be a string")
    if text is not None and not isinstance(text, str):
        raise ValueError("tab text must be a string")
    title = (title or "").strip()[:MAX_TITLE_LEN]
    text = text or ""
    if len(text) > MAX_TEXT_LEN:
        raise ValueError("note too large")
    tab_id = str(raw.get("id") or "").strip() or str(uuid.uuid4())
    return {
        "id": tab_id,
        "title": title,
        "text": text,
        "archived": bool(raw.get("archived")),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def normalize_doc(raw: Any) -> dict[str, Any]:
    """Validate/normalize a notes document; raises ValueError on bad payload."""
    if not isinstance(raw, dict):
        raise ValueError("notes payload must be an object")
    tabs_raw = raw.get("tabs")
    if tabs_raw is None:
        tabs_raw = []
    if not isinstance(tabs_raw, list):
        raise ValueError("tabs must be a list")
    if len(tabs_raw) > MAX_TABS:
        raise ValueError(f"too many note tabs (max {MAX_TABS})")
    tabs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in tabs_raw:
        tab = _normalize_tab(item)
        if tab is None:
            continue
        if tab["id"] in seen_ids:
            tab["id"] = str(uuid.uuid4())
        seen_ids.add(tab["id"])
        tabs.append(tab)
    return {"tabs": tabs}


def load_doc(base_dir: Path, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _notes_path(base_dir, session)
        if not path.is_file():
            return _empty_doc()
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return _empty_doc()
        try:
            return normalize_doc(raw)
        except ValueError:
            return _empty_doc()


def save_doc(base_dir: Path, doc: Any, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    normalized = normalize_doc(doc)
    with user_lock(base_dir, session):
        path = _notes_path(base_dir, session)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return normalized
