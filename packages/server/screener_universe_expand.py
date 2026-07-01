"""
Add NSE-listed symbols from screener_market_sets.json into screener when missing.

Validates against NSE EQUITY_L (EQ / BE / BZ series). Does not import BSE numeric codes.
"""
from __future__ import annotations

import csv
import io
import sqlite3
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_NSE_EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
ALLOWED_NSE_SERIES = frozenset({"EQ", "BE", "BZ"})

AUTOMOBILES = "Automobiles"
AUTO_AND_AUTO_COMPONENTS = "Automobile and Auto Components"


def fetch_nse_equity_symbols(
    *,
    url: str = DEFAULT_NSE_EQUITY_L_URL,
    user_agent: str = DEFAULT_USER_AGENT,
    allowed_series: Iterable[str] = ALLOWED_NSE_SERIES,
) -> Dict[str, str]:
    from http_ssl import https_ssl_context

    allowed = {str(s).strip().upper() for s in allowed_series}
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=90, context=https_ssl_context()) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    out: Dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        sym = (row.get("SYMBOL") or "").strip().upper()
        series = (row.get(" SERIES") or row.get("SERIES") or "").strip().upper()
        if sym and series in allowed:
            out[sym] = series
    return out


def _industry_hint_for_symbol(symbol: str, market_sets: Dict[str, Set[str]]) -> Optional[str]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    if sym in (market_sets.get(AUTOMOBILES) or set()):
        return "Automobiles"
    if sym in (market_sets.get(AUTO_AND_AUTO_COMPONENTS) or set()):
        return "Auto Components"
    return None


def expand_screener_from_market_sets(
    data_dir: Path,
    db_path: Path,
    *,
    nse_equity_url: str = DEFAULT_NSE_EQUITY_L_URL,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, object]:
    from screener_market_sets import load_market_sets

    market_sets = load_market_sets(data_dir)
    candidates: Set[str] = set()
    for syms in market_sets.values():
        candidates |= syms
    if not candidates:
        return {
            "candidates": 0,
            "inserted": 0,
            "skipped_not_nse": [],
            "skipped_already_present": [],
            "inserted_symbols": [],
        }

    nse_symbols = fetch_nse_equity_symbols(url=nse_equity_url, user_agent=user_agent)
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT UPPER(TRIM(symbol)) FROM screener")
        existing = {str(r[0]).strip().upper() for r in cur.fetchall() if r[0]}

        inserted: List[str] = []
        skipped_not_nse: List[str] = []
        skipped_already: List[str] = []

        for sym in sorted(candidates):
            if sym in existing:
                skipped_already.append(sym)
                continue
            if sym not in nse_symbols:
                skipped_not_nse.append(sym)
                continue
            industry = _industry_hint_for_symbol(sym, market_sets)
            cur.execute(
                """
                INSERT OR IGNORE INTO screener (symbol, nse_industry, nse_sector)
                VALUES (?, ?, ?)
                """,
                (sym, industry, "Consumer Discretionary" if industry else None),
            )
            if cur.rowcount:
                inserted.append(sym)
                existing.add(sym)

        conn.commit()
    finally:
        conn.close()

    return {
        "candidates": len(candidates),
        "inserted": len(inserted),
        "skipped_not_nse": skipped_not_nse,
        "skipped_already_present": skipped_already,
        "inserted_symbols": inserted,
    }


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Expand screener universe from market sets")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    data_dir = args.data_dir or (root / "data")
    db_path = args.db or (data_dir / "nse_data.db")

    try:
        result = expand_screener_from_market_sets(data_dir, db_path)
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))
    print(f"Inserted {result['inserted']} symbol(s)")
