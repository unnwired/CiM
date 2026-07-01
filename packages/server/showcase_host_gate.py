"""Host-only route gating for web showcase clients."""
from __future__ import annotations

_HOST_ONLY_PREFIXES = (
    "/api/admin/",
    "/api/update/",
)


def path_requires_showcase_host(path: str, method: str, query: str = "") -> bool:
    p = path or ""
    m = (method or "GET").upper()
    if any(p.startswith(prefix) for prefix in _HOST_ONLY_PREFIXES):
        return True
    if m in ("POST", "PUT", "PATCH", "DELETE"):
        if p.startswith("/api/sector-mapping"):
            return True
        if "/screener-quarters/" in p and p.rstrip("/").endswith("/refresh"):
            return True
    # GET /api/screener-quarters/* (incl. fetch_if_missing) is allowed for signed-in showcase
    # clients — only manual POST …/refresh stays host-only.
    return False
