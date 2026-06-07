"""
CLI: sync screener nse_sector / nse_industry from NSE index CSVs (+ optional BSE file).

  python scripts/sync_exchange_classification.py

Uses paths relative to repo root: data/nse_data.db, data/sector_mapping.json
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "nse_data.db"
sys.path.insert(0, str(ROOT / "server"))

import exchange_classification_sync as ec  # noqa: E402

if __name__ == "__main__":
    r = ec.run_sync(DATA, DB, refresh_canonical=True)
    print(r)
