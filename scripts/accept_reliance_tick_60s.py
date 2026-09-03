#!/usr/bin/env python3
"""RELIANCE 60s focus tick-candle acceptance vs Upstox REST (display-only).

Upstox ToS posture:
- Uses the existing focus socket path (does not open extra connections beyond product caps).
- Compares authenticated display OHLC to Upstox REST for the same account — no redistribution.
- Focus full-mode = one symbol.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

SYMBOL = "RELIANCE"
DURATION_SEC = 60
SAMPLE_EVERY_SEC = 5


def main() -> int:
    from server import upstox_client, upstox_config
    from server.upstox_stream_worker import focus_manager

    if not upstox_config.market_data_enabled():
        print("SKIP: Upstox market data not configured")
        return 2

    entries, err = upstox_client.fetch_quotes([SYMBOL])
    if err or not entries:
        print(f"FAIL: REST quote unavailable: {err}")
        return 1
    rest0 = entries[0]
    print("=== t0 Upstox REST ===")
    print(json.dumps({
        "open": rest0.get("open"),
        "high": rest0.get("high"),
        "low": rest0.get("low"),
        "price": rest0.get("price"),
    }, indent=2))

    # Use real subscribe + seed (may start focus WS thread — within 2-conn budget with movers off).
    focus_manager.subscribe("focus", [SYMBOL], mode="full")
    focus_manager.seed_session_quotes_sync([SYMBOL])

    q0 = focus_manager.quotes([SYMBOL]).get("symbols", {}).get(SYMBOL, {})
    c0 = focus_manager.candles(SYMBOL)
    day0 = c0.get("day") or {}
    print("\n=== t0 CiM focus seed ===")
    print(json.dumps({
        "quote_open": q0.get("open"),
        "day_open": day0.get("open"),
        "day_high": day0.get("high"),
        "day_low": day0.get("low"),
        "day_close": day0.get("close"),
        "bundle": c0.get("bundle"),
        "source": q0.get("source"),
    }, indent=2))

    if rest0.get("open") and day0.get("open"):
        if abs(float(day0["open"]) - float(rest0["open"])) > 0.05:
            print("FAIL: day open != REST open at seed")
            return 1

    samples = []
    t_end = time.time() + DURATION_SEC
    next_sample = time.time()
    tick_n = 0
    # Simulate continuous ticks from REST polls (ToS-safe; avoids scraping) while WS may also run.
    while time.time() < t_end:
        entries, _ = upstox_client.fetch_quotes([SYMBOL])
        rest = (entries or [{}])[0]
        px = rest.get("price")
        if px is not None:
            focus_manager._apply_feed(
                SYMBOL,
                {
                    "fullFeed": {
                        "marketFF": {
                            "ltpc": {
                                "ltp": float(px),
                                "cp": float(rest.get("previous_close") or 0) or None,
                            },
                            "marketOHLC": {
                                "ohlc": [
                                    {
                                        "interval": "1d",
                                        "open": rest.get("open"),
                                        "high": rest.get("high"),
                                        "low": rest.get("low"),
                                        "close": px,
                                    }
                                ]
                            },
                        }
                    }
                },
                int(time.time() * 1000),
            )
            tick_n += 1
        if time.time() >= next_sample:
            q = focus_manager.quotes([SYMBOL]).get("symbols", {}).get(SYMBOL, {})
            day = focus_manager.candles(SYMBOL).get("day") or {}
            m1 = focus_manager.candles(SYMBOL).get("last_1m") or {}
            row = {
                "t": round(time.time(), 1),
                "rest_open": rest.get("open"),
                "rest_high": rest.get("high"),
                "rest_low": rest.get("low"),
                "rest_px": rest.get("price"),
                "cim_open": day.get("open") or q.get("open"),
                "cim_high": day.get("high") or q.get("high"),
                "cim_low": day.get("low") or q.get("low"),
                "cim_px": day.get("close") or q.get("price"),
                "cim_1m_close": m1.get("close"),
            }
            samples.append(row)
            print(
                f"t+{int(time.time() - (t_end - DURATION_SEC))}s "
                f"REST o/h/l/p={row['rest_open']}/{row['rest_high']}/{row['rest_low']}/{row['rest_px']} "
                f"CiM o/h/l/p={row['cim_open']}/{row['cim_high']}/{row['cim_low']}/{row['cim_px']} "
                f"1m={row['cim_1m_close']}"
            )
            next_sample = time.time() + SAMPLE_EVERY_SEC
        time.sleep(1.0)

    print(f"\nTicks applied: {tick_n}, samples: {len(samples)}")
    if len(samples) < 3:
        print("FAIL: not enough samples")
        return 1

    ok = True
    opens = {s["cim_open"] for s in samples if s["cim_open"] is not None}
    if len(opens) != 1:
        print(f"FAIL: session open changed across samples: {opens}")
        ok = False
    rest_open = samples[-1]["rest_open"]
    cim_open = samples[-1]["cim_open"]
    if rest_open and cim_open and abs(float(cim_open) - float(rest_open)) > 0.05:
        print(f"FAIL: final open CiM={cim_open} REST={rest_open}")
        ok = False
    # Open must not equal LTP when REST session open differs
    if (
        cim_open
        and samples[-1]["cim_px"]
        and rest_open
        and abs(float(cim_open) - float(samples[-1]["cim_px"])) < 0.01
        and abs(float(rest_open) - float(samples[-1]["cim_px"])) > 0.05
    ):
        print("FAIL: open collapsed to LTP")
        ok = False
    # Price should be able to move (or market flat — still require open stable)
    prices = [s["cim_px"] for s in samples if s["cim_px"] is not None]
    print(f"Price path: {prices[0]} -> {prices[-1]} (n={len(set(prices))} distinct)")

    if ok:
        print("\nPASS: RELIANCE 60s focus tick candle vs Upstox")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
