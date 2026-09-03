"""
Annual vs TTM income-statement comparison from cached Screener quarterly results.

TTM  = sum of the latest 4 quarters (Sales / Net Profit)
Annual = sum of the 4 quarters of the last completed fiscal year
         (FY-end inferred as March when present, else December)
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Optional, Set

MONTH_FROM_LABEL = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

METRIC_SLUGS = {
    "total_revenue": ("sales", "revenue", "total_income"),
    "net_income": ("net_profit", "net_income", "profit_after_tax", "pat"),
}

VALID_METRICS = frozenset(METRIC_SLUGS)
VALID_CONDITIONS = frozenset({"ttm_gt_annual", "ttm_lt_annual"})
# Legacy chip keys from the first ship (Annual-centric wording).
_LEGACY_CONDITION_MAP = {
    "annual_gt_ttm": "ttm_lt_annual",  # Annual > TTM  ≡  TTM < Annual
    "annual_lt_ttm": "ttm_gt_annual",  # Annual < TTM  ≡  TTM > Annual
}
VALID_BASES = frozenset({"consolidated", "standalone"})


def _normalize_metrics(filter_def: dict[str, Any]) -> list[str]:
    raw = filter_def.get("metrics")
    if raw is None and filter_def.get("metric") is not None:
        raw = [filter_def.get("metric")]
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        m = str(item or "").strip().lower()
        if m in VALID_METRICS and m not in seen:
            out.append(m)
            seen.add(m)
    if not out:
        out = ["total_revenue"]
    # Stable order for labels / cache keys
    order = ("total_revenue", "net_income")
    return [m for m in order if m in seen] or out


def normalize_annual_vs_ttm_params(filter_def: dict[str, Any]) -> dict[str, Any]:
    metrics = _normalize_metrics(filter_def)
    condition = str(filter_def.get("condition") or "ttm_gt_annual").strip().lower()
    condition = _LEGACY_CONDITION_MAP.get(condition, condition)
    if condition not in VALID_CONDITIONS:
        condition = "ttm_gt_annual"
    basis = str(filter_def.get("basis") or "consolidated").strip().lower()
    if basis not in VALID_BASES:
        basis = "consolidated"
    return {"metrics": metrics, "condition": condition, "basis": basis}


def parse_screener_numeric(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text or text in {"-", "—"}:
        return None
    text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        n = float(text)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def period_month(period: dict | None) -> Optional[int]:
    if not isinstance(period, dict):
        return None
    date_key = str(period.get("date_key") or "").strip()
    if len(date_key) >= 7 and date_key[4] == "-":
        try:
            return int(date_key[5:7])
        except ValueError:
            pass
    label = str(period.get("period") or "").strip().lower()
    m = re.match(r"([a-z]{3})", label)
    if m:
        return MONTH_FROM_LABEL.get(m.group(1))
    return None


def infer_fy_end_month(periods: list[dict]) -> int:
    months = [period_month(p) for p in periods]
    months = [m for m in months if m is not None]
    if 3 in months:
        return 3
    if 12 in months:
        return 12
    return 3


def _row_values_for_metric(payload: dict, metric: str) -> Optional[list[Optional[float]]]:
    slugs = METRIC_SLUGS.get(metric) or ()
    rows = payload.get("rows") or []
    by_slug = {
        str(row.get("slug") or "").strip().lower(): row
        for row in rows
        if isinstance(row, dict)
    }
    chosen = None
    for slug in slugs:
        if slug in by_slug and not by_slug[slug].get("is_pdf"):
            chosen = by_slug[slug]
            break
    if chosen is None:
        # Label fallback (Sales / Net Profit)
        want = ("sales", "revenue") if metric == "total_revenue" else ("net profit", "net income")
        for row in rows:
            if not isinstance(row, dict) or row.get("is_pdf"):
                continue
            label = str(row.get("label") or "").strip().lower()
            if any(w in label for w in want):
                chosen = row
                break
    if chosen is None:
        return None
    raw_values = chosen.get("values") or []
    periods = payload.get("periods") or []
    n = len(periods)
    if n < 4:
        return None
    out: list[Optional[float]] = []
    for i in range(n):
        raw = raw_values[i] if i < len(raw_values) else None
        out.append(parse_screener_numeric(raw))
    return out


def compute_annual_and_ttm(
    payload: dict,
    metric: str,
) -> Optional[tuple[float, float, dict[str, Any]]]:
    """
    Returns (annual, ttm, meta) or None when insufficient data.
    """
    periods = payload.get("periods") or []
    if not isinstance(periods, list) or len(periods) < 4:
        return None
    values = _row_values_for_metric(payload, metric)
    if values is None or len(values) < 4:
        return None

    ttm_slice = values[-4:]
    if any(v is None for v in ttm_slice):
        return None
    ttm = float(sum(ttm_slice))  # type: ignore[arg-type]

    fy_end = infer_fy_end_month(periods)
    annual_end = None
    for i in range(len(periods) - 1, 2, -1):
        if period_month(periods[i]) == fy_end:
            annual_end = i
            break
    if annual_end is None:
        return None
    annual_slice = values[annual_end - 3 : annual_end + 1]
    if len(annual_slice) != 4 or any(v is None for v in annual_slice):
        return None
    annual = float(sum(annual_slice))  # type: ignore[arg-type]

    meta = {
        "fy_end_month": fy_end,
        "annual_end_period": (periods[annual_end] or {}).get("period"),
        "ttm_end_period": (periods[-1] or {}).get("period"),
        "annual": annual,
        "ttm": ttm,
    }
    return annual, ttm, meta


def passes_ttm_vs_annual(annual: float, ttm: float, condition: str) -> bool:
    cond = _LEGACY_CONDITION_MAP.get(condition, condition)
    if cond == "ttm_gt_annual":
        return ttm > annual
    if cond == "ttm_lt_annual":
        return ttm < annual
    return False


# Back-compat alias for older imports/tests
def passes_annual_vs_ttm(annual: float, ttm: float, condition: str) -> bool:
    return passes_ttm_vs_annual(annual, ttm, condition)


def _pick_payload_for_symbol(
    by_symbol: dict[str, dict[str, dict]],
    symbol: str,
    preferred_basis: str,
) -> Optional[dict]:
    bases = by_symbol.get(symbol) or {}
    if preferred_basis in bases:
        return bases[preferred_basis]
    # Fallback to the other basis so coverage is not empty.
    for b in ("consolidated", "standalone"):
        if b in bases:
            return bases[b]
    return None


def load_screener_quarterly_by_symbol(conn: sqlite3.Connection) -> dict[str, dict[str, dict]]:
    """
    symbol -> basis -> payload
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbol, basis, payload_json
        FROM screener_quarterly
        WHERE basis IN ('consolidated', 'standalone')
        """
    )
    out: dict[str, dict[str, dict]] = {}
    for symbol, basis, payload_json in cur.fetchall():
        sym = str(symbol or "").strip().upper()
        b = str(basis or "").strip().lower()
        if not sym or b not in VALID_BASES:
            continue
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload["symbol"] = sym
        payload["basis"] = b
        out.setdefault(sym, {})[b] = payload
    return out


def query_annual_vs_ttm_symbols(
    conn: sqlite3.Connection,
    filter_def: dict[str, Any],
    sector_symbols: Optional[Set[str]] = None,
) -> list[str]:
    params = normalize_annual_vs_ttm_params(filter_def)
    metrics = params["metrics"]
    condition = params["condition"]
    basis = params["basis"]

    by_symbol = load_screener_quarterly_by_symbol(conn)
    matches: list[str] = []
    for sym in sorted(by_symbol.keys()):
        if sector_symbols is not None and sym not in sector_symbols:
            continue
        payload = _pick_payload_for_symbol(by_symbol, sym, basis)
        if not payload:
            continue
        ok = True
        for metric in metrics:
            computed = compute_annual_and_ttm(payload, metric)
            if computed is None:
                ok = False
                break
            annual, ttm, _meta = computed
            if not passes_ttm_vs_annual(annual, ttm, condition):
                ok = False
                break
        if ok:
            matches.append(sym)
    return matches
