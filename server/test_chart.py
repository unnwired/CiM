import sys
sys.path.insert(0, r"D:\Programs\NSE Pulse\Claude Ai\server")

from server import get_chart_data, get_db_connection, aggregate_ohlcv, TIMEFRAME_CONFIG
import pandas as pd

symbol    = "21STCENMGM"
timeframe = "1D"

print("Step 1: Connecting to DB...")
conn = get_db_connection()

print("Step 2: Querying prices...")
raw_df = pd.read_sql_query(
    "SELECT Date, Open, High, Low, Close, Volume FROM prices WHERE Symbol = ? ORDER BY Date ASC LIMIT 10",
    conn,
    params=(symbol,),
)
conn.close()

print(f"Rows returned: {len(raw_df)}")
print(raw_df.head())
print("\nColumn types:")
print(raw_df.dtypes)

print("\nStep 3: Cleaning numerics...")
for col in ["Open", "High", "Low", "Close", "Volume"]:
    raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce").round(2)

raw_df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
print(f"Rows after clean: {len(raw_df)}")

print("\nStep 4: Aggregating OHLCV...")
bars = aggregate_ohlcv(raw_df, timeframe)
print(f"Bars generated: {len(bars)}")
print(bars[:3])
