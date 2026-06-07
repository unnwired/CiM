"""Smoke test: applied split ledger skips re-pending (no Yahoo/network)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import split_utils as su  # noqa: E402


def main() -> int:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    try:
        su.ensure_stock_split_events_table(conn)
        su.mark_pending(
            conn, symbol="RELIANCE", split_date="2025-05-01", ratio=2.0, source="test"
        )
        su.mark_applied(
            conn, symbol="RELIANCE", split_date="2025-05-01", ratio=2.0, source="test"
        )
        assert su.is_split_applied(conn, "RELIANCE", "2025-05-01", 2.0)
        added = su.mark_pending(
            conn, symbol="RELIANCE", split_date="2025-05-01", ratio=2.0, source="scan"
        )
        assert added is False
        assert len(su.list_pending(conn)) == 0
        su.mark_pending(
            conn, symbol="TCS", split_date="2025-06-01", ratio=3.0, source="scan"
        )
        pending = su.list_pending(conn)
        assert len(pending) == 1
        assert pending[0]["symbol"] == "TCS"
        su.mark_applied(
            conn, symbol="TCS", split_date="2025-06-01", ratio=3.0, source="apply"
        )
        assert su.count_by_status(conn)[su.STATUS_APPLIED] == 2
        print("test_split_ledger_smoke: PASS")
        return 0
    finally:
        conn.close()
        os.unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
