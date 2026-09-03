"""Unit tests for TradingView quarterly overlay matching."""
from __future__ import annotations

from datetime import date

import tv_quarterly_overlay as ov


def test_period_end_from_date_key():
    assert ov.period_end_date({"date_key": "2024-09-30", "period": "Sep 2024"}) == date(2024, 9, 30)


def test_period_end_from_label():
    assert ov.period_end_date({"period": "Mar 2025"}) == date(2025, 3, 31)
    assert ov.period_end_date({"period": "Sep 2024"}) == date(2024, 9, 30)


def test_match_release_within_window():
    periods = [
        {"period": "Jun 2024", "date_key": "2024-06-30"},
        {"period": "Sep 2024", "date_key": "2024-09-30"},
        {"period": "Dec 2024", "date_key": "2024-12-31"},
    ]
    # Print ~1 month after Sep quarter end → Sep column
    assert ov.match_release_to_period_index("2024-10-28", periods) == 1
    # Before earliest period end → no match
    assert ov.match_release_to_period_index("2024-06-15", periods) is None
    # Too far after Dec end → no match
    assert ov.match_release_to_period_index("2025-07-01", periods) is None


def test_assign_prefers_tighter_delta():
    periods = [
        {"period": "Jun 2024", "date_key": "2024-06-30"},
        {"period": "Sep 2024", "date_key": "2024-09-30"},
    ]
    # Release 5 days after Sep end beats being 100 days after Jun end
    idx = ov.match_release_to_period_index("2024-10-05", periods)
    assert idx == 1


def test_build_tv_overlay_rows_fills_matched_quarter():
    periods = [
        {"period": "Jun 2024", "date_key": "2024-06-30"},
        {"period": "Sep 2024", "date_key": "2024-09-30"},
        {"period": "Dec 2024", "date_key": "2024-12-31"},
    ]
    events = [
        {
            "earnings_release_date": "2024-10-28",
            "eps_actual": 12.5,
            "eps_estimate": 11.0,
            "revenue_actual": 5.5e10,
            "revenue_estimate": 5.0e10,
        },
        {
            "earnings_release_next_date": "2025-01-20",
            "eps_estimate": 13.0,
            "revenue_estimate": 5.8e10,
        },
    ]
    rows = ov.build_tv_overlay_rows(periods, events)
    assert len(rows) == 4
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["tv_eps_estimate"]["values"] == [None, 11.0, 13.0]
    assert by_slug["tv_eps_actual"]["values"] == [None, 12.5, None]
    assert by_slug["tv_rev_estimate"]["values"] == [None, 5.0e10, 5.8e10]
    assert by_slug["tv_rev_actual"]["values"] == [None, 5.5e10, None]
    for r in rows:
        assert r["source"] == "tradingview"
        assert r["is_pdf"] is False


def test_richer_event_keeps_actuals():
    periods = [{"period": "Sep 2024", "date_key": "2024-09-30"}]
    events = [
        {
            "earnings_release_date": "2024-10-28",
            "eps_actual": 12.5,
            "eps_estimate": 11.0,
            "revenue_actual": 1e10,
            "revenue_estimate": 9e9,
        },
        {
            "earnings_release_date": "2024-10-28",
            "eps_estimate": 99.0,
            "revenue_estimate": 99.0,
        },
    ]
    rows = ov.build_tv_overlay_rows(periods, events)
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["tv_eps_actual"]["values"] == [12.5]
    assert by_slug["tv_eps_estimate"]["values"] == [11.0]
    assert by_slug["tv_rev_actual"]["values"] == [1e10]


def test_normalize_overlay_event():
    assert ov.normalize_overlay_event(None) is None
    assert ov.normalize_overlay_event({}) is None
    got = ov.normalize_overlay_event({
        "earnings_release_next_date": "2025-04-15T00:00:00",
        "eps_estimate": "10.5",
        "revenue_estimate": "1000000000",
    })
    assert got["earnings_release_date"] == "2025-04-15"
    assert got["eps_estimate"] == 10.5
    assert got["revenue_estimate"] == 1e9
    assert got["eps_actual"] is None


def test_normalize_rejects_screener_hybrid():
    assert ov.normalize_overlay_event({
        "earnings_release_date": "2024-10-28",
        "eps_actual": 1.0,
        "revenue_actual": 5.06e9,
        "eps_estimate": 11.0,
        "revenue_estimate": 7.9e9,
        "source": "tv_estimate_vs_screener_consolidated",
        "comparison_source": "tv_reported_estimate_vs_screener_consolidated",
    }) is None
    # Pure TV source still accepted
    got = ov.normalize_overlay_event({
        "earnings_release_date": "2024-10-28",
        "revenue_actual": 1.345e10,
        "revenue_estimate": 7.9e9,
        "source": "tradingview_reported",
        "comparison_source": "tradingview_reported",
    })
    assert got is not None
    assert got["revenue_actual"] == 1.345e10
