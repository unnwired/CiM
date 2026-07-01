"""Tests for web User-Agent parsing."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from client_user_agent import parse_user_agent, web_client_env_from_user_agent


class ClientUserAgentTests(unittest.TestCase):
    def test_android_chrome_mobile(self):
        ua = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        )
        env = web_client_env_from_user_agent(ua)
        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(env["client_platform"], "web")
        self.assertEqual(env["client_os"], "Android")
        self.assertEqual(env["client_os_version"], "14")
        self.assertEqual(env["client_browser"], "Chrome")
        self.assertEqual(env["client_browser_version"], "120")
        self.assertEqual(env["client_device_type"], "mobile")

    def test_windows_edge(self):
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
        parsed = parse_user_agent(ua)
        self.assertEqual(parsed["client_os"], "Windows")
        self.assertEqual(parsed["client_os_version"], "10/11")
        self.assertEqual(parsed["client_browser"], "Edge")
        self.assertEqual(parsed["client_device_type"], "desktop")

    def test_iphone_safari(self):
        ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
        )
        env = web_client_env_from_user_agent(ua)
        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(env["client_os"], "iOS")
        self.assertEqual(env["client_browser"], "Safari")
        self.assertEqual(env["client_device_type"], "mobile")

    def test_mac_firefox(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"
        env = web_client_env_from_user_agent(ua)
        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(env["client_os"], "macOS")
        self.assertEqual(env["client_browser"], "Firefox")
        self.assertEqual(env["client_browser_version"], "121")

    def test_empty_returns_none(self):
        self.assertIsNone(web_client_env_from_user_agent(""))
        self.assertIsNone(web_client_env_from_user_agent(None))


if __name__ == "__main__":
    unittest.main()
