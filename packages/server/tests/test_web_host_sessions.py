"""Tests for web host per-browser session mode."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from server import license_client as lc
from server import session_store as ss
from server.product_config import is_web_host_mode
from server.user_data_paths import email_safe, user_namespace_dir


from server.web_auth import cookie_secure_for_request, cookie_session_id, session_cookie_name
from starlette.requests import Request


def _request(host: str = "", *, proto: str = "", scheme: str = "http") -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if host:
        headers.append((b"host", host.encode("utf-8")))
    if proto:
        headers.append((b"x-forwarded-proto", proto.encode("utf-8")))
    scope = {
        "type": "http",
        "headers": headers,
        "scheme": scheme,
        "path": "/",
        "server": ("127.0.0.1", 8001),
    }
    return Request(scope)


class CookieSecureTests(unittest.TestCase):
    def test_localhost_not_secure(self):
        self.assertFalse(cookie_secure_for_request(_request("127.0.0.1:8001")))

    def test_tailscale_host_is_secure(self):
        self.assertTrue(cookie_secure_for_request(_request("charts-in-motion.tail22251c.ts.net")))

    def test_forwarded_proto_https(self):
        self.assertTrue(cookie_secure_for_request(_request("127.0.0.1:8001", proto="https")))


class SessionCookieNameTests(unittest.TestCase):
    def test_live_and_testbed_use_distinct_cookie_names(self):
        with tempfile.TemporaryDirectory() as live_tmp, tempfile.TemporaryDirectory() as test_tmp:
            live = Path(live_tmp)
            test = Path(test_tmp)
            for base in (live, test):
                (base / "config").mkdir()
                (base / "config" / ".cim-web-host").write_text("", encoding="utf-8")
            (live / "config" / "showcase_host.json").write_text(
                json.dumps({"port": 8001, "role": "live"}), encoding="utf-8"
            )
            (test / "config" / "showcase_host.json").write_text(
                json.dumps({"port": 8002, "role": "testbed"}), encoding="utf-8"
            )
            self.assertEqual(session_cookie_name(live), "cim_sid_live")
            self.assertEqual(session_cookie_name(test), "cim_sid_testbed")

    def test_cookie_session_id_reads_install_specific_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            (base / "config" / ".cim-web-host").write_text("", encoding="utf-8")
            (base / "config" / "showcase_host.json").write_text(
                json.dumps({"port": 8002, "role": "testbed"}), encoding="utf-8"
            )
            scope = {
                "type": "http",
                "headers": [(b"cookie", b"cim_sid_testbed=abcdef0123456789abcdef0123456789")],
                "scheme": "http",
                "path": "/",
                "server": ("127.0.0.1", 8002),
            }
            req = Request(scope)
            self.assertEqual(cookie_session_id(req, base), "abcdef0123456789abcdef0123456789")


class WebHostModeTests(unittest.TestCase):
    def test_is_web_host_mode_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertFalse(is_web_host_mode(base))
            (base / "config").mkdir()
            (base / "config" / ".cim-web-host").write_text("", encoding="utf-8")
            self.assertTrue(is_web_host_mode(base))

    def test_session_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sid = ss.create_session(base, {"email": "a@b.com", "refresh_token": "rt"})
            loaded = ss.load_session_by_id(base, sid)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["email"], "a@b.com")
            ss.delete_session_by_id(base, sid)
            self.assertIsNone(ss.load_session_by_id(base, sid))

    def test_email_safe(self):
        self.assertEqual(email_safe("User@Example.COM"), "user_at_example.com")

    def test_user_namespace_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            session = {"email": "user@example.com"}
            path = user_namespace_dir(base, session)
            self.assertIn("user_at_example.com", str(path))

    def test_license_status_web_no_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            (base / "config" / ".cim-online-only").write_text("", encoding="utf-8")
            (base / "config" / ".cim-web-host").write_text("", encoding="utf-8")
            status = lc.license_status_for_client(base, None, host_mode="web")
            self.assertFalse(status["valid"])
            self.assertEqual(status["host_mode"], "web")

    def test_license_status_includes_testbed_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            (base / "config" / ".cim-web-host").write_text("", encoding="utf-8")
            (base / "config" / "showcase_host.json").write_text(
                json.dumps({"port": 8002, "role": "testbed", "label": "Testbed"}),
                encoding="utf-8",
            )
            status = lc.license_status_for_client(base, None, host_mode="web")
            self.assertEqual(status.get("showcase_role"), "testbed")
            self.assertEqual(status.get("showcase_label"), "Testbed")


if __name__ == "__main__":
    unittest.main()
