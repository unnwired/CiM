"""Lightweight schema migration runner (delegates to existing ensure_* helpers)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS: list[tuple[str, str]] = [
    (
        "004_historical_data_index",
        "CREATE INDEX IF NOT EXISTS idx_hist_symbol_date ON historical_data(Symbol, Date)",
    ),
]


def run_migrations(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {row[0] for row in conn.execute("SELECT id FROM schema_migrations").fetchall()}
    count = 0
    for migration_id, sql in MIGRATIONS:
        if migration_id in applied:
            continue
        try:
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (id) VALUES (?)", (migration_id,))
            conn.commit()
            count += 1
            print(f"[migration] Applied: {migration_id}")
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)",
                    (migration_id,),
                )
                conn.commit()
            else:
                print(f"[migration] WARNING: {migration_id} failed: {exc}")
    return count


def run_startup_migrations(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        return run_migrations(conn)
    finally:
        conn.close()
