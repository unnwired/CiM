"""Tests for MACD histogram chain filter (same-side and cross-zero crossover)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

SERVER_PKG = ROOT / "packages" / "server"
if str(SERVER_PKG) not in sys.path:
    sys.path.insert(0, str(SERVER_PKG))

from macd_hist_chain_filter import (  # noqa: E402
    bars_needed_for_filter,
    evaluate_macd_hist_chain,
    normalize_macd_hist_chain_params,
    resolve_cross_zero_segments,
)


class MacdHistChainFilterTests(unittest.TestCase):
    def test_bars_needed_cross_zero(self):
        p = normalize_macd_hist_chain_params({
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        })
        self.assertEqual(bars_needed_for_filter(p), 7)

    def test_parse_bool_false_string(self):
        p = normalize_macd_hist_chain_params({"allow_cross_zero": "false"})
        self.assertFalse(p["allow_cross_zero"])

    def test_legacy_both_normalizes_to_negative(self):
        p = normalize_macd_hist_chain_params({"histogram_side": "both"})
        self.assertEqual(p["histogram_side"], "negative")

    def test_hdfcbank_like_all_negative_fails_cross_zero(self):
        chain = [-21.822, -28.1827, -27.3523, -27.0727, -25.7222, -24.3542, -23.5529]
        f_off = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allowed_stragglers": 0,
            "allow_cross_zero": False,
        }
        f_on = {**f_off, "allow_cross_zero": True, "cross_zero_bars": 3, "cross_zero_stragglers": 0}
        self.assertTrue(evaluate_macd_hist_chain(chain, f_off))
        self.assertFalse(evaluate_macd_hist_chain(chain, f_on))

    def test_receding_negative_cross_zero_requires_newest_positive(self):
        chain = [-4.0, -3.0, -2.0, -1.0, 1.0, 2.0, -0.5]
        f = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertFalse(evaluate_macd_hist_chain(chain, f))

    def test_same_side_negative_receding_pass(self):
        chain = [-5.0, -4.0, -3.0, -2.0, -1.0]
        f = {"histogram_side": "negative", "chain_mode": "receding", "bars_to_compare": 5}
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_same_side_negative_receding_fail_wrong_side(self):
        chain = [-3.0, -2.0, -1.0, 1.0]
        f = {"histogram_side": "negative", "chain_mode": "receding", "bars_to_compare": 4}
        self.assertFalse(evaluate_macd_hist_chain(chain, f))

    def test_same_side_positive_increasing_pass(self):
        chain = [1.0, 2.0, 3.0, 4.0]
        f = {"histogram_side": "positive", "chain_mode": "increasing", "bars_to_compare": 4}
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_receding_negative_cross_zero_pass(self):
        chain = [-4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0]
        f = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_receding_negative_cross_zero_fail_opposite_receding(self):
        chain = [-4.0, -3.0, -2.0, -1.0, 3.0, 2.0, 1.0]
        f = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertFalse(evaluate_macd_hist_chain(chain, f))

    def test_receding_positive_cross_zero_pass(self):
        chain = [4.0, 3.0, 2.0, 1.0, -1.0, -2.0, -3.0]
        f = {
            "histogram_side": "positive",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_increasing_negative_cross_zero_pass(self):
        chain = [5.0, 4.0, 3.0, -1.0, -2.0, -3.0, -4.0]
        f = {
            "histogram_side": "negative",
            "chain_mode": "increasing",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_increasing_negative_segment_order(self):
        chain = [5.0, 4.0, 3.0, -1.0, -2.0, -3.0, -4.0]
        params = normalize_macd_hist_chain_params({
            "histogram_side": "negative",
            "chain_mode": "increasing",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        })
        seg_sel, seg_opp = resolve_cross_zero_segments(chain, params)
        self.assertEqual(seg_opp, [5.0, 4.0, 3.0])
        self.assertEqual(seg_sel, [-1.0, -2.0, -3.0, -4.0])

    def test_increasing_positive_cross_zero_pass(self):
        chain = [-5.0, -4.0, -3.0, 1.0, 2.0, 3.0, 4.0]
        f = {
            "histogram_side": "positive",
            "chain_mode": "increasing",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_cross_zero_no_sign_flip_fails(self):
        chain = [-4.0, -3.0, -2.0, -1.0, -0.5, -0.3, -0.1]
        f = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
        }
        self.assertFalse(evaluate_macd_hist_chain(chain, f))

    def test_stragglers_per_segment_independent(self):
        chain = [-4.0, -3.0, -2.0, -1.5, 1.0, 2.0, 2.5]
        f = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allowed_stragglers": 1,
            "allow_cross_zero": True,
            "cross_zero_bars": 3,
            "cross_zero_stragglers": 1,
        }
        self.assertTrue(evaluate_macd_hist_chain(chain, f))

    def test_cross_zero_disabled_uses_tail_on_selected_side_only(self):
        chain = [-5.0, -4.0, -3.0, -2.0, -1.0, 3.0, 2.0, 1.0]
        f = {
            "histogram_side": "negative",
            "chain_mode": "receding",
            "bars_to_compare": 4,
            "allow_cross_zero": False,
        }
        self.assertFalse(evaluate_macd_hist_chain(chain, f))
        self.assertTrue(evaluate_macd_hist_chain([-4.0, -3.0, -2.0, -1.0], f))


if __name__ == "__main__":
    unittest.main()
