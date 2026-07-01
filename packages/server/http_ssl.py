"""HTTPS TLS context for urllib — uses certifi CA bundle on embedded Windows Python."""
from __future__ import annotations

import ssl
from typing import Optional

_ssl_context: Optional[ssl.SSLContext] = None


def https_ssl_context() -> ssl.SSLContext:
    """
    Return an SSL context trusted for public HTTPS (GitHub API, license API, etc.).

    Embedded Python on Windows often lacks OS CA integration; certifi supplies Mozilla's CA bundle.
    """
    global _ssl_context
    if _ssl_context is not None:
        return _ssl_context
    try:
        import certifi

        _ssl_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        _ssl_context = ssl.create_default_context()
    return _ssl_context
