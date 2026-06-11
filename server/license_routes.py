"""Local FastAPI routes — proxy online auth to Cloudflare Worker."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException

from server import license_client as lc

router = APIRouter(prefix="/api", tags=["license"])

_BASE_DIR = Path(__file__).resolve().parent.parent


def configure_base_dir(base_dir: Path) -> None:
    global _BASE_DIR
    _BASE_DIR = Path(base_dir)


def _http_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "status_code", 502)
    payload = getattr(exc, "payload", None)
    detail = str(exc)
    if isinstance(payload, dict) and payload.get("detail"):
        detail = str(payload["detail"])
    extra = payload if isinstance(payload, dict) else {}
    if code == 401 and extra.get("need_totp"):
        raise HTTPException(
            status_code=401,
            detail={"detail": detail, "need_totp": True},
            headers={"X-Need-Totp": "1"},
        )
    raise HTTPException(status_code=int(code) if isinstance(code, int) else 502, detail=detail)


@router.get("/license/status")
def license_status():
    return lc.license_status_for_client(_BASE_DIR)


@router.post("/auth/signup")
def auth_signup(payload: dict = Body(...)):
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    try:
        return lc.signup(email, password)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/login")
def auth_login(payload: dict = Body(...)):
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    totp_code = payload.get("totp_code")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    try:
        return lc.login_and_save(_BASE_DIR, email, password, totp_code=str(totp_code) if totp_code else None)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/logout")
def auth_logout():
    lc.logout(_BASE_DIR)
    return {"status": "ok"}


@router.post("/auth/reset-with-recovery-code")
def auth_reset(payload: dict = Body(...)):
    try:
        return lc.worker_reset_password(
            str(payload.get("email") or ""),
            str(payload.get("recovery_code") or ""),
            str(payload.get("new_password") or ""),
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/complete")
def auth_complete():
    """Called after login — session already saved; client should restart backend."""
    status = lc.license_status_for_client(_BASE_DIR)
    if not status.get("valid"):
        raise HTTPException(status_code=403, detail="No valid session")
    return {"status": "ok", "restart_required": True, "license": status}


@router.post("/auth/totp/enroll")
def totp_enroll():
    session = lc.ensure_session_fresh(_BASE_DIR)
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        return lc.worker_totp_enroll(session["access_token"])
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/totp/confirm")
def totp_confirm(payload: dict = Body(...)):
    session = lc.ensure_session_fresh(_BASE_DIR)
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        return lc.worker_totp_confirm(session["access_token"], str(payload.get("code") or ""))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/totp/disable")
def totp_disable(payload: dict = Body(...)):
    session = lc.ensure_session_fresh(_BASE_DIR)
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        return lc.worker_totp_disable(
            session["access_token"],
            str(payload.get("password") or ""),
            str(payload.get("totp_code") or ""),
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/recovery/regenerate")
def recovery_regenerate(payload: dict = Body(...)):
    session = lc.ensure_session_fresh(_BASE_DIR)
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        return lc.worker_recovery_regenerate(
            session["access_token"],
            str(payload.get("password") or ""),
            str(payload.get("totp_code") or "") or None,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/license/heartbeat")
def license_heartbeat():
    session = lc.ensure_session_fresh(_BASE_DIR)
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        resp = lc.worker_heartbeat(session["access_token"])
        updated = lc.load_session(_BASE_DIR) or session
        lc._apply_token_response(updated, resp)
        lc.save_session(_BASE_DIR, updated)
        return resp
    except Exception as exc:
        if lc.within_offline_grace(session):
            return {"valid": True, "offline_cached": True}
        raise _http_error(exc) from exc
