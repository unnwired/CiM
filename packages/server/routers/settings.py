"""Layout and UI settings routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter(tags=["settings"])

_LAYOUT_PATH: Path | None = None
_BASE_DIR: Path | None = None
_DEFAULT_LAYOUT = {
    "stochrsi": 130,
    "macd": 130,
    "dashboardPaneWidth": 320,
    "maxChartTabs": 5,
}
# Only merge these from defaults when the user has no layout file yet.
# If layout.json exists without stochrsi/macd, omit them so the client does not
# treat server defaults as saved values (which blocked localStorage restore).
_INDICATOR_LAYOUT_KEYS = frozenset({"stochrsi", "macd", "panelOrder"})


def configure_layout(data_dir: Path) -> None:
    global _LAYOUT_PATH, _BASE_DIR
    _BASE_DIR = data_dir.parent if data_dir.name == "data" else data_dir
    _LAYOUT_PATH = data_dir / "layout.json"


def _layout_path(request: Request | None = None) -> Path:
    from server.product_config import is_web_host_mode
    from server.user_data_paths import maybe_migrate_legacy_user_files, user_file
    from server.web_auth import get_request_session, load_browser_session, require_request_session

    if _BASE_DIR and is_web_host_mode(_BASE_DIR) and request is not None:
        session = get_request_session()
        if not session:
            sid, loaded = load_browser_session(_BASE_DIR, request)
            if loaded:
                session = loaded
        if session:
            maybe_migrate_legacy_user_files(_BASE_DIR, session)
            return user_file(_BASE_DIR, "layout.json", session)
        require_request_session(request, _BASE_DIR)
    if _LAYOUT_PATH is None:
        raise RuntimeError("settings router not configured")
    return _LAYOUT_PATH


@router.get("/api/layout")
def get_layout(request: Request):
    path = _layout_path(request)
    if not path.exists():
        return dict(_DEFAULT_LAYOUT)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return dict(_DEFAULT_LAYOUT)
    except Exception:
        return dict(_DEFAULT_LAYOUT)
    base = {k: v for k, v in _DEFAULT_LAYOUT.items() if k not in _INDICATOR_LAYOUT_KEYS}
    return {**base, **data}


@router.post("/api/layout")
def save_layout(request: Request, payload: dict = Body(...)):
    path = _layout_path(request)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    current = loaded if isinstance(loaded, dict) else {}
            except Exception:
                current = {}
        merged = {**current, **(payload or {})}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        return {"status": "saved"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
