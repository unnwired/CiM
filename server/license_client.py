"""Online license client — Cloudflare Worker proxy, encrypted local session."""
from __future__ import annotations

import hashlib
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from server import app_code_crypto as _crypto

SESSION_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def device_id() -> str:
    return _crypto.current_machine_code()


def device_name() -> str:
    return socket.gethostname()[:120] or "Unknown PC"


def app_version(base_dir: Path) -> str:
    vf = base_dir / _crypto.VERSION_FILE
    if vf.is_file():
        return vf.read_text(encoding="utf-8", errors="ignore").strip()[:40]
    return ""


def license_api_url() -> str:
    from server.product_config import license_api_url as _url
    return _url().rstrip("/")


def session_path(base_dir: Path) -> Path:
    from server.product_config import session_file_rel
    return base_dir / session_file_rel()


def _session_key(base_dir: Path) -> bytes:
    try:
        secret = _crypto.distribution_secret(base_dir)
    except Exception:
        secret = b"dev-session-key"
    return hashlib.sha256(secret + b"cim-session-v1" + device_id().encode("utf-8")).digest()


def _encrypt_session_payload(plain: bytes, base_dir: Path) -> bytes:
    return _crypto.encrypt_bytes(plain, key=_session_key(base_dir), base_dir=base_dir)


def _decrypt_session_payload(blob: bytes, base_dir: Path) -> bytes:
    return _crypto.decrypt_bytes(blob, key=_session_key(base_dir), base_dir=base_dir)


def load_session(base_dir: Path) -> Optional[dict[str, Any]]:
    path = session_path(base_dir)
    if not path.is_file():
        return None
    try:
        blob = path.read_bytes()
        if blob.startswith(_crypto.MAGIC):
            plain = _decrypt_session_payload(blob, base_dir)
        else:
            plain = blob
        data = json.loads(plain.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_session(base_dir: Path, data: dict[str, Any]) -> None:
    path = session_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["version"] = SESSION_VERSION
    data["device_id"] = device_id()
    plain = json.dumps(data, separators=(",", ":")).encode("utf-8")
    path.write_bytes(_encrypt_session_payload(plain, base_dir))


def clear_session(base_dir: Path) -> None:
    path = session_path(base_dir)
    if path.is_file():
        path.unlink()


def offline_grace_days(base_dir: Path) -> int:
    from server.product_config import offline_grace_days as _days
    return _days()


def _apply_token_response(session: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    now = _utcnow()
    expires_in = int(resp.get("expires_in") or 3600)
    grace_days = int(resp.get("offline_grace_days") or offline_grace_days(Path(".")))
    session["access_token"] = resp.get("access_token") or session.get("access_token")
    if resp.get("refresh_token"):
        session["refresh_token"] = resp["refresh_token"]
    session["access_expires_at"] = (now + timedelta(seconds=expires_in)).isoformat()
    session["last_online_check_at"] = now.isoformat()
    session["offline_grace_until"] = (now + timedelta(days=grace_days)).isoformat()
    if resp.get("email"):
        session["email"] = resp["email"]
    session["plan"] = resp.get("plan") or "free"
    return session


def _worker_request(
    method: str,
    path: str,
    body: Optional[dict[str, Any]] = None,
    bearer: Optional[str] = None,
    timeout: float = 25.0,
) -> dict[str, Any]:
    url = f"{license_api_url()}{path}"
    # Cloudflare Bot Management blocks Python-urllib/* (Error 1010) without a browser-like UA.
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-CiM-Client": "ChartsInMotion/1.0",
    }
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 403 and ("1010" in raw or "browser" in raw.lower()):
            err = RuntimeError(
                "License server blocked this PC (Cloudflare 1010). Restart CiM after updating, "
                "or contact support if this persists."
            )
            setattr(err, "status_code", 403)
            setattr(err, "payload", {"detail": err.args[0]})
            raise err from exc
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"detail": (raw or exc.reason or "License server error")[:500]}
        err = RuntimeError(str(detail.get("detail") or detail))
        setattr(err, "status_code", exc.code)
        setattr(err, "payload", detail)
        raise err from exc


def worker_signup(email: str, password: str) -> dict[str, Any]:
    return _worker_request("POST", "/auth/signup", {"email": email, "password": password})


def worker_login(base_dir: Path, email: str, password: str, totp_code: Optional[str] = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "email": email,
        "password": password,
        "device_id": device_id(),
        "device_name": device_name(),
        "app_version": app_version(base_dir),
    }
    if totp_code:
        body["totp_code"] = totp_code
    return _worker_request("POST", "/auth/login", body)


def worker_refresh(base_dir: Path, session: dict[str, Any]) -> dict[str, Any]:
    return _worker_request(
        "POST",
        "/auth/refresh",
        {"refresh_token": session.get("refresh_token"), "device_id": device_id()},
    )


