"""
Fetch symbol lists from saved Screener.in screen URLs for Dashboard filters.

Uses optional session cookies (data/screener_session.json). Results are cached in SQLite.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Set

from screener_sector_fallback import DEFAULT_UA, load_screener_cookie_header
from screener_symbol_slug import SCREENER_COMPANY_SLUG_ALIASES, screener_company_slug_candidates

SCREENER_SITE = "https://www.screener.in"
SCREEN_PATH_RE = re.compile(
    r"^https?://(?:www\.)?screener\.in/screens/(\d+)(?:/([^/?#]*))?/?",
    re.I,
)
COMPANY_LINK_RE = re.compile(
    r'href=["\'](/company/([^/"\'?#]+)/?)',
    re.I,
)
PAGE_OF_RE = re.compile(r"Showing\s+page\s+\d+\s+of\s+(\d+)", re.I)

DEFAULT_CACHE_TTL_HOURS = 6
MAX_PAGES = 100
PAGE_DELAY_SEC = 0.75


def ensure_screener_screen_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS screener_screen_cache (
            cache_key TEXT PRIMARY KEY,
            screen_url TEXT NOT NULL,
            screen_name TEXT,
            symbols_json TEXT NOT NULL,
            symbol_count INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_screener_screen_cache_fetched "
        "ON screener_screen_cache(fetched_at)"
    )
    conn.commit()


def normalize_screen_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Screen URL is required")
    if text.startswith("/"):
        text = f"{SCREENER_SITE}{text}"
    parsed = urllib.parse.urlparse(text)
    if parsed.netloc and "screener.in" not in parsed.netloc.lower():
        raise ValueError("URL must be a screener.in screen link")
    path = parsed.path or ""
    m = SCREEN_PATH_RE.match(f"{parsed.scheme or 'https'}://{parsed.netloc or 'www.screener.in'}{path}")
    if not m:
        raise ValueError(
            "URL must be a saved Screener screen, e.g. "
            "https://www.screener.in/screens/123456/my-screen/"
        )
    screen_id = m.group(1)
    slug = (m.group(2) or "").strip("/")
    base = f"{SCREENER_SITE}/screens/{screen_id}/"
    if slug:
        base += f"{slug}/"
    return base


def screen_cache_key(screen_url: str) -> str:
    return hashlib.sha256(normalize_screen_url(screen_url).encode("utf-8")).hexdigest()[:40]


def _http_get(url: str, cookie_header: str, timeout: int = 45) -> str:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    import urllib.request

    req = urllib.request.Request(url, headers=headers)
    from http_ssl import https_ssl_context

    with urllib.request.urlopen(req, timeout=timeout, context=https_ssl_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_company_slugs_from_html(html: str) -> Set[str]:
    slugs: Set[str] = set()
    for _href, slug in COMPANY_LINK_RE.findall(html or ""):
        s = str(slug or "").strip()
        if not s or s.lower() in {"source", "consolidated"}:
            continue
        slugs.add(s)
    return slugs


def detect_page_count(html: str) -> int:
    m = PAGE_OF_RE.search(html or "")
    if not m:
        return 1
    try:
        return max(1, int(m.group(1)))
    except ValueError:
        return 1


def build_slug_to_symbol_map(symbols: Set[str]) -> dict[str, str]:
    slug_map: dict[str, str] = {}
    reverse_alias = {v.upper(): k for k, v in SCREENER_COMPANY_SLUG_ALIASES.items()}
    for sym in symbols:
        su = str(sym).strip().upper()
        if not su:
            continue
        slug_map[su] = su
        for slug in screener_company_slug_candidates(su):
            slug_map[slug.upper()] = su
    for slug, sym in reverse_alias.items():
        slug_map.setdefault(slug.upper(), sym)
    return slug_map


def slugs_to_nse_symbols(slugs: Set[str], universe: Set[str], slug_map: dict[str, str]) -> Set[str]:
    out: Set[str] = set()
    for slug in slugs:
        key = str(slug or "").strip().upper()
        if not key:
            continue
        sym = slug_map.get(key)
        if sym and sym in universe:
            out.add(sym)
            continue
        # Hyphenated Screener folder → NSE ticker guess
        guess = key.replace("-", "_")
        if guess in universe:
            out.add(guess)
            continue
        compact = key.replace("-", "").replace("_", "")
        if compact in universe:
            out.add(compact)
    return out


def fetch_screen_slugs(
    screen_url: str,
    *,
    cookie_header: str = "",
    delay_sec: float = PAGE_DELAY_SEC,
    log: Optional[Callable[[str], None]] = None,
) -> tuple[Set[str], int]:
    base = normalize_screen_url(screen_url)
    all_slugs: Set[str] = set()
    first_html = _http_get(base, cookie_header)
    all_slugs |= extract_company_slugs_from_html(first_html)
    pages = min(detect_page_count(first_html), MAX_PAGES)
    if log:
        log(f"Screener screen page 1/{pages}: {len(all_slugs)} company links")
    for page in range(2, pages + 1):
        time.sleep(delay_sec)
        sep = "&" if "?" in base else "?"
        page_url = f"{base}{sep}page={page}"
        html = _http_get(page_url, cookie_header)
        page_slugs = extract_company_slugs_from_html(html)
        if not page_slugs:
            break
        before = len(all_slugs)
        all_slugs |= page_slugs
        if log:
            log(f"Screener screen page {page}/{pages}: +{len(all_slugs) - before} links")
        if len(all_slugs) == before:
            break
    return all_slugs, pages


def _cache_row_is_fresh(fetched_at: str | None, ttl_hours: float) -> bool:
    if not fetched_at:
        return False
    try:
        ts = datetime.strptime(str(fetched_at)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - ts < timedelta(hours=max(0.25, float(ttl_hours)))


def read_screen_cache(conn: sqlite3.Connection, cache_key: str) -> dict | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT screen_url, screen_name, symbols_json, symbol_count, fetched_at "
        "FROM screener_screen_cache WHERE cache_key = ?",
        (cache_key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    try:
        symbols = json.loads(row[2] or "[]")
    except json.JSONDecodeError:
        symbols = []
    return {
        "screen_url": row[0],
        "screen_name": row[1],
        "symbols": [str(s).strip().upper() for s in symbols if str(s).strip()],
        "symbol_count": int(row[3] or 0),
        "fetched_at": row[4],
    }


def write_screen_cache(
    conn: sqlite3.Connection,
    cache_key: str,
    screen_url: str,
    screen_name: str | None,
    symbols: list[str],
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO screener_screen_cache (
            cache_key, screen_url, screen_name, symbols_json, symbol_count, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            screen_url = excluded.screen_url,
            screen_name = excluded.screen_name,
            symbols_json = excluded.symbols_json,
            symbol_count = excluded.symbol_count,
            fetched_at = excluded.fetched_at
        """,
        (
            cache_key,
            screen_url,
            screen_name,
            json.dumps(symbols),
            len(symbols),
            now,
        ),
    )
    conn.commit()


