"""
Remove legacy shared instrument_notes rows from an export copy of nse_data.db.

Distribution builds must not ship developer notes baked into the market database.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from server.instrument_notes_store import clear_instrument_notes_table  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: sanitize_export_db.py <path-to-nse_data.db>", file=sys.stderr)
        return 2
    db_path = Path(sys.argv[1])
    if not db_path.is_file():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        return 1
    removed = clear_instrument_notes_table(db_path)
    print(f"Cleared {removed} row(s) from instrument_notes in {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
