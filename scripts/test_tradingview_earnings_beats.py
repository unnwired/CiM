#!/usr/bin/env python3
"""CLI smoke test for TradingView earnings calendar (reported + upcoming)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from tradingview_earnings import fetch_earnings_calendar  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("reported", "upcoming"), default="reported")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--month", type=int, default=None, help="1-12, 0=all months")
    p.add_argument("--period", default="this_month")
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()

    data = fetch_earnings_calendar(
        mode=args.mode,
        year=args.year,
        month=args.month,
        period=args.period,
        limit=args.limit,
        use_cache=False,
    )
    print(json.dumps({
        "mode": data.get("mode"),
        "filters": data.get("filters"),
        "scanner_total": data.get("scanner_total"),
        "count": data.get("count"),
        "sample": (data.get("rows") or [])[:3],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
