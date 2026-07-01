"""Per-user / per-machine instrument notes (never stored in shared market DB)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto
from server.core.install_root import get_data_dir
from server.user_data_paths import email_safe, user_lock

NOTES_FILENAME = "instrument_notes.json"
_INSTRUMENT_TYPES = frozenset({"stock", "index"})

_legacy_migrated = False
_legacy_migrate_lock = threading.Lock()


def normalize_instrument_type(value: str) -> str:
    it = (value or "stock").strip().lower()
    if it not in _INSTRUMENT_TYPES:
        raise ValueError("instrument_type must be stock or index")
    return it


def resolve_notes_namespace(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    """Directory for this user+machine (or _local+machine when unsigned)."""
    email = str((session or {}).get("email") or "").strip()
    machine = _crypto.current_machine_code().strip().upper()
    segment = email_safe(email) if email else "_local"
    ns = base_dir / "data" / "users" / segment / machine
    ns.mkdir(parents=True, exist_ok=True)
    return ns


def notes_file_path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_notes_namespace(base_dir, session) / NOTES_FILENAME


def _load_notes_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_notes_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _maybe_migrate_legacy_table(base_dir: Path, namespace_dir: Path, notes_path: Path) -> None:
    """Move legacy shared DB notes into _local namespace once, then clear the table."""
    global _legacy_migrated
    if namespace_dir.parent.name != "_local":
        return
    if notes_path.is_file():
        return

    with _legacy_migrate_lock:
        if _legacy_migrated or notes_path.is_file():
            return
        db_path = get_data_dir(base_dir) / "nse_data.db"
        if not db_path.is_file():
            _legacy_migrated = True
            return
        payload: dict[str, Any] = {}
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT symbol, instrument_type, note_text FROM instrument_notes"
                ).fetchall()
                for row in rows:
                    sym = str(row["symbol"] or "").strip()
                    it = str(row["instrument_type"] or "stock").strip().lower()
                    text = row["note_text"] if row["note_text"] is not None else ""
                    if not sym or it not in _INSTRUMENT_TYPES:
                        continue
                    payload.setdefault(sym, {})[it] = str(text)
                if payload:
                    _save_notes_file(notes_path, payload)
                conn.execute("DELETE FROM instrument_notes")
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error:
            return
        _legacy_migrated = True


def load_note(
    base_dir: Path,
    symbol: str,
    instrument_type: str,
    session: Optional[dict[str, Any]] = None,
) -> str:
    it = normalize_instrument_type(instrument_type)
    sym = str(symbol or "").strip()
    if not sym:
        return ""
    with user_lock(base_dir, session):
        ns = resolve_notes_namespace(base_dir, session)
        path = ns / NOTES_FILENAME
        _maybe_migrate_legacy_table(base_dir, ns, path)
        data = _load_notes_file(path)
        entry = data.get(sym)
        if not isinstance(entry, dict):
            return ""
        note = entry.get(it, "")
        return note if isinstance(note, str) else str(note or "")


def has_note(
    base_dir: Path,
    symbol: str,
    instrument_type: str,
    session: Optional[dict[str, Any]] = None,
) -> bool:
    return bool(load_note(base_dir, symbol, instrument_type, session).strip())


def save_note(
    base_dir: Path,
    symbol: str,
    instrument_type: str,
    note: str,
    session: Optional[dict[str, Any]] = None,
) -> None:
    it = normalize_instrument_type(instrument_type)
    sym = str(symbol or "").strip()
    if not sym:
        raise ValueError("symbol required")
    if not isinstance(note, str):
        raise ValueError("note must be a string")
    if len(note) > 100_000:
        raise ValueError("note too large")

    with user_lock(base_dir, session):
        ns = resolve_notes_namespace(base_dir, session)
        path = ns / NOTES_FILENAME
        _maybe_migrate_legacy_table(base_dir, ns, path)
        data = _load_notes_file(path)
        if not note.strip():
            if sym in data:
                entry = data[sym]
                if isinstance(entry, dict):
                    entry.pop(it, None)
                    if not entry:
                        data.pop(sym, None)
        else:
            data.setdefault(sym, {})[it] = note
        _save_notes_file(path, data)


def clear_instrument_notes_table(db_path: Path) -> int:
    """Export sanitizer: remove all rows from legacy shared table."""
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            count_row = conn.execute("SELECT COUNT(*) FROM instrument_notes").fetchone()
            removed = int(count_row[0]) if count_row else 0
        except sqlite3.Error:
            return 0
        conn.execute("DELETE FROM instrument_notes")
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM instrument_notes").fetchone()
        if remaining and int(remaining[0]) != 0:
            raise RuntimeError("instrument_notes table not empty after DELETE")
        return removed
    finally:
        conn.close()
