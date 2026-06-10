"""Charts In Motion (CiM) product identity — single source for Python runtime."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRODUCT_JSON = _REPO_ROOT / "config" / "product.json"


@lru_cache(maxsize=1)
def load_product_config() -> dict[str, Any]:
    if _PRODUCT_JSON.is_file():
        with open(_PRODUCT_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {
        "displayName": "Charts In Motion",
        "displayNameDev": "Charts In Motion Dev",
        "slug": "CiM",
        "localAppDataFolder": "CiM",
        "desktopFolder": "CiMDesktop",
        "licenseFile": "data/.cim-license",
        "bootstrapModule": "server.cim_bootstrap:app",
        "updateZipPrefix": "CiM-Update-",
        "githubOwner": "unnwired",
        "githubRepo": "CiM-Updates",
        "exportFolderName": "CiM",
    }


def display_name(dev: bool = False) -> str:
    cfg = load_product_config()
    return cfg["displayNameDev"] if dev else cfg["displayName"]


def local_appdata_folder() -> str:
    return str(load_product_config().get("localAppDataFolder") or "CiM")


def license_file_rel() -> str:
    return str(load_product_config().get("licenseFile") or "data/.cim-license")


def update_zip_prefix() -> str:
    return str(load_product_config().get("updateZipPrefix") or "CiM-Update-")


def github_owner() -> str:
    return os.getenv("CIM_GITHUB_OWNER", "").strip() or load_product_config().get("githubOwner", "unnwired")


def github_repo() -> str:
    return os.getenv("CIM_GITHUB_REPO", "").strip() or load_product_config().get("githubRepo", "CiM-Updates")


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def is_dev_env() -> bool:
    return env_flag("CIM_DEV")
