"""Upstox market-data configuration (Analytics Token from environment or local .env)."""
from __future__ import annotations

import os
from pathlib import Path

_DOTENV_LOADED = False


def _candidate_env_files() -> list[Path]:
    paths: list[Path] = []
    install = os.getenv("CIM_INSTALL_ROOT", "").strip()
    if install:
        paths.append(Path(install) / ".env")
    # packages/server/upstox_config.py -> parents[2] = repo or install root when layout is packages/server
    here = Path(__file__).resolve()
    for parent in here.parents:
        paths.append(parent / ".env")
        if len(paths) > 8:
            break
    paths.append(Path.cwd() / ".env")
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _ensure_dotenv() -> None:
    """Load UPSTOX_* from the first readable .env if not already in the process env."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    if os.getenv("UPSTOX_ANALYTICS_TOKEN", "").strip():
        return
    keys = ("UPSTOX_ANALYTICS_TOKEN", "CIM_UPSTOX_DISABLED")
    for path in _candidate_env_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        found = False
        for line in text.splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, _, v = raw.partition("=")
            k = k.strip()
            if k not in keys:
                continue
            if os.getenv(k, "").strip():
                continue
            val = v.strip().strip("'").strip('"')
            os.environ[k] = val
            found = True
        if found:
            return


def analytics_token() -> str:
    _ensure_dotenv()
    return os.getenv("UPSTOX_ANALYTICS_TOKEN", "").strip()


def is_disabled() -> bool:
    _ensure_dotenv()
    raw = os.getenv("CIM_UPSTOX_DISABLED", "").strip().lower()
    return raw in ("1", "true", "yes")


def is_configured() -> bool:
    return bool(analytics_token())


def market_data_enabled() -> bool:
    """True when Analytics Token is set and Upstox has not been opted out."""
    return is_configured() and not is_disabled()
