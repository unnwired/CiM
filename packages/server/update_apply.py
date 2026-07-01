"""

Charts In Motion in-app update: local UPDATE folder first, GitHub Releases second.

"""

from __future__ import annotations



import json

import os

import subprocess

from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple



from fastapi import APIRouter, Body, HTTPException, Query



import github_updates

from server.core.install_root import get_install_root

BASE_DIR = get_install_root()

UPDATE_DIR = BASE_DIR / "UPDATE"

VERSION_FILE = BASE_DIR / "version.txt"

CONFIG_GITHUB = BASE_DIR / "config" / "github_updates.json"

APPLY_SCRIPT = BASE_DIR / "scripts" / "CiMApplyUpdate.ps1"

PENDING_FILE = BASE_DIR / "runtime" / "logs" / "update-pending.json"

github_updates.configure_paths(BASE_DIR)



PROTECTED_REL = frozenset({

    "data/watchlists.json",

    "data/portfolio.json",

    "data/layout.json",

    "data/saved_filters.json",

    "data/screener_session.json",

    "data/.cim-license",

    "data/.cim-session.json",

})



router = APIRouter(prefix="/api/update", tags=["update"])





def configure_install_root(base_dir: Path) -> None:

    """Encrypted runtime imports can live in app-cache; update files stay in install root."""

    global BASE_DIR, UPDATE_DIR, VERSION_FILE, CONFIG_GITHUB, APPLY_SCRIPT, PENDING_FILE



    BASE_DIR = Path(base_dir)

    UPDATE_DIR = BASE_DIR / "UPDATE"

    VERSION_FILE = BASE_DIR / "version.txt"

    CONFIG_GITHUB = BASE_DIR / "config" / "github_updates.json"

    APPLY_SCRIPT = BASE_DIR / "scripts" / "CiMApplyUpdate.ps1"

    PENDING_FILE = BASE_DIR / "runtime" / "logs" / "update-pending.json"

    github_updates.configure_paths(BASE_DIR)





def _read_version() -> str:

    if VERSION_FILE.exists():

        raw = VERSION_FILE.read_text(encoding="utf-8-sig", errors="ignore").strip()

        return raw.lstrip("\ufeff") or "0.0.0"

    return "0.0.0"





def _parse_version(v: str) -> Tuple[int, ...]:

    return github_updates.parse_version_tuple(v)





def _is_newer(candidate: str, current: str) -> bool:

    return github_updates.is_newer_version(candidate, current)





def _load_json(path: Path) -> Dict[str, Any]:

    return json.loads(path.read_text(encoding="utf-8-sig"))





def _validate_manifest(manifest: Dict[str, Any]) -> None:

    if not manifest.get("version"):

        raise ValueError("manifest missing version")

    files = manifest.get("files")

    if not isinstance(files, list) or len(files) == 0:

        raise ValueError("manifest files[] empty")

    for entry in files:

        rel = str(entry.get("path", "")).replace("\\", "/")

        if rel in PROTECTED_REL or rel.startswith("data/screener_profile/") or rel.startswith("data/users/"):

            raise ValueError(f"manifest must not include protected path: {rel}")

        if not rel:

            raise ValueError("manifest entry missing path")





def _local_update_package_roots() -> List[Path]:

    roots: List[Path] = []

    if not UPDATE_DIR.is_dir():

        return roots

    flat_manifest = UPDATE_DIR / "update.manifest.json"

    flat_payload = UPDATE_DIR / "payload"

    if flat_manifest.exists() and flat_payload.is_dir():

        roots.append(UPDATE_DIR)

    for child in sorted(UPDATE_DIR.iterdir()):

        if not child.is_dir() or not child.name.startswith("CiM-Update"):

            continue

        if (child / "update.manifest.json").is_file() and (child / "payload").is_dir():

            roots.append(child)

    return roots





def _local_payload_root(package_root: Path) -> Path:

    p = package_root / "payload"

    return p if p.is_dir() else package_root





def _check_local_package(

    package_root: Path,

    current: str,

    *,

    validate_files: bool = True,

) -> Optional[Dict[str, Any]]:

    mf = package_root / "update.manifest.json"

    if not mf.exists():

        return None

    manifest = _load_json(mf)

    _validate_manifest(manifest)

    ver = str(manifest["version"])

    if not _is_newer(ver, current):

        return None

    if validate_files:

        payload_root = _local_payload_root(package_root)

        missing = []

        for entry in manifest["files"]:

            rel = str(entry["path"]).replace("\\", "/")

            if not (payload_root / rel.replace("/", os.sep)).is_file():

                missing.append(rel)

        if missing:

            raise HTTPException(

                400,

                detail={"error": "missing_local_payload", "paths": missing[:20]},

            )

    return {

        "source": "local",

        "version": ver,

        "minAppVersion": manifest.get("minAppVersion", ""),

        "fileCount": len(manifest["files"]),

        "manifestPath": str(mf),

        "sourceDir": str(package_root),

        "manifest": manifest,

    }





def _check_local(current: str, *, validate_files: bool = True) -> Optional[Dict[str, Any]]:

    best: Optional[Dict[str, Any]] = None

    for package_root in _local_update_package_roots():

        try:

            info = _check_local_package(

                package_root, current, validate_files=validate_files

            )

        except HTTPException as e:

            raise e

        except Exception as e:

            err_local = err_local or str(e)

            continue

        if not info:

            continue

        if not best or _parse_version(info["version"]) > _parse_version(best["version"]):

            best = info

    return best





