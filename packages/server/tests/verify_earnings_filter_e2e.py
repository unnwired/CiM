"""One-off E2E check: earnings filter must return symbols via combined path."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import server.server as srv  # noqa: E402


def main() -> int:
    srv.invalidate_filter_cache()
    body = {
        "filter_type": "earnings",
        "report_window": "month_range",
        "from_year": 2026,
        "from_month": 4,
        "to_year": 2026,
        "to_month": 6,
        "eps_surprise_min": 0.0,
        "revenue_surprise_min": 0.0,
    }
    print("=== filter_earnings (direct) ===")
    direct = srv.filter_earnings(body)
    direct_syms = direct.get("symbols") or []
    print(f"count={direct.get('count')} sample={direct_syms[:10]}")

    print("=== _combined_filter_symbols ===")
    combined = srv._combined_filter_symbols([body], [])
    combined_list = sorted(combined or [])
    print(f"count={len(combined_list)} sample={combined_list[:10]}")

    if not direct_syms:
        print("FAIL: direct filter_earnings returned zero symbols")
        return 1
    if not combined_list:
        print("FAIL: combined path returned zero symbols")
        return 1
    if set(direct_syms) != set(combined_list):
        print("FAIL: combined set differs from direct filter_earnings")
        return 1
    print("OK: earnings filter E2E passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
