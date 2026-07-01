"""E2E: combined filters use native evaluators and return symbols + chart data."""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import server.server as srv  # noqa: E402


def _check(name: str, symbols: set[str] | None) -> bool:
    count = len(symbols or [])
    sample = sorted(symbols or [])[:8]
    print(f"{name}: count={count} sample={sample}")
    if count <= 0:
        print(f"FAIL: {name} returned zero symbols")
        return False
    return True


def _check_chart(symbol: str, timeframe: str = "1D") -> bool:
    from fastapi.testclient import TestClient

    client = TestClient(srv.app)
    r = client.get(f"/api/chart-data/{symbol}?timeframe={timeframe}&bars_limit=120")
    if r.status_code != 200:
        print(f"FAIL: chart-data {symbol} -> HTTP {r.status_code}")
        return False
    bars = (r.json() or {}).get("bars") or []
    if not bars:
        print(f"FAIL: chart-data {symbol} returned no bars")
        return False
    print(f"chart-data {symbol} ({timeframe}): bars={len(bars)}")
    return True


def _check_stocks_api(filters: list, label: str) -> bool:
    from fastapi.testclient import TestClient

    client = TestClient(srv.app)
    q = urllib.parse.quote(json.dumps(filters, separators=(",", ":")))
    r = client.get(f"/api/stocks?pageSize=5&filters={q}")
    if r.status_code != 200:
        print(f"FAIL: /api/stocks {label} -> HTTP {r.status_code}")
        return False
    body = r.json() or {}
    total = int(body.get("total") or 0)
    data = body.get("data") or []
    print(f"/api/stocks {label}: total={total} page_rows={len(data)}")
    if total <= 0 or not data:
        print(f"FAIL: /api/stocks {label} returned no rows")
        return False
    sym = str(data[0].get("Symbol") or data[0].get("symbol") or "").strip().upper()
    if not sym:
        print(f"FAIL: /api/stocks {label} missing symbol in first row")
        return False
    return _check_chart(sym)


def main() -> int:
    db_path = ROOT / "data" / "nse_data.db"
    if not db_path.exists():
        print(f"FAIL: database missing at {db_path}")
        return 1
    srv.DB_PATH = db_path
    srv.invalidate_filter_cache()

    earnings = {
        "filter_type": "earnings",
        "report_window": "month_range",
        "from_year": 2026,
        "from_month": 4,
        "to_year": 2026,
        "to_month": 6,
        "eps_surprise_min": 0.0,
        "revenue_surprise_min": 0.0,
    }

    macd = {
        "filter_type": "macd",
        "timeframe": "1D",
        "condition": "above",
        "target": "signal",
    }

    hist_2w = {
        "filter_type": "macd_hist_chain",
        "timeframe": "2W",
        "histogram_side": "positive",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": False,
    }

    hist_1d = {
        "filter_type": "macd_hist_chain",
        "timeframe": "1D",
        "histogram_side": "positive",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": False,
    }

    macd_hist_addon = {
        **macd,
        "hist_chain_enabled": True,
        "histogram_side": "positive",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": False,
    }

    print("=== earnings (combined) ===")
    if not _check("earnings combined", srv._combined_filter_symbols([earnings], [])):
        return 1

    print("=== MACD + histogram chip (2W) ===")
    macd_hist = srv._combined_filter_symbols([macd, hist_2w], [])
    if not _check("macd + hist_2w", macd_hist):
        return 1

    print("=== two histogram chips (2W + 1D) ===")
    dual_hist = srv._combined_filter_symbols([hist_2w, hist_1d], [])
    if not _check("hist_2w & hist_1d", dual_hist):
        return 1

    print("=== MACD with histogram add-on ===")
    macd_addon = srv._combined_filter_symbols([macd_hist_addon], [])
    if not _check("macd hist_chain_enabled", macd_addon):
        return 1

    print("=== /api/stocks with filters (list + chart) ===")
    if not _check_stocks_api([earnings], "earnings"):
        return 1
    if not _check_stocks_api([macd, hist_2w], "macd+hist"):
        return 1

    print("OK: combined filters E2E passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
