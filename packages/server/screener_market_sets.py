"""
Screener.in market list pages → symbol sets for Market Sector filters.

Fetches paginated /market/... tables (e.g. Automobile and Auto Components, Automobiles)
and persists symbol lists under data/screener_market_sets.json.
"""
from __future__ import annotations

import html as html_module
import json
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

COMPANY_SYMBOL_RE = re.compile(r"/company/([^/\"'?]+)/", re.I)
PAGE_OF_RE = re.compile(r"Showing\s+page\s+\d+\s+of\s+(\d+)", re.I)

# Screener taxonomy under Consumer Discretionary (IN02).
MARKET_SET_SPECS: List[Dict[str, str]] = [
    {
        "sector": "Automobile and Auto Components",
        "path": "/market/IN02/IN0201/",
        "screener_code": "IN0201",
    },
    {
        "sector": "Automobiles",
        "path": "/market/IN02/IN0201/IN020101/",
        "screener_code": "IN020101",
    },
]


def market_sets_path(data_dir: Path) -> Path:
    return data_dir / "screener_market_sets.json"


def default_market_sets_dict() -> Dict[str, object]:
    return {
        "version": 1,
        "updated_at": None,
        "sets": {spec["sector"]: [] for spec in MARKET_SET_SPECS},
    }


def _http_get(url: str, *, user_agent: str = DEFAULT_UA, timeout: int = 45) -> str:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    from http_ssl import https_ssl_context

    with urllib.request.urlopen(req, timeout=timeout, context=https_ssl_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def normalize_market_symbol(raw: str) -> Optional[str]:
    sym = html_module.unescape(str(raw or "").strip()).upper()
    if not sym or sym in ("CONSOLIDATED", "STANDALONE"):
        return None
    # Screener market tables sometimes link BSE-only numeric codes; NSE universe uses tickers.
    if sym.isdigit():
        return None
    return sym


def extract_company_symbols(html: str) -> Set[str]:
    out: Set[str] = set()
    for raw in COMPANY_SYMBOL_RE.findall(html or ""):
        sym = normalize_market_symbol(raw)
        if sym:
            out.add(sym)
    return out


def detect_page_count(html: str) -> int:
    m = PAGE_OF_RE.search(html or "")
    if not m:
        return 1
    try:
        return max(1, int(m.group(1)))
    except ValueError:
        return 1


def fetch_market_page_symbols(
    base_url: str,
    path: str,
    *,
    user_agent: str = DEFAULT_UA,
    delay_sec: float = 0.6,
    log: Optional[Callable[[str], None]] = None,
) -> Set[str]:
    base = base_url.rstrip("/")
    first_url = f"{base}{path}"
    first_html = _http_get(first_url, user_agent=user_agent)
    symbols = extract_company_symbols(first_html)
    pages = detect_page_count(first_html)
    if log:
        log(f"{path}: page 1/{pages}, {len(symbols)} symbols")
    for page in range(2, pages + 1):
        time.sleep(delay_sec)
        sep = "&" if "?" in path else "?"
        page_url = f"{base}{path}{sep}page={page}"
        html = _http_get(page_url, user_agent=user_agent)
        page_syms = extract_company_symbols(html)
        symbols |= page_syms
        if log:
            log(f"{path}: page {page}/{pages}, +{len(page_syms)} ({len(symbols)} total)")
    return symbols


def refresh_market_sets(
    data_dir: Path,
    *,
    base_url: str = "https://www.screener.in",
    user_agent: str = DEFAULT_UA,
    delay_sec: float = 0.6,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, object]:
    sets: Dict[str, List[str]] = {}
    for spec in MARKET_SET_SPECS:
        sector = spec["sector"]
        syms = fetch_market_page_symbols(
            base_url,
            spec["path"],
            user_agent=user_agent,
            delay_sec=delay_sec,
            log=log,
        )
        sets[sector] = sorted(syms)
    out = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sets": sets,
    }
    save_market_sets(data_dir, out)
    return out


def save_market_sets(data_dir: Path, data: Dict[str, object]) -> None:
    p = market_sets_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_market_sets(data_dir: Path) -> Dict[str, Set[str]]:
    p = market_sets_path(data_dir)
    if not p.is_file():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    raw = data.get("sets") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Set[str]] = {}
    for sector, symbols in raw.items():
        if not isinstance(symbols, list):
            continue
        cleaned = {str(s).strip().upper() for s in symbols if str(s).strip()}
        if cleaned:
            out[str(sector).strip()] = cleaned
    return out


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Refresh Screener.in market symbol sets")
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    data_dir = args.data_dir
    if data_dir is None:
        try:
            from repo_paths import DATA_DIR as _DATA_DIR

            data_dir = _DATA_DIR
        except ImportError:
            data_dir = Path(__file__).resolve().parents[2] / "data"

    def _log(msg: str) -> None:
        print(msg, flush=True)

    try:
        result = refresh_market_sets(data_dir, log=_log)
    except urllib.error.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)
    for name, syms in (result.get("sets") or {}).items():
        print(f"  {name}: {len(syms)} symbols")
    print(f"Saved {market_sets_path(data_dir)}")
