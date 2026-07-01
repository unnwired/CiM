"""
Uvicorn entry for Charts In Motion distribution builds with encrypted app code.

Dev / plaintext trees: imports server.server directly.
Encrypted trees: decrypt to LOCALAPPDATA cache, then load server from cache.
Auth-only mode: when no offline key and no online session, serve plaintext auth shell.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import signal
import sys
import threading
import time
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from server.core.install_root import get_install_root  # noqa: E402

_BASE_DIR = get_install_root()
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from server import app_code_crypto as _crypto  # noqa: E402


def _requires_auth_only() -> bool:
    from server.product_config import is_web_host_mode

    if is_web_host_mode(_BASE_DIR):
        return False
    if _crypto.access_granted(_BASE_DIR):
        return False
    from server.product_config import require_online_auth

    if require_online_auth():
        return True
    if _crypto.is_development_tree(_BASE_DIR):
        return False
    if _crypto.is_online_only_distribution(_BASE_DIR):
        return True
    if _crypto.is_plaintext_distribution(_BASE_DIR):
        return True
    if not _crypto.needs_encrypted_bootstrap(_BASE_DIR):
        return False
    return True


def _build_auth_only_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from server.license_routes import configure_base_dir, router as license_router

    configure_base_dir(_BASE_DIR)
    app = FastAPI(title="Charts In Motion Auth")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(license_router)

    auth_dir = _BASE_DIR / "frontend" / "auth"
    if auth_dir.is_dir():
        app.mount("/auth-static", StaticFiles(directory=str(auth_dir)), name="auth-static")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "auth_only"}

    @app.post("/api/admin/stop-all")
    def stop_all():
        """Let Electron restart into the full app after sign-in (parity with server.server)."""

        def _shutdown() -> None:
            time.sleep(0.35)
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except Exception:
                os._exit(0)

        threading.Thread(target=_shutdown, daemon=True).start()
        return {"status": "stopping", "scope": "backend"}

    @app.get("/")
    def auth_root():
        index = auth_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        raise HTTPException(status_code=503, detail="Auth UI missing")

    @app.get("/{full_path:path}")
    def auth_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        asset = (auth_dir / full_path).resolve()
        if str(asset).startswith(str(auth_dir.resolve())) and asset.is_file():
            return FileResponse(str(asset))
        index = auth_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        raise HTTPException(status_code=404, detail="Not Found")

    app.state.cim_auth_only = True
    return app


def _is_auth_only_app(app) -> bool:
    return bool(getattr(getattr(app, "state", None), "cim_auth_only", False))


def _prepare_sys_path() -> Path:
    cache_or_base = _crypto.ensure_app_cache(_BASE_DIR)
    if cache_or_base != _BASE_DIR:
        cache_root = str(cache_or_base)
        if cache_root not in sys.path:
            sys.path.insert(0, cache_root)
    return cache_or_base


def _load_server_module_from_cache(cache_root: Path):
    """Load server.server from decrypted server.pyc (plain import does not find .pyc-only modules)."""
    cache_server = cache_root / "server"
    pyc_path = cache_server / "server.pyc"
    if not pyc_path.is_file():
        raise ModuleNotFoundError("server.server (missing decrypted server.pyc)")

    if "server" not in sys.modules:
        init_py = cache_server / "__init__.py"
        init_pyc = cache_server / "__init__.pyc"
        if init_py.is_file():
            pkg_spec = importlib.util.spec_from_file_location(
                "server",
                init_py,
                submodule_search_locations=[str(cache_server)],
            )
        elif init_pyc.is_file():
            loader = importlib.machinery.SourcelessFileLoader("server", str(init_pyc))
            pkg_spec = importlib.util.spec_from_loader("server", loader)
            pkg_spec.submodule_search_locations = [str(cache_server)]
        else:
            pkg_spec = importlib.util.spec_from_file_location(
                "server",
                cache_server,
                submodule_search_locations=[str(cache_server)],
            )
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules["server"] = pkg_mod
        if pkg_spec.loader:
            pkg_spec.loader.exec_module(pkg_mod)

    for subpkg in ("core", "routers"):
        subdir = cache_server / subpkg
        if not subdir.is_dir():
            continue
        pkg_name = f"server.{subpkg}"
        if pkg_name in sys.modules:
            continue
        init_py = subdir / "__init__.py"
        init_pyc = subdir / "__init__.pyc"
        if init_py.is_file():
            sub_spec = importlib.util.spec_from_file_location(
                pkg_name,
                init_py,
                submodule_search_locations=[str(subdir)],
            )
        elif init_pyc.is_file():
            sub_loader = importlib.machinery.SourcelessFileLoader(pkg_name, str(init_pyc))
            sub_spec = importlib.util.spec_from_loader(pkg_name, sub_loader)
            sub_spec.submodule_search_locations = [str(subdir)]
        else:
            sub_spec = importlib.util.spec_from_file_location(
                pkg_name,
                subdir,
                submodule_search_locations=[str(subdir)],
            )
        sub_mod = importlib.util.module_from_spec(sub_spec)
        sys.modules[pkg_name] = sub_mod
        if sub_spec.loader:
            sub_spec.loader.exec_module(sub_mod)
        for mod_pyc in sorted(subdir.glob("*.pyc")):
            if mod_pyc.stem == "__init__":
                continue
            mod_name = f"{pkg_name}.{mod_pyc.stem}"
            if mod_name in sys.modules:
                continue
            mod_loader = importlib.machinery.SourcelessFileLoader(mod_name, str(mod_pyc))
            mod_spec = importlib.util.spec_from_loader(mod_name, mod_loader)
            mod_obj = importlib.util.module_from_spec(mod_spec)
            sys.modules[mod_name] = mod_obj
            mod_loader.exec_module(mod_obj)

    loader = importlib.machinery.SourcelessFileLoader("server.server", str(pyc_path))
    spec = importlib.util.spec_from_loader("server.server", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server.server"] = mod
    loader.exec_module(mod)
    _repoint_server_install_paths(mod)
    return mod


def _repoint_server_install_paths(mod) -> None:
    """Decrypted server.pyc lives under LOCALAPPDATA; data and UI stay under install dir."""
    install = _BASE_DIR
    mod.BASE_DIR = install
    mod.DATA_DIR = install / "data"
    mod.CSV_PATH = mod.DATA_DIR / "nse_dataset.csv"
    mod.DB_PATH = mod.DATA_DIR / "nse_data.db"
    mod.FRONTEND_BUILD_DIR = install / "frontend" / "build"
    for attr, rel in (
        ("SCRAPE_INDICES_PATH", "scrape_indices.py"),
        ("SCRAPE_FINANCIALS_PATH", "scrape_financials.py"),
        ("SCRAPE_DAILY_PATH", "scrape_daily.py"),
        ("SCRAPE_4H_PATH", "scrape_4h.py"),
    ):
        if hasattr(mod, attr):
            setattr(mod, attr, install / rel)
    update_apply = sys.modules.get("update_apply")
    if update_apply is not None and hasattr(update_apply, "configure_install_root"):
        update_apply.configure_install_root(install)
    movers_data = sys.modules.get("nse_pulse_movers_data")
    if movers_data is not None and hasattr(movers_data, "configure_paths"):
        movers_data.configure_paths(data_dir=install / "data")
    movers_live = sys.modules.get("nse_pulse_movers_live")
    if movers_live is not None and hasattr(movers_live, "configure_paths"):
        movers_live.configure_paths(data_dir=install / "data")
    try:
        from server.license_routes import configure_base_dir

        configure_base_dir(install)
    except Exception:
        pass
    try:
        from server.routers import settings as _settings_router

        _settings_router.configure_layout(install / "data")
    except Exception:
        pass


def _load_server_app():
    cache_or_base = _prepare_sys_path()
    if cache_or_base != _BASE_DIR and _crypto.has_encrypted_server(_BASE_DIR):
        return _load_server_module_from_cache(cache_or_base).app
    mod = importlib.import_module("server.server")
    return mod.app


def _patch_static_mount_for_cache(app) -> None:
    """Point /static at decrypted cache when install tree only has *.js.enc."""
    js_install = _BASE_DIR / "frontend" / "build" / "static" / "js"
    if not any(js_install.glob("*.js.enc")):
        return
    if not any(js_install.glob("*.js")):
        _crypto.ensure_app_cache(_BASE_DIR)
    cache_static = _crypto.app_cache_root(_BASE_DIR) / "frontend" / "build" / "static"
    if not cache_static.is_dir():
        return
    from fastapi.staticfiles import StaticFiles
    from starlette.routing import Mount

    routes = [
        r for r in app.router.routes if getattr(r, "name", None) != "static"
    ]
    static_route = Mount("/static", StaticFiles(directory=str(cache_static)), name="static")
    insert_at = next(
        (idx for idx, route in enumerate(routes) if getattr(route, "path", None) == "/{full_path:path}"),
        len(routes),
    )
    routes.insert(insert_at, static_route)
    app.router.routes = routes


_cache_prepared = False
_app = None


def _get_app():
    global _cache_prepared, _app
    if _app is not None:
        # Same uvicorn process: upgrade auth shell → full app once session is saved.
        if _is_auth_only_app(_app) and not _requires_auth_only():
            _app = None
            _cache_prepared = False
        else:
            return _app
    if _requires_auth_only():
        _app = _build_auth_only_app()
        return _app
    if not _cache_prepared:
        _cache_prepared = True
        if _crypto.needs_distribution_bootstrap(_BASE_DIR):
            if _crypto.needs_encrypted_bootstrap(_BASE_DIR):
                _prepare_sys_path()
    _app = _load_server_app()
    _patch_static_mount_for_cache(_app)
    try:
        from server.web_host import patch_web_host_app

        patch_web_host_app(_app, _BASE_DIR)
    except Exception:
        pass
    return _app


class _AppProxy:
    """Lazy FastAPI app that remains a valid ASGI callable for uvicorn."""

    def __getattr__(self, name):
        return getattr(_get_app(), name)

    async def __call__(self, scope, receive, send):
        await _get_app()(scope, receive, send)


app = _AppProxy()


def _preload_web_host_app() -> None:
    """Load full server at import so first browser hit is not a cold import + migrations."""
    try:
        from server.product_config import is_web_host_mode

        if is_web_host_mode(_BASE_DIR):
            _get_app()
    except Exception as exc:
        print(f"[cim_bootstrap] web host preload warning: {exc}")


_preload_web_host_app()
