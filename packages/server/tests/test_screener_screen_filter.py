"""Tests for Screener.in screen URL filter helpers."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[1]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from screener_screen_filter import (
    build_slug_to_symbol_map,
    detect_page_count,
    extract_company_slugs_from_html,
    normalize_screen_url,
    screen_cache_key,
    slugs_to_nse_symbols,
)


SAMPLE_HTML = """
<html><body>
<p>Showing page 1 of 3</p>
<table>
<tr><td><a href="/company/RELIANCE/">Reliance</a></td></tr>
<tr><td><a href="/company/BAJAJ-AUTO/consolidated/">Bajaj Auto</a></td></tr>
<tr><td><a href="/company/TCS/">TCS</a></td></tr>
</table>
</body></html>
"""


class TestScreenerScreenFilter(unittest.TestCase):
    def test_normalize_screen_url(self):
        url = normalize_screen_url("https://www.screener.in/screens/2115435/garp3months/?foo=1")
        self.assertEqual(url, "https://www.screener.in/screens/2115435/garp3months/")

    def test_normalize_rejects_company_page(self):
        with self.assertRaises(ValueError):
            normalize_screen_url("https://www.screener.in/company/RELIANCE/")

    def test_cache_key_stable(self):
        a = screen_cache_key("https://www.screener.in/screens/1/test/")
        b = screen_cache_key("https://www.screener.in/screens/1/test")
        self.assertEqual(a, b)

    def test_extract_slugs(self):
        slugs = extract_company_slugs_from_html(SAMPLE_HTML)
        self.assertEqual(slugs, {"RELIANCE", "BAJAJ-AUTO", "TCS"})

    def test_detect_page_count(self):
        self.assertEqual(detect_page_count(SAMPLE_HTML), 3)
        self.assertEqual(detect_page_count("<html></html>"), 1)

    def test_slugs_to_nse_symbols(self):
        universe = {"RELIANCE", "TCS", "BAJAJ_AUTO"}
        slug_map = build_slug_to_symbol_map(universe)
        matched = slugs_to_nse_symbols({"RELIANCE", "BAJAJ-AUTO", "TCS"}, universe, slug_map)
        self.assertEqual(matched, {"RELIANCE", "TCS", "BAJAJ_AUTO"})

    def test_cache_table_roundtrip(self):
        from screener_screen_filter import (
            ensure_screener_screen_cache_table,
            read_screen_cache,
            write_screen_cache,
        )

        conn = sqlite3.connect(":memory:")
        ensure_screener_screen_cache_table(conn)
        key = screen_cache_key("https://www.screener.in/screens/99/demo/")
        write_screen_cache(conn, key, "https://www.screener.in/screens/99/demo/", "Demo", ["AAA", "BBB"])
        row = read_screen_cache(conn, key)
        self.assertIsNotNone(row)
        self.assertEqual(row["symbols"], ["AAA", "BBB"])
        self.assertEqual(row["screen_name"], "Demo")
        conn.close()


if __name__ == "__main__":
    unittest.main()
