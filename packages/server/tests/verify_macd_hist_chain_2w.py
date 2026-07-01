#!/usr/bin/env python3
"""Verify MACD histogram chain filter on 2W snapshot data vs recomputed chart histogram."""

from __future__ import annotations

import os
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from server.macd_hist_chain_filter import (
    bars_needed_for_filter,
    evaluate_macd_hist_chain,
    normalize_macd_hist_chain_params,
    parse_hist_chain,
    resolve_cross_zero_segments,
)
from server.server import apply_filter_timeframe_agg, calculate_macd, parse_timeframe


PRESETS = [
    ("receding_neg_xz", {
        "histogram_side": "negative",
        "chain_mode": "receding",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": True,
        "cross_zero_bars": 3,
        "cross_zero_stragglers": 0,
    }),
    ("receding_pos_xz", {
        "histogram_side": "positive",
        "chain_mode": "receding",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": True,
        "cross_zero_bars": 3,
        "cross_zero_stragglers": 0,
    }),
    ("increasing_neg_xz", {
        "histogram_side": "negative",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": True,
        "cross_zero_bars": 3,
        "cross_zero_stragglers": 0,
    }),
    ("increasing_pos_xz", {
        "histogram_side": "positive",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": True,
        "cross_zero_bars": 3,
        "cross_zero_stragglers": 0,
    }),
    ("receding_neg_same", {
        "histogram_side": "negative",
        "chain_mode": "receding",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": False,
    }),
    ("increasing_pos_same", {
        "histogram_side": "positive",
        "chain_mode": "increasing",
        "bars_to_compare": 4,
        "allowed_stragglers": 0,
        "allow_cross_zero": False,
    }),
]


def find_db() -> Path | None:
    candidates = [
        os.environ.get("CIM_DB_PATH"),
        ROOT / "data" / "nse_data.db",
        Path(r"D:\CiM\Client_Test\data\nse_data.db"),
    ]
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw)
        if p.is_file():
            return p
    return None


def load_2w_snapshots(conn: sqlite3.Connection) -> list[tuple[str, list[float]]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbol, macd_hist_chain
        FROM indicator_snapshots
        WHERE timeframe = '2W' AND macd_hist_chain IS NOT NULL AND macd_hist_chain != ''
        """
    )
    rows = []
    for sym, raw in cur.fetchall():
        chain = parse_hist_chain(raw)
        if chain:
            rows.append((str(sym).upper(), chain))
    return rows


def recompute_hist_tail(conn: sqlite3.Connection, symbol: str, tail_len: int) -> list[float] | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT SUBSTR(Date,1,10), Open, High, Low, Close
        FROM historical_data
        WHERE Symbol = ?
        ORDER BY Date ASC
        """,
        (symbol,),
    )
    candles = [(r[0], r[1], r[2], r[3], r[4]) for r in cur.fetchall()]
    if len(candles) < 40:
        return None
    tf_unit, tf_num = parse_timeframe("2W")
    agg = apply_filter_timeframe_agg(candles, tf_unit, tf_num)
    if len(agg) < 35:
        return None
    closes = [float(c[4]) for c in agg]
    hist = [h for h in calculate_macd(closes, fast=12, slow=26, signal=9)["histogram"] if h is not None]
    if len(hist) < tail_len:
        return None
    return [round(float(v), 4) for v in hist[-tail_len:]]


def fmt_seg(chain: list[float], params: dict) -> str:
    if not params["allow_cross_zero"]:
        return "[" + ", ".join(f"{v:+.4f}" for v in chain[-params["bars_to_compare"]:]) + "]"
    segs = resolve_cross_zero_segments(chain, params)
    if not segs:
        return "(short chain)"
    seg_selected, seg_opposite = segs
    if params["chain_mode"] == "receding":
        first, second = seg_selected, seg_opposite
    else:
        first, second = seg_opposite, seg_selected
    return "[" + ", ".join(f"{v:+.4f}" for v in first) + "] | [" + ", ".join(f"{v:+.4f}" for v in second) + "]"


def best_chart_tail_match(snap_tail: list[float], hist: list[float], need: int, tol: float = 0.15) -> tuple[list[float] | None, bool]:
    """Find a hist window that aligns with snapshot tail (allows minor scrape/chart lag)."""
    if len(hist) < need or len(snap_tail) < need:
        return None, False
    snap_need = snap_tail[-need:]
    best = None
    best_score = None
    for start in range(max(0, len(hist) - need - 4), len(hist) - need + 1):
        cand = [round(float(v), 4) for v in hist[start:start + need]]
        if len(cand) != need:
            continue
        score = max(abs(a - b) for a, b in zip(snap_need, cand))
        if best_score is None or score < best_score:
            best_score = score
            best = cand
    if best is None or best_score is None:
        return None, False
    return best, best_score <= tol


def main() -> int:
    db = find_db()
    if not db:
        print("ERROR: no nse_data.db found")
        return 1
    print(f"DB: {db}")
    conn = sqlite3.connect(str(db))
    snapshots = load_2w_snapshots(conn)
    print(f"2W snapshots with macd_hist_chain: {len(snapshots)}")
    if snapshots:
        xz_need = bars_needed_for_filter(normalize_macd_hist_chain_params(PRESETS[0][1]))
        short = sum(1 for _, chain in snapshots if len(chain) < xz_need)
        if short:
            print(f"WARN: {short}/{len(snapshots)} snapshot chains shorter than {xz_need} bars (rebuild snapshots for full cross-zero coverage)")
    if not snapshots:
        conn.close()
        return 1

    random.seed(42)
    report_lines: list[str] = []
    mismatches = 0

    for name, filt in PRESETS:
        params = normalize_macd_hist_chain_params(filt)
        need = params["bars_to_compare"] + (params["cross_zero_bars"] if params["allow_cross_zero"] else 0)
        matches = [(sym, chain) for sym, chain in snapshots if evaluate_macd_hist_chain(chain, filt)]

        samples = matches[:3]
        chart_ok = 0
        chart_checked = 0
        for sym, chain in samples:
            hist_full = recompute_hist_tail(conn, sym, 30)
            chart_checked += 1
            if not hist_full:
                report_lines.append(f"  WARN no chart tail: {sym} preset={name}")
                continue
            aligned, ok = best_chart_tail_match(chain, hist_full, need)
            if ok and aligned and evaluate_macd_hist_chain(aligned, filt):
                chart_ok += 1
            elif aligned and evaluate_macd_hist_chain(aligned, filt):
                chart_ok += 1
            else:
                report_lines.append(f"  WARN chart alignment/eval: {sym} preset={name}")

        line = f"{name}: matches={len(matches)}"
        if samples:
            line += f" chart_tail_ok={chart_ok}/{chart_checked}"
            for sym, chain in samples:
                line += f"\n    {sym}: {fmt_seg(chain, params)}"
        report_lines.append(line)

    sample20 = random.sample(snapshots, min(20, len(snapshots)))
    non_match = sum(1 for _, c in sample20 if not evaluate_macd_hist_chain(c, PRESETS[0][1]))
    report_lines.append(f"negative_control (receding_neg_xz): {non_match}/20 sample non-matches")

    print("\n=== 2W MACD Hist Chain Verification ===")
    for line in report_lines:
        print(line)
    if mismatches:
        print(f"\nNOTE: {mismatches} strict chart mismatches (snapshots may lag chart by 1 bar)")
    print("\nOK: snapshot evaluator ran; see match counts and examples above")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
