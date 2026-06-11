#!/usr/bin/env python3
"""
Cross-platform smoke test. Requires backend running on :8000.

Usage: python scripts/smoke_test.py [--base URL]
"""
from __future__ import annotations

import argparse
import sys

try:
    import requests
except ImportError:
    print("smoke_test: install requests (pip install requests)")
    sys.exit(2)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, got: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  OK {name}")
        PASS += 1
    else:
        suffix = f"  ({got})" if got else ""
        print(f"  FAIL {name}{suffix}")
        FAIL += 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print("CiM Smoke Test")
    print("=" * 40)

    try:
        r = requests.get(f"{base}/api/health", timeout=5)
    except requests.RequestException as exc:
        print(f"  FAIL backend unreachable: {exc}")
        return 1

    check("GET /api/health -> 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        body = r.json()
        check("health.status == ok", body.get("status") == "ok")
        check("health.db_exists == true", body.get("db_exists") is True)

    try:
        r = requests.get(f"{base}/api/stocks?pageSize=500", timeout=15)
    except requests.RequestException as exc:
        check("GET /api/stocks", False, str(exc))
        r = None

    symbols = []
    if r is not None:
        check("GET /api/stocks -> 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check("stocks.total >= 1", data.get("total", 0) >= 1, str(data.get("total")))
            symbols = [s.get("Symbol") for s in data.get("data", [])[:3] if s.get("Symbol")]

    for sym in symbols or ["RELIANCE", "TCS"]:
        try:
            r2 = requests.get(
                f"{base}/api/chart-data/{sym}?timeframe=1D&bars_limit=100",
                timeout=15,
            )
            ok = r2.status_code == 200 and len(r2.json().get("bars", [])) > 0
            check(f"chart {sym} -> 200 with bars", ok, str(r2.status_code))
        except requests.RequestException as exc:
            check(f"chart {sym}", False, str(exc))

    for sym in ("RELIANCE", "TCS"):
        if sym in (symbols or []):
            continue
        try:
            r2 = requests.get(
                f"{base}/api/chart-data/{sym}?timeframe=1D&bars_limit=100",
                timeout=15,
            )
            ok = r2.status_code == 200 and len(r2.json().get("bars", [])) > 0
            check(f"chart {sym} -> 200 with bars", ok, str(r2.status_code))
        except requests.RequestException as exc:
            check(f"chart {sym}", False, str(exc))

    try:
        r = requests.get(f"{base}/api/indices", timeout=10)
        check("GET /api/indices -> 200", r.status_code == 200)
        if r.status_code == 200:
            check("indices.data not empty", len(r.json().get("data", [])) > 0)
    except requests.RequestException as exc:
        check("GET /api/indices", False, str(exc))

    try:
        r = requests.get(f"{base}/", timeout=10)
        if r.status_code == 200:
            check("Frontend build served", "root" in r.text or "/static/" in r.text)
    except requests.RequestException:
        pass

    print("=" * 40)
    print(f"Results: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
