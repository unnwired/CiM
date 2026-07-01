"""Cookie-based auth for web host showcase mode."""
from __future__ import annotations

import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from server import license_client as lc
from server import session_store as ss
from server.product_config import is_web_host_mode, showcase_host_allowed_for_request
from server.showcase_host_gate import path_requires_showcase_host

LEGACY_SESSION_COOKIE = "cim_sid"
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.I)

_request_session: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "cim_request_session", default=None
)
_request_session_id: ContextVar[Optional[str]] = ContextVar(
    "cim_request_session_id", default=None
)


def load_showcase_install_settings(base_dir: Path) -> dict[str, Any]:
    path = Path(base_dir) / "config" / "showcase_host.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def session_cookie_name(base_dir: Path | None = None) -> str:
    """
    Per-install session cookie so testbed (8002) and live (8001) on 127.0.0.1
    do not overwrite each other's sign-in (HTTP cookies ignore port).
    """
    from server.core.install_root import get_install_root

    root = Path(base_dir) if base_dir else get_install_root()
    if not is_web_host_mode(root):
        return LEGACY_SESSION_COOKIE
    settings = load_showcase_install_settings(root)
    role = str(settings.get("role") or "").strip().lower()
    if role in ("live", "testbed"):
        return f"cim_sid_{role}"
    try:
        port = int(settings.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    if port > 0:
        return f"cim_sid_{port}"
    return "cim_sid_showcase"


def cookie_session_id(request: Request, base_dir: Path | None = None) -> Optional[str]:
    key = session_cookie_name(base_dir)
    raw = request.cookies.get(key, "").strip().lower()
    if raw and _SESSION_ID_RE.match(raw):
        return raw
    # One release of legacy shared cookie — migrate reads only.
    if key != LEGACY_SESSION_COOKIE:
        legacy = request.cookies.get(LEGACY_SESSION_COOKIE, "").strip().lower()
        if legacy and _SESSION_ID_RE.match(legacy):
            return legacy
    return None


def set_request_context(session_id: Optional[str], session: Optional[dict[str, Any]]) -> None:
    _request_session_id.set(session_id)
    _request_session.set(session)


def get_request_session() -> Optional[dict[str, Any]]:
    return _request_session.get()


def get_request_session_id() -> Optional[str]:
    return _request_session_id.get()


def load_browser_session(base_dir: Path, request: Request) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    sid = cookie_session_id(request, base_dir)
    if not sid:
        return None, None
    session = ss.load_session_by_id(base_dir, sid)
    if not session:
        return sid, None
    return sid, session


def ensure_browser_session_fresh(base_dir: Path, session_id: str) -> Optional[dict[str, Any]]:
    session = ss.load_session_by_id(base_dir, session_id)
    if not session:
        return None
    if lc.access_token_valid(session):
        return session
    if session.get("refresh_token"):
        try:
            resp = lc.worker_refresh(base_dir, session)
            lc._apply_token_response(session, resp)
            ss.save_session_by_id(base_dir, session_id, session)
            return session
        except Exception:
            pass
    if lc.within_offline_grace(session):
        return session
    return None


def cookie_secure_for_request(request: Request) -> bool:
    """True when the browser origin is HTTPS (Tailscale Funnel, reverse proxy, etc.)."""
    forwarded = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded == "https":
        return True
    ssl = str(request.headers.get("x-forwarded-ssl") or "").lower()
    if ssl in ("on", "1", "true"):
        return True
    forwarded_hdr = str(request.headers.get("forwarded") or "").lower()
    if "proto=https" in forwarded_hdr:
        return True
    host = (request.headers.get("host") or request.url.hostname or "").split(":")[0].lower()
    if host.endswith(".ts.net") or host.endswith(".tailscale.net"):
        return True
    return str(request.url.scheme).lower() == "https"


def session_is_valid(session: Optional[dict[str, Any]]) -> bool:
    if not session or not session.get("refresh_token"):
        return False
    stored_dev = str(session.get("device_id") or "").strip().upper()
    live_dev = lc.device_id().strip().upper()
    if stored_dev and stored_dev != live_dev:
        return False
    if lc.access_token_valid(session):
        return True
    return lc.within_offline_grace(session)


def set_session_cookie(
    response: Response,
    session_id: str,
    *,
    secure: bool,
    base_dir: Path | None = None,
) -> None:
    key = session_cookie_name(base_dir)
    response.set_cookie(
        key=key,
        value=session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    if key != LEGACY_SESSION_COOKIE:
        response.delete_cookie(
            key=LEGACY_SESSION_COOKIE,
            path="/",
            secure=secure,
            samesite="lax",
        )


def clear_session_cookie(
    response: Response,
    *,
    secure: bool = False,
    base_dir: Path | None = None,
) -> None:
    key = session_cookie_name(base_dir)
    response.delete_cookie(
        key=key,
        path="/",
        secure=secure,
        samesite="lax",
    )
    if key != LEGACY_SESSION_COOKIE:
        response.delete_cookie(
            key=LEGACY_SESSION_COOKIE,
            path="/",
            secure=secure,
            samesite="lax",
        )


def require_request_session(request: Request, base_dir: Path) -> dict[str, Any]:
    sid = cookie_session_id(request, base_dir)
    if not sid:
        raise HTTPException(status_code=401, detail="Sign in required")
    session = ensure_browser_session_fresh(base_dir, sid)
    if not session or not session_is_valid(session):
        raise HTTPException(status_code=401, detail="Sign in required")
    set_request_context(sid, session)
    return session


def _is_public_api_path(path: str) -> bool:
    if path == "/api/health":
        return True
    if path.startswith("/api/auth/"):
        return True
    if path.startswith("/api/license/status"):
        return True
    return False


class WebHostAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, base_dir: Path):
        super().__init__(app)
        self.base_dir = Path(base_dir)

    async def dispatch(self, request: Request, call_next):
        if not is_web_host_mode(self.base_dir):
            return await call_next(request)

        set_request_context(None, None)
        path = request.url.path or ""

        if not path.startswith("/api/") or _is_public_api_path(path):
            if path.startswith("/api/"):
                sid, session = load_browser_session(self.base_dir, request)
                if sid and session:
                    session = ensure_browser_session_fresh(self.base_dir, sid) or session
                    set_request_context(sid, session)
            return await call_next(request)

        sid, session = load_browser_session(self.base_dir, request)
        if not sid:
            return JSONResponse(status_code=401, content={"detail": "Sign in required"})
        session = ensure_browser_session_fresh(self.base_dir, sid)
        if not session or not session_is_valid(session):
            return JSONResponse(status_code=401, content={"detail": "Sign in required"})
        set_request_context(sid, session)

        if path_requires_showcase_host(path, request.method, request.url.query):
            if not showcase_host_allowed_for_request(request, self.base_dir):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Host-only operation"},
                )

        return await call_next(request)


def install_web_host_middleware(app, base_dir: Path) -> None:
    if not is_web_host_mode(base_dir):
        return
    app.add_middleware(WebHostAuthMiddleware, base_dir=base_dir)
