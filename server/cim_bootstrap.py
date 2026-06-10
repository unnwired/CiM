"""
Uvicorn entry for Charts In Motion distribution builds with encrypted app code.

Dev / plaintext trees: imports server.server directly.
Encrypted trees: decrypt to LOCALAPPDATA cache, then load server from cache.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from server import app_code_crypto as _crypto  # noqa: E402


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
        if init_py.is_file():
            pkg_spec = importlib.util.spec_from_file_location(
                "server",
                init_py,
                submodule_search_locations=[str(cache_server)],
            )
        else:
            pkg_spec = importlib.util.spec_from_file_location("server", cache_server)
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules["server"] = pkg_mod
        if pkg_spec.loader:
            pkg_spec.loader.exec_module(pkg_mod)

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
    static_route = Mount("/static", app=StaticFiles(directory=str(cache_static)), name="static")
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
        return _app
    if not _cache_prepared:
        _cache_prepared = True
        if _crypto.needs_encrypted_bootstrap(_BASE_DIR) and not _crypto.is_development_tree(_BASE_DIR):
            _prepare_sys_path()
    _app = _load_server_app()
    _patch_static_mount_for_cache(_app)
    return _app


class _AppProxy:
    """Lazy FastAPI app that remains a valid ASGI callable for uvicorn."""

    def __getattr__(self, name):
        return getattr(_get_app(), name)

    async def __call__(self, scope, receive, send):
        await _get_app()(scope, receive, send)


app = _AppProxy()
