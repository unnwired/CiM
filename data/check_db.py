import sqlite3

DB_PATH = r"D:\Programs\NSE Pulse\Claude Ai\data\nse_data.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("Tables in database:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()
for t in tables:
    print(f"  {t[0]}")

print("\nFor each table, showing columns and first row:")
for t in tables:
    name = t[0]
    print(f"\n--- {name} ---")
    cursor.execute(f"PRAGMA table_info({name});")
    cols = cursor.fetchall()
    for c in cols:
        print(f"  col: {c[1]} ({c[2]})")
    cursor.execute(f"SELECT * FROM {name} LIMIT 1;")
    row = cursor.fetchone()
    print(f"  sample row: {row}")

conn.close()
