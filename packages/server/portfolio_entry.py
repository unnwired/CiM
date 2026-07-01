"""Portfolio entry price and P/L % helpers."""
from __future__ import annotations

from typing import Any, Optional


def parse_entry_price(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def compute_pl_pct(price: Any, entry_price: Any) -> Optional[float]:
    """Return P/L % vs entry: ((price - entry) / entry) * 100, rounded to 2 dp."""
    try:
        px = float(price)
        entry = float(entry_price)
    except (TypeError, ValueError):
        return None
    if entry <= 0 or px != px:  # NaN guard
        return None
    return round((px - entry) / entry * 100.0, 2)
