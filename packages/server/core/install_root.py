"""Install root path guard for dev vs encrypted distribution."""

from __future__ import annotations

import os
from pathlib import Path

_INSTALL_ROOT: Path | None = None


def _detect_install_root() -> Path:
    """Walk up from server/core until we find the Charts In Motion install / repo root."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "data" / "nse_data.db").is_file():
            return candidate
        if (candidate / "db_sqlite.py").is_file() and (candidate / "runtime").is_dir():
            return candidate
        if (candidate / "version.txt").is_file() and (candidate / "runtime" / "python").is_dir():
            return candidate
    # Export layout: install/server/core -> install root
    return here.parent.parent.parent


def get_install_root() -> Path:
    """Return the Charts In Motion install root (repo root in dev)."""
    global _INSTALL_ROOT
    if _INSTALL_ROOT is not None:
        return _INSTALL_ROOT
    env_root = os.getenv("CIM_INSTALL_ROOT", "").strip()
    if env_root:
        _INSTALL_ROOT = Path(env_root).resolve()
        return _INSTALL_ROOT
    _INSTALL_ROOT = _detect_install_root()
    return _INSTALL_ROOT


def set_install_root(path: Path) -> None:
    """Called by cim_bootstrap when repointing encrypted distribution paths."""
    global _INSTALL_ROOT
    _INSTALL_ROOT = Path(path).resolve()


def resolve_from_install_root(*parts: str) -> Path:
    return get_install_root().joinpath(*parts)


def resolve_frontend_build_dir(install_root: Path | None = None) -> Path:
    """Dev repo uses packages/browser/build; exports use frontend/build."""
    root = install_root or get_install_root()
    for rel in ("packages/browser/build", "frontend/build"):
        candidate = root / rel
        if (candidate / "index.html").is_file():
            return candidate
    return root / "frontend" / "build"


def get_data_dir(install_root: Path | None = None) -> Path:
    """Canonical data\ folder under install / repo root."""
    return (install_root or get_install_root()) / "data"
