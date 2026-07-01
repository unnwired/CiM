import sqlite3
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "data/nse_data.db")
conn = sqlite3.connect(str(p))
row = conn.execute("PRAGMA integrity_check").fetchone()
print(p, row[0])
conn.close()
sys.exit(0 if row and row[0] == "ok" else 1)
