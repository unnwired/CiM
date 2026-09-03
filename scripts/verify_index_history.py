"""
Scan and repair calendar gaps in index_history (all chartable indices).

Examples:
  python scripts/verify_index_history.py --scan
  python scripts/verify_index_history.py --repair
  python scripts/verify_index_history.py --repair --symbol ^CNXNXT50
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.index_history_integrity import (  # noqa: E402
    format_integrity_report,
    purge_non_session_index_bars,
    repair_index_gaps,
    scan_index_history,
)

DB_PATH = ROOT / "data" / "nse_data.db"


def _resolve_db_path(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path).expanduser().resolve()
    return DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Index history gap scan/repair")
    parser.add_argument("--scan", action="store_true", help="Scan only (default if no --repair)")
    parser.add_argument("--repair", action="store_true", help="Repair detected gaps")
    parser.add_argument(
        "--purge-non-session",
        action="store_true",
        help="Delete equity-index bars on weekends/holidays (fixes Sat/Sun clones)",
    )
    parser.add_argument("--since", help="Only purge dates on/after YYYY-MM-DD")
    parser.add_argument("--symbol", action="append", dest="symbols", help="Limit to symbol(s)")
    parser.add_argument("--db", dest="db_path", help="SQLite path (default: data/nse_data.db)")
    parser.add_argument("--dry-run", action="store_true", help="Repair dry-run (scan + plan only)")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_path)
    if not db_path.is_file():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    do_repair = bool(args.repair)
    do_purge = bool(args.purge_non_session)
    conn = sqlite3.connect(db_path)
    try:
        if do_purge:
            result = purge_non_session_index_bars(
                conn,
                symbols=args.symbols,
                since=args.since,
            )
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(
                    f"Purged {result.get('deleted', 0)} non-session bar(s) "
                    f"across {result.get('symbols', 0)} equity index symbol(s)."
                )
                dates = result.get("dates") or []
                if dates:
                    print("Dates removed: " + ", ".join(dates))
        elif do_repair:
            result = repair_index_gaps(
                conn,
                symbols=args.symbols,
                dry_run=bool(args.dry_run),
                log_fn=print,
            )
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(format_integrity_report(result))
        else:
            scan = scan_index_history(conn, symbols=args.symbols)
            if args.json:
                print(json.dumps(scan, indent=2, default=str))
            else:
                print(format_integrity_report(scan))
                affected = [s for s in scan.get("symbols", []) if s.get("gaps")]
                if affected:
                    print(f"\n{affected.__len__()} symbol(s) with gaps. Run with --repair to backfill.")
                else:
                    print("\nNo gaps detected.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
