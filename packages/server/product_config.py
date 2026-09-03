"""Charts In Motion (CiM) product identity — single source for Python runtime."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

def _repo_root() -> Path:
    from server.core.install_root import get_install_root

    return get_install_root()


_PRODUCT_JSON = _repo_root() / "config" / "product.json"


@lru_cache(maxsize=1)
def load_product_config() -> dict[str, Any]:
    if _PRODUCT_JSON.is_file():
        with open(_PRODUCT_JSON, encoding="utf-8-sig") as f:
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


def session_file_rel() -> str:
    return str(load_product_config().get("sessionFile") or "data/.cim-session.json")


def license_api_url() -> str:
    return os.getenv("CIM_LICENSE_API_URL", "").strip() or str(
        load_product_config().get("licenseApiUrl") or "https://chartsinmotion.chartsinmotion.workers.dev"
    )


def offline_grace_days() -> int:
    raw = load_product_config().get("offlineGraceDays", 7)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 7


def max_devices_per_account() -> int:
    raw = load_product_config().get("maxDevicesPerAccount", 2)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 2


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


def require_online_auth() -> bool:
    """When set, dev trees use the sign-in shell until a valid online session exists."""
    return env_flag("CIM_REQUIRE_ONLINE_AUTH")


def is_web_host_mode(base_dir: Path | None = None) -> bool:
    """Browser showcase host: per-browser cookie sessions, shared market DB."""
    if env_flag("CIM_WEB_HOST"):
        return True
    root = base_dir or _repo_root()
    return (root / "config" / ".cim-web-host").is_file()


def is_showcase_host(base_dir: Path | None = None) -> bool:
    """This install may mutate shared market data (EOD jobs, admin routes)."""
    if env_flag("CIM_SHOWCASE_HOST"):
        return True
    root = base_dir or _repo_root()
    return (root / "config" / ".cim-showcase-host").is_file()


def showcase_host_allowed_for_request(request, base_dir: Path | None = None) -> bool:
    """Only loopback clients may run host-only admin/EOD routes in browser showcase mode."""
    client = getattr(request, "client", None)
    host = (getattr(client, "host", None) or "").strip()
    return host in ("127.0.0.1", "::1", "localhost")


def online_only_activation() -> bool:
    """When true, distribution installs skip vendor install keys (online session only)."""
    if env_flag("CIM_ONLINE_ONLY"):
        return True
    return bool(load_product_config().get("onlineOnlyActivation"))


def _showcase_host_settings(base_dir: Path | None = None) -> dict[str, Any]:
    root = base_dir or _repo_root()
    path = root / "config" / "showcase_host.json"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def yahoo_primary_pipeline(base_dir: Path | None = None) -> bool:
    """
    Skip full-universe NSE quote-equity scrape on Admin Update / price refresh.

    Market data is Upstox-first (charts, movers, screener quotes); NSE bulk scrape
    only triggers WAF "NSE block detected" noise. Default ON for all installs
    (desktop + showcase). Opt out with showcase_host.json yahooPrimaryPipeline=false
    or CIM_YAHOO_PRIMARY_PIPELINE=0.
    """
    raw = os.getenv("CIM_YAHOO_PRIMARY_PIPELINE", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    settings = _showcase_host_settings(base_dir)
    if settings.get("yahooPrimaryPipeline") is True:
        return True
    if settings.get("yahooPrimaryPipeline") is False:
        return False
    # Default on everywhere — desktop had no showcase_host.json and kept hitting NSE.
    return True
