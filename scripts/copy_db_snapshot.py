"""
Safe SQLite copy for distribution export / smoke tests.

Never copy nse_data.db with Copy-Item while WAL is active — that corrupts the file.
Uses sqlite3 backup API and verifies integrity on the destination.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def copy_sqlite_snapshot(src: Path, dst: Path) -> None:
    src = Path(src).resolve()
    dst = Path(dst).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source DB missing: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    for path in (dst, Path(str(dst) + "-wal"), Path(str(dst) + "-shm")):
        if path.is_file():
            path.unlink()

    src_uri = f"file:{src.as_posix()}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True)
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
        row = dst_conn.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise RuntimeError(f"integrity_check failed after backup: {row}")
    finally:
        src_conn.close()
        dst_conn.close()


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: copy_db_snapshot.py <source.db> <dest.db>")
        return 1
    copy_sqlite_snapshot(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"OK: {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
