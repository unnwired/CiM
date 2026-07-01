"""Gzip + long-cache headers for hashed static assets (showcase / web host)."""
from __future__ import annotations

import re

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HASHED_STATIC_RE = re.compile(
    r"^/static/(?:js|css|media)/[a-zA-Z0-9_.-]+\.[a-f0-9]{8}\.[a-z0-9]+$"
)
_AUTH_STATIC_RE = re.compile(r"^/auth-static/[a-zA-Z0-9_.-]+\.(?:css|js)$")


class CacheStaticMiddleware:
    """Immutable cache for fingerprinted build assets; auth shell CSS/JS."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        cacheable = bool(_HASHED_STATIC_RE.match(path) or _AUTH_STATIC_RE.match(path))
        if not cacheable:
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"cache-control", b"public, max-age=31536000, immutable"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


def install_http_perf_middleware(app) -> None:
    """Gzip responses and cache hashed /static + /auth-static assets."""
    app.add_middleware(CacheStaticMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=400)