def query_screener_screen_symbols(
    conn: sqlite3.Connection,
    screen_url: str,
    *,
    screen_name: str | None = None,
    data_dir: Path,
    force_refresh: bool = False,
    cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
    sector_symbols: Optional[Set[str]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    normalized = normalize_screen_url(screen_url)
    key = screen_cache_key(normalized)
    ensure_screener_screen_cache_table(conn)

    cached = None if force_refresh else read_screen_cache(conn, key)
    if cached and _cache_row_is_fresh(cached.get("fetched_at"), cache_ttl_hours):
        symbols = list(cached["symbols"])
        source = "cache"
        fetched_at = cached.get("fetched_at")
    else:
        cookie_header = load_screener_cookie_header(data_dir)
        try:
            slugs, _pages = fetch_screen_slugs(normalized, cookie_header=cookie_header, log=log)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Screener screen fetch failed (HTTP {exc.code})") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Screener screen fetch failed: {exc.reason}") from exc

        cur = conn.cursor()
        cur.execute("SELECT symbol FROM screener")
        universe = {str(r[0]).strip().upper() for r in cur.fetchall() if r[0]}
        slug_map = build_slug_to_symbol_map(universe)
        matched = slugs_to_nse_symbols(slugs, universe, slug_map)
        symbols = sorted(matched)
        write_screen_cache(conn, key, normalized, screen_name, symbols)
        source = "live"
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if sector_symbols is not None:
        symbols = [s for s in symbols if s in sector_symbols]

    return {
        "symbols": symbols,
        "count": len(symbols),
        "screen_url": normalized,
        "screen_name": screen_name,
        "fetched_at": fetched_at,
        "source": source,
    }
