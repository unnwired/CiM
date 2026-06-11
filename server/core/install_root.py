"""Install root path guard for dev vs encrypted distribution."""

from __future__ import annotations

import os
from pathlib import Path

_INSTALL_ROOT: Path | None = None


def get_install_root() -> Path:
    """Return the Charts In Motion install root (repo root in dev)."""
    global _INSTALL_ROOT
    if _INSTALL_ROOT is not None:
        return _INSTALL_ROOT
    env_root = os.getenv("CIM_INSTALL_ROOT", "").strip()
    if env_root:
        _INSTALL_ROOT = Path(env_root).resolve()
        return _INSTALL_ROOT
    # server/core/install_root.py -> server -> repo root
    _INSTALL_ROOT = Path(__file__).resolve().parent.parent.parent
    return _INSTALL_ROOT


def set_install_root(path: Path) -> None:
    """Called by cim_bootstrap when repointing encrypted distribution paths."""
    global _INSTALL_ROOT
    _INSTALL_ROOT = Path(path).resolve()


def resolve_from_install_root(*parts: str) -> Path:
    return get_install_root().joinpath(*parts)
