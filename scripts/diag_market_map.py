"""Quick diagnostic: DB + market map API path."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

DB = ROOT / "data" / "nse_data.db"


def db_check():
    print("=== DB:", DB, "exists=", DB.is_file())
    if not DB.is_file():
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT substr(Date,1,10), Close FROM historical_data WHERE Symbol=? ORDER BY Date DESC LIMIT 3",
        ("M&M",),
    )
    hist = cur.fetchall()
    cur.execute("SELECT change_percent, price FROM screener WHERE UPPER(TRIM(symbol))=?", ("M&M",))
    sc = cur.fetchone()
    conn.close()
    print("M&M historical:", hist)
    print("M&M screener:", sc)
    if len(hist) >= 2:
        chg = round((hist[0][1] - hist[1][1]) / hist[1][1] * 100, 2)
        print("M&M computed 1D%:", chg)


def api_check():
    try:
        import urllib.request

        for port in (8000, 5000, 8765, 3001):
            url = f"http://127.0.0.1:{port}/api/market-map/index/%5ENSEI?period=1D&force=true"
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = json.loads(r.read().decode())
                mm = next((x for x in data.get("constituents", []) if x.get("symbol") == "M&M"), None)
                s = data.get("summary", {})
                print(f"\n=== API port {port} ===")
                print("source:", data.get("source"))
                print("summary:", s)
                print("M&M:", mm)
                return
            except Exception:
                continue
        print("\n=== API: no server responded on common ports ===")
    except Exception as e:
        print("API check error:", e)


def code_check():
    from nse_constituents import fetch_constituents_for_symbol
    from db_sqlite import connect_sqlite

    conn = connect_sqlite(DB)
    rows, src, err = fetch_constituents_for_symbol("^NSEI", conn)
    adv = sum(1 for r in rows if r.get("change_pct") is not None and float(r["change_pct"]) > 0)
    dec = sum(1 for r in rows if r.get("change_pct") is not None and float(r["change_pct"]) < 0)
    mm = next((r for r in rows if r["symbol"] == "M&M"), None)
    conn.close()
    print("\n=== Python fetch_constituents_for_symbol (^NSEI) ===")
    print("source:", src, "error:", err)
    print("breadth:", adv, "up", dec, "down")
    print("M&M:", mm)


if __name__ == "__main__":
    db_check()
    code_check()
    api_check()