def _check_github(current: str) -> Optional[Dict[str, Any]]:

    try:

        return github_updates.check_github_update(current)

    except Exception as e:

        raise HTTPException(502, detail=f"GitHub update check failed: {e}") from e





def _pick_update(

    local_info: Optional[Dict],

    github_info: Optional[Dict],

) -> Optional[Dict]:

    candidates = [c for c in (local_info, github_info) if c]

    if not candidates:

        return None

    if local_info and github_info:

        if _parse_version(local_info["version"]) >= _parse_version(github_info["version"]):

            return local_info

    return max(candidates, key=lambda c: _parse_version(str(c.get("version", "0"))))





def _public_update_info(info: Optional[Dict]) -> Optional[Dict]:

    if not info:

        return None

    return {k: v for k, v in info.items() if k != "manifest"}





@router.get("/settings")

def update_settings():

    settings = github_updates.get_client_settings()

    settings["currentVersion"] = _read_version()

    try:

        from server import app_code_crypto as crypto

        settings["productName"] = crypto.product_display_name(BASE_DIR)

    except Exception:

        settings["productName"] = "CiM"

    return settings





@router.get("/check")

def update_check(background: bool = Query(False)):

    current = _read_version()

    local_info = None

    github_info = None

    err_local = None

    validate_files = not background

    try:

        local_info = _check_local(current, validate_files=validate_files)

    except HTTPException:

        raise

    except Exception as e:

        err_local = str(e)

    try:

        github_info = _check_github(current)

    except HTTPException:

        raise

    except Exception as e:

        err_local = err_local or str(e)

        github_info = None



    picked = _pick_update(local_info, github_info)

    settings = github_updates.get_client_settings()

    return {

        "currentVersion": current,

        "available": picked is not None,

        "update": _public_update_info(picked),

        "localError": err_local,

        "checkIntervalMinutes": settings.get("checkIntervalMinutes", 90),

        "backgroundCheckEnabled": settings.get("backgroundCheckEnabled", True),

        "githubRepo": settings.get("repo", ""),

    }





@router.post("/download")

def update_download():

    check = update_check(background=False)

    if not check.get("available"):

        raise HTTPException(404, detail="No update available")

    info = check["update"]

    source = info.get("source")



    if source == "local":

        return {

            "status": "ready",

            "version": info["version"],

            "updatePackageDir": info.get("sourceDir", ""),

            "fileCount": info.get("fileCount", 0),

        }



    if source != "github":

        raise HTTPException(400, detail="No GitHub update selected")



    download_url = str(info.get("downloadUrl", "")).strip()

    version = str(info.get("version", "")).strip()

    if not download_url or not version:

        raise HTTPException(502, detail="GitHub release missing download URL")



    try:

        package_dir = github_updates.download_and_extract_zip(download_url, version)

    except Exception as e:

        raise HTTPException(502, detail=f"GitHub download failed: {e}") from e



    try:

        local_after = _check_local_package(

            package_dir, _read_version(), validate_files=True

        )

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(

            502,

            detail=f"Downloaded update failed validation after extract: {e}",

        ) from e



    if not local_after:

        mf = package_dir / "update.manifest.json"

        mf_ver = ""

        try:

            if mf.is_file():

                mf_ver = str(_load_json(mf).get("version", ""))

        except Exception:

            pass

        raise HTTPException(

            502,

            detail=(

                "Downloaded update failed local validation after extract. "

                f"Release={version}, manifest={mf_ver or '?'}, "

                f"installed={_read_version()}. "

                "Ensure the GitHub ZIP matches the release tag and is newer than your install."

            ),

        )



    return {

        "status": "downloaded",

        "version": local_after["version"],

        "updatePackageDir": str(package_dir),

        "fileCount": local_after.get("fileCount", 0),

    }





@router.post("/apply")

def update_apply(body: dict = Body(default={})):

    check = update_check(background=False)

    if not check.get("available"):

        raise HTTPException(404, detail="No update available")

    info = check["update"]

    source = info.get("source")



    if source == "github":

        raise HTTPException(

            400,

            detail="GitHub update must be downloaded first (POST /api/update/download)",

        )



    if source != "local":

        raise HTTPException(400, detail="No local update ready to apply")



    manifest = _load_json(Path(info["manifestPath"]))

    source_dir = info["sourceDir"]



    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)

    pending = {

        "version": manifest["version"],

        "source": "local",

        "sourceDir": source_dir,

        "manifest": manifest,

    }

    PENDING_FILE.write_text(json.dumps(pending, indent=2), encoding="utf-8")



    if not APPLY_SCRIPT.exists():

        raise HTTPException(500, detail=f"Missing apply script: {APPLY_SCRIPT}")



    ps_args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(APPLY_SCRIPT),
        "-InstallRoot",
        str(BASE_DIR),
        "-ManifestPath",
        str(PENDING_FILE),
    ]
    apply_env = os.environ.copy()
    apply_env["CIM_NO_PAUSE"] = "1"
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        ps_args,
        cwd=str(BASE_DIR),
        env=apply_env,
        creationflags=creationflags,
        close_fds=False,
    )

    return {

        "status": "apply_scheduled",

        "message": "Charts In Motion will close to apply update.",

        "version": manifest["version"],

        "source": "local",

        "fileCount": len(manifest.get("files", [])),

    }


github_updates.configure_paths(BASE_DIR)
