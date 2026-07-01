"""
Screener.in — full market cap (INR) from the public company HTML.

Parses the key-metrics list item for "Market Cap": the crores figure lives in
`<span class="number">…</span>` before "Cr.", not on the same text line as the label.

Optional: data/screener_session.json cookies (same shape as screener_sector_fallback)
improve reliability when Screener serves richer HTML to logged-in sessions.

Uses one requests.Session per thread (thread-safe with ThreadPoolExecutor).
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from pathlib import Path
from typing import Optional

SCREENER_BASE = "https://www.screener.in"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Screener key-metrics markup (2024+): label and value are in separate nodes, e.g.
#   <span class="name"> … Market Cap … </span>
#   <span class="nowrap value"> ₹ <span class="number">1,01,843</span> … Cr.
_MCAP_FROM_METRICS_LI = re.compile(
    r'<span[^>]*\bclass="[^"]*\bname\b[^"]*"[^>]*>[\s\S]*?Market\s*Cap[\s\S]*?</span>'
    r"[\s\S]{0,2000}?"
    r'<span[^>]*\bclass="[^"]*\bnumber\b[^"]*"[^>]*>([\d,\.\s]+)</span>'
    r"[\s\S]{0,200}?"
    r"Cr\.?",
    re.I,
)

# Older / compact inline copy: "Market Cap ₹ 1,01,946 Cr."
_MCAP_COMPACT = re.compile(
    r"Market\s*Cap\s*[₹Rs.\s\u00a0]*\s*([\d,\.\s]+)\s*Cr\.?",
    re.I,
)

_tls = threading.local()


def _cookie_header_from_session_file(data_dir: Path) -> str:
    p = data_dir / "screener_session.json"
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts: list[str] = []
    for c in data.get("cookies") or []:
        dom = str(c.get("domain", "")).lower()
        if "screener.in" not in dom:
            continue
        name = c.get("name")
        val = c.get("value")
        if name and val is not None:
            parts.append(f"{name}={val}")
    return "; ".join(parts)


def _parse_mcap_crores_to_inr(html: str) -> Optional[int]:
    """Parse total market cap in crores from HTML; return whole INR or None."""
    for rx in (_MCAP_FROM_METRICS_LI, _MCAP_COMPACT):
        m = rx.search(html)
        if not m:
            continue
        raw = m.group(1).strip().replace(",", "").replace(" ", "")
        if not raw or raw == ".":
            continue
        try:
            crores = float(raw)
            if crores < 0 or crores > 5e7:
                continue
            return int(round(crores * 1e7))
        except ValueError:
            continue
    return None


def _thread_session(cookie_header: str):
    import requests

    s = getattr(_tls, "screener_req", None)
    if s is None:
        s = requests.Session()
        h = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "DNT": "1",
            "Referer": f"{SCREENER_BASE}/",
            "Upgrade-Insecure-Requests": "1",
        }
        if cookie_header:
            h["Cookie"] = cookie_header
        s.headers.update(h)
        _tls.screener_req = s
    return s


def fetch_screener_market_cap_inr(symbol: str, data_dir: Path) -> Optional[int]:
    """
    Return full market cap in whole rupees from Screener.in, or None if not found.
    """
    from urllib.parse import quote

    from screener_symbol_slug import screener_company_slug_candidates

    nse_sym = str(symbol or "").strip().upper()
    if not nse_sym:
        return None

    cookie_header = _cookie_header_from_session_file(data_dir)
    sess = _thread_session(cookie_header)
    time.sleep(random.uniform(0.25, 0.65))

    for slug in screener_company_slug_candidates(nse_sym):
        encoded = quote(slug, safe="")
        paths = (
            f"/company/{encoded}/consolidated/",
            f"/company/{encoded}/",
        )
        for path in paths:
            url = f"{SCREENER_BASE}{path}"
            try:
                r = sess.get(url, timeout=28)
                if r.status_code != 200:
                    continue
                ct = (r.headers.get("content-type") or "").lower()
                if "html" not in ct and "text" not in ct:
                    continue
                val = _parse_mcap_crores_to_inr(r.text)
                if val is not None:
                    return val
            except Exception:
                continue
    return None
