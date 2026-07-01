"""
Issued share count fetch — Yahoo → Screener.in → NSE (optional) cascade.

One source per symbol: first successful layer wins.
NSE tier skipped on showcase/testbed (yahoo_primary_pipeline).
"""
from __future__ import annotations

import time as time_module
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal, Optional
from zoneinfo import ZoneInfo

import requests

from server.live_quote_providers import _equity_yahoo_ticker, _finite
from server.market_cap_live import nse_issued_from_quote
from server.screener_market_cap import fetch_screener_market_cap_inr

IST = ZoneInfo("Asia/Kolkata")

IssuedSharesSource = Literal["yahoo", "screener", "nse", "none"]
NseFetchStatus = Literal["ok", "blocked", "failed"]

YAHOO_WORKERS = 8
YAHOO_SYMBOL_TIMEOUT = 6.0

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


@dataclass(frozen=True)
class IssuedSharesResult:
    symbol: str
    issued_shares: Optional[int]
    source: IssuedSharesSource
    nse_status: Optional[NseFetchStatus] = None


@dataclass
class IssuedSharesCascadeState:
    """Shared job state for NSE fast-fail across symbols."""

    allow_nse: bool
    nse_blocked: bool = False


def _positive_int(v: object) -> Optional[int]:
    n = _finite(v)
    if n is None or n <= 0:
        return None
    try:
        return int(round(float(n)))
    except (TypeError, ValueError):
        return None


def fetch_yahoo_issued_shares(symbol: str) -> Optional[int]:
    """Layer A: Yahoo sharesOutstanding / impliedSharesOutstanding."""
    ticker = _equity_yahoo_ticker(symbol)
    if not ticker:
        return None
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        try:
            fi = t.fast_info
            for key in ("shares", "sharesOutstanding", "impliedSharesOutstanding"):
                shares = _positive_int(getattr(fi, key, None) if hasattr(fi, key) else None)
                if shares is None and isinstance(fi, dict):
                    shares = _positive_int(fi.get(key))
                if shares is not None:
                    return shares
        except Exception:
            pass
        info = t.info or {}
        for key in ("sharesOutstanding", "impliedSharesOutstanding"):
            shares = _positive_int(info.get(key))
            if shares is not None:
                return shares
    except Exception:
        pass
    return None


def fetch_screener_issued_shares(
    symbol: str,
    data_dir: Path,
    price: Optional[float],
) -> Optional[int]:
    """Layer B: Screener.in market cap (INR) ÷ stored screener price."""
    px = _finite(price)
    if px is None or px <= 0:
        return None
    mcap_inr = fetch_screener_market_cap_inr(symbol, data_dir)
    if mcap_inr is None or mcap_inr <= 0:
        return None
    try:
        shares = int(round(float(mcap_inr) / float(px)))
        return shares if shares > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def make_nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    s.get("https://www.nseindia.com", timeout=15)
    time_module.sleep(1)
    s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
    time_module.sleep(1)
    return s


def fetch_nse_issued_shares(session: requests.Session, symbol: str) -> tuple[Optional[int], NseFetchStatus]:
    """Layer C: NSE quote-equity securityInfo.issuedSize."""
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    try:
        r = session.get(url, timeout=12)
        if r.status_code in (401, 403):
            return None, "blocked"
        if r.status_code == 200:
            issued = nse_issued_from_quote(r.json())
            return (issued, "ok") if issued is not None else (None, "failed")
    except requests.exceptions.Timeout:
        return None, "failed"
    except Exception:
        return None, "failed"
    return None, "failed"


