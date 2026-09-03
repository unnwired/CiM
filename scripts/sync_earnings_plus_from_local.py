"""Recompute earnings_plus_cache from local screener_quarterly (no Screener scrape)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="append", dest="dbs", help="Path to nse_data.db (repeatable)")
    parser.add_argument("--symbol", action="append", dest="symbols", default=[])
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    packages = repo / "packages"
    sys.path.insert(0, str(packages))

    import server.server as srv

    dbs = [Path(p) for p in (args.dbs or [
        str(repo / "data" / "nse_data.db"),
        r"D:\CiM\Client_Test\data\nse_data.db",
        r"D:\CiM\Client\data\nse_data.db",
    ])]
    rc = 0
    for db in dbs:
        if not db.is_file():
            print(f"SKIP missing {db}")
            continue
        print(f"=== {db} ===")
        try:
            srv.DB_PATH = db
            srv.DATA_DIR = db.parent
            summary = srv.run_sync_earnings_plus_cache_from_local(
                symbols=args.symbols or None,
                quiet=True,
                trigger="cli_local_sync",
            )
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            try:
                samples = {}
                for sym in ("KIRLPNU", "MEDPLUS"):
                    row = conn.execute(
                        "SELECT decision, basis_used, latest_period, note FROM earnings_plus_cache WHERE symbol=?",
                        (sym,),
                    ).fetchone()
                    samples[sym] = dict(row) if row else None
                counts = {
                    r["decision"]: r["n"]
                    for r in conn.execute(
                        "SELECT decision, COUNT(*) AS n FROM earnings_plus_cache GROUP BY decision"
                    )
                }
            finally:
                conn.close()
            summary["samples"] = samples
            summary["decision_counts"] = counts
            print(json.dumps(summary, indent=2))
        except Exception as exc:
            rc = 1
            print(f"ERROR {db}: {exc}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
