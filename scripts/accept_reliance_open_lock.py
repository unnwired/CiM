#!/usr/bin/env python3
"""Quick open-lock check after 60s acceptance (ASCII-only)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "packages"
sys.path.insert(0, str(PKG))

from server import upstox_client, upstox_config
from server.upstox_stream_worker import focus_manager

SYMBOL = "RELIANCE"


def main() -> int:
    if not upstox_config.market_data_enabled():
        print("SKIP")
        return 2
    entries, err = upstox_client.fetch_quotes([SYMBOL])
    if err or not entries:
        print("FAIL rest", err)
        return 1
    rest = entries[0]
    focus_manager.subscribe("focus", [SYMBOL], mode="full")
    focus_manager.seed_session_quotes_sync([SYMBOL])
    prices = [1288.6, 1289.0, 1287.5, 1290.2, 1288.8]
    for i, p in enumerate(prices):
        focus_manager._apply_feed(
            SYMBOL,
            {
                "fullFeed": {
                    "marketFF": {
                        "ltpc": {"ltp": float(p), "cp": float(rest.get("previous_close") or 0)},
                        "marketOHLC": {
                            "ohlc": [
                                {
                                    "interval": "1d",
                                    "open": rest.get("open"),
                                    "high": rest.get("high"),
                                    "low": rest.get("low"),
                                    "close": p,
                                }
                            ]
                        },
                    }
                }
            },
            int(time.time() * 1000) + i,
        )
        day = focus_manager.candles(SYMBOL).get("day") or {}
        print(
            f"tick{i+1} px={p} open={day.get('open')} high={day.get('high')} "
            f"low={day.get('low')} close={day.get('close')}"
        )
    day = focus_manager.candles(SYMBOL).get("day") or {}
    if abs(float(day["open"]) - float(rest["open"])) > 0.05:
        print("FAIL open drift")
        return 1
    print("PASS open locked", day["open"], "REST", rest["open"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
