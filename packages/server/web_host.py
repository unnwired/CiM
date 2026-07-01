"""Web host patches applied to the full FastAPI app after load."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.http_perf import install_http_perf_middleware
from server.product_config import is_web_host_mode
from server.web_auth import (
    ensure_browser_session_fresh,
    install_web_host_middleware,
    load_browser_session,
    session_is_valid,
)

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


def _no_cache_file(path: Path) -> FileResponse:
    return FileResponse(str(path), headers=_NO_CACHE_HEADERS)


def patch_web_host_app(app, base_dir: Path) -> None:
    if not is_web_host_mode(base_dir):
        return

    install_web_host_middleware(app, base_dir)
    install_http_perf_middleware(app)

    auth_dir = base_dir / "frontend" / "auth"
    build_dir = base_dir / "frontend" / "build"
    if auth_dir.is_dir() and not any(getattr(r, "name", None) == "auth-static" for r in app.router.routes):
        app.mount(
            "/auth-static",
            StaticFiles(directory=str(auth_dir)),
            name="auth-static",
        )

    def _serve_auth_index():
        index = auth_dir / "index.html"
        if index.is_file():
            return _no_cache_file(index)
        raise HTTPException(status_code=503, detail="Auth UI missing")

    def _serve_react_index():
        index = build_dir / "index.html"
        if index.is_file():
            return _no_cache_file(index)
        raise HTTPException(status_code=503, detail="Frontend build missing")

    def _session_for_page(request: Request):
        sid, session = load_browser_session(base_dir, request)
        if not sid or not session:
            return None
        if session_is_valid(session):
            return session
        session = ensure_browser_session_fresh(base_dir, sid) or session
        if session_is_valid(session):
            return session
        return None

    app.router.routes = [
        r
        for r in app.router.routes
        if getattr(r, "path", None) not in ("/", "/{full_path:path}")
    ]

    @app.get("/")
    def web_host_root(request: Request):
        if _session_for_page(request):
            return _serve_react_index()
        return _serve_auth_index()

    @app.get("/{full_path:path}")
    def web_host_spa(request: Request, full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if not _session_for_page(request):
            if full_path.startswith("auth-static/"):
                asset = (auth_dir / full_path.replace("auth-static/", "", 1)).resolve()
                if str(asset).startswith(str(auth_dir.resolve())) and asset.is_file():
                    return FileResponse(str(asset))
            return _serve_auth_index()
        if build_dir.exists():
            asset = (build_dir / full_path).resolve()
            build_root = build_dir.resolve()
            if str(asset).startswith(str(build_root)) and asset.is_file():
                return FileResponse(str(asset))
        return _serve_react_index()
