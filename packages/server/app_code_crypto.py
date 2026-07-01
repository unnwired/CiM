"""
Charts In Motion (CiM) app-code encryption helpers (server bytecode + frontend static JS).

Distribution builds encrypt payloads at publish time; runtime decrypts to
%LOCALAPPDATA%\\CiM\\app-cache\\{version}\\ after install-key validation.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import shutil
from pathlib import Path
from typing import Iterable, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover
    AESGCM = None  # type: ignore

MAGIC = b"FXAC1\x00"
NONCE_LEN = 12
TAG_LEN = 16
APP_CODE_SALT = b"flowx-app-code-v1"
LICENSE_FILE = "data/.cim-license"
DIST_PROFILE_FILE = "config/.fx-dist.cfg"
LEGACY_DIST_PROFILE_FILE = "config/.flowx_vendor_secret"
PLAINTEXT_DIST_MARKER = "config/.cim-plaintext-dist"
ONLINE_ONLY_MARKER = "config/.cim-online-only"
VERSION_FILE = "version.txt"
PLAINTEXT_BOOTSTRAP_STEMS = frozenset(
    {
        "__init__",
        "app_code_crypto",
        "cim_bootstrap",
        "product_config",
        "_cim_dist_embedded",
        "license_client",
        "license_routes",
        "session_store",
        "user_data_paths",
        "web_auth",
        "showcase_host_gate",
    }
)


def is_dev_mode() -> bool:
    from server.product_config import is_dev_env
    return is_dev_env()


def has_embedded_distribution_secret(base_dir: Path) -> bool:
    return (base_dir / "server" / "_cim_dist_embedded.py").is_file()


def is_plaintext_distribution(base_dir: Path) -> bool:
    """Client install built with Build-CiM-Plaintext (readable source, online auth gate)."""
    return (base_dir / PLAINTEXT_DIST_MARKER).is_file() and has_embedded_distribution_secret(base_dir)


def is_online_only_distribution(base_dir: Path) -> bool:
    """Shipped install activates only via online sign-in (no vendor install key)."""
    if (base_dir / ONLINE_ONLY_MARKER).is_file():
        return True
    from server.product_config import online_only_activation

    return online_only_activation()


def is_development_tree(base_dir: Path) -> bool:
    """Repo / dev working copy — not a client-only distribution install."""
    server_py = base_dir / "server" / "server.py"
    packages_server_py = base_dir / "packages" / "server" / "server.py"
    profile = distribution_profile_path(base_dir)
    has_embedded = has_embedded_distribution_secret(base_dir)
    if is_plaintext_distribution(base_dir):
        return False
    is_distribution = (
        (profile.is_file() or has_embedded)
        and (has_encrypted_server(base_dir) or has_encrypted_js(base_dir))
        and not server_py.is_file()
    )
    if is_distribution:
        return False
    if server_py.is_file() or packages_server_py.is_file():
        return True
    if is_dev_mode():
        return True
    return False


def product_display_name(base_dir: Path) -> str:
    """UI product label from config/product.json."""
    from server.product_config import display_name
    return display_name(dev=is_development_tree(base_dir))


def _read_vendor_secret_text(secret_path: Path) -> str:
    """Read vendor secret without BOM/whitespace drift (must match Inno + Show-CiMInstallKey)."""
    raw = secret_path.read_text(encoding="utf-8-sig", errors="ignore").strip()
    return raw.lstrip("\ufeff").strip()


def distribution_profile_path(base_dir: Path) -> Path:
    """Installed distribution profile (neutral filename); legacy path supported."""
    new_path = base_dir / DIST_PROFILE_FILE
    if new_path.is_file():
        return new_path
    legacy = base_dir / LEGACY_DIST_PROFILE_FILE
    if legacy.is_file():
        return legacy
    return new_path


def _embedded_distribution_secret(base_dir: Path) -> Optional[bytes]:
    mod_path = base_dir / "server" / "_cim_dist_embedded.py"
    if not mod_path.is_file():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("_cim_dist_embedded_runtime", mod_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.distribution_secret_bytes()


def distribution_secret(base_dir: Optional[Path] = None) -> bytes:
    # New builds: server/_cim_dist_embedded.py (config/.fx-dist.cfg is not shipped).
    # Legacy installs may still have config/.fx-dist.cfg on disk.
    if base_dir is not None:
        embedded = _embedded_distribution_secret(base_dir)
        if embedded is not None:
            return embedded
        secret_path = distribution_profile_path(base_dir)
        if secret_path.is_file():
            return _read_vendor_secret_text(secret_path).encode("utf-8")
    raw = os.getenv("CIM_LICENSE_SECRET", "").strip()
    if not raw:
        raw = "cim-distribution-change-me"
    return raw.encode("utf-8")


def app_code_key(base_dir: Optional[Path] = None) -> bytes:
    return hashlib.sha256(distribution_secret(base_dir) + APP_CODE_SALT).digest()


def machine_code_for_guid(guid: str) -> str:
    """MD5 of MachineGuid — matches Inno Setup 6 GetMD5OfString(AnsiString)."""
    return hashlib.md5(guid.strip().encode("utf-8")).hexdigest().upper()


def install_key_for_machine(
    machine_code: str, secret: Optional[bytes] = None, base_dir: Optional[Path] = None
) -> str:
    """MD5-based key (matches Inno Setup 6 GetMD5OfString on Secret + MachineCode, Ansi/UTF-8)."""
    if secret is None:
        sec_text = distribution_secret(base_dir).decode("utf-8")
    elif isinstance(secret, bytes):
        sec_text = secret.decode("utf-8")
    else:
        sec_text = secret
    payload = sec_text + machine_code.strip().upper()
    hex_key = hashlib.md5(payload.encode("utf-8")).hexdigest().upper()
    return "-".join(hex_key[i : i + 4] for i in range(0, 24, 4))


def validate_install_key(
    machine_code: str, install_key: str, secret: Optional[bytes] = None, base_dir: Optional[Path] = None
) -> bool:
    expected = install_key_for_machine(machine_code, secret, base_dir)
    supplied = install_key.strip().upper().replace(" ", "")
    if "-" not in supplied and len(supplied) >= 24:
        supplied = "-".join(supplied[i : i + 4] for i in range(0, min(24, len(supplied)), 4))
    return hmac.compare_digest(expected, supplied)


def read_license(base_dir: Path) -> tuple[str, str]:
    path = base_dir / LICENSE_FILE
    if not path.exists():
        return "", ""
    machine = ""
    key = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "machinecode":
                machine = v
            elif k == "installkey":
                key = v
    return machine, key


def current_machine_code() -> str:
    """Machine code for this PC (same formula as Inno Setup GetMachineCode)."""
    guid = "NO-GUID"
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                guid = str(guid).strip()
        except OSError:
            pass
    return machine_code_for_guid(guid)


def license_valid(base_dir: Path) -> bool:
    from server.product_config import require_online_auth

    if is_development_tree(base_dir) and not require_online_auth():
        return True
    machine, key = read_license(base_dir)
    if not machine or not key:
        return False
    if not validate_install_key(machine, key, base_dir=base_dir):
        return False
    live = current_machine_code()
    return hmac.compare_digest(machine.strip().upper(), live.strip().upper())


def access_granted(base_dir: Path) -> bool:
    """Online-only distribution: valid session. Legacy: offline key OR online session."""
    from server.product_config import require_online_auth

    if is_development_tree(base_dir) and not require_online_auth():
        return True
    if is_online_only_distribution(base_dir):
        from server.license_client import online_session_valid

        return online_session_valid(base_dir)
    if license_valid(base_dir):
        return True
    from server.license_client import online_session_valid

    return online_session_valid(base_dir)


def encrypt_bytes(plaintext: bytes, key: Optional[bytes] = None, base_dir: Optional[Path] = None) -> bytes:
    if AESGCM is None:
        raise RuntimeError("cryptography package required for app-code encryption")
    k = key or app_code_key(base_dir)
    nonce = os.urandom(NONCE_LEN)
    ciphertext = AESGCM(k).encrypt(nonce, plaintext, None)
    return MAGIC + nonce + ciphertext


def decrypt_bytes(blob: bytes, key: Optional[bytes] = None, base_dir: Optional[Path] = None) -> bytes:
    if AESGCM is None:
        raise RuntimeError("cryptography package required for app-code decryption")
    if len(blob) < len(MAGIC) + NONCE_LEN + TAG_LEN:
        raise ValueError("encrypted blob too short")
    if not blob.startswith(MAGIC):
        raise ValueError("invalid app-code magic")
    k = key or app_code_key(base_dir)
    off = len(MAGIC)
    nonce = blob[off : off + NONCE_LEN]
    ciphertext = blob[off + NONCE_LEN :]
    return AESGCM(k).decrypt(nonce, ciphertext, None)


def read_installed_version(base_dir: Path) -> str:
    vf = base_dir / VERSION_FILE
    if vf.exists():
        return vf.read_text(encoding="utf-8", errors="ignore").strip() or "0.0.0"
    return "0.0.0"


def app_cache_root(base_dir: Path) -> Path:
    local = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    version = read_installed_version(base_dir)
    safe_ver = "".join(c if c.isalnum() or c in ".-_" else "_" for c in version)
    from server.product_config import local_appdata_folder
    return Path(local) / local_appdata_folder() / "app-cache" / safe_ver


def clear_app_cache(base_dir: Path) -> None:
    root = app_cache_root(base_dir).parent
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def has_encrypted_server(base_dir: Path) -> bool:
    server_dir = base_dir / "server"
    if not server_dir.is_dir():
        return False
    return any(server_dir.rglob("*.pyc.enc"))


def has_encrypted_js(base_dir: Path) -> bool:
    js_dir = base_dir / "frontend" / "build" / "static" / "js"
    if not js_dir.is_dir():
        return False
    return any(js_dir.glob("*.js.enc"))


def needs_encrypted_bootstrap(base_dir: Path) -> bool:
    if is_development_tree(base_dir):
        return False
    if is_plaintext_distribution(base_dir):
        return False
    return has_encrypted_server(base_dir) or has_encrypted_js(base_dir)


def needs_distribution_bootstrap(base_dir: Path) -> bool:
    """Encrypted or plaintext distribution — use cim_bootstrap (auth gate + full app)."""
    if is_development_tree(base_dir):
        return False
    return needs_encrypted_bootstrap(base_dir) or is_plaintext_distribution(base_dir)


def iter_server_encrypt_targets(server_dir: Path) -> Iterable[Path]:
    for path in sorted(server_dir.rglob("*.pyc")):
        if path.stem in PLAINTEXT_BOOTSTRAP_STEMS:
            continue
        yield path


def iter_js_encrypt_targets(js_dir: Path) -> Iterable[Path]:
    if not js_dir.is_dir():
        return
    for path in sorted(js_dir.glob("*.js")):
        if path.name.endswith(".js.enc"):
            continue
        yield path


def decrypt_server_to_cache(base_dir: Path, cache_dir: Path, key: Optional[bytes] = None) -> None:
    server_dir = base_dir / "server"
    cache_server = cache_dir / "server"
    cache_server.mkdir(parents=True, exist_ok=True)
    for enc_path in sorted(server_dir.rglob("*.pyc.enc")):
        rel = enc_path.relative_to(server_dir)
        out_path = cache_server / rel.with_suffix("")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(decrypt_bytes(enc_path.read_bytes(), key))
    for plain_path in sorted(server_dir.rglob("*")):
        if not plain_path.is_file():
            continue
        if plain_path.suffix == ".enc":
            continue
        if plain_path.suffix not in {".py", ".pyc"}:
            continue
        rel = plain_path.relative_to(server_dir)
        out_path = cache_server / rel
        if out_path.exists():
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plain_path, out_path)
    init_src = server_dir / "__init__.py"
    if init_src.exists():
        dst = cache_server / "__init__.py"
        if not dst.exists():
            shutil.copy2(init_src, dst)


def decrypt_js_to_cache(base_dir: Path, cache_dir: Path, key: Optional[bytes] = None) -> None:
    js_dir = base_dir / "frontend" / "build" / "static" / "js"
    if not js_dir.is_dir():
        return
    cache_js = cache_dir / "frontend" / "build" / "static" / "js"
    cache_js.mkdir(parents=True, exist_ok=True)
    for enc_path in sorted(js_dir.glob("*.js.enc")):
        name = enc_path.name[: -len(".enc")]
        out_path = cache_js / name
        out_path.write_bytes(decrypt_bytes(enc_path.read_bytes(), key))


def sync_plaintext_static_to_cache(base_dir: Path, cache_dir: Path) -> None:
    """Copy CSS/media/etc. from install tree; encrypted builds only store *.js.enc on disk."""
    src_static = base_dir / "frontend" / "build" / "static"
    if not src_static.is_dir():
        return
    dst_static = cache_dir / "frontend" / "build" / "static"
    dst_static.mkdir(parents=True, exist_ok=True)
    for item in sorted(src_static.iterdir()):
        if item.name == "js":
            continue
        target = dst_static / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(item, target)
        elif item.is_file():
            shutil.copy2(item, target)


def _install_enc_fingerprint(base_dir: Path) -> str:
    """Hash of encrypted payloads on disk; invalidates app-cache when export is rebuilt."""
    parts: list[str] = []
    server_dir = base_dir / "server"
    if server_dir.is_dir():
        for enc in sorted(server_dir.rglob("*.pyc.enc")):
            st = enc.stat()
            rel = enc.relative_to(server_dir).as_posix()
            parts.append(f"s:{rel}:{st.st_size}:{st.st_mtime_ns}")
    js_dir = base_dir / "frontend" / "build" / "static" / "js"
    if js_dir.is_dir():
        for enc in sorted(js_dir.glob("*.js.enc")):
            st = enc.stat()
            parts.append(f"j:{enc.name}:{st.st_size}:{st.st_mtime_ns}")
    if not parts:
        return ""
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _index_referenced_main_js(base_dir: Path) -> Optional[str]:
    index = base_dir / "frontend" / "build" / "index.html"
    if not index.is_file():
        return None
    import re

    text = index.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'/static/js/([^"]+\.js)"', text)
    return match.group(1) if match else None


def _cache_serves_index_js(base_dir: Path, cache_dir: Path) -> bool:
    main_js = _index_referenced_main_js(base_dir)
    if not main_js:
        return True
    return (cache_dir / "frontend" / "build" / "static" / "js" / main_js).is_file()


def cache_is_current(base_dir: Path, cache_dir: Path) -> bool:
    marker = cache_dir / ".ready"
    if not marker.is_file() or not cache_static_ready(cache_dir):
        return False
    if not _cache_serves_index_js(base_dir, cache_dir):
        return False
    expected = _install_enc_fingerprint(base_dir) or "ok"
    return marker.read_text(encoding="utf-8").strip() == expected


def cache_static_ready(cache_dir: Path) -> bool:
    static_root = cache_dir / "frontend" / "build" / "static"
    js_dir = static_root / "js"
    if not js_dir.is_dir() or not any(js_dir.glob("*.js")):
        return False
    css_dir = static_root / "css"
    return css_dir.is_dir() and any(css_dir.glob("*.css"))


def ensure_app_cache(base_dir: Path) -> Path:
    if is_development_tree(base_dir) or not needs_encrypted_bootstrap(base_dir):
        return base_dir
    if not access_granted(base_dir):
        raise RuntimeError(
            "Charts In Motion license missing or invalid. Sign in or re-run the installer."
        )
    cache_dir = app_cache_root(base_dir)
    if cache_is_current(base_dir, cache_dir):
        return cache_dir
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = app_code_key(base_dir)
    try:
        if has_encrypted_server(base_dir):
            decrypt_server_to_cache(base_dir, cache_dir, key)
        if has_encrypted_js(base_dir):
            decrypt_js_to_cache(base_dir, cache_dir, key)
            sync_plaintext_static_to_cache(base_dir, cache_dir)
    except Exception as exc:
        shutil.rmtree(cache_dir, ignore_errors=True)
        if exc.__class__.__name__ == "InvalidTag":
            raise RuntimeError(
                "Charts In Motion could not decrypt app files (secret mismatch). "
                "Re-run Install-Client-Update.bat from a fresh CiM-Update ZIP built after "
                "encrypt_app_code.ps1, or reinstall CiMSetup. Do not mix encrypted files from "
                "different builds."
            ) from exc
        raise
    marker = cache_dir / ".ready"
    marker.write_text(_install_enc_fingerprint(base_dir) or "ok", encoding="utf-8")
    return cache_dir
