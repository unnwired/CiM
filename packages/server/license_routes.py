"""Local FastAPI routes — proxy online auth to Cloudflare Worker."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Request, Response

from server.client_user_agent import web_client_env_from_user_agent
from server import license_client as lc
from server import session_store as ss
from server.auth_social_proof import get_users_online, record_sign_out, record_successful_login
from server.product_config import is_web_host_mode
from server.user_data_paths import maybe_migrate_legacy_user_files
from server.web_auth import (
    clear_session_cookie,
    cookie_secure_for_request,
    cookie_session_id,
    ensure_browser_session_fresh,
    get_request_session,
    load_browser_session,
    require_request_session,
    session_is_valid,
    set_session_cookie,
    set_request_context,
)

from server.core.install_root import get_install_root

router = APIRouter(prefix="/api", tags=["license"])

_BASE_DIR = get_install_root()


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


def _client_ip_from_request(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip
    if request.client and request.client.host:
        host = request.client.host
        if host not in ("127.0.0.1", "::1", "localhost"):
            return host
    return None


def _web_client_env_from_request(request: Request) -> Optional[dict[str, str]]:
    if not is_web_host_mode(_BASE_DIR):
        return None
    return web_client_env_from_user_agent(request.headers.get("user-agent"))


def _active_session(request: Request) -> Optional[dict[str, Any]]:
    if is_web_host_mode(_BASE_DIR):
        session = get_request_session()
        if session:
            return session
        sid = cookie_session_id(request, _BASE_DIR)
        if sid:
            return ensure_browser_session_fresh(_BASE_DIR, sid)
        return None
    return lc.ensure_session_fresh(_BASE_DIR)


@router.get("/license/status")
def license_status(request: Request):
    if is_web_host_mode(_BASE_DIR):
        sid, session = load_browser_session(_BASE_DIR, request)
        if sid and session:
            session = ensure_browser_session_fresh(_BASE_DIR, sid) or session
            if session_is_valid(session):
                set_request_context(sid, session)
            else:
                session = None
        return lc.license_status_for_client(_BASE_DIR, session, host_mode="web")
    return lc.license_status_for_client(_BASE_DIR, host_mode="desktop")


@router.get("/auth/social-proof")
def auth_social_proof():
    if not is_web_host_mode(_BASE_DIR):
        raise HTTPException(status_code=404, detail="Not available")
    return {"users_online": get_users_online(_BASE_DIR)}


@router.get("/auth/enter-check")
def auth_enter_check(request: Request):
    """Same gate as GET / — used by the sign-in page before redirecting to the app."""
    if not is_web_host_mode(_BASE_DIR):
        return {"app_ready": True}
    sid, session = load_browser_session(_BASE_DIR, request)
    if not sid or not session:
        raise HTTPException(status_code=401, detail="Sign in required")
    session = ensure_browser_session_fresh(_BASE_DIR, sid) or session
    if not session_is_valid(session):
        raise HTTPException(status_code=401, detail="Sign in required")
    set_request_context(sid, session)
    return {
        "app_ready": True,
        "email": session.get("email"),
        "host_mode": "web",
    }


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
def auth_login(request: Request, response: Response, payload: dict = Body(...)):
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    totp_code = payload.get("totp_code")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    try:
        if is_web_host_mode(_BASE_DIR):
            had_valid_session = False
            sid, existing = load_browser_session(_BASE_DIR, request)
            if sid and existing:
                existing = ensure_browser_session_fresh(_BASE_DIR, sid) or existing
                had_valid_session = session_is_valid(existing)
            session_id, resp = lc.login_and_create_browser_session(
                _BASE_DIR,
                email,
                password,
                totp_code=str(totp_code) if totp_code else None,
                client_ip=_client_ip_from_request(request),
                client_env=_web_client_env_from_request(request),
            )
            set_session_cookie(
                response, session_id, secure=cookie_secure_for_request(request), base_dir=_BASE_DIR
            )
            session = ss.load_session_by_id(_BASE_DIR, session_id)
            if session:
                maybe_migrate_legacy_user_files(_BASE_DIR, session)
                set_request_context(session_id, session)
            if not had_valid_session:
                record_successful_login(_BASE_DIR)
            return resp
        return lc.login_and_save(
            _BASE_DIR,
            email,
            password,
            totp_code=str(totp_code) if totp_code else None,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    if is_web_host_mode(_BASE_DIR):
        sid = cookie_session_id(request, _BASE_DIR)
        had_session = bool(sid)
        if sid:
            lc.logout_browser_session(_BASE_DIR, sid)
        clear_session_cookie(response, secure=cookie_secure_for_request(request), base_dir=_BASE_DIR)
        set_request_context(None, None)
        if had_session:
            record_sign_out(_BASE_DIR)
        return {"status": "ok"}
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
def auth_complete(request: Request, response: Response):
    if is_web_host_mode(_BASE_DIR):
        session = require_request_session(request, _BASE_DIR)
        sid = cookie_session_id(request, _BASE_DIR)
        if sid:
            set_session_cookie(response, sid, secure=cookie_secure_for_request(request), base_dir=_BASE_DIR)
        status = lc.license_status_for_client(_BASE_DIR, session, host_mode="web")
        if not status.get("valid"):
            raise HTTPException(status_code=403, detail="No valid session")
        return {"status": "ok", "restart_required": False, "license": status}
    status = lc.license_status_for_client(_BASE_DIR, host_mode="desktop")
    if not status.get("valid"):
        raise HTTPException(status_code=403, detail="No valid session")
    return {"status": "ok", "restart_required": True, "license": status}


@router.post("/auth/totp/enroll")
def totp_enroll(request: Request):
    session = _active_session(request)
    if is_web_host_mode(_BASE_DIR):
        session = require_request_session(request, _BASE_DIR)
    elif not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        return lc.worker_totp_enroll(session["access_token"])
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/totp/confirm")
def totp_confirm(request: Request, payload: dict = Body(...)):
    session = _active_session(request)
    if is_web_host_mode(_BASE_DIR):
        session = require_request_session(request, _BASE_DIR)
    elif not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        return lc.worker_totp_confirm(session["access_token"], str(payload.get("code") or ""))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/totp/disable")
def totp_disable(request: Request, payload: dict = Body(...)):
    session = _active_session(request)
    if is_web_host_mode(_BASE_DIR):
        session = require_request_session(request, _BASE_DIR)
    elif not session or not session.get("access_token"):
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
def recovery_regenerate(request: Request, payload: dict = Body(...)):
    session = _active_session(request)
    if is_web_host_mode(_BASE_DIR):
        session = require_request_session(request, _BASE_DIR)
    elif not session or not session.get("access_token"):
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
def license_heartbeat(request: Request):
    if is_web_host_mode(_BASE_DIR):
        session = require_request_session(request, _BASE_DIR)
        sid = cookie_session_id(request, _BASE_DIR)
    else:
        session = lc.ensure_session_fresh(_BASE_DIR)
        sid = None
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        client_ip = _client_ip_from_request(request) if is_web_host_mode(_BASE_DIR) else None
        client_env = _web_client_env_from_request(request)
        resp = lc.worker_heartbeat(session["access_token"], client_ip=client_ip, client_env=client_env)
        lc._apply_token_response(session, resp)
        if is_web_host_mode(_BASE_DIR) and sid:
            ss.save_session_by_id(_BASE_DIR, sid, session)
        else:
            lc.save_session(_BASE_DIR, session)
        return resp
    except Exception as exc:
        if lc.within_offline_grace(session):
            return {"valid": True, "offline_cached": True}
        raise _http_error(exc) from exc
