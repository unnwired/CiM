"""MACD histogram chain filter — same-side or two-phase cross-zero crossover."""
from __future__ import annotations

from typing import Any


def parse_hist_chain(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    chain: list[float] = []
    for token in str(raw).split("|"):
        t = token.strip()
        if not t:
            continue
        try:
            chain.append(float(t))
        except (TypeError, ValueError):
            return None
    return chain if chain else None


def _parse_bool(value: Any) -> bool:
    """Strict bool coercion — bool('false') must stay False."""
    if value is True or value == 1:
        return True
    if value is False or value == 0 or value is None:
        return False
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off", ""):
            return False
    return bool(value)


def normalize_macd_hist_chain_params(filter_def: dict[str, Any]) -> dict[str, Any]:
    bars_to_compare = max(2, min(30, int(filter_def.get("bars_to_compare", 4) or 4)))
    allowed_stragglers = max(0, min(int(filter_def.get("allowed_stragglers", 0) or 0), bars_to_compare - 1))
    histogram_side = str(filter_def.get("histogram_side", "negative") or "negative").strip().lower()
    if histogram_side not in ("negative", "positive"):
        histogram_side = "negative"
    chain_mode = str(filter_def.get("chain_mode", "increasing") or "increasing").strip().lower()
    if chain_mode not in ("receding", "increasing"):
        chain_mode = "increasing"
    allow_cross_zero = _parse_bool(filter_def.get("allow_cross_zero", False))
    cross_zero_bars = max(1, min(30, int(filter_def.get("cross_zero_bars", 1) or 1)))
    cross_zero_stragglers = max(
        0,
        min(int(filter_def.get("cross_zero_stragglers", 0) or 0), cross_zero_bars - 1),
    )
    if not allow_cross_zero:
        cross_zero_bars = 0
        cross_zero_stragglers = 0
    return {
        "bars_to_compare": bars_to_compare,
        "allowed_stragglers": allowed_stragglers,
        "histogram_side": histogram_side,
        "chain_mode": chain_mode,
        "allow_cross_zero": allow_cross_zero,
        "cross_zero_bars": cross_zero_bars,
        "cross_zero_stragglers": cross_zero_stragglers,
    }


def bars_needed_for_filter(params: dict[str, Any]) -> int:
    """Minimum histogram bars required in chain_all for evaluation."""
    if params.get("allow_cross_zero"):
        return int(params["bars_to_compare"]) + int(params["cross_zero_bars"])
    return int(params["bars_to_compare"])


def bars_needed_for_filter_def(filter_def: dict[str, Any]) -> int:
    return bars_needed_for_filter(normalize_macd_hist_chain_params(filter_def))


def _chain_matches_magnitude(chain: list[float], chain_mode: str, allowed_stragglers: int) -> bool:
    if len(chain) < 2:
        return len(chain) == 1
    violations = 0
    for i in range(1, len(chain)):
        if chain_mode == "increasing":
            is_match = abs(chain[i]) > abs(chain[i - 1])
        else:
            is_match = abs(chain[i]) < abs(chain[i - 1])
        if not is_match:
            violations += 1
            if violations > allowed_stragglers:
                return False
    return True


def _segment_on_side(chain: list[float], histogram_side: str) -> bool:
    if histogram_side == "negative":
        return all(v < 0 for v in chain)
    return all(v > 0 for v in chain)


def _opposite_side(histogram_side: str) -> str:
    return "positive" if histogram_side == "negative" else "negative"


def _junction_crosses_zero(seg1: list[float], seg2: list[float]) -> bool:
    if not seg1 or not seg2:
        return False
    a, b = seg1[-1], seg2[0]
    if a == 0 or b == 0:
        return False
    return (a < 0 < b) or (a > 0 > b)


def _newest_bar_in_post_cross_phase(chain_all: list[float], params: dict[str, Any]) -> bool:
    """Newest bar must be on the post-cross leg (opposite side for receding, selected for increasing)."""
    if not chain_all:
        return False
    v = chain_all[-1]
    if v == 0:
        return False
    histogram_side = params["histogram_side"]
    chain_mode = params["chain_mode"]
    if chain_mode == "receding":
        if histogram_side == "negative":
            return v > 0
        return v < 0
    if histogram_side == "negative":
        return v < 0
    return v > 0


def resolve_cross_zero_segments(
    chain_all: list[float], params: dict[str, Any]
) -> tuple[list[float], list[float]] | None:
    """Return (selected-side segment, opposite-side segment) oldest→newest within the window."""
    bars_to_compare = params["bars_to_compare"]
    cross_zero_bars = params["cross_zero_bars"]
    total = bars_to_compare + cross_zero_bars
    if len(chain_all) < total:
        return None
    window = chain_all[-total:]
    if params["chain_mode"] == "receding":
        seg_selected = window[:bars_to_compare]
        seg_opposite = window[bars_to_compare:]
    else:
        seg_opposite = window[:cross_zero_bars]
        seg_selected = window[cross_zero_bars:]
    return seg_selected, seg_opposite


def evaluate_macd_hist_chain(chain_all: list[float], filter_def: dict[str, Any]) -> bool:
    params = normalize_macd_hist_chain_params(filter_def)
    histogram_side = params["histogram_side"]
    chain_mode = params["chain_mode"]
    allow_cross_zero = params["allow_cross_zero"]

    if allow_cross_zero:
        segments = resolve_cross_zero_segments(chain_all, params)
        if segments is None:
            return False
        seg_selected, seg_opposite = segments
        opposite_side = _opposite_side(histogram_side)

        if not _segment_on_side(seg_selected, histogram_side):
            return False
        if not _chain_matches_magnitude(seg_selected, chain_mode, params["allowed_stragglers"]):
            return False

        if not _segment_on_side(seg_opposite, opposite_side):
            return False
        opposite_mode = "increasing" if chain_mode == "receding" else "receding"
        if not _chain_matches_magnitude(seg_opposite, opposite_mode, params["cross_zero_stragglers"]):
            return False

        if chain_mode == "receding":
            if not _junction_crosses_zero(seg_selected, seg_opposite):
                return False
        else:
            if not _junction_crosses_zero(seg_opposite, seg_selected):
                return False
        if not _newest_bar_in_post_cross_phase(chain_all, params):
            return False
        return True

    bars_to_compare = params["bars_to_compare"]
    if len(chain_all) < bars_to_compare:
        return False
    chain = chain_all[-bars_to_compare:]
    if not _segment_on_side(chain, histogram_side):
        return False
    return _chain_matches_magnitude(chain, chain_mode, params["allowed_stragglers"])
