"""Quick verify Nifty Healthcare index row, chart, constituents."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

SYMBOL = "NIFTY_HEALTHCARE.NS"
DB = Path(r"D:\CiM\Client_Test\data\nse_data.db")
if not DB.exists():
    DB = ROOT / "data" / "nse_data.db"


def main() -> int:
    spec = importlib.util.spec_from_file_location("scrape_indices", ROOT / "scrape_indices.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT symbol, name, category FROM indices WHERE symbol=?", (SYMBOL,))
    print("index row:", cur.fetchone())
    cur.execute("SELECT COUNT(*) FROM index_history WHERE Symbol=?", (SYMBOL,))
    print("history bars:", cur.fetchone()[0])
    added = mod.ensure_equity_index_rows(conn)
    print("ensure added:", added)
    conn.close()

    import server.server as srv

    srv.DB_PATH = DB
    from fastapi.testclient import TestClient

    client = TestClient(srv.app)
    items = [
        i
        for i in client.get("/api/indices").json().get("data", [])
        if i.get("symbol") == SYMBOL
    ]
    if not items:
        print("FAIL: missing from /api/indices")
        return 1
    print("api:", items[0].get("name"), "chartable=", items[0].get("chartable"))

    cons = client.get(f"/api/index-constituents/{SYMBOL}").json().get("data", [])
    print("constituents:", len(cons))
    if len(cons) != 20:
        print(f"FAIL: expected 20 constituents, got {len(cons)}")
        return 1

    chart = client.get(f"/api/index-chart/{SYMBOL}?timeframe=1D&bars_limit=50")
    bars = (chart.json() or {}).get("bars") or []
    print("chart bars:", len(bars))
    if chart.status_code != 200 or not bars:
        print("FAIL: index chart missing bars")
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