def fetch_issued_shares_cascade(
    symbol: str,
    *,
    data_dir: Path,
    price: Optional[float],
    state: IssuedSharesCascadeState,
    nse_session: Optional[requests.Session],
) -> IssuedSharesResult:
    """Try Yahoo → Screener → NSE (if allowed and not globally blocked)."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return IssuedSharesResult(symbol=sym, issued_shares=None, source="none")

    shares = fetch_yahoo_issued_shares(sym)
    if shares is not None:
        return IssuedSharesResult(symbol=sym, issued_shares=shares, source="yahoo")

    shares = fetch_screener_issued_shares(sym, data_dir, price)
    if shares is not None:
        return IssuedSharesResult(symbol=sym, issued_shares=shares, source="screener")

    if not state.allow_nse or state.nse_blocked or nse_session is None:
        return IssuedSharesResult(symbol=sym, issued_shares=None, source="none")

    issued, nse_status = fetch_nse_issued_shares(nse_session, sym)
    if nse_status == "blocked":
        state.nse_blocked = True
        return IssuedSharesResult(
            symbol=sym, issued_shares=None, source="none", nse_status="blocked"
        )
    if issued is not None:
        return IssuedSharesResult(symbol=sym, issued_shares=issued, source="nse", nse_status="ok")
    return IssuedSharesResult(symbol=sym, issued_shares=None, source="none", nse_status="failed")


def fetch_yahoo_batch(symbols: list[str]) -> dict[str, int]:
    """Parallel Yahoo layer for a symbol batch."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: dict[str, int] = {}
    if not symbols:
        return out
    workers = min(YAHOO_WORKERS, max(1, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_yahoo_issued_shares, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                shares = fut.result(timeout=YAHOO_SYMBOL_TIMEOUT)
                if shares is not None:
                    out[sym] = shares
            except Exception:
                continue
    return out


def process_symbol_batch(
    symbols: list[str],
    prices: dict[str, float],
    *,
    data_dir: Path,
    state: IssuedSharesCascadeState,
    nse_session: Optional[requests.Session],
    cancel_check: Optional[Callable[[], bool]] = None,
) -> list[IssuedSharesResult]:
    """Batch: parallel Yahoo, then sequential Screener/NSE for misses."""
    from server.admin_job_control import JobCancelled, raise_if_cancelled

    if cancel_check:
        if cancel_check():
            raise JobCancelled()
    else:
        raise_if_cancelled()

    results: list[IssuedSharesResult] = []
    yahoo_hits = fetch_yahoo_batch(symbols)

    for sym in symbols:
        if cancel_check and cancel_check():
            raise JobCancelled()

        if sym in yahoo_hits:
            results.append(
                IssuedSharesResult(symbol=sym, issued_shares=yahoo_hits[sym], source="yahoo")
            )
            continue

        price = prices.get(sym)
        shares = fetch_screener_issued_shares(sym, data_dir, price)
        if shares is not None:
            results.append(
                IssuedSharesResult(symbol=sym, issued_shares=shares, source="screener")
            )
            continue

        if not state.allow_nse or state.nse_blocked or nse_session is None:
            results.append(IssuedSharesResult(symbol=sym, issued_shares=None, source="none"))
            continue

        issued, nse_status = fetch_nse_issued_shares(nse_session, sym)
        if nse_status == "blocked":
            state.nse_blocked = True
            results.append(
                IssuedSharesResult(
                    symbol=sym, issued_shares=None, source="none", nse_status="blocked"
                )
            )
            continue
        if issued is not None:
            results.append(
                IssuedSharesResult(symbol=sym, issued_shares=issued, source="nse", nse_status="ok")
            )
        else:
            results.append(
                IssuedSharesResult(symbol=sym, issued_shares=None, source="none", nse_status="failed")
            )

    return results


def issued_shares_source_meta_key(symbol: str) -> str:
    return f"issued_shares_source:{str(symbol).strip().upper()}"


def issued_shares_source_updated_meta_key(symbol: str) -> str:
    return f"issued_shares_source_updated:{str(symbol).strip().upper()}"


def set_issued_shares_source(conn, symbol: str, source: IssuedSharesSource) -> None:
    from server.bars_4h import ensure_updater_meta_table, set_meta

    now = datetime.now(IST).isoformat()
    ensure_updater_meta_table(conn)
    set_meta(conn, issued_shares_source_meta_key(symbol), source)
    set_meta(conn, issued_shares_source_updated_meta_key(symbol), now)


def count_issued_shares_sources(conn) -> dict[str, int]:
    """Aggregate issued_shares_source:* keys from updater_meta."""
    rows = conn.execute(
        "SELECT value, COUNT(*) FROM updater_meta WHERE key LIKE 'issued_shares_source:%' "
        "AND key NOT LIKE 'issued_shares_source_updated:%' GROUP BY value"
    ).fetchall()
    out = {"yahoo": 0, "screener": 0, "nse": 0, "none": 0}
    for val, cnt in rows:
        key = str(val or "none").strip().lower()
        if key in out:
            out[key] = int(cnt)
        else:
            out["none"] += int(cnt)
    return out
