"""Layout and UI settings routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

router = APIRouter(tags=["settings"])

_LAYOUT_PATH: Path | None = None
_DEFAULT_LAYOUT = {
    "stochrsi": 130,
    "macd": 130,
    "dashboardPaneWidth": 320,
    "maxChartTabs": 5,
}


def configure_layout(data_dir: Path) -> None:
    global _LAYOUT_PATH
    _LAYOUT_PATH = data_dir / "layout.json"


def _layout_path() -> Path:
    if _LAYOUT_PATH is None:
        raise RuntimeError("settings router not configured")
    return _LAYOUT_PATH


@router.get("/api/layout")
def get_layout():
    path = _layout_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {**_DEFAULT_LAYOUT, **data}
        except Exception:
            pass
    return dict(_DEFAULT_LAYOUT)


@router.post("/api/layout")
def save_layout(payload: dict = Body(...)):
    path = _layout_path()
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
