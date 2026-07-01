"""
Charts In Motion GitHub Releases update provider (unnwired/CiM-Updates).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from http_ssl import https_ssl_context

USER_AGENT = "CiM-Update/1.0"
GITHUB_API_ACCEPT = "application/vnd.github+json"

DEFAULT_OWNER = "unnwired"
DEFAULT_REPO = "CiM-Updates"
DEFAULT_ASSET_PREFIX = "CiM-Update-"
DEFAULT_ASSET_SUFFIX = ".zip"

_install_root: Optional[Path] = None
_config_path: Optional[Path] = None


def configure_paths(install_root: Path) -> None:
    global _install_root, _config_path
    _install_root = Path(install_root)
    _config_path = _install_root / "config" / "github_updates.json"


def _root() -> Path:
    if _install_root is not None:
        return _install_root
    from server.core.install_root import get_install_root

    return get_install_root()


def _config_file() -> Path:
    if _config_path is not None:
        return _config_path
    return _root() / "config" / "github_updates.json"


def _staging_root() -> Path:
    return Path(os.getenv("LOCALAPPDATA", "")) / "CiM" / "update-staging"


def _update_dir() -> Path:
    return _root() / "UPDATE"


def _log_dir() -> Path:
    d = _root() / "runtime" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_log(line: str) -> None:
    log_file = _log_dir() / "update-download.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line}\n")


def load_github_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "owner": DEFAULT_OWNER,
        "repo": DEFAULT_REPO,
        "assetPrefix": DEFAULT_ASSET_PREFIX,
        "assetSuffix": DEFAULT_ASSET_SUFFIX,
        "checkIntervalMinutes": 90,
        "backgroundCheckEnabled": True,
    }
    path = _config_file()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass
    owner = os.getenv("CIM_GITHUB_OWNER", "").strip()
    repo = os.getenv("CIM_GITHUB_REPO", "").strip()
    if owner:
        cfg["owner"] = owner
    if repo:
        cfg["repo"] = repo
    return cfg


def parse_version_tuple(v: str) -> Tuple[int, ...]:
    text = str(v).strip().lstrip("\ufeff")
    parts = []
    for piece in re.split(r"[.\-]", text):
        if not piece:
            continue
        m = re.match(r"^(\d+)", piece)
        parts.append(int(m.group(1)) if m else 0)
    return tuple(parts) if parts else (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    return parse_version_tuple(candidate) > parse_version_tuple(current)


def version_from_release(tag_name: str, asset_name: str = "") -> str:
    for src in (asset_name, tag_name):
        if not src:
            continue
        m = re.search(r"CiM-Update-(\d+(?:\.\d+)*)", src, re.I)
        if m:
            return m.group(1)
        m = re.search(r"v?(\d+(?:\.\d+)*)", src, re.I)
        if m:
            return m.group(1)
    return tag_name.lstrip("vV").strip() or "0.0.0"


def _github_request(url: str, timeout: int = 30) -> Any:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": GITHUB_API_ACCEPT,
        },
    )
    with urlopen(req, timeout=timeout, context=https_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_latest_release(cfg: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    cfg = cfg or load_github_config()
    owner = str(cfg.get("owner", DEFAULT_OWNER)).strip()
    repo = str(cfg.get("repo", DEFAULT_REPO)).strip()
    if not owner or not repo:
        return None
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        data = _github_request(url)
        return data if isinstance(data, dict) else None
    except HTTPError as e:
        if e.code == 404:
            return None
        raise
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        raise RuntimeError(f"GitHub release check failed: {e}") from e


def pick_release_asset(
    release: Dict[str, Any],
    cfg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    cfg = cfg or load_github_config()
    prefix = str(cfg.get("assetPrefix", DEFAULT_ASSET_PREFIX))
    suffix = str(cfg.get("assetSuffix", DEFAULT_ASSET_SUFFIX))
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return None
    tag = str(release.get("tag_name", ""))
    expected_version = version_from_release(tag, "")
    candidates = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", ""))
        if not name.startswith(prefix) or not name.endswith(suffix):
            continue
        if expected_version and expected_version not in name:
            continue
        candidates.append(asset)
    if not candidates and assets:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            if name.startswith(prefix) and name.endswith(suffix):
                candidates.append(asset)
    if not candidates:
        return None
    return candidates[0]


def check_github_update(current: str) -> Optional[Dict[str, Any]]:
    cfg = load_github_config()
    release = fetch_latest_release(cfg)
    if not release:
        return None
    asset = pick_release_asset(release, cfg)
    if not asset:
        return None
    tag = str(release.get("tag_name", ""))
    asset_name = str(asset.get("name", ""))
    ver = version_from_release(tag, asset_name)
    if not is_newer_version(ver, current):
        return None
    download_url = str(asset.get("browser_download_url", "")).strip()
    if not download_url:
        return None
    return {
        "source": "github",
        "version": ver,
        "releaseTag": tag,
        "assetName": asset_name,
        "downloadUrl": download_url,
        "repo": f"{cfg.get('owner')}/{cfg.get('repo')}",
    }


def _download_bytes(url: str, timeout: int = 600) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout, context=https_ssl_context()) as resp:
        return resp.read()


def _normalize_extracted_root(extract_dir: Path, target_dir: Path) -> None:
    """If ZIP has a single top-level CiM-Update-* folder, hoist contents to target_dir."""
    if not extract_dir.is_dir():
        raise ValueError(f"Extract dir missing: {extract_dir}")
    entries = [p for p in extract_dir.iterdir() if p.name not in (".", "..")]
    if len(entries) == 1 and entries[0].is_dir() and entries[0].name.startswith("CiM-Update"):
        inner = entries[0]
        target_dir.mkdir(parents=True, exist_ok=True)
        for child in inner.iterdir():
            dest = target_dir / child.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(child), str(dest))
        shutil.rmtree(inner, ignore_errors=True)
        return
    if extract_dir.resolve() != target_dir.resolve():
        target_dir.mkdir(parents=True, exist_ok=True)
        for child in extract_dir.iterdir():
            dest = target_dir / child.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(child), str(dest))


def download_and_extract_zip(asset_url: str, version: str) -> Path:
    """Download release ZIP to staging and extract into UPDATE/CiM-Update-{version}/."""
    ver = str(version).strip()
    if not ver:
        raise ValueError("version required")
    staging = _staging_root() / ver
    zip_path = staging / "package.zip"
    extract_tmp = staging / "_extract"
    target_dir = _update_dir() / f"CiM-Update-{ver}"

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    extract_tmp.mkdir(parents=True, exist_ok=True)

    _append_log(f"GitHub download started (version={ver})")
    try:
        data = _download_bytes(asset_url)
        zip_path.write_bytes(data)
        _append_log(f"Downloaded {len(data)} bytes to {zip_path}")

        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_tmp)

        _normalize_extracted_root(extract_tmp, target_dir)

        manifest_path = target_dir / "update.manifest.json"
        payload_dir = target_dir / "payload"
        if not manifest_path.is_file() or not payload_dir.is_dir():
            raise ValueError(
                "Update package invalid after extract "
                f"(need update.manifest.json and payload\\ under {target_dir})"
            )

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            mf_ver = str(manifest.get("version", "")).strip()
            if mf_ver and mf_ver != ver:
                _append_log(f"Warning: manifest version {mf_ver} != release {ver}")
        except Exception:
            pass

        _append_log(f"Extracted to {target_dir}")
        return target_dir
    finally:
        if extract_tmp.exists():
            shutil.rmtree(extract_tmp, ignore_errors=True)


def get_client_settings() -> Dict[str, Any]:
    cfg = load_github_config()
    return {
        "checkIntervalMinutes": int(cfg.get("checkIntervalMinutes") or 90),
        "backgroundCheckEnabled": bool(cfg.get("backgroundCheckEnabled", True)),
        "repo": f"{cfg.get('owner')}/{cfg.get('repo')}",
    }
