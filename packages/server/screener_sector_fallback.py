"""
Fill missing nse_sector / nse_industry from Screener.in company pages (peer breadcrumb).

Parses the HTML under <section id="peers"> — Broad Sector + Industry links — same pattern
as the live site (see <p class="sub"> with icon-globe and /market/... anchors).

Respect Screener.in robots/ToS: conservative delays, optional logged-in cookies from
data/screener_session.json (from screener_login.py). Use at your own risk for automation.
"""
from __future__ import annotations

import html as html_module
import json
import random
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

from screener_symbol_slug import screener_company_slug_candidates

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

PEERS_SECTION = re.compile(r'<section\s+id="peers"[^>]*>([\s\S]*?)</section>', re.I)
BREADCRUMB_P = re.compile(
    r'<p\s+class="sub">\s*<i\s+class="icon-globe"></i>([\s\S]*?)</p>',
    re.I,
)
MARKET_ANCHOR = re.compile(
    r'<a\s+href="/market[^"]*"[\s\S]*?title="([^"]+)"[\s\S]*?>([^<]*)</a>',
    re.I,
)


def load_screener_cookie_header(data_dir: Path) -> str:
    p = data_dir / "screener_session.json"
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts: List[str] = []
    for c in data.get("cookies") or []:
        dom = str(c.get("domain", "")).lower()
        if "screener.in" not in dom:
            continue
        name = c.get("name")
        val = c.get("value")
        if name and val is not None:
            parts.append(f"{name}={val}")
    return "; ".join(parts)


def _http_get(url: str, cookie_header: str, timeout: int = 35) -> str:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    req = urllib.request.Request(url, headers=headers)
    from http_ssl import https_ssl_context

    with urllib.request.urlopen(req, timeout=timeout, context=https_ssl_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_screener_sector_label(html: str) -> Optional[str]:
    """Return a single display label, e.g. 'Information Technology › Computers - Software & Consulting'."""
    m = PEERS_SECTION.search(html)
    if not m:
        return None
    chunk = m.group(1)
    pm = BREADCRUMB_P.search(chunk)
    if not pm:
        # Fallback: first <p class="sub"> that mentions /market/
        for sub in re.finditer(r'<p\s+class="sub">([\s\S]*?)</p>', chunk, re.I):
            if "/market/" in sub.group(1):
                pm = sub
                break
    if not pm:
        return None
    inner = pm.group(1)
    broad: Optional[str] = None
    industry: Optional[str] = None
    for title, raw_text in MARKET_ANCHOR.findall(inner):
        text = html_module.unescape(raw_text.strip())
        if not text:
            continue
        t = title.strip()
        if t == "Broad Sector":
            broad = text
        elif t == "Industry":
            industry = text
    if broad and industry and broad.casefold() != industry.casefold():
        return f"{broad} > {industry}"
    return industry or broad


def fetch_sector_for_symbol(symbol: str, cookie_header: str) -> Optional[str]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    for slug in screener_company_slug_candidates(sym):
        for suffix in ("/consolidated/", "/"):
            url = f"https://www.screener.in/company/{quote(slug, safe='')}{suffix}"
            try:
                html = _http_get(url, cookie_header)
            except urllib.error.HTTPError as e:
                if e.code in (404, 403):
                    continue
                raise
            except Exception:
                continue
            label = extract_screener_sector_label(html)
            if label:
                return label
    return None


def fill_unclassified_from_screener(
    db_path: Path,
    data_dir: Path,
    *,
    only_empty_industry: bool = True,
    delay_min: float = 1.0,
    delay_max: float = 2.2,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    message_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, int]:
    """
    Update screener.nse_sector and nse_industry for rows with empty industry (optional).
    """
    cookies = load_screener_cookie_header(data_dir)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        if only_empty_industry:
            cur.execute(
                """
                SELECT symbol FROM screener
                WHERE nse_industry IS NULL OR TRIM(nse_industry) = ''
                ORDER BY CASE WHEN issued_shares IS NOT NULL AND price IS NOT NULL AND price > 0
                    THEN CAST(issued_shares AS REAL) * price ELSE market_cap END DESC NULLS LAST
                """
            )
        else:
            cur.execute(
                "SELECT symbol FROM screener ORDER BY CASE WHEN issued_shares IS NOT NULL "
                "AND price IS NOT NULL AND price > 0 THEN CAST(issued_shares AS REAL) * price "
                "ELSE market_cap END DESC NULLS LAST"
            )
        symbols = [str(r[0]).strip().upper() for r in cur.fetchall() if r[0]]
    finally:
        conn.close()

    total = len(symbols)
    updated = 0
    failed = 0
    skipped = 0

    if progress_callback and total > 0:
        progress_callback(0, total)

    for i, sym in enumerate(symbols):
        if progress_callback:
            progress_callback(i + 1, total)
        if message_callback:
            message_callback(f"Screener.in: {sym} ({i + 1}/{total})…")

        try:
            label = fetch_sector_for_symbol(sym, cookies)
        except Exception:
            label = None
            failed += 1
            time.sleep(random.uniform(delay_min, delay_max))
            continue

        if not label:
            skipped += 1
        else:
            conn = sqlite3.connect(str(db_path))
            try:
                c2 = conn.cursor()
                c2.execute(
                    "UPDATE screener SET nse_sector = ?, nse_industry = ? WHERE symbol = ?",
                    (label, label, sym),
                )
                if c2.rowcount and c2.rowcount > 0:
                    updated += 1
                conn.commit()
            finally:
                conn.close()

        time.sleep(random.uniform(delay_min, delay_max))

    return {
        "symbols_considered": total,
        "updated": updated,
        "failed_http": failed,
        "no_peer_data": skipped,
    }
