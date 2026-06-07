#!/usr/bin/env python3
"""
Backfill historical_data for NSE ticker renames (symbol lineage).

Usage (from project root):
  runtime\\python\\python.exe scripts\\backfill_symbol_history.py UNITDSPR
  runtime\\python\\python.exe scripts\\backfill_symbol_history.py --all
  runtime\\python\\python.exe scripts\\backfill_symbol_history.py --check UNITDSPR

See docs/SYMBOL_LINEAGE.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_sqlite import connect_sqlite  # noqa: E402
from symbol_lineage import (  # noqa: E402
    get_lineage_entry,
    lineage_backfill_needed,
    list_lineage_canonicals,
    run_lineage_backfill,
)

DB_PATH = ROOT / "data" / "nse_data.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill rename-aware OHLC history")
    parser.add_argument("symbols", nargs="*", help="Canonical NSE symbols (e.g. UNITDSPR)")
    parser.add_argument("--all", action="store_true", help="All symbols in symbol_lineage.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only print whether lineage backfill is needed (no writes)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run backfill even if shallow-history check passes",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols if s.strip()]
    if args.all:
        symbols = list_lineage_canonicals()
    if not symbols:
        parser.error("Provide symbol(s) or --all")

    conn = connect_sqlite(DB_PATH)
    exit_code = 0
    try:
        for sym in symbols:
            entry = get_lineage_entry(sym)
            if not entry:
                print(f"[skip] {sym}: not in data/symbol_lineage.json")
                exit_code = 1
                continue
            needed = lineage_backfill_needed(conn, sym, entry)
            if args.check:
                cur = conn.cursor()
                cur.execute(
                    "SELECT MIN(substr(Date,1,10)), COUNT(*) FROM historical_data WHERE Symbol = ?",
                    (sym,),
                )
                row = cur.fetchone()
                print(
                    f"{sym}: lineage_backfill_needed={needed} "
                    f"(db_min={row[0] if row else None}, rows={row[1] if row else 0})"
                )
                continue
            if not needed and not args.force:
                print(f"[ok] {sym}: history already spans required range (use --force to re-fetch)")
                continue
            print(f"[run] {sym}: merging predecessor + canonical Yahoo history…")

            def log(msg: str) -> None:
                print(msg)

            result = run_lineage_backfill(conn, sym, log=log)
            if result.get("ok"):
                print(
                    f"[done] {sym}: {result.get('rows_written')} rows, "
                    f"{result.get('min_date')} -> {result.get('max_date')}"
                )
            else:
                print(f"[fail] {sym}: {result.get('error')}")
                exit_code = 1
    finally:
        conn.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
