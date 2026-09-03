"""Per-account interest basket (persistent symbol tray; never in shared market DB)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto
from server.user_data_paths import email_safe, user_lock

BASKET_FILENAME = "user_basket.json"
MAX_SYMBOLS = 200
ALLOWED_KINDS = frozenset({"stock", "index"})


def resolve_user_basket_namespace(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    email = str((session or {}).get("email") or "").strip()
    machine = _crypto.current_machine_code().strip().upper()
    segment = email_safe(email) if email else "_local"
    ns = base_dir / "data" / "users" / segment / machine
    ns.mkdir(parents=True, exist_ok=True)
    return ns


def _basket_path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_user_basket_namespace(base_dir, session) / BASKET_FILENAME


def _empty_doc() -> dict[str, Any]:
    return {"symbols": []}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _normalize_entry(raw: Any) -> Optional[dict[str, Any]]:
    if isinstance(raw, str):
        sym = raw.strip().upper()
        if not sym:
            return None
        return {"symbol": sym, "kind": "stock", "addedAt": _utc_now_iso()}
    if not isinstance(raw, dict):
        return None
    sym = str(raw.get("symbol") or "").strip().upper()
    if not sym:
        return None
    kind = str(raw.get("kind") or "stock").strip().lower()
    if kind not in ALLOWED_KINDS:
        kind = "stock"
    added = str(raw.get("addedAt") or raw.get("added_at") or "").strip() or _utc_now_iso()
    return {"symbol": sym, "kind": kind, "addedAt": added}


def normalize_doc(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("basket payload must be an object")
    rows_raw = raw.get("symbols")
    if rows_raw is None:
        rows_raw = []
    if not isinstance(rows_raw, list):
        raise ValueError("symbols must be a list")
    if len(rows_raw) > MAX_SYMBOLS:
        raise ValueError(f"too many basket symbols (max {MAX_SYMBOLS})")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in rows_raw:
        entry = _normalize_entry(item)
        if entry is None:
            continue
        key = (entry["symbol"], entry["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return {"symbols": out}


def load_doc(base_dir: Path, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _basket_path(base_dir, session)
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
        path = _basket_path(base_dir, session)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return normalized


def add_symbol(
    base_dir: Path,
    symbol: str,
    *,
    kind: str = "stock",
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    entry = _normalize_entry({"symbol": symbol, "kind": kind})
    if entry is None:
        raise ValueError("invalid symbol")
    doc = load_doc(base_dir, session=session)
    key = (entry["symbol"], entry["kind"])
    existing = {(e["symbol"], e["kind"]) for e in doc["symbols"]}
    if key not in existing:
        if len(doc["symbols"]) >= MAX_SYMBOLS:
            raise ValueError(f"too many basket symbols (max {MAX_SYMBOLS})")
        doc["symbols"].append(entry)
        return save_doc(base_dir, doc, session=session)
    return doc


def remove_symbol(
    base_dir: Path,
    symbol: str,
    *,
    kind: str | None = None,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("invalid symbol")
    kind_n = str(kind or "").strip().lower() or None
    if kind_n and kind_n not in ALLOWED_KINDS:
        kind_n = None
    doc = load_doc(base_dir, session=session)
    next_rows = [
        e for e in doc["symbols"]
        if not (
            e["symbol"] == sym
            and (kind_n is None or e["kind"] == kind_n)
        )
    ]
    return save_doc(base_dir, {"symbols": next_rows}, session=session)
