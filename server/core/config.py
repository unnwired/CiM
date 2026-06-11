"""Shared path and constant configuration."""

from __future__ import annotations

import os
from pathlib import Path

from server.core.install_root import get_install_root

BASE_DIR = get_install_root()
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "nse_dataset.csv"
_db_override = os.getenv("CIM_DB_PATH", "").strip()
DB_PATH = Path(_db_override) if _db_override else DATA_DIR / "nse_data.db"
