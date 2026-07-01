"""Tests for gzip + static cache middleware."""
from __future__ import annotations

import unittest

from server.http_perf import _AUTH_STATIC_RE, _HASHED_STATIC_RE


class TestHttpPerfPatterns(unittest.TestCase):
    def test_hashed_main_js(self):
        self.assertTrue(_HASHED_STATIC_RE.match("/static/js/main.d683dabd.js"))

    def test_hashed_chunk_js(self):
        self.assertTrue(_HASHED_STATIC_RE.match("/static/js/188.80511961.chunk.js"))

    def test_hashed_css(self):
        self.assertTrue(_HASHED_STATIC_RE.match("/static/css/main.ffdfd042.css"))

    def test_index_html_not_hashed_static(self):
        self.assertFalse(_HASHED_STATIC_RE.match("/static/js/main.js"))

    def test_auth_static(self):
        self.assertTrue(_AUTH_STATIC_RE.match("/auth-static/auth.js"))
        self.assertTrue(_AUTH_STATIC_RE.match("/auth-static/auth.css"))


if __name__ == "__main__":
    unittest.main()
