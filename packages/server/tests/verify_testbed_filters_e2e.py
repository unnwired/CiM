"""HTTP E2E against running showcase (Client_Test) using TestClient + install DB."""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

INSTALL = Path(r"D:\CiM\Client_Test")
REPO = Path(__file__).resolve().parents[3]
PKG = REPO / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import server.server as srv  # noqa: E402


def main() -> int:
    db = INSTALL / "data" / "nse_data.db"
    if not db.exists():
        print(f"FAIL: missing {db}")
        return 1
    srv.DB_PATH = db
    srv.invalidate_filter_cache()

    from fastapi.testclient import TestClient

    client = TestClient(srv.app)

    earnings = [{
        "filter_type": "earnings",
        "report_window": "month_range",
        "from_year": 2026,
        "from_month": 4,
        "to_year": 2026,
        "to_month": 6,
        "eps_surprise_min": 0.0,
        "revenue_surprise_min": 0.0,
    }]
    hist = [{
        "filter_type": "macd_hist_chain",
        "timeframe": "2W",
        "histogram_side": "positive",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": False,
    }]
    macd_hist = [
        {
            "filter_type": "macd",
            "timeframe": "1D",
            "condition": "above",
            "target": "signal",
        },
        hist[0],
    ]

    def stocks(filters: list, label: str) -> tuple[int, str | None]:
        q = urllib.parse.quote(json.dumps(filters, separators=(",", ":")))
        r = client.get(f"/api/stocks?pageSize=5&filters={q}")
        if r.status_code != 200:
            print(f"FAIL {label}: HTTP {r.status_code} {r.text[:200]}")
            return -1, None
        body = r.json() or {}
        total = int(body.get("total") or 0)
        sym = None
        data = body.get("data") or []
        if data:
            sym = str(data[0].get("Symbol") or "").strip().upper()
        print(f"OK {label}: total={total} first={sym}")
        return total, sym

    total, sym = stocks(earnings, "earnings")
    if total <= 0:
        return 1

    print("=== combined MACD + histogram (uses cached MACD if warm) ===")
    total2, sym2 = stocks(macd_hist, "macd+hist_2w")
    if total2 <= 0:
        return 1

    chart_sym = sym2 or sym or "RELIANCE"
    cr = client.get(f"/api/chart-data/{chart_sym}?timeframe=1D&bars_limit=120")
    if cr.status_code != 200:
        print(f"FAIL chart: HTTP {cr.status_code}")
        return 1
    bars = (cr.json() or {}).get("bars") or []
    print(f"OK chart {chart_sym}: bars={len(bars)}")
    if not bars:
        print("FAIL chart returned no bars")
        return 1

    _, sym3 = stocks(hist, "hist_2w_only")
    if sym3 is None:
        return 1

    print("OK: testbed filter + chart E2E passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
