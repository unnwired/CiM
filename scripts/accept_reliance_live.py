#!/usr/bin/env python3
"""RELIANCE live open acceptance check — compares Upstox REST vs CiM stream seed."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

SYMBOL = "RELIANCE"


def main() -> int:
    from server import upstox_client, upstox_config
    from server.upstox_stream_worker import focus_manager

    if not upstox_config.market_data_enabled():
        print("SKIP: Upstox market data not configured")
        return 2

    entries, err = upstox_client.fetch_quotes([SYMBOL])
    if err:
        print(f"REST fetch error: {err}")
        return 1
    if not entries:
        print("REST fetch returned no quotes")
        return 1
    rest = entries[0]
    rest_open = rest.get("open")
    rest_px = rest.get("price")
    print("=== Upstox REST reference ===")
    print(json.dumps({
        "symbol": SYMBOL,
        "open": rest_open,
        "high": rest.get("high"),
        "low": rest.get("low"),
        "price": rest_px,
        "previous_close": rest.get("previous_close"),
    }, indent=2))

    with __import__("unittest.mock").mock.patch.object(focus_manager, "_ensure_thread"), __import__(
        "unittest.mock"
    ).mock.patch("server.upstox_stream_worker.upstox_instruments.instrument_map", return_value={}), __import__(
        "unittest.mock"
    ).mock.patch(
        "server.upstox_stream_worker.upstox_instruments.resolve_instrument_keys",
        return_value=({SYMBOL: "NSE_EQ|INE002A01018"}, []),
    ):
        focus_manager.subscribe("focus", [SYMBOL], mode="full")
        focus_manager.seed_session_quotes_sync([SYMBOL])

    q = focus_manager.quotes([SYMBOL]).get("symbols", {}).get(SYMBOL, {})
    print("\n=== CiM focus seed ===")
    print(json.dumps({
        "symbol": SYMBOL,
        "open": q.get("open"),
        "high": q.get("high"),
        "low": q.get("low"),
        "price": q.get("price"),
        "source": q.get("source"),
    }, indent=2))

    # Simulate first LTPC tick before any day OHLC in feed
    focus_manager._apply_feed(
        SYMBOL,
        {"ltpc": {"ltp": float(rest_px or q.get("price") or 0), "cp": float(rest.get("previous_close") or 0)}},
        int(time.time() * 1000),
    )
    q2 = focus_manager.quotes([SYMBOL]).get("symbols", {}).get(SYMBOL, {})
    print("\n=== CiM after first LTPC tick ===")
    print(json.dumps({
        "symbol": SYMBOL,
        "open": q2.get("open"),
        "high": q2.get("high"),
        "low": q2.get("low"),
        "price": q2.get("price"),
        "source": q2.get("source"),
    }, indent=2))

    ok = True
    if rest_open and q.get("open"):
        if abs(float(q["open"]) - float(rest_open)) > 0.05:
            print(f"\nFAIL: seeded open {q['open']} != REST open {rest_open}")
            ok = False
    if q2.get("open") and rest_open:
        if abs(float(q2["open"]) - float(rest_open)) > 0.05:
            print(f"\nFAIL: post-tick open {q2['open']} != REST open {rest_open}")
            ok = False
    if q2.get("open") and q2.get("price") and abs(float(q2["open"]) - float(q2["price"])) < 0.01:
        if rest_open and abs(float(rest_open) - float(q2["price"])) > 0.05:
            print("\nFAIL: open equals LTP but REST session open differs")
            ok = False

    if ok:
        print("\nPASS: session open preserved")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
