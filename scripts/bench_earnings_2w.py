"""Quick benchmark for earnings 2W batch helper."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import sqlite3

import server as srv

DB = ROOT / "data" / "nse_data.db"
conn = sqlite3.connect(str(DB))
cur = conn.cursor()
cur.execute("SELECT symbol FROM screener LIMIT 800")
syms = [r[0] for r in cur.fetchall()]
conn.close()

t0 = time.perf_counter()
out = srv._batch_change_2w_pct(sqlite3.connect(str(DB)), syms)
elapsed = time.perf_counter() - t0
print(f"symbols={len(syms)} hits={len(out)} sec={elapsed:.2f}")
if "PARAS" in syms or "PARAS" in out:
    print("PARAS 2w%", out.get("PARAS"))