def worker_logout(session: dict[str, Any]) -> None:
    rt = session.get("refresh_token")
    if rt:
        try:
            _worker_request("POST", "/auth/logout", {"refresh_token": rt})
        except Exception:
            pass


def worker_reset_password(email: str, recovery_code: str, new_password: str) -> dict[str, Any]:
    return _worker_request(
        "POST",
        "/auth/reset-with-recovery-code",
        {"email": email, "recovery_code": recovery_code, "new_password": new_password},
    )


def worker_license_status(access_token: str) -> dict[str, Any]:
    return _worker_request("GET", "/license/status", bearer=access_token)


def worker_heartbeat(access_token: str) -> dict[str, Any]:
    return _worker_request("POST", "/license/heartbeat", body={}, bearer=access_token)


def worker_totp_enroll(access_token: str) -> dict[str, Any]:
    return _worker_request("POST", "/auth/totp/enroll", body={}, bearer=access_token)


def worker_totp_confirm(access_token: str, code: str) -> dict[str, Any]:
    return _worker_request("POST", "/auth/totp/confirm", {"code": code}, bearer=access_token)


def worker_totp_disable(access_token: str, password: str, totp_code: str) -> dict[str, Any]:
    return _worker_request(
        "POST",
        "/auth/totp/disable",
        {"password": password, "totp_code": totp_code},
        bearer=access_token,
    )


def worker_recovery_regenerate(access_token: str, password: str, totp_code: Optional[str] = None) -> dict[str, Any]:
    body: dict[str, Any] = {"password": password}
    if totp_code:
        body["totp_code"] = totp_code
    return _worker_request("POST", "/auth/recovery/regenerate", body, bearer=access_token)


def access_token_valid(session: dict[str, Any]) -> bool:
    exp = _parse_iso(str(session.get("access_expires_at") or ""))
    if not exp:
        return False
    return _utcnow() < exp - timedelta(seconds=30)


def within_offline_grace(session: dict[str, Any]) -> bool:
    grace = _parse_iso(str(session.get("offline_grace_until") or ""))
    if not grace:
        last = _parse_iso(str(session.get("last_online_check_at") or ""))
        if not last:
            return False
        grace = last + timedelta(days=offline_grace_days(Path(".")))
    return _utcnow() < grace


def try_refresh_session(base_dir: Path) -> bool:
    session = load_session(base_dir)
    if not session or not session.get("refresh_token"):
        return False
    try:
        resp = worker_refresh(base_dir, session)
        _apply_token_response(session, resp)
        save_session(base_dir, session)
        return True
    except Exception:
        return False


def online_session_valid(base_dir: Path, allow_refresh: bool = True) -> bool:
    from server.product_config import require_online_auth

    if _crypto.is_development_tree(base_dir) and not require_online_auth():
        return True
    session = load_session(base_dir)
    if not session or not session.get("refresh_token"):
        return False
    stored_dev = str(session.get("device_id") or "").strip().upper()
    live_dev = device_id().strip().upper()
    if stored_dev and stored_dev != live_dev:
        return False
    if access_token_valid(session):
        return True
    if allow_refresh and try_refresh_session(base_dir):
        return True
    return within_offline_grace(session)


def ensure_session_fresh(base_dir: Path) -> Optional[dict[str, Any]]:
    session = load_session(base_dir)
    if not session:
        return None
    if access_token_valid(session):
        return session
    if try_refresh_session(base_dir):
        return load_session(base_dir)
    if within_offline_grace(session):
        return session
    return None


def login_and_save(base_dir: Path, email: str, password: str, totp_code: Optional[str] = None) -> dict[str, Any]:
    resp = worker_login(base_dir, email, password, totp_code)
    session: dict[str, Any] = {"email": resp.get("email") or email}
    _apply_token_response(session, resp)
    save_session(base_dir, session)
    return resp


def signup(email: str, password: str) -> dict[str, Any]:
    return worker_signup(email, password)


def logout(base_dir: Path) -> None:
    session = load_session(base_dir)
    if session:
        worker_logout(session)
    clear_session(base_dir)


def license_status_for_client(base_dir: Path) -> dict[str, Any]:
    from server.product_config import require_online_auth

    if _crypto.is_development_tree(base_dir) and not require_online_auth():
        return {"mode": "dev", "valid": True, "plan": "free"}
    if not _crypto.is_online_only_distribution(base_dir) and _crypto.license_valid(base_dir):
        return {"mode": "offline_key", "valid": True, "plan": "free"}
    session = ensure_session_fresh(base_dir)
    if not session:
        return {"mode": "none", "valid": False}
    offline = not access_token_valid(session)
    return {
        "mode": "online",
        "valid": True,
        "email": session.get("email"),
        "plan": session.get("plan") or "free",
        "offline_cached": offline,
        "offline_grace_until": session.get("offline_grace_until"),
        "device_id": device_id(),
    }
