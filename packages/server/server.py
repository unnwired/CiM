import json
import math
import os
import re
import signal
import sys
import subprocess
import threading
import time as time_module
import random
import statistics
import sqlite3
import importlib.util
import smtplib
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Query, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Callable, Optional, Set, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.message import EmailMessage


def _sibling_module_path(stem: str) -> Path:
    """Resolve server/*.py or *.pyc (distribution exports strip .py sources)."""
    base = Path(__file__).resolve().parent / stem
    path = base.with_suffix(".py")
    if not path.exists():
        path = base.with_suffix(".pyc")
    return path


def _load_module_from_path(module_name: str, path: Path):
    if not path.exists():
        raise RuntimeError(f"Cannot load {module_name}: missing {path}")
    # Sibling modules (market_sectors, etc.) may use bare imports; keep server/ on path.
    parent = str(path.resolve().parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {module_name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_market_sectors():
    return _load_module_from_path(
        "nse_pulse_market_sectors",
        _sibling_module_path("market_sectors"),
    )


market_sectors = _load_market_sectors()


def _load_exchange_classification_sync():
    return _load_module_from_path(
        "nse_pulse_exchange_classification_sync",
        _sibling_module_path("exchange_classification_sync"),
    )


exchange_classification_sync = _load_exchange_classification_sync()


def _load_market_cap_live():
    return _load_module_from_path(
        "nse_pulse_market_cap_live",
        _sibling_module_path("market_cap_live"),
    )


market_cap_live = _load_market_cap_live()
_MCAP_SQL = market_cap_live.EFFECTIVE_MCAP_SQL


def _load_knowledge_base():
    return _load_module_from_path(
        "cim_knowledge_base",
        _sibling_module_path("knowledge_base"),
    )


knowledge_base = _load_knowledge_base()

# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────

import sys as _sys

_SERVER_DIR = Path(__file__).resolve().parent
if str(_SERVER_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SERVER_DIR))

from server.core.install_root import get_install_root, resolve_frontend_build_dir

BASE_DIR = get_install_root()
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "nse_dataset.csv"
_db_override = os.getenv("CIM_DB_PATH", "").strip()
DB_PATH = Path(_db_override) if _db_override else DATA_DIR / "nse_data.db"

if str(BASE_DIR) not in _sys.path:
    _sys.path.insert(0, str(BASE_DIR))
from db_sqlite import connect_sqlite as _connect_sqlite, ensure_wal_mode as _ensure_wal_mode
from tradingview_earnings import (  # noqa: E402
    lookup_tv_close_prices,
    lookup_tv_market_metrics,
    current_month_ist,
    current_year_ist,
    fetch_earnings_beats,
    fetch_earnings_calendar,
    fetch_recent_reported_for_resync,
    fetch_upcoming_estimates_for_symbols,
    is_beat_report_row,
    is_tv_eps_rev_beat_row,
    symbols_with_earnings_today,
    RECENT_RESYNC_LOOKBACK_DAYS,
)
import tv_quarterly_overlay  # noqa: E402
from server.core.cache import (
    CACHE_PROFILE_AGGRESSIVE,
    CACHE_PROFILE_NORMAL,
    CHART_CACHE_SCHEMA as _CHART_CACHE_SCHEMA,
    caches as _app_caches,
)
from server.core.migrations import run_startup_migrations
from server import price_lookback  # noqa: E402
import screener_quarters  # noqa: E402
from screener_symbol_slug import SCREENER_COMPANY_SLUG_ALIASES  # noqa: E402
from macd_hist_chain_filter import (  # noqa: E402
    bars_needed_for_filter_def,
    evaluate_macd_hist_chain,
    normalize_macd_hist_chain_params,
    parse_hist_chain,
)
from avg_volume_filter import query_avg_volume_symbols  # noqa: E402
from annual_vs_ttm_filter import (  # noqa: E402
    normalize_annual_vs_ttm_params,
    query_annual_vs_ttm_symbols,
)
from screener_screen_filter import query_screener_screen_symbols  # noqa: E402
from filter_rebuild_registry import (  # noqa: E402
    INDICATOR_FAMILIES,
    public_options_payload,
)
from range_channel_filter import (  # noqa: E402
    bars_needed_for_range_channel,
    evaluate_range_channel,
)
from snapshot_bars import chart_candles_for_timeframe  # noqa: E402
SCRAPE_INDICES_PATH = BASE_DIR / "scrape_indices.py"
SCRAPE_FINANCIALS_PATH = BASE_DIR / "scrape_financials.py"
SCRAPE_MF_PATH = BASE_DIR / "scrape_mf.py"
SCRAPE_DAILY_PATH = BASE_DIR / "scrape_daily.py"
SCRAPE_4H_PATH = BASE_DIR / "scrape_4h.py"
SCRAPE_30M_PATH = BASE_DIR / "scrape_30m.py"

VALID_SORT_COLUMNS = {
    "Symbol", "Market Cap", "Price", "Change %",
    "Monthly Change %", "PE",
    "Revenue Growth TTM YoY", "Revenue Growth Quarterly QoQ",
    "Net Income TTM YoY", "Net Income Quarterly QoQ",
    "EBITDA Growth Quarterly QoQ",
    "Market Sector",
}

SNAPSHOT_TIMEFRAMES = ("30m", "4H", "1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W", "4W", "1M")
SNAPSHOT_LIGHT_TIMEFRAMES = ("30m", "4H", "1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W")
# If fewer than this fraction of screener symbols have a row for a timeframe, skip snapshots
# for filters and use candle-based paths (partial snapshot data would otherwise cap matches).
SNAPSHOT_FILTER_MIN_COVERAGE = 0.80
# Timeframes the daily rebuild keeps current. Their snapshots must not trail the newest
# daily bar; 4W/1M come from the full rebuild only, so they keep the coverage-only check.
# 30m/4H are EOD session bars — last rebuild is authoritative (not in freshness set).
SNAPSHOT_FRESHNESS_TIMEFRAMES = frozenset({"1D", "2D", "3D", "4D", "5D", "6D", "1W", "2W"})
# Keep in sync with scrape_daily.MACD_HIST_CHAIN_MAX_BARS
MACD_HIST_CHAIN_MAX_BARS = 60
FULL_REBUILD_CONFIRM_TOKEN = "REBUILD_FULL_UNIVERSE"

NUMERIC_DISPLAY_COLUMNS = [
    "Price", "Change %", "Monthly Change %", "PE",
    "Revenue Growth TTM YoY", "Revenue Growth Quarterly QoQ",
    "Net Income TTM YoY", "Net Income Quarterly QoQ",
    "EBITDA Growth Quarterly QoQ", "Market Cap",
]

OUTPUT_COLUMNS = [
    "Symbol",
    "Market Cap",
    "Price",
    "Change %",
    "Monthly Change %",
    "PE",
    "Revenue Growth TTM YoY",
    "Revenue Growth Quarterly QoQ",
    "Net Income TTM YoY",
    "Net Income Quarterly QoQ",
    "EBITDA Growth Quarterly QoQ",
    "Market Sector",
]

FEEDBACK_TO_EMAIL = "unnwired@gmail.com"
FEEDBACK_SMTP_HOST = os.getenv("NSE_PULSE_SMTP_HOST", "")
FEEDBACK_SMTP_PORT = int(os.getenv("NSE_PULSE_SMTP_PORT", "587"))
FEEDBACK_SMTP_USER = os.getenv("NSE_PULSE_SMTP_USER", "")
FEEDBACK_SMTP_PASS = os.getenv("NSE_PULSE_SMTP_PASS", "")
FEEDBACK_FROM_EMAIL = os.getenv("NSE_PULSE_FROM_EMAIL", FEEDBACK_SMTP_USER or "noreply@cim.local")

TIMEFRAME_CONFIG = {
    "30m": {"anchor": "session_30m"},
    "4H":  {"anchor": "session_4h"},
    "1D":  {"anchor": "day",   "days": 1},
    "2D":  {"anchor": "day",   "days": 2},
    "3D":  {"anchor": "day",   "days": 3},
    "4D":  {"anchor": "day",   "days": 4},
    "5D":  {"anchor": "day",   "days": 5},
    "6D":  {"anchor": "day",   "days": 6},
    "7D":  {"anchor": "day",   "days": 7},
    "1W":  {"anchor": "week",  "weeks": 1},
    "2W":  {"anchor": "week",  "weeks": 2},
    "3W":  {"anchor": "week",  "weeks": 3},
    "4W":  {"anchor": "week",  "weeks": 4},
    "1M":  {"anchor": "month", "months": 1},
    "2M":  {"anchor": "month", "months": 2},
    "3M":  {"anchor": "month", "months": 3},
    "4M":  {"anchor": "month", "months": 4},
    "5M":  {"anchor": "month", "months": 5},
    "6M":  {"anchor": "month", "months": 6},
    "7M":  {"anchor": "month", "months": 7},
    "8M":  {"anchor": "month", "months": 8},
    "9M":  {"anchor": "month", "months": 9},
    "10M": {"anchor": "month", "months": 10},
    "11M": {"anchor": "month", "months": 11},
    "12M": {"anchor": "month", "months": 12},
}

# ──────────────────────────────────────────────
# APP INIT
# ──────────────────────────────────────────────

app = FastAPI(title="NSE Pulse API", version="1.0.0")

try:
    from update_apply import configure_install_root as _update_configure_install_root
    from update_apply import router as _cim_update_router

    _update_configure_install_root(BASE_DIR)
    app.include_router(_cim_update_router)
except Exception as _cim_update_err:
    print(f"[update] routes not loaded: {_cim_update_err}")

try:
    from server.license_routes import configure_base_dir as _license_configure_base_dir
    from server.license_routes import router as _license_router

    _license_configure_base_dir(BASE_DIR)
    app.include_router(_license_router)
except Exception as _license_err:
    print(f"[license] routes not loaded: {_license_err}")

try:
    from server.routers import settings as _settings_router

    _settings_router.configure_layout(DATA_DIR)
    app.include_router(_settings_router.router)
except Exception as _settings_err:
    print(f"[settings] routes not loaded: {_settings_err}")

try:
    from server.live_routes import router as _live_router

    app.include_router(_live_router)
except Exception as _live_err:
    print(f"[live] routes not loaded: {_live_err}")

FRONTEND_BUILD_DIR = resolve_frontend_build_dir(BASE_DIR)
if FRONTEND_BUILD_DIR.exists():
    static_dir = FRONTEND_BUILD_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv(
            "CIM_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
            ",http://localhost:8001,http://127.0.0.1:8001,http://localhost:8002,http://127.0.0.1:8002",
        ).split(",")
        if o.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
def _on_startup():
    if DB_PATH.exists():
        mode = _ensure_wal_mode(DB_PATH)
        print(f"[db] journal_mode={mode}")
        run_startup_migrations(DB_PATH)
        try:
            from server import market_data_version as _mdv

            conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
            try:
                _mdv.ensure_table(conn)
                conn.commit()
            finally:
                conn.close()
        except Exception as mdv_err:
            print(f"[market_data_version] init warning: {mdv_err}")
    market_sectors.ensure_screener_sector_columns(DB_PATH)
    market_sectors.ensure_screener_isin_column(DB_PATH)
    try:
        from server.universe_price_refresh import ensure_screener_price_columns

        conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
        try:
            ensure_screener_price_columns(conn)
        finally:
            conn.close()
    except Exception as price_col_err:
        print(f"[screener_price_columns] init warning: {price_col_err}")
    screener_quarters.ensure_screener_quarterly_table(DB_PATH)
    market_cap_live.ensure_issued_shares_column(DB_PATH)
    market_cap_live.seed_issued_from_pilot_json(DB_PATH, DATA_DIR)
    market_sectors.ensure_default_mapping_file(DATA_DIR)
    try:
        market_sectors.ensure_index_sector_cores(DATA_DIR, DB_PATH)
    except Exception as sector_core_err:
        print(f"[index-industry-sectors] init warning: {sector_core_err}")
    try:
        if hasattr(movers_live, "configure_paths"):
            movers_live.configure_paths(data_dir=DATA_DIR)
        movers_live.init(get_db_connection)
        from server import upstox_instruments

        upstox_instruments.configure_paths(data_dir=DATA_DIR)
        try:
            from server import upstox_history

            upstox_history.configure_paths(data_dir=DATA_DIR)
        except Exception:
            pass
    except Exception as e:
        print(f"[movers_live] init warning: {e}")
    try:
        _configure_admin_job_scheduler()
        print("[admin_job_scheduler] started (all tasks opt-in until enabled in Admin Scheduler)")
    except Exception as e:
        print(f"[admin_job_scheduler] init warning: {e}")
    try:
        from server import alert_evaluator
        from tradingview_earnings import fetch_earnings_calendar as _fetch_earnings_calendar

        def _alert_fetch_earnings(**kwargs):
            """Same filter path as /api/earnings-beats (incl. Earnings+ + screener prices)."""
            earnings_plus = str(kwargs.pop("earnings_plus", "all") or "all").strip().lower()
            if earnings_plus not in EARNINGS_PLUS_FILTER_MODES:
                earnings_plus = "all"
            mode = str(kwargs.get("mode") or "").strip().lower()
            payload = _fetch_earnings_calendar(**kwargs)
            if mode == "reported":
                filtered_rows, earnings_plus_cache = _apply_reported_earnings_plus_filter(
                    payload.get("rows") or [],
                    earnings_plus,
                )
                payload["earnings_plus_cache"] = earnings_plus_cache
                payload["rows"] = filtered_rows
                payload["count"] = len(filtered_rows)
                if earnings_plus != "all":
                    payload["total_matches"] = len(filtered_rows)
                    if payload.get("matched_symbols") is not None:
                        payload["matched_symbols"] = len(filtered_rows)
            return _enrich_earnings_rows_with_screener_prices(payload)

        alert_evaluator.start(BASE_DIR, DB_PATH, _alert_fetch_earnings)
        print("[alert_evaluator] started")
    except Exception as e:
        print(f"[alert_evaluator] init warning: {e}")
    # Phase C: keep critical lookups indexed for chart/filter performance.
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        ensure_earnings_chart_events_table(conn)
        ensure_earnings_plus_cache_table(conn)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_symbol_date ON historical_data(Symbol, Date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_screener_symbol ON screener(symbol)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_screener_mcap ON screener(market_cap)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS indicator_snapshots (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                close_curr REAL,
                close_prev REAL,
                open_curr REAL,
                open_prev REAL,
                high_curr REAL,
                high_prev REAL,
                low_curr REAL,
                low_prev REAL,
                ema9 REAL,
                ema9_prev REAL,
                ema21 REAL,
                ema21_prev REAL,
                ema50 REAL,
                ema50_prev REAL,
                ema100 REAL,
                ema100_prev REAL,
                ema200 REAL,
                ema200_prev REAL,
                macd REAL,
                macd_prev REAL,
                macd_signal REAL,
                macd_signal_prev REAL,
            macd_hist_chain TEXT,
                stoch_k REAL,
                stoch_k_prev REAL,
                stoch_d REAL,
                stoch_d_prev REAL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, timeframe)
            )
            """
        )
        cur.execute("PRAGMA table_info(indicator_snapshots)")
        cols = {str(r[1]).strip().lower() for r in cur.fetchall() if len(r) > 1}
        if "macd_hist_chain" not in cols:
            cur.execute("ALTER TABLE indicator_snapshots ADD COLUMN macd_hist_chain TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_indicator_snapshots_tf_symbol ON indicator_snapshots(timeframe, symbol)")
        try:
            from volume_stats_rebuild import ensure_symbol_volume_stats_table
            from range_channel_snapshots_rebuild import ensure_range_channel_snapshots_table

            ensure_symbol_volume_stats_table(conn)
            ensure_range_channel_snapshots_table(conn)
        except Exception as vol_rc_err:
            print(f"[filter_rebuild_tables] init warning: {vol_rc_err}")
        try:
            import split_utils as _split_utils_boot

            _split_utils_boot.ensure_stock_split_events_table(conn)
        except Exception as e:
            print(f"[split_utils] table ensure warning: {e}")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instrument_notes (
                symbol TEXT NOT NULL,
                instrument_type TEXT NOT NULL,
                note_text TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, instrument_type)
            )
            """
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    def _ensure_equity_indices_background():
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "scrape_indices_boot",
                SCRAPE_INDICES_PATH,
            )
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            conn = get_db_connection()
            try:
                added = mod.ensure_equity_index_rows(conn)
                if added:
                    print(f"[indices] ensured {added} equity index row(s) from NSE catalog")
                backfilled = mod.sync_nse_index_history(conn)
                if backfilled:
                    print(f"[indices] synced {backfilled} NSE index history row(s)")
            finally:
                conn.close()
        except Exception as e:
            print(f"[indices] ensure equity catalog warning: {e}")

    threading.Thread(
        target=_ensure_equity_indices_background,
        name="ensure-equity-indices",
        daemon=True,
    ).start()

    # Persisted cache mode: restore last saved operator choice on startup.
    try:
        layout = _load_layout_file()
        set_cache_mode(bool(layout.get("aggressiveCacheRam", False)))
    except Exception:
        set_cache_mode(False)
    print(
        f"[cache] Aggressive Cache (RAM): "
        f"{'ON' if AGGRESSIVE_CACHE_RAM else 'OFF'} "
        f"(chart_ttl={CHART_CACHE_TTL}s, filter_ttl={FILTER_CACHE_TTL}s)"
    )


# ──────────────────────────────────────────────
# DB HELPER
# ──────────────────────────────────────────────

def get_db_connection():
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found: {DB_PATH}")
    return _connect_sqlite(DB_PATH, row_factory=True)


def ensure_earnings_chart_events_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_chart_events (
            symbol TEXT NOT NULL,
            earnings_release_date TEXT NOT NULL,
            outcome_kind TEXT NOT NULL,
            eps_actual REAL,
            eps_estimate REAL,
            eps_surprise_pct REAL,
            revenue_actual REAL,
            revenue_estimate REAL,
            revenue_surprise_pct REAL,
            source TEXT NOT NULL DEFAULT 'tradingview_latest_fq',
            comparison_source TEXT,
            comparison_status TEXT,
            comparison_basis TEXT,
            comparison_note TEXT,
            matched_period TEXT,
            matched_period_date_key TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, earnings_release_date)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_earnings_chart_events_symbol_date "
        "ON earnings_chart_events(symbol, earnings_release_date DESC)"
    )
    cols = {
        str(r["name"]).strip().lower()
        for r in conn.execute("PRAGMA table_info(earnings_chart_events)").fetchall()
    }
    if "comparison_source" not in cols:
        conn.execute("ALTER TABLE earnings_chart_events ADD COLUMN comparison_source TEXT")
    if "comparison_status" not in cols:
        conn.execute("ALTER TABLE earnings_chart_events ADD COLUMN comparison_status TEXT")
    if "comparison_basis" not in cols:
        conn.execute("ALTER TABLE earnings_chart_events ADD COLUMN comparison_basis TEXT")
    if "comparison_note" not in cols:
        conn.execute("ALTER TABLE earnings_chart_events ADD COLUMN comparison_note TEXT")
    if "matched_period" not in cols:
        conn.execute("ALTER TABLE earnings_chart_events ADD COLUMN matched_period TEXT")
    if "matched_period_date_key" not in cols:
        conn.execute("ALTER TABLE earnings_chart_events ADD COLUMN matched_period_date_key TEXT")
    conn.execute(
        """
        UPDATE earnings_chart_events
        SET
            comparison_source = 'tradingview_reported',
            comparison_status = 'verified',
            comparison_basis = NULL,
            comparison_note = NULL,
            matched_period = NULL,
            matched_period_date_key = NULL
        WHERE comparison_status = 'discrepancy'
        """
    )


def ensure_earnings_plus_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_plus_cache (
            symbol TEXT NOT NULL PRIMARY KEY,
            decision TEXT NOT NULL,
            basis_used TEXT,
            latest_period TEXT,
            latest_period_date_key TEXT,
            previous_period TEXT,
            previous_year_period TEXT,
            note TEXT,
            source_fetched_at TEXT,
            computed_at TEXT NOT NULL,
            refresh_after TEXT NOT NULL,
            last_error TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_earnings_plus_cache_refresh_after
        ON earnings_plus_cache(refresh_after)
        """
    )


def _normalize_symbol_token(symbol: str | None) -> str:
    return str(symbol or "").strip().upper()


def _to_finite_number(value) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _parse_ymd_date(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_screener_numeric(value) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"-", "—"}:
        return None
    text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    return _to_finite_number(text)


def _compute_surprise_pct(actual: float | None, estimate: float | None) -> float | None:
    if actual is None or estimate is None:
        return None
    if estimate == 0:
        return 0.0 if actual == 0 else None
    return ((actual - estimate) / abs(estimate)) * 100.0


def _pick_latest_symbol_row(rows: list[dict], symbol: str, date_field: str) -> dict | None:
    sym = _normalize_symbol_token(symbol)
    latest = None
    for row in rows or []:
        if _normalize_symbol_token(row.get("symbol")) != sym:
            continue
        row_date = str(row.get(date_field) or "").strip()
        if not row_date:
            continue
        if latest is None or row_date > str(latest.get(date_field) or ""):
            latest = row
    return latest


def _reported_row_has_complete_outcome(row: dict | None) -> bool:
    if not row:
        return False
    return (
        _to_finite_number(row.get("eps_surprise_pct")) is not None
        and _to_finite_number(row.get("revenue_surprise_pct")) is not None
    )


def _base_event_from_row(
    *,
    symbol: str,
    earnings_release_date: str,
    outcome_kind: str,
    eps_actual,
    eps_estimate,
    eps_surprise_pct,
    revenue_actual,
    revenue_estimate,
    revenue_surprise_pct,
    source: str,
    comparison_source: str,
    comparison_status: str,
    comparison_basis: str | None = None,
    comparison_note: str | None = None,
    matched_period: str | None = None,
    matched_period_date_key: str | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "earnings_release_date": earnings_release_date,
        "outcome_kind": outcome_kind,
        "eps_actual": eps_actual,
        "eps_estimate": eps_estimate,
        "eps_surprise_pct": eps_surprise_pct,
        "revenue_actual": revenue_actual,
        "revenue_estimate": revenue_estimate,
        "revenue_surprise_pct": revenue_surprise_pct,
        "source": source,
        "comparison_source": comparison_source,
        "comparison_status": comparison_status,
        "comparison_basis": comparison_basis,
        "comparison_note": comparison_note,
        "matched_period": matched_period,
        "matched_period_date_key": matched_period_date_key,
    }


def _event_from_reported_row(row: dict) -> dict | None:
    symbol = _normalize_symbol_token(row.get("symbol"))
    earnings_release_date = str(row.get("earnings_release_date") or "").strip()
    if not symbol or not earnings_release_date:
        return None
    outcome_kind = "beat" if is_beat_report_row(row) else "miss"
    return _base_event_from_row(
        symbol=symbol,
        earnings_release_date=earnings_release_date,
        outcome_kind=outcome_kind,
        eps_actual=row.get("eps_actual"),
        eps_estimate=row.get("eps_estimate"),
        eps_surprise_pct=row.get("eps_surprise_pct"),
        revenue_actual=row.get("revenue_actual"),
        revenue_estimate=row.get("revenue_estimate"),
        revenue_surprise_pct=row.get("revenue_surprise_pct"),
        source="tradingview_reported",
        comparison_source="tradingview_reported",
        comparison_status="verified",
    )


def _event_from_incomplete_reported_row(row: dict) -> dict | None:
    symbol = _normalize_symbol_token(row.get("symbol"))
    earnings_release_date = str(row.get("earnings_release_date") or "").strip()
    if not symbol or not earnings_release_date:
        return None
    outcome_kind = "beat" if is_beat_report_row(row) else "miss"
    return _base_event_from_row(
        symbol=symbol,
        earnings_release_date=earnings_release_date,
        outcome_kind=outcome_kind,
        eps_actual=row.get("eps_actual"),
        eps_estimate=row.get("eps_estimate"),
        eps_surprise_pct=row.get("eps_surprise_pct"),
        revenue_actual=row.get("revenue_actual"),
        revenue_estimate=row.get("revenue_estimate"),
        revenue_surprise_pct=row.get("revenue_surprise_pct"),
        source="tradingview_reported_incomplete",
        comparison_source="tradingview_reported_incomplete",
        comparison_status="unverified",
        comparison_note="TradingView reported row is incomplete and Screener fallback was unavailable.",
    )


def _extract_latest_screener_consolidated_metrics(symbol: str) -> dict | None:
    payload, status = screener_quarters.get_quarters(
        DB_PATH,
        DATA_DIR,
        symbol,
        "consolidated",
        fetch_if_missing=True,
        force_refresh=False,
    )
    if status == "error" or not payload:
        return None
    periods = payload.get("periods") or []
    rows = payload.get("rows") or []
    if not periods or not rows:
        return None
    latest_idx = len(periods) - 1
    latest_period = periods[latest_idx] or {}
    row_by_slug = {
        str(row.get("slug") or "").strip().lower(): row
        for row in rows
    }
    sales_row = row_by_slug.get("sales")
    eps_row = row_by_slug.get("eps_in_rs")
    if not eps_row:
        eps_row = next(
            (row for row in rows if "eps" in str(row.get("label") or "").strip().lower()),
            None,
        )
    sales_actual = None
    eps_actual = None
    if sales_row:
        sales_values = sales_row.get("values") or []
        if latest_idx < len(sales_values):
            sales_actual = _parse_screener_numeric(sales_values[latest_idx])
    if eps_row:
        eps_values = eps_row.get("values") or []
        if latest_idx < len(eps_values):
            eps_actual = _parse_screener_numeric(eps_values[latest_idx])
    if sales_actual is None and eps_actual is None:
        return None
    return {
        "period": str(latest_period.get("period") or "").strip(),
        "period_date_key": str(latest_period.get("date_key") or "").strip(),
        "sales_actual": (sales_actual * 1e7) if sales_actual is not None else None,
        "eps_actual": eps_actual,
        "fetched_at": payload.get("fetched_at"),
    }


def _screener_row_by_slug(rows: list[dict]) -> dict[str, dict]:
    return {
        str(row.get("slug") or "").strip().lower(): row
        for row in rows or []
    }


def _screener_row_value(row: dict | None, index: int) -> float | None:
    if not row or index < 0:
        return None
    values = row.get("values") or []
    if index >= len(values):
        return None
    return _parse_screener_numeric(values[index])


def _payload_latest_period_meta(payload: dict | None) -> tuple[str | None, str | None]:
    """Return (period_label, date_key) for the last Screener quarter column."""
    if not isinstance(payload, dict):
        return None, None
    periods = payload.get("periods") or []
    if not periods:
        return None, None
    last = periods[-1] if isinstance(periods[-1], dict) else {}
    label = str(last.get("period") or "").strip() or None
    date_key = str(last.get("date_key") or "").strip() or None
    return label, date_key


def _fmt_earnings_plus_metric(value: float | None, *, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    if percent:
        return f"{value:g}%"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


EARNINGS_PLUS_CACHE_REFRESH_HOURS = 18
# Keep at 1: Screener scrapes write screener_quarterly; parallel workers lock SQLite.
EARNINGS_PLUS_REFRESH_WORKERS = 1
EARNINGS_PLUS_REFRESH_STALL_SEC = 120
# TradingView print ↔ Screener quarterly update: expect Screener the same day,
# a day early, or up to a couple of days later — not a quarter-end calendar span.
EARNINGS_PLUS_SCREENER_SYNC_DAYS = 2
# Prefer standalone when consolidated Screener quarters lag by more than this.
EARNINGS_PLUS_BASIS_LAG_DAYS = 80
# Used only by provisional chart fallback (TV estimates vs Screener actuals), not E+ badges.
EARNINGS_PLUS_CHART_PERIOD_MAX_DAYS = 150
# Start Screener/E+ pull this many days before an upcoming TV earnings date.
EARNINGS_PLUS_UPCOMING_PRESCAN_LEAD_DAYS = 1
_earnings_plus_progress_lock = threading.Lock()
_earnings_plus_db_write_lock = threading.Lock()
_earnings_plus_bg_sync_lock = threading.Lock()
_earnings_plus_bg_sync_pending: set[str] = set()
_earnings_plus_bg_sync_running = False


def _now_db_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_db_timestamp(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _timestamp_is_stale(value: str | None, *, max_age_hours: int = EARNINGS_PLUS_CACHE_REFRESH_HOURS) -> bool:
    parsed = _parse_db_timestamp(value)
    if parsed is None:
        return True
    return (datetime.now() - parsed) > timedelta(hours=max_age_hours)


def _earnings_plus_refresh_after_timestamp() -> str:
    return (datetime.now() + timedelta(hours=EARNINGS_PLUS_CACHE_REFRESH_HOURS)).strftime("%Y-%m-%d %H:%M:%S")


def _earnings_plus_period_mismatch(entry: dict | None, local_latest_period_date_key: str | None) -> bool:
    """True when local Screener quarters moved past the quarter the cache was scored on."""
    if not entry:
        return bool(str(local_latest_period_date_key or "").strip())
    cached = str(entry.get("latest_period_date_key") or "").strip()
    local = str(local_latest_period_date_key or "").strip()
    if local and cached and local != cached:
        return True
    if local and not cached:
        return True
    return False


def _earnings_plus_cache_is_stale(
    entry: dict | None,
    local_latest_period_date_key: str | None = None,
) -> bool:
    """
    Whether an Earnings+ cache row should be treated as stale for filters/charts/refresh.

    Qualified / not_qualified do not age out by clock alone, but they ARE stale when
    local Screener quarterly data has a newer latest period than the cached decision.
    Insufficient / failed rows still expire on refresh_after / source age.
    """
    if not entry:
        return True
    if _earnings_plus_period_mismatch(entry, local_latest_period_date_key):
        return True
    decision = str(entry.get("decision") or "").strip().lower()
    if decision in ("qualified", "not_qualified"):
        return False
    if decision == "insufficient_data":
        if not entry.get("source_fetched_at"):
            return True
        return _timestamp_is_stale(entry.get("refresh_after")) or _timestamp_is_stale(
            entry.get("source_fetched_at")
        )
    return _timestamp_is_stale(entry.get("refresh_after")) or _timestamp_is_stale(
        entry.get("source_fetched_at")
    )


def _evaluate_earnings_plus_payload(payload: dict | None, basis: str) -> dict:
    basis_label = "Consolidated" if basis == "consolidated" else "Standalone"
    empty = {
        "decision": "insufficient_data",
        "basis_used": basis,
        "latest_period": None,
        "latest_period_date_key": None,
        "previous_period": None,
        "previous_year_period": None,
        "note": f"{basis_label} Screener quarterly data is incomplete for Earnings+.",
        "source_fetched_at": payload.get("fetched_at") if isinstance(payload, dict) else None,
    }
    if not isinstance(payload, dict):
        return empty
    periods = payload.get("periods") or []
    rows = payload.get("rows") or []
    if len(periods) < 5 or not rows:
        return empty
    latest_idx = len(periods) - 1
    previous_idx = latest_idx - 1
    previous_year_idx = latest_idx - 4
    if previous_idx < 0 or previous_year_idx < 0:
        return empty

    row_by_slug = _screener_row_by_slug(rows)
    opm_row = row_by_slug.get("opm")
    net_profit_row = row_by_slug.get("net_profit")
    eps_row = row_by_slug.get("eps_in_rs")
    if not eps_row:
        eps_row = next(
            (row for row in rows if "eps" in str(row.get("label") or "").strip().lower()),
            None,
        )
    if not opm_row or not net_profit_row or not eps_row:
        return empty

    latest_opm = _screener_row_value(opm_row, latest_idx)
    previous_opm = _screener_row_value(opm_row, previous_idx)
    previous_year_opm = _screener_row_value(opm_row, previous_year_idx)

    latest_profit = _screener_row_value(net_profit_row, latest_idx)
    previous_profit = _screener_row_value(net_profit_row, previous_idx)
    previous_year_profit = _screener_row_value(net_profit_row, previous_year_idx)

    latest_eps = _screener_row_value(eps_row, latest_idx)
    previous_eps = _screener_row_value(eps_row, previous_idx)
    previous_year_eps = _screener_row_value(eps_row, previous_year_idx)

    if any(
        value is None
        for value in (
            latest_opm,
            previous_opm,
            previous_year_opm,
            latest_profit,
            previous_profit,
            previous_year_profit,
            latest_eps,
            previous_eps,
            previous_year_eps,
        )
    ):
        return empty

    latest_period = periods[latest_idx] or {}
    previous_period = periods[previous_idx] or {}
    previous_year_period = periods[previous_year_idx] or {}
    latest_period_label = str(latest_period.get("period") or "").strip()
    previous_period_label = str(previous_period.get("period") or "").strip()
    previous_year_period_label = str(previous_year_period.get("period") or "").strip()

    opm_qoq_ok = latest_opm >= previous_opm
    opm_yoy_ok = latest_opm >= previous_year_opm
    profit_qoq_ok = latest_profit > previous_profit
    profit_yoy_ok = latest_profit > previous_year_profit
    eps_qoq_ok = latest_eps > previous_eps
    eps_yoy_ok = latest_eps > previous_year_eps
    matches = all((opm_qoq_ok, opm_yoy_ok, profit_qoq_ok, profit_yoy_ok, eps_qoq_ok, eps_yoy_ok))

    opm_l = _fmt_earnings_plus_metric(latest_opm, percent=True)
    opm_q = _fmt_earnings_plus_metric(previous_opm, percent=True)
    opm_y = _fmt_earnings_plus_metric(previous_year_opm, percent=True)
    np_l = _fmt_earnings_plus_metric(latest_profit)
    np_q = _fmt_earnings_plus_metric(previous_profit)
    np_y = _fmt_earnings_plus_metric(previous_year_profit)
    eps_l = _fmt_earnings_plus_metric(latest_eps)
    eps_q = _fmt_earnings_plus_metric(previous_eps)
    eps_y = _fmt_earnings_plus_metric(previous_year_eps)

    if matches:
        note = (
            f"{basis_label} Earnings+: {latest_period_label} beats "
            f"{previous_period_label} (QoQ) and {previous_year_period_label} (YoY) — "
            f"OPM {opm_l} (≥ {opm_q}, ≥ {opm_y}); "
            f"Net Profit {np_l} (> {np_q}, > {np_y}); "
            f"EPS {eps_l} (> {eps_q}, > {eps_y})."
        )
    else:
        fails: list[str] = []
        if not opm_qoq_ok:
            fails.append(f"OPM {opm_l} < QoQ {previous_period_label} {opm_q}")
        if not opm_yoy_ok:
            fails.append(f"OPM {opm_l} < YoY {previous_year_period_label} {opm_y}")
        if not profit_qoq_ok:
            fails.append(f"Net Profit {np_l} ≤ QoQ {previous_period_label} {np_q}")
        if not profit_yoy_ok:
            fails.append(f"Net Profit {np_l} ≤ YoY {previous_year_period_label} {np_y}")
        if not eps_qoq_ok:
            fails.append(f"EPS {eps_l} ≤ QoQ {previous_period_label} {eps_q}")
        if not eps_yoy_ok:
            fails.append(f"EPS {eps_l} ≤ YoY {previous_year_period_label} {eps_y}")
        note = (
            f"{basis_label} does not qualify for Earnings+ in {latest_period_label}: "
            + "; ".join(fails)
            + "."
        )

    return {
        "decision": "qualified" if matches else "not_qualified",
        "basis_used": basis,
        "latest_period": latest_period_label,
        "latest_period_date_key": str(latest_period.get("date_key") or "").strip(),
        "previous_period": previous_period_label,
        "previous_year_period": previous_year_period_label,
        "note": note,
        "source_fetched_at": payload.get("fetched_at"),
    }


def _earnings_plus_entry_from_evaluation(
    sym: str,
    evaluation: dict,
    *,
    computed_at: str,
    last_error: str | None,
    source_stale: bool,
) -> dict:
    return {
        "symbol": sym,
        "decision": evaluation["decision"],
        "basis_used": evaluation["basis_used"],
        "latest_period": evaluation["latest_period"],
        "latest_period_date_key": evaluation["latest_period_date_key"],
        "previous_period": evaluation["previous_period"],
        "previous_year_period": evaluation["previous_year_period"],
        "note": evaluation["note"],
        "source_fetched_at": evaluation["source_fetched_at"],
        "computed_at": computed_at,
        "refresh_after": computed_at if source_stale else _earnings_plus_refresh_after_timestamp(),
        "last_error": last_error,
    }


def _load_earnings_plus_basis_evaluation(
    sym: str,
    basis: str,
    *,
    fetch_if_missing: bool,
    refresh_stale: bool,
    force_refresh: bool = False,
) -> tuple[dict, str | None, bool]:
    """Returns (evaluation, last_error, source_stale)."""
    last_error = None
    payload, status = screener_quarters.get_quarters(
        DB_PATH,
        DATA_DIR,
        sym,
        basis,
        fetch_if_missing=fetch_if_missing,
        force_refresh=bool(force_refresh),
    )
    if (
        not force_refresh
        and refresh_stale
        and payload
        and _timestamp_is_stale(payload.get("fetched_at"))
    ):
        payload, status = screener_quarters.get_quarters(
            DB_PATH,
            DATA_DIR,
            sym,
            basis,
            fetch_if_missing=True,
            force_refresh=True,
        )
    if status == "error":
        last_error = (payload or {}).get("error") or last_error
    elif status == "cache_stale":
        last_error = (payload or {}).get("refresh_error") or last_error
    evaluation = _evaluate_earnings_plus_payload(payload, basis)
    source_stale = status == "cache_stale" or _timestamp_is_stale(evaluation.get("source_fetched_at"))
    return evaluation, last_error, source_stale


def _earnings_plus_period_date(evaluation: dict | None):
    if not evaluation:
        return None
    return _parse_ymd_date(evaluation.get("latest_period_date_key"))


def _earnings_plus_basis_is_lagging(older_ev: dict | None, newer_ev: dict | None) -> bool:
    """True when older_ev's latest quarter is materially behind newer_ev (incomplete consol)."""
    older_day = _earnings_plus_period_date(older_ev)
    newer_day = _earnings_plus_period_date(newer_ev)
    if older_day is None or newer_day is None:
        return False
    return (newer_day - older_day).days >= EARNINGS_PLUS_BASIS_LAG_DAYS


def _pick_best_earnings_plus_entry(sym: str, basis_results: list[tuple[str, dict, str | None, bool]], computed_at: str) -> dict:
    """
    Prefer consolidated when it can be evaluated (qualified or not_qualified).
    If consolidated quarters lag standalone by a full quarter+, use standalone — otherwise
    names like JUSTDIAL stay "qualified" on ancient consolidated while July reported the
    current quarter on standalone.
    Standalone is also used when consolidated is insufficient_data or missing.
    """
    by_basis = {basis: (ev, err, stale) for basis, ev, err, stale in basis_results}
    last_error = None
    for _, _, err, _ in basis_results:
        if err:
            last_error = err

    def _entry_from_basis(basis: str) -> dict:
        ev, err, stale = by_basis[basis]
        return _earnings_plus_entry_from_evaluation(
            sym, ev, computed_at=computed_at, last_error=err or last_error, source_stale=stale,
        )

    consolidated = by_basis.get("consolidated")
    standalone = by_basis.get("standalone")
    if consolidated:
        c_ev = consolidated[0]
        c_decision = str(c_ev.get("decision") or "").strip().lower()
        if c_decision in ("qualified", "not_qualified"):
            if standalone and _earnings_plus_basis_is_lagging(c_ev, standalone[0]):
                s_decision = str(standalone[0].get("decision") or "").strip().lower()
                if s_decision in ("qualified", "not_qualified", "insufficient_data"):
                    return _entry_from_basis("standalone")
            return _entry_from_basis("consolidated")

    if standalone:
        return _entry_from_basis("standalone")

    return {
        "symbol": sym,
        "decision": "insufficient_data",
        "basis_used": None,
        "latest_period": None,
        "latest_period_date_key": None,
        "previous_period": None,
        "previous_year_period": None,
        "note": "No cached Screener quarterly data is available for Earnings+ yet.",
        "source_fetched_at": None,
        "computed_at": computed_at,
        "refresh_after": computed_at,
        "last_error": last_error,
    }


def _build_earnings_plus_cache_entry(
    symbol: str,
    *,
    fetch_if_missing: bool,
    refresh_stale: bool,
    force_refresh: bool = False,
) -> dict:
    sym = _normalize_symbol_token(symbol)
    computed_at = _now_db_timestamp()
    basis_results: list[tuple[str, dict, str | None, bool]] = []
    for basis in ("consolidated", "standalone"):
        evaluation, last_error, source_stale = _load_earnings_plus_basis_evaluation(
            sym,
            basis,
            fetch_if_missing=fetch_if_missing,
            refresh_stale=refresh_stale,
            force_refresh=force_refresh,
        )
        basis_results.append((basis, evaluation, last_error, source_stale))
    return _pick_best_earnings_plus_entry(sym, basis_results, computed_at)


def _upsert_earnings_plus_cache_entry(conn: sqlite3.Connection, entry: dict) -> None:
    ensure_earnings_plus_cache_table(conn)
    conn.execute(
        """
        INSERT INTO earnings_plus_cache (
            symbol, decision, basis_used, latest_period, latest_period_date_key,
            previous_period, previous_year_period, note, source_fetched_at,
            computed_at, refresh_after, last_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            decision = excluded.decision,
            basis_used = excluded.basis_used,
            latest_period = excluded.latest_period,
            latest_period_date_key = excluded.latest_period_date_key,
            previous_period = excluded.previous_period,
            previous_year_period = excluded.previous_year_period,
            note = excluded.note,
            source_fetched_at = excluded.source_fetched_at,
            computed_at = excluded.computed_at,
            refresh_after = excluded.refresh_after,
            last_error = excluded.last_error
        """,
        (
            entry.get("symbol"),
            entry.get("decision"),
            entry.get("basis_used"),
            entry.get("latest_period"),
            entry.get("latest_period_date_key"),
            entry.get("previous_period"),
            entry.get("previous_year_period"),
            entry.get("note"),
            entry.get("source_fetched_at"),
            entry.get("computed_at"),
            entry.get("refresh_after"),
            entry.get("last_error"),
        ),
    )


def _read_local_screener_latest_period_keys(
    conn: sqlite3.Connection,
    symbols: list[str],
) -> dict[str, str]:
    """Prefer consolidated Screener latest date_key; fall back to standalone."""
    normalized = [
        sym for sym in dict.fromkeys(_normalize_symbol_token(symbol) for symbol in symbols)
        if sym
    ]
    if not normalized:
        return {}
    placeholders = ",".join("?" * len(normalized))
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT symbol, basis, payload_json
            FROM screener_quarterly
            WHERE symbol IN ({placeholders})
            """,
            normalized,
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return {}
    by_sym: dict[str, dict[str, str]] = {}
    for symbol, basis, payload_json in rows:
        sym = _normalize_symbol_token(symbol)
        if not sym:
            continue
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        except (TypeError, json.JSONDecodeError):
            continue
        _, date_key = _payload_latest_period_meta(payload if isinstance(payload, dict) else None)
        if not date_key:
            continue
        bucket = by_sym.setdefault(sym, {})
        basis_key = str(basis or "").strip().lower()
        if basis_key in ("consolidated", "standalone"):
            bucket[basis_key] = date_key
    out: dict[str, str] = {}
    for sym, bases in by_sym.items():
        # Use the newest local quarter across bases so lagging consolidated cannot hide
        # a fresher standalone period (JUSTDIAL-style) from staleness checks.
        consol = bases.get("consolidated") or ""
        stand = bases.get("standalone") or ""
        if consol and stand:
            c_day = _parse_ymd_date(consol)
            s_day = _parse_ymd_date(stand)
            if c_day and s_day:
                out[sym] = stand if s_day >= c_day else consol
            else:
                out[sym] = consol or stand
        else:
            out[sym] = consol or stand or ""
    return {k: v for k, v in out.items() if v}


def _read_earnings_plus_cache_entries(conn: sqlite3.Connection, symbols: list[str]) -> dict[str, dict]:
    ensure_earnings_plus_cache_table(conn)
    normalized = [
        sym for sym in dict.fromkeys(_normalize_symbol_token(symbol) for symbol in symbols)
        if sym
    ]
    if not normalized:
        return {}
    placeholders = ",".join("?" * len(normalized))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            symbol, decision, basis_used, latest_period, latest_period_date_key,
            previous_period, previous_year_period, note, source_fetched_at,
            computed_at, refresh_after, last_error
        FROM earnings_plus_cache
        WHERE symbol IN ({placeholders})
        """,
        normalized,
    )
    local_keys = _read_local_screener_latest_period_keys(conn, normalized)
    results: dict[str, dict] = {}
    for row in cur.fetchall():
        entry = dict(row)
        sym = _normalize_symbol_token(entry.get("symbol"))
        entry["is_stale"] = _earnings_plus_cache_is_stale(entry, local_keys.get(sym))
        results[sym] = entry
    return results


def _read_earnings_plus_cache_entry(conn: sqlite3.Connection, symbol: str) -> dict | None:
    entries = _read_earnings_plus_cache_entries(conn, [symbol])
    return entries.get(_normalize_symbol_token(symbol))


def _ensure_earnings_plus_cache_current(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    fetch_if_missing: bool = False,
    refresh_stale: bool = False,
) -> dict | None:
    """
    Return a non-stale Earnings+ cache row. If local Screener quarters advanced past the
    cached verdict, recompute from local (or scrape when refresh_stale/fetch requested).
    """
    sym = _normalize_symbol_token(symbol)
    if not sym:
        return None
    entry = _read_earnings_plus_cache_entry(conn, sym)
    if entry and not entry.get("is_stale"):
        return entry
    return _refresh_earnings_plus_cache_for_symbol(
        conn,
        sym,
        fetch_if_missing=fetch_if_missing or entry is None,
        refresh_stale=refresh_stale,
    )


def _refresh_earnings_plus_cache_for_symbol(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    fetch_if_missing: bool,
    refresh_stale: bool,
    force_refresh: bool = False,
) -> dict:
    # Network/scrape outside the write lock; serialize only the DB upsert.
    entry = _build_earnings_plus_cache_entry(
        symbol,
        fetch_if_missing=fetch_if_missing,
        refresh_stale=refresh_stale,
        force_refresh=force_refresh,
    )
    with _earnings_plus_db_write_lock:
        _upsert_earnings_plus_cache_entry(conn, entry)
    entry["is_stale"] = False
    return entry


def _enqueue_earnings_plus_screener_sync(symbols: list[str]) -> None:
    """Background Screener pull for TV releases not yet synced — never block the API."""
    global _earnings_plus_bg_sync_running
    cleaned = [
        sym for sym in dict.fromkeys(_normalize_symbol_token(s) for s in symbols or [])
        if sym
    ]
    if not cleaned:
        return
    with _earnings_plus_bg_sync_lock:
        _earnings_plus_bg_sync_pending.update(cleaned)
        if _earnings_plus_bg_sync_running:
            return
        _earnings_plus_bg_sync_running = True

    def _drain() -> None:
        global _earnings_plus_bg_sync_running
        try:
            while True:
                with _earnings_plus_bg_sync_lock:
                    batch = sorted(_earnings_plus_bg_sync_pending)
                    _earnings_plus_bg_sync_pending.clear()
                if not batch:
                    return
                # Serial writes — parallel scrapes were locking SQLite under load.
                for sym in batch:
                    try:
                        conn = get_db_connection()
                        try:
                            _refresh_earnings_plus_cache_for_symbol(
                                conn,
                                sym,
                                fetch_if_missing=True,
                                refresh_stale=True,
                                force_refresh=True,
                            )
                            with _earnings_plus_db_write_lock:
                                conn.commit()
                        finally:
                            conn.close()
                    except Exception as exc:
                        print(f"[earnings_plus] bg screener sync failed {sym}: {exc}")
        finally:
            with _earnings_plus_bg_sync_lock:
                if _earnings_plus_bg_sync_pending:
                    threading.Thread(
                        target=_drain, name="earnings-plus-bg-sync", daemon=True
                    ).start()
                else:
                    _earnings_plus_bg_sync_running = False

    threading.Thread(target=_drain, name="earnings-plus-bg-sync", daemon=True).start()


def _upcoming_prescan_symbols(*, lead_days: int | None = None) -> list[dict]:
    """
    TV upcoming rows whose release is today or within lead_days (default 1).

    Starts Screener/E+ work one day before the print so data is ready when TV lands.
    """
    lead = EARNINGS_PLUS_UPCOMING_PRESCAN_LEAD_DAYS if lead_days is None else max(0, int(lead_days))
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    end = today + timedelta(days=lead)
    try:
        payload = fetch_earnings_calendar(
            mode="upcoming",
            period="coming_week",
            limit=2000,
            use_cache=True,
        )
    except Exception as exc:
        print(f"[earnings_plus] upcoming prescan TV fetch failed: {exc}")
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for row in payload.get("rows") or []:
        sym = _normalize_symbol_token(row.get("symbol"))
        if not sym or sym in seen:
            continue
        release = (
            row.get("earnings_release_next_date")
            or row.get("earnings_release_date")
            or row.get("date")
        )
        release_day = _parse_ymd_date(release)
        if release_day is None:
            continue
        if today <= release_day <= end:
            seen.add(sym)
            out.append({
                "symbol": sym,
                "earnings_release_date": release_day.isoformat(),
            })
    return out


def _build_earnings_plus_helper_from_cache_entry(entry: dict | None) -> dict | None:
    if not entry or entry.get("decision") != "qualified" or entry.get("is_stale"):
        return None
    return {
        "label": "Earnings+",
        "basis": entry.get("basis_used"),
        "latest_period": entry.get("latest_period"),
        "latest_period_date_key": entry.get("latest_period_date_key"),
        "previous_period": entry.get("previous_period"),
        "previous_year_period": entry.get("previous_year_period"),
        "note": entry.get("note"),
        "source": "earnings_plus_cache",
        "fetched_at": entry.get("source_fetched_at"),
        "computed_at": entry.get("computed_at"),
        "is_stale": bool(entry.get("is_stale")),
    }


def _summarize_earnings_plus_cache(entries: dict[str, dict], symbols: list[str]) -> dict:
    total = len(symbols)
    missing = 0
    stale = 0
    qualified = 0
    ready = 0
    for symbol in symbols:
        entry = entries.get(symbol)
        if not entry:
            missing += 1
            continue
        ready += 1
        if entry.get("decision") == "qualified":
            qualified += 1
        if entry.get("is_stale"):
            stale += 1
    return {
        "source": "earnings_plus_cache",
        "total_symbols": total,
        "ready_symbols": ready,
        "qualified_symbols": qualified,
        "missing_symbols": missing,
        "stale_symbols": stale,
    }


def _earnings_plus_screener_fetch_day(entry: dict | None):
    """Calendar day Screener data (or E+ compute) was last pulled for this symbol."""
    if not entry:
        return None
    return _parse_ymd_date(entry.get("source_fetched_at")) or _parse_ymd_date(entry.get("computed_at"))


def _earnings_plus_screener_synced_to_release(entry: dict | None, release_date: str | None) -> bool:
    """
    True when Screener was fetched in time for this TradingView release.

    Expect pull from (release − SYNC_DAYS) onward. A fetch days/weeks *after* the
    print still counts as synced (post-print data). Only a fetch *before* that
    window means we have not yet scored this print.
    """
    release_day = _parse_ymd_date(release_date)
    fetch_day = _earnings_plus_screener_fetch_day(entry)
    if release_day is None or fetch_day is None:
        return False
    earliest = release_day - timedelta(days=EARNINGS_PLUS_SCREENER_SYNC_DAYS)
    return fetch_day >= earliest


def _earnings_plus_entry_matches_report_row(entry: dict | None, row: dict | None) -> bool:
    """Screener data is in sync with this TV release (heal/refresh planning only)."""
    if not entry or not row:
        return False
    return _earnings_plus_screener_synced_to_release(entry, row.get("earnings_release_date"))


def _earnings_plus_cache_needs_refresh(
    entry: dict | None,
    report_row: dict | None,
    *,
    force: bool = False,
    local_latest_period_date_key: str | None = None,
) -> bool:
    """True when symbol needs scrape/recompute for the current TV release."""
    if force:
        return True
    if not entry:
        return True
    if local_latest_period_date_key is None and entry.get("is_stale"):
        return True
    if _earnings_plus_period_mismatch(entry, local_latest_period_date_key):
        return True
    # New TV print and Screener not yet pulled for that event → refresh.
    if report_row and not _earnings_plus_screener_synced_to_release(
        entry, report_row.get("earnings_release_date")
    ):
        return True
    decision = str(entry.get("decision") or "").strip().lower()
    if decision == "insufficient_data":
        return True
    if decision in ("qualified", "not_qualified"):
        return False
    if entry.get("is_stale"):
        return True
    return False


def _plan_earnings_plus_cache_refresh(
    entries: dict[str, dict],
    rows: list[dict],
    *,
    force: bool = False,
    only_incomplete: bool = False,
    local_period_keys: dict[str, str] | None = None,
) -> tuple[list[str], int]:
    """
    Symbols to refresh: missing cache rows first, then stale / Screener-not-synced-to-TV.
    Returns (ordered_symbols, skipped_count).
    """
    row_by_sym: dict[str, dict] = {}
    for row in rows or []:
        sym = _normalize_symbol_token(row.get("symbol"))
        if sym and sym not in row_by_sym:
            row_by_sym[sym] = row
    local_period_keys = local_period_keys or {}

    if force:
        symbols = list(row_by_sym.keys())
        if only_incomplete:
            symbols = [
                sym for sym in symbols
                if not entries.get(sym)
                or str(entries.get(sym, {}).get("decision") or "").strip().lower() == "insufficient_data"
            ]
            return symbols, len(row_by_sym) - len(symbols)
        return symbols, 0

    missing: list[str] = []
    needs_update: list[str] = []
    skipped = 0
    for sym, report_row in row_by_sym.items():
        entry = entries.get(sym)
        if only_incomplete:
            if entry and str(entry.get("decision") or "").strip().lower() != "insufficient_data":
                skipped += 1
                continue
        elif not _earnings_plus_cache_needs_refresh(
            entry,
            report_row,
            force=False,
            local_latest_period_date_key=local_period_keys.get(sym),
        ):
            skipped += 1
            continue
        if entry is None:
            missing.append(sym)
        else:
            needs_update.append(sym)
    return missing + needs_update, skipped


def _earnings_plus_row_is_qualified(entry: dict | None, row: dict | None = None) -> bool:
    """
    Same rule for watchlist/chart badges and Earnings page filters.

    Qualified = cache says qualified and not stale vs local Screener.
    Badge persists until the next earnings print: Screener advancing to a new quarter
    (or a new TV release forcing a resync) triggers rescore; if that print fails E+,
    decision becomes not_qualified and the badge drops.
    ``row`` is accepted for API compatibility but does not apply a day-span gate.
    """
    del row  # persistence is symbol-level until next print, not release↔period_end math
    if not entry:
        return False
    if entry.get("is_stale"):
        return False
    return str(entry.get("decision") or "").strip().lower() == "qualified"


def _heal_earnings_plus_entries_for_reported_rows(
    rows: list[dict],
    *,
    force_screener_on_mismatch: bool = False,
) -> dict[str, dict]:
    """
    Ensure Earnings+ cache is scored for each row's TradingView release.

    Local recompute when missing/stale/Screener not synced to the TV print. When
    force_screener_on_mismatch=True (E+ only/exclude or admin refresh), scrape Screener
    for symbols still not synced after local recompute.
    """
    symbols = list(dict.fromkeys(
        sym for sym in (
            _normalize_symbol_token(row.get("symbol"))
            for row in rows or []
        )
        if sym
    ))
    if not symbols:
        return {}

    row_by_sym: dict[str, dict] = {}
    for row in rows or []:
        sym = _normalize_symbol_token(row.get("symbol"))
        if sym and sym not in row_by_sym:
            row_by_sym[sym] = row

    conn = get_db_connection()
    try:
        entries = _read_earnings_plus_cache_entries(conn, symbols)
        heal_local: list[str] = []
        for sym in symbols:
            entry = entries.get(sym)
            report_row = row_by_sym.get(sym)
            if (
                entry is None
                or entry.get("is_stale")
                or (
                    report_row
                    and not _earnings_plus_screener_synced_to_release(
                        entry, report_row.get("earnings_release_date")
                    )
                )
            ):
                heal_local.append(sym)

        for sym in heal_local:
            entry = _refresh_earnings_plus_cache_for_symbol(
                conn,
                sym,
                fetch_if_missing=True,
                refresh_stale=True,
                force_refresh=False,
            )
            entries[sym] = entry
        with _earnings_plus_db_write_lock:
            conn.commit()

        if force_screener_on_mismatch:
            heal_scrape: list[str] = []
            for sym in heal_local:
                entry = entries.get(sym)
                report_row = row_by_sym.get(sym)
                if report_row and not _earnings_plus_screener_synced_to_release(
                    entry, report_row.get("earnings_release_date")
                ):
                    heal_scrape.append(sym)
            # Serial Screener scrapes — parallel workers were locking nse_data.db.
            for sym in heal_scrape:
                try:
                    entry = _refresh_earnings_plus_cache_for_symbol(
                        conn,
                        sym,
                        fetch_if_missing=True,
                        refresh_stale=True,
                        force_refresh=True,
                    )
                    entries[sym] = entry
                except Exception as exc:
                    print(f"[earnings_plus] heal scrape failed {sym}: {exc}")
            with _earnings_plus_db_write_lock:
                conn.commit()

        local_keys = _read_local_screener_latest_period_keys(conn, list(entries.keys()))
        for sym, entry in entries.items():
            entry["is_stale"] = _earnings_plus_cache_is_stale(entry, local_keys.get(sym))
        return entries
    finally:
        conn.close()


EARNINGS_PLUS_FILTER_MODES = frozenset({"all", "only", "exclude", "tv_eps_rev_beat"})


def _apply_reported_earnings_plus_filter(
    rows: list[dict],
    earnings_plus_filter: str,
) -> tuple[list[dict], dict]:
    """
    Stamp each reported row with ``earnings_plus`` and optionally filter.

    Request path is **read-only**: never heal/scrape/write here (that locked SQLite and
    broke Earnings + alerts). Badge = qualified + not stale from cache. Unsynced /
    missing / stale symbols are queued for background Screener sync.

    Filter modes:
      all | only | exclude — Screener Earnings+ quality
      tv_eps_rev_beat — TradingView reported EPS > est AND reported revenue > est
    """
    mode = str(earnings_plus_filter or "all").strip().lower()
    if mode not in EARNINGS_PLUS_FILTER_MODES:
        mode = "all"
    symbols = list(dict.fromkeys(
        sym for sym in (
            _normalize_symbol_token(row.get("symbol"))
            for row in rows or []
        )
        if sym
    ))
    entries: dict[str, dict] = {}
    if symbols:
        conn = get_db_connection()
        try:
            entries = _read_earnings_plus_cache_entries(conn, symbols)
        finally:
            conn.close()

    needs_bg: list[str] = []
    for row in rows or []:
        sym = _normalize_symbol_token(row.get("symbol"))
        if not sym:
            continue
        entry = entries.get(sym)
        if (
            entry is None
            or entry.get("is_stale")
            or not _earnings_plus_screener_synced_to_release(
                entry, row.get("earnings_release_date")
            )
        ):
            needs_bg.append(sym)
    if needs_bg:
        _enqueue_earnings_plus_screener_sync(needs_bg)

    summary = _summarize_earnings_plus_cache(entries, symbols)

    stamped_rows: list[dict] = []
    release_unsynced_qualified = 0
    badge_qualified = 0
    for row in rows or []:
        out = dict(row)
        sym = _normalize_symbol_token(out.get("symbol"))
        entry = entries.get(sym)
        row_qualified = _earnings_plus_row_is_qualified(entry, row=out)
        out["earnings_plus"] = bool(row_qualified)
        if row_qualified:
            badge_qualified += 1
            helper = _build_earnings_plus_helper_from_cache_entry(entry)
            if helper and helper.get("note"):
                out["earnings_plus_note"] = helper["note"]
            elif entry and entry.get("note"):
                out["earnings_plus_note"] = entry.get("note")
        else:
            out.pop("earnings_plus_note", None)
        if (
            entry
            and str(entry.get("decision") or "").strip().lower() == "qualified"
            and not entry.get("is_stale")
            and not _earnings_plus_screener_synced_to_release(entry, out.get("earnings_release_date"))
        ):
            release_unsynced_qualified += 1
        stamped_rows.append(out)

    summary["period_matched_qualified"] = badge_qualified
    summary["badge_qualified"] = badge_qualified
    summary["release_mismatch_qualified"] = release_unsynced_qualified
    summary["release_unsynced_qualified"] = release_unsynced_qualified
    summary["bg_sync_queued"] = len(list(dict.fromkeys(needs_bg)))

    if mode == "all":
        summary["filtered_symbols"] = len(stamped_rows)
        return stamped_rows, summary

    filtered_rows: list[dict] = []
    for row in stamped_rows:
        row_qualified = bool(row.get("earnings_plus"))
        if mode == "only" and row_qualified:
            filtered_rows.append(row)
        elif mode == "exclude" and not row_qualified:
            filtered_rows.append(row)
        elif mode == "tv_eps_rev_beat" and is_tv_eps_rev_beat_row(row):
            filtered_rows.append(row)
    summary["filtered_symbols"] = len(filtered_rows)
    return filtered_rows, summary


def _release_matches_screener_period(release_date: str | None, period_date_key: str | None) -> bool:
    """Chart provisional fallback only: TV release vs Screener quarter end."""
    release_day = _parse_ymd_date(release_date)
    period_day = _parse_ymd_date(period_date_key)
    if release_day is None or period_day is None:
        return False
    delta_days = (release_day - period_day).days
    return 0 <= delta_days <= EARNINGS_PLUS_CHART_PERIOD_MAX_DAYS


def _same_release_window(date_a: str | None, date_b: str | None, max_days: int = 14) -> bool:
    day_a = _parse_ymd_date(date_a)
    day_b = _parse_ymd_date(date_b)
    if day_a is None or day_b is None:
        return False
    return abs((day_a - day_b).days) <= max_days


def _revenues_look_comparable(actual: float | None, estimate: float | None) -> bool:
    if actual is None or estimate is None:
        return False
    smaller = min(abs(actual), abs(estimate))
    larger = max(abs(actual), abs(estimate))
    if smaller == 0:
        return larger == 0
    return (larger / smaller) <= 1000


def _build_screener_fallback_event(
    symbol: str,
    *,
    release_date: str | None,
    eps_estimate_value,
    revenue_estimate_value,
    comparison_source: str,
) -> dict | None:
    sym = _normalize_symbol_token(symbol)
    if not sym:
        return None
    resolved_release_date = str(release_date or "").strip()
    release_day = _parse_ymd_date(resolved_release_date)
    if (
        comparison_source == "tv_upcoming_estimate_vs_screener_consolidated"
        and release_day is not None
        and release_day > datetime.now(ZoneInfo("Asia/Kolkata")).date()
    ):
        return None
    screener_latest = _extract_latest_screener_consolidated_metrics(sym)
    if not screener_latest:
        return None
    if not _release_matches_screener_period(
        resolved_release_date,
        screener_latest.get("period_date_key"),
    ):
        return None
    eps_estimate = _to_finite_number(eps_estimate_value)
    revenue_estimate = _to_finite_number(revenue_estimate_value)
    eps_actual = _to_finite_number(screener_latest.get("eps_actual"))
    revenue_actual = _to_finite_number(screener_latest.get("sales_actual"))
    if (
        eps_estimate is None
        or revenue_estimate is None
        or eps_actual is None
        or revenue_actual is None
        or not _revenues_look_comparable(revenue_actual, revenue_estimate)
    ):
        return None
    eps_surprise_pct = _compute_surprise_pct(eps_actual, eps_estimate)
    revenue_surprise_pct = _compute_surprise_pct(revenue_actual, revenue_estimate)
    outcome_kind = (
        "beat"
        if eps_actual >= eps_estimate and revenue_actual >= revenue_estimate
        else "miss"
    )
    matched_period = screener_latest.get("period") or screener_latest.get("period_date_key") or None
    return _base_event_from_row(
        symbol=sym,
        earnings_release_date=resolved_release_date,
        outcome_kind=outcome_kind,
        eps_actual=eps_actual,
        eps_estimate=eps_estimate,
        eps_surprise_pct=eps_surprise_pct,
        revenue_actual=revenue_actual,
        revenue_estimate=revenue_estimate,
        revenue_surprise_pct=revenue_surprise_pct,
        source="tv_estimate_vs_screener_consolidated",
        comparison_source=comparison_source,
        comparison_status="provisional",
        comparison_basis="consolidated",
        comparison_note=(
            "Provisional: TradingView estimates compared with Screener consolidated actuals"
            f"{f' ({matched_period})' if matched_period else ''}."
        ),
        matched_period=matched_period,
        matched_period_date_key=screener_latest.get("period_date_key"),
    )


def _select_latest_chart_event(symbol: str) -> dict | None:
    sym = _normalize_symbol_token(symbol)
    if not sym:
        return None
    reported_payload = fetch_earnings_calendar(
        mode="reported",
        limit=25,
        use_cache=True,
        symbols=[sym],
    )
    latest_reported = _pick_latest_symbol_row(
        reported_payload.get("rows") or [],
        sym,
        "earnings_release_date",
    )
    latest_upcoming = _pick_latest_symbol_row(
        fetch_upcoming_estimates_for_symbols([sym]),
        sym,
        "earnings_release_next_date",
    )
    fallback_event = None
    if latest_reported:
        fallback_event = _build_screener_fallback_event(
            sym,
            release_date=latest_reported.get("earnings_release_date"),
            eps_estimate_value=latest_reported.get("eps_estimate"),
            revenue_estimate_value=latest_reported.get("revenue_estimate"),
            comparison_source="tv_reported_estimate_vs_screener_consolidated",
        )
    if fallback_event is None and latest_upcoming:
        fallback_event = _build_screener_fallback_event(
            sym,
            release_date=latest_upcoming.get("earnings_release_next_date"),
            eps_estimate_value=latest_upcoming.get("eps_estimate"),
            revenue_estimate_value=latest_upcoming.get("revenue_estimate"),
            comparison_source="tv_upcoming_estimate_vs_screener_consolidated",
        )
    if latest_reported and _reported_row_has_complete_outcome(latest_reported):
        return _event_from_reported_row(latest_reported)
    if fallback_event:
        if (
            latest_reported
            and latest_reported.get("earnings_release_date")
            and _same_release_window(
                latest_reported.get("earnings_release_date"),
                fallback_event.get("earnings_release_date"),
            )
        ):
            fallback_event["earnings_release_date"] = str(latest_reported.get("earnings_release_date")).strip()
        return fallback_event
    if latest_reported:
        return _event_from_incomplete_reported_row(latest_reported)
    return None


def _upsert_earnings_chart_event(conn: sqlite3.Connection, event: dict) -> None:
    matched_period = event.get("matched_period")
    if matched_period:
        conn.execute(
            """
            DELETE FROM earnings_chart_events
            WHERE symbol = ?
              AND matched_period = ?
              AND earnings_release_date <> ?
            """,
            (
                event["symbol"],
                matched_period,
                event["earnings_release_date"],
            ),
        )
    conn.execute(
        """
        INSERT INTO earnings_chart_events (
            symbol,
            earnings_release_date,
            outcome_kind,
            eps_actual,
            eps_estimate,
            eps_surprise_pct,
            revenue_actual,
            revenue_estimate,
            revenue_surprise_pct,
            source,
            comparison_source,
            comparison_status,
            comparison_basis,
            comparison_note,
            matched_period,
            matched_period_date_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, earnings_release_date) DO UPDATE SET
            outcome_kind = excluded.outcome_kind,
            eps_actual = excluded.eps_actual,
            eps_estimate = excluded.eps_estimate,
            eps_surprise_pct = excluded.eps_surprise_pct,
            revenue_actual = excluded.revenue_actual,
            revenue_estimate = excluded.revenue_estimate,
            revenue_surprise_pct = excluded.revenue_surprise_pct,
            source = excluded.source,
            comparison_source = excluded.comparison_source,
            comparison_status = excluded.comparison_status,
            comparison_basis = excluded.comparison_basis,
            comparison_note = excluded.comparison_note,
            matched_period = excluded.matched_period,
            matched_period_date_key = excluded.matched_period_date_key,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            event["symbol"],
            event["earnings_release_date"],
            event["outcome_kind"],
            event.get("eps_actual"),
            event.get("eps_estimate"),
            event.get("eps_surprise_pct"),
            event.get("revenue_actual"),
            event.get("revenue_estimate"),
            event.get("revenue_surprise_pct"),
            event.get("source") or "tradingview_latest_fq",
            event.get("comparison_source"),
            event.get("comparison_status"),
            event.get("comparison_basis"),
            event.get("comparison_note"),
            event.get("matched_period"),
            event.get("matched_period_date_key"),
        ),
    )


def _refresh_symbol_earnings_chart_events(conn: sqlite3.Connection, symbol: str) -> None:
    sym = _normalize_symbol_token(symbol)
    if not sym:
        return
    latest = _select_latest_chart_event(sym)
    if latest is not None:
        _upsert_earnings_chart_event(conn, latest)


def run_resync_recent_tv_earnings(
    *,
    lookback_days: int | None = None,
    trigger: str = "manual",
) -> dict:
    """
    Re-pull TradingView reported earnings for the last N release days and overwrite
    stored chart events. One market scan — not a full-universe per-symbol crawl.
    """
    days = int(lookback_days) if lookback_days is not None else RECENT_RESYNC_LOOKBACK_DAYS
    days = max(1, min(14, days))
    set_job("earnings_tv_resync", f"Re-syncing TradingView earnings (last {days} days)...")
    try:
        with _earnings_beats_resp_lock:
            _earnings_beats_resp_cache.clear()
        payload = fetch_recent_reported_for_resync(lookback_days=days, limit=2000)
        rows = list(payload.get("rows") or [])
        upserted = 0
        skipped = 0
        symbols: list[str] = []
        conn = get_db_connection()
        try:
            for row in rows:
                if _reported_row_has_complete_outcome(row):
                    event = _event_from_reported_row(row)
                else:
                    event = _event_from_incomplete_reported_row(row)
                if event is None:
                    skipped += 1
                    continue
                _upsert_earnings_chart_event(conn, event)
                upserted += 1
                sym = str(event.get("symbol") or "").strip().upper()
                if sym and sym not in symbols:
                    symbols.append(sym)
            conn.commit()
        finally:
            conn.close()
        meta = {
            "lookback_days": days,
            "scanner_rows": len(rows),
            "upserted": upserted,
            "skipped": skipped,
            "symbols": len(symbols),
            "trigger": trigger,
            "fetched_at": payload.get("fetched_at"),
        }
        msg = (
            f"TV earnings re-sync complete: {upserted} chart event(s) updated "
            f"from {len(rows)} scanner row(s) (last {days} days)."
        )
        finish_job(msg, meta=meta)
        return meta
    except Exception as e:
        fail_job(str(e))
        raise


def _sched_start_earnings_tv_resync() -> bool:
    def _worker() -> None:
        run_resync_recent_tv_earnings(trigger="scheduled")

    result = _start_or_queue_job(
        "earnings_tv_resync",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="TV earnings re-sync",
        source="scheduled",
        coalesce_key="earningsTvResync",
    )
    return result.get("status") in ("started", "queued")


def _read_symbol_earnings_chart_events(conn: sqlite3.Connection, symbol: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            symbol,
            earnings_release_date,
            outcome_kind,
            eps_actual,
            eps_estimate,
            eps_surprise_pct,
            revenue_actual,
            revenue_estimate,
            revenue_surprise_pct,
            source,
            comparison_source,
            comparison_status,
            comparison_basis,
            comparison_note,
            matched_period,
            matched_period_date_key,
            updated_at
        FROM earnings_chart_events
        WHERE symbol = ?
        ORDER BY earnings_release_date DESC
        """,
        (_normalize_symbol_token(symbol),),
    ).fetchall()
    return [dict(row) for row in rows]


def _collect_tv_overlay_events(symbol: str) -> list[dict]:
    """Pure TradingView reported + upcoming only (never Screener / chart hybrids)."""
    sym = _normalize_symbol_token(symbol)
    if not sym:
        return []
    events: list[dict] = []

    # Live reported calendar rows (latest FQ-centric; include whatever TV returns).
    try:
        reported_payload = fetch_earnings_calendar(
            mode="reported",
            limit=25,
            use_cache=True,
            symbols=[sym],
        )
        for row in reported_payload.get("rows") or []:
            if _normalize_symbol_token(row.get("symbol")) != sym:
                continue
            normalized = tv_quarterly_overlay.normalize_overlay_event(row)
            if normalized:
                events.append(normalized)
    except Exception as exc:
        print(f"[tv_quarterly_overlay] reported lookup failed ({sym}): {exc}")

    # Live upcoming estimates (estimates only until TV prints actuals).
    try:
        for row in fetch_upcoming_estimates_for_symbols([sym]):
            if _normalize_symbol_token(row.get("symbol")) != sym:
                continue
            normalized = tv_quarterly_overlay.normalize_overlay_event({
                "earnings_release_next_date": row.get("earnings_release_next_date"),
                "eps_estimate": row.get("eps_estimate"),
                "revenue_estimate": row.get("revenue_estimate"),
                # Explicit: never carry Screener actuals into TV overlay rows.
                "eps_actual": None,
                "revenue_actual": None,
            })
            if normalized:
                events.append(normalized)
    except Exception as exc:
        print(f"[tv_quarterly_overlay] upcoming lookup failed ({sym}): {exc}")

    return events


def _attach_tv_quarterly_overlay(symbol: str, payload: dict | None) -> dict | None:
    """Add TradingView-only tv_rows aligned to Screener periods (— when TV missing)."""
    if not isinstance(payload, dict):
        return payload
    periods = payload.get("periods") or []
    if not periods:
        payload["tv_rows"] = tv_quarterly_overlay.build_tv_overlay_rows([], [])
        return payload
    try:
        events = _collect_tv_overlay_events(symbol)
        payload["tv_rows"] = tv_quarterly_overlay.build_tv_overlay_rows(periods, events)
    except Exception as exc:
        print(f"[tv_quarterly_overlay] build failed ({symbol}): {exc}")
        payload["tv_rows"] = tv_quarterly_overlay.build_tv_overlay_rows(periods, [])
    return payload


# ──────────────────────────────────────────────
# SCREENER DATA LOADER — cached at startup
# ──────────────────────────────────────────────

_stock_df: Optional[pd.DataFrame] = None
# Enriched Price/1D%/1M% copy — avoid full-universe historical SQL on every list read.
_stock_df_ohlc: Optional[pd.DataFrame] = None
_stock_df_ohlc_ts: float = 0.0
_stock_df_lock = threading.Lock()
SCREENER_OHLC_REFRESH_TTL_SEC = 45.0
# 4H integrity must not block chart-data; cooldown + background thread.


_4h_integrity_last_ts: dict[str, float] = {}
_4h_integrity_lock = threading.Lock()
_4H_INTEGRITY_COOLDOWN_SEC = 900.0
CHART_CACHE_TTL: int = _app_caches.chart_ttl
CHART_CACHE_MAX_ENTRIES: int = _app_caches.chart_max_entries
FILTER_CACHE_TTL: int = _app_caches.filter_ttl
FILTER_CACHE_MAX_ENTRIES: int = _app_caches.filter_max_entries
AGGRESSIVE_CACHE_RAM: bool = _app_caches.aggressive



def _load_layout_file() -> dict:
    if not LAYOUT_PATH.exists():
        return {}
    try:
        with open(LAYOUT_PATH, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_layout_merge(extra: dict):
    LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = _load_layout_file()
    current.update(extra or {})
    with open(LAYOUT_PATH, "w") as f:
        json.dump(current, f, indent=2)


def set_cache_mode(enabled: bool):
    global AGGRESSIVE_CACHE_RAM, CHART_CACHE_TTL, CHART_CACHE_MAX_ENTRIES, FILTER_CACHE_TTL, FILTER_CACHE_MAX_ENTRIES
    _app_caches.set_mode(enabled)
    AGGRESSIVE_CACHE_RAM = _app_caches.aggressive
    CHART_CACHE_TTL = _app_caches.chart_ttl
    CHART_CACHE_MAX_ENTRIES = _app_caches.chart_max_entries
    FILTER_CACHE_TTL = _app_caches.filter_ttl
    FILTER_CACHE_MAX_ENTRIES = _app_caches.filter_max_entries


def get_chart_cache(symbol, timeframe, ema_periods):
    return _app_caches.get_chart(symbol, timeframe, ema_periods)


def set_chart_cache(symbol, timeframe, ema_periods, data):
    _app_caches.set_chart(symbol, timeframe, ema_periods, data)


def invalidate_chart_cache(symbol=None):
    _app_caches.invalidate_chart(symbol)
    try:
        if symbol is None:
            market_map.invalidate_cache()
        else:
            market_map.invalidate_cache(symbol)
    except Exception:
        pass
    invalidate_filter_cache()


def invalidate_stock_df():
    global _stock_df, _stock_df_ohlc, _stock_df_ohlc_ts
    with _stock_df_lock:
        _stock_df = None
        _stock_df_ohlc = None
        _stock_df_ohlc_ts = 0.0
    invalidate_filter_cache()


def _schedule_4h_integrity_check(symbol: str) -> None:
    """Queue a non-blocking 4H rescale scan (cooldown). Never call on the request path synchronously."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    now = time_module.time()
    with _4h_integrity_lock:
        last = float(_4h_integrity_last_ts.get(sym) or 0.0)
        if now - last < _4H_INTEGRITY_COOLDOWN_SEC:
            return
        _4h_integrity_last_ts[sym] = now

    def _worker() -> None:
        try:
            conn = get_db_connection()
            try:
                from server.bars_4h_integrity import rescan_rescale_symbol_if_needed

                applied = rescan_rescale_symbol_if_needed(conn, sym, lookback_calendar_days=120)
                if applied:
                    invalidate_chart_cache(sym)
            finally:
                conn.close()
        except Exception:
            pass

    threading.Thread(target=_worker, name=f"4h-integrity-{sym}", daemon=True).start()


# screener.price often equals yesterday's close on cold start — treat as stale (use 2-bar hist).
_SCREENER_PRICE_STALE_REL_EPS = 0.0001


def _finite_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _live_snap_day_change(snap: dict) -> Optional[float]:
    """1D % from movers live cache entry; None if not usable."""
    if not snap:
        return None
    chg = _finite_float(snap.get("change_pct"))
    if chg is not None:
        return round(chg, 2)
    px = _finite_float(snap.get("price"))
    prev = _finite_float(snap.get("previous_close"))
    if px is not None and prev is not None and prev > 0:
        return round((px - prev) / prev * 100.0, 2)
    return None


def _should_apply_live_day_change(existing_chg: Optional[float], live_chg: Optional[float]) -> bool:
    """Avoid clobbering a real historical % with a stale live 0 on startup."""
    if live_chg is None:
        return False
    if existing_chg is None:
        return True
    try:
        ex = float(existing_chg)
        lv = float(live_chg)
    except (TypeError, ValueError):
        return True
    if abs(lv) < 0.005 and abs(ex) > 0.05:
        return False
    return True


def _apply_movers_live_prices_only(df: pd.DataFrame) -> None:
    """Cheap in-memory overlay from movers_live cache (no SQL)."""
    if df is None or getattr(df, "empty", False):
        return
    try:
        if not movers_data._session_day_intraday_active():
            return
    except Exception:
        return
    try:
        live = movers_live.live_cache_snapshot()
    except Exception:
        live = {}
    if not live:
        return
    for idx, row in df.iterrows():
        sym = str(row.get("Symbol", "")).strip().upper()
        snap = live.get(sym)
        if not snap or not movers_live.cache_quote_fresh(snap):
            continue
        existing_chg = _finite_float(row.get("Change %"))
        live_chg = _live_snap_day_change(snap)
        px = _finite_float(snap.get("price"))
        if px is not None:
            df.at[idx, "Price"] = round(px, 2)
        if _should_apply_live_day_change(existing_chg, live_chg):
            df.at[idx, "Change %"] = live_chg
    for col in ("Price", "Change %"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)


def _apply_live_screener_ohlc(df: pd.DataFrame, conn) -> None:
    """
    Refresh Price and 1D/1M % from historical_data (expensive full-universe SQL).
    Callers must TTL-cache the result — do not run on every list/search request.

    On a session day before 16:00 IST, when the latest DB bar is still yesterday,
    use screener.price vs prior close only when it differs materially from that close;
    otherwise use last-two-bar historical % (avoids 0% on cold start).
    """
    if df is None or getattr(df, "empty", False):
        return

    try:
        session_intraday = False
        today_s = ""
        try:
            session_intraday = movers_data._session_day_intraday_active()
            today_s = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        except Exception:
            pass

        eps = _SCREENER_PRICE_STALE_REL_EPS
        if session_intraday and today_s:
            day_chg_sql = f"""
            SELECT s.symbol AS symbol,
              CASE
                WHEN substr((SELECT MAX(Date) FROM historical_data h WHERE h.Symbol = s.symbol), 1, 10) < '{today_s}'
                     AND s.price IS NOT NULL AND s.price > 0
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) IS NOT NULL
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) > 0
                     AND ABS(
                       s.price - (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                     ) > (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) * {eps}
                THEN ROUND((
                  s.price
                  - (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                ) / (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) * 100, 2)
                ELSE ROUND((
                  (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                  - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = s.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
                ) / NULLIF((
                  SELECT Close FROM historical_data h3 WHERE h3.Symbol = s.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
                ), 0) * 100, 2)
              END AS day_chg_pct,
              CASE
                WHEN substr((SELECT MAX(Date) FROM historical_data h WHERE h.Symbol = s.symbol), 1, 10) < '{today_s}'
                     AND s.price IS NOT NULL AND s.price > 0
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) IS NOT NULL
                     AND (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) > 0
                     AND ABS(
                       s.price - (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                     ) > (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) * {eps}
                THEN ROUND(s.price, 2)
                ELSE (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
              END AS display_price
            FROM screener s
            WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = s.symbol)
            """
        else:
            day_chg_sql = """
            SELECT s.symbol AS symbol,
              ROUND((
                (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
                - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = s.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
              ) / NULLIF((
                SELECT Close FROM historical_data h3 WHERE h3.Symbol = s.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
              ), 0) * 100, 2) AS day_chg_pct,
              (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1) AS display_price
            FROM screener s
            WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = s.symbol)
            """
        day_chg = pd.read_sql_query(day_chg_sql, conn)
        if not day_chg.empty:
            day_chg["Symbol"] = day_chg["symbol"].astype(str).str.strip().str.upper()
            m = df[["Symbol"]].merge(day_chg[["Symbol", "day_chg_pct", "display_price"]], on="Symbol", how="left")
            df["Change %"] = m["day_chg_pct"].combine_first(df["Change %"])
            df["Price"] = m["display_price"].combine_first(df["Price"])
        else:
            last_close_sql = (
                "SELECT Symbol, Close AS last_close FROM historical_data WHERE Date = "
                "(SELECT MAX(Date) FROM historical_data h2 WHERE h2.Symbol = historical_data.Symbol)"
            )
            lc = pd.read_sql_query(last_close_sql, conn)
            if not lc.empty:
                lc.columns = ["symbol", "last_close"]
                lc["Symbol"] = lc["symbol"].astype(str).str.strip().str.upper()
                m = df[["Symbol"]].merge(lc[["Symbol", "last_close"]], on="Symbol", how="left")
                df["Price"] = m["last_close"].combine_first(df["Price"])

        month_chg_sql = """
        SELECT s.symbol AS symbol,
          ROUND((
            (SELECT Close FROM historical_data h1 WHERE h1.Symbol = s.symbol ORDER BY h1.Date DESC LIMIT 1)
            - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = s.symbol AND SUBSTR(h2.Date,1,7) <
               SUBSTR((SELECT MAX(Date) FROM historical_data h3 WHERE h3.Symbol = s.symbol),1,7)
               ORDER BY h2.Date DESC LIMIT 1)
          ) / NULLIF((
            SELECT Close FROM historical_data h4 WHERE h4.Symbol = s.symbol AND SUBSTR(h4.Date,1,7) <
               SUBSTR((SELECT MAX(Date) FROM historical_data h5 WHERE h5.Symbol = s.symbol),1,7)
               ORDER BY h4.Date DESC LIMIT 1
          ), 0) * 100, 2) AS month_chg_pct
        FROM screener s
        WHERE EXISTS (SELECT 1 FROM historical_data h WHERE h.Symbol = s.symbol)
        """
        month_chg = pd.read_sql_query(month_chg_sql, conn)
        if not month_chg.empty:
            month_chg["Symbol"] = month_chg["symbol"].astype(str).str.strip().str.upper()
            m = df[["Symbol"]].merge(month_chg[["Symbol", "month_chg_pct"]], on="Symbol", how="left")
            df["Monthly Change %"] = m["month_chg_pct"].combine_first(df["Monthly Change %"])

        if session_intraday:
            _apply_movers_live_prices_only(df)

        for col in ("Price", "Change %", "Monthly Change %"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
    except Exception as e:
        print(f"[_apply_live_screener_ohlc] {e}")


def _index_live_day_change_map(conn, symbols: list) -> dict:
    """1D % from last two index_history closes; keys = index symbol string."""
    if not symbols:
        return {}
    out = {}
    try:
        cur = conn.cursor()
        ph = ",".join("?" * len(symbols))
        cur.execute(
            f"""
            SELECT i.symbol AS sym,
              ROUND((
                (SELECT Close FROM index_history h1 WHERE h1.Symbol = i.symbol ORDER BY h1.Date DESC LIMIT 1)
                - (SELECT Close FROM index_history h2 WHERE h2.Symbol = i.symbol ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
              ) / NULLIF((
                SELECT Close FROM index_history h3 WHERE h3.Symbol = i.symbol ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
              ), 0) * 100, 2) AS live_chg
            FROM indices i
            WHERE i.symbol IN ({ph})
              AND EXISTS (SELECT 1 FROM index_history ih WHERE ih.Symbol = i.symbol)
            """,
            symbols,
        )
        for sym, pct in cur.fetchall():
            if sym is not None:
                out[str(sym).strip()] = pct
    except Exception:
        pass
    return out


def _equity_day_change_pct_single(symbol: str, conn) -> Optional[float]:
    """One trading-day % — matches watchlist / Pulse `Change %`."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    try:
        session_intraday = movers_data._session_day_intraday_active()
        today_s = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    except Exception:
        session_intraday = False
        today_s = ""
    try:
        cur = conn.cursor()
        if session_intraday and today_s:
            cur.execute(
                """
                SELECT
                  substr((SELECT MAX(Date) FROM historical_data WHERE Symbol = ?), 1, 10),
                  (SELECT Close FROM historical_data WHERE Symbol = ? ORDER BY Date DESC LIMIT 1),
                  (SELECT price FROM screener WHERE UPPER(TRIM(symbol)) = ?)
                """,
                (sym, sym, sym),
            )
            row = cur.fetchone()
            if row and row[0] and str(row[0]) < today_s and row[1] and row[2]:
                prev_f = float(row[1])
                px_f = float(row[2])
                if prev_f > 0 and px_f > 0:
                    return round((px_f - prev_f) / prev_f * 100.0, 2)
            try:
                snap = movers_live.get_symbol_live_snapshot(sym, allow_fetch=False)
                if snap:
                    px = snap.get("price")
                    prev = snap.get("previous_close")
                    if px is not None and prev is not None:
                        prev_f = float(prev)
                        px_f = float(px)
                        if prev_f > 0:
                            return round((px_f - prev_f) / prev_f * 100.0, 2)
                    chg = snap.get("change_pct")
                    if chg is not None and math.isfinite(float(chg)):
                        return round(float(chg), 2)
            except Exception:
                pass
        cur.execute(
            """
            SELECT ROUND((
                (SELECT Close FROM historical_data h1 WHERE h1.Symbol = ? ORDER BY h1.Date DESC LIMIT 1)
                - (SELECT Close FROM historical_data h2 WHERE h2.Symbol = ? ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
            ) / NULLIF((
                SELECT Close FROM historical_data h3 WHERE h3.Symbol = ? ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
            ), 0) * 100, 4)
            FROM historical_data h0 WHERE h0.Symbol = ? LIMIT 1
            """,
            (sym, sym, sym, sym),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        v = float(row[0])
        if not math.isfinite(v):
            return None
        return round(v, 2)
    except Exception:
        return None


def _index_day_change_pct_single(symbol: str, conn) -> Optional[float]:
    """Last vs previous index_history close; matches index list live 1D % logic."""
    sym = str(symbol or "").strip()
    if not sym:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ROUND((
                (SELECT Close FROM index_history h1 WHERE h1.Symbol = ? ORDER BY h1.Date DESC LIMIT 1)
                - (SELECT Close FROM index_history h2 WHERE h2.Symbol = ? ORDER BY h2.Date DESC LIMIT 1 OFFSET 1)
            ) / NULLIF((
                SELECT Close FROM index_history h3 WHERE h3.Symbol = ? ORDER BY h3.Date DESC LIMIT 1 OFFSET 1
            ), 0) * 100, 4)
            FROM index_history h0 WHERE h0.Symbol = ? LIMIT 1
            """,
            (sym, sym, sym, sym),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        v = float(row[0])
        if not math.isfinite(v):
            return None
        return round(v, 2)
    except Exception:
        return None


def _normalize_filter_body(body: dict) -> dict:
    if not isinstance(body, dict):
        return {}
    b = dict(body)
    # Keep cache keys stable across equivalent payloads
    if isinstance(b.get("market_sectors"), list):
        b["market_sectors"] = sorted([str(x).strip() for x in b["market_sectors"] if str(x).strip()])
    return b


def get_filter_cache(endpoint: str, body: dict):
    return _app_caches.get_filter(endpoint, body)


def set_filter_cache(endpoint: str, body: dict, data: dict):
    _app_caches.set_filter(endpoint, body, data)


def invalidate_filter_cache():
    _app_caches.invalidate_filters()


def get_combined_filter_cache(cache_key: str) -> Optional[Set[str]]:
    cached = _app_caches.get_combined_filter(cache_key)
    return set(cached) if cached is not None else None


def set_combined_filter_cache(cache_key: str, symbols: Set[str]) -> None:
    _app_caches.set_combined_filter(cache_key, frozenset(symbols))


def _combined_filter_cache_key(filters: list, market_sectors: list) -> str:
    normalized = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        item = {k: v for k, v in f.items() if k != "label"}
        normalized.append(item)
    normalized.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))
    payload = {
        "filters": normalized,
        "market_sectors": sorted([str(x).strip() for x in (market_sectors or []) if str(x).strip()]),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _macd_hist_chain_row_chain(row) -> list[float] | None:
    try:
        raw = row["macd_hist_chain"] if "macd_hist_chain" in row.keys() else None
    except Exception:
        raw = None
    return parse_hist_chain(raw)


def _macd_hist_chain_matches_snapshot_row(row, filter_def: dict) -> bool:
    chain_all = _macd_hist_chain_row_chain(row)
    if not chain_all:
        return False
    if len(chain_all) < bars_needed_for_filter_def(filter_def):
        return False
    return evaluate_macd_hist_chain(chain_all, filter_def)


def _macd_filter_hist_chain_enabled(filter_def: dict) -> bool:
    if str(filter_def.get("filter_type", "")).strip().lower() == "macd_hist_chain":
        return True
    if str(filter_def.get("source", "")).strip().lower() == "histogram":
        return True
    from server.macd_hist_chain_filter import _parse_bool

    return _parse_bool(filter_def.get("hist_chain_enabled", False))


def _macd_filter_hist_chain_only(filter_def: dict) -> bool:
    if str(filter_def.get("filter_type", "")).strip().lower() == "macd_hist_chain":
        return True
    if str(filter_def.get("source", "")).strip().lower() == "histogram":
        return True
    from server.macd_hist_chain_filter import _parse_bool

    return _parse_bool(filter_def.get("hist_chain_only", False))


def _macd_line_condition_matches_row(row, filter_def: dict, _rv) -> bool:
    source = str(filter_def.get("source", "macd")).strip().lower()
    if source not in ("macd", "signal"):
        source = "macd"
    condition = str(filter_def.get("condition", "above")).strip().lower()
    pct_value = float(filter_def.get("pct_value", 0) or 0)
    target = str(filter_def.get("target", "value")).strip().lower()
    target_value = float(filter_def.get("target_value", 0) or 0)
    src_curr = _rv("macd") if source == "macd" else _rv("macd_signal")
    src_prev = _rv("macd_prev") if source == "macd" else _rv("macd_signal_prev")
    if src_curr is None:
        return False
    if target == "value":
        tgt_curr = target_value
        tgt_prev = target_value
    elif target == "macd":
        tgt_curr = _rv("macd")
        tgt_prev = _rv("macd_prev")
    else:
        tgt_curr = _rv("macd_signal")
        tgt_prev = _rv("macd_signal_prev")
    if tgt_curr is None:
        return False
    if condition == "above":
        return src_curr > tgt_curr
    if condition == "above_eq":
        return src_curr >= tgt_curr
    if condition == "below":
        return src_curr < tgt_curr
    if condition == "below_eq":
        return src_curr <= tgt_curr
    if condition == "crosses_up":
        return src_prev is not None and tgt_prev is not None and src_prev <= tgt_prev and src_curr > tgt_curr
    if condition == "crosses_down":
        return src_prev is not None and tgt_prev is not None and src_prev >= tgt_prev and src_curr < tgt_curr
    if condition == "above_pct":
        return tgt_curr != 0 and src_curr > tgt_curr * (1 + pct_value / 100)
    if condition == "below_pct":
        return tgt_curr != 0 and src_curr < tgt_curr * (1 - pct_value / 100)
    return False


def _macd_filter_matches_snapshot_row(row, filter_def: dict) -> bool:
    if _macd_filter_hist_chain_only(filter_def):
        return _macd_hist_chain_matches_snapshot_row(row, filter_def)

    def _rv(k: str):
        try:
            return row[k] if k in row.keys() else None
        except Exception:
            return None

    if not _macd_line_condition_matches_row(row, filter_def, _rv):
        return False
    if _macd_filter_hist_chain_enabled(filter_def):
        return _macd_hist_chain_matches_snapshot_row(row, filter_def)
    return True


def _sector_allowed_symbols(body: dict) -> Optional[Set[str]]:
    raw = body.get("market_sectors")
    if not isinstance(raw, list) or len(raw) == 0:
        return None
    names = [str(x).strip() for x in raw if str(x).strip()]
    if not names:
        return None
    if not DB_PATH.exists():
        return None
    out = market_sectors.symbol_set_for_market_sectors(DATA_DIR, DB_PATH, names)
    # If names do not resolve via sector mapping, do not restrict filter math to an empty
    # symbol set (that yields zero matches for every technical filter). get_stocks still
    # applies the Market Sector column filter from the same market_sectors list.
    if out is not None and len(out) == 0:
        return None
    return out


def _parse_json_list_param(raw: str) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _parse_snapshot_timeframes_csv(raw: Optional[str]) -> Optional[Tuple[str, ...]]:
    if raw is None:
        return None
    try:
        from filter_rebuild_registry import normalize_snapshot_timeframe
    except Exception:
        def normalize_snapshot_timeframe(x):  # type: ignore
            s = str(x or "").strip()
            return "30m" if s.lower() == "30m" else s.upper()

    parts = [normalize_snapshot_timeframe(x) for x in str(raw).split(",") if str(x).strip()]
    if not parts:
        return None
    seen = set()
    out = []
    for tf in parts:
        if tf in SNAPSHOT_TIMEFRAMES and tf not in seen:
            out.append(tf)
            seen.add(tf)
    return tuple(out) if out else None


def _run_filter_symbols(filter_def: dict, market_sectors: list) -> Set[str]:
    if not isinstance(filter_def, dict):
        return set()
    body = {**filter_def, "market_sectors": market_sectors or []}
    filter_type = str(filter_def.get("filter_type", "ema")).strip().lower()
    if filter_type == "macd":
        result = filter_macd(body)
    elif filter_type == "macd_hist_chain":
        result = filter_macd_hist_chain(body)
    elif filter_type == "stochrsi":
        result = filter_stochrsi(body)
    elif filter_type == "price":
        result = filter_price(body)
    elif filter_type == "marketcap":
        result = filter_marketcap(body)
    elif filter_type == "earnings":
        result = filter_earnings(body)
    elif filter_type == "range_channel":
        result = filter_range_channel(body)
    elif filter_type == "avg_volume":
        result = filter_avg_volume(body)
    elif filter_type == "annual_vs_ttm":
        result = filter_annual_vs_ttm(body)
    elif filter_type == "screener":
        result = filter_screener(body)
    else:
        result = filter_ema(body)
    return set(result.get("symbols") or [])


def _filter_priority(filter_def: dict) -> tuple:
    """Lower tuple sorts earlier (more selective filters first)."""
    if not isinstance(filter_def, dict):
        return (99, 99)
    ftype = str(filter_def.get("filter_type", "ema")).strip().lower()
    condition = str(filter_def.get("condition", "")).strip().lower()
    base_rank = {
        "earnings": 0,
        "screener": 0,
        "marketcap": 1,
        "annual_vs_ttm": 1,
        "price": 2,
        "ema": 3,
        "macd": 4,
        "macd_hist_chain": 5,
        "range_channel": 5,
        "stochrsi": 6,
        "avg_volume": 1,
    }.get(ftype, 6)
    cond_rank = {
        "crosses_up": 0,
        "crosses_down": 0,
        "above_pct": 1,
        "below_pct": 1,
        "above": 2,
        "below": 2,
        "above_eq": 3,
        "below_eq": 3,
    }.get(condition, 4)
    return (base_rank, cond_rank)


def _evaluate_snapshot_filter_row(filter_def: dict, row: dict) -> bool:
    def _rv(k: str):
        try:
            # sqlite3.Row supports key access but not dict.get().
            return row[k] if k in row.keys() else None
        except Exception:
            return None

    ftype = str(filter_def.get("filter_type", "ema")).strip().lower()
    condition = str(filter_def.get("condition", "above")).strip().lower()
    pct_value = float(filter_def.get("pct_value", 0) or 0)
    try:
        if ftype == "ema":
            ema_period = int(filter_def.get("ema_period", 21))
            target = str(filter_def.get("target", "price")).strip().lower()
            target_ema_period = int(filter_def.get("target_ema_period", 50))
            if ema_period not in [9, 21, 50, 100, 200]:
                return False
            ema_curr = _rv(f"ema{ema_period}")
            ema_prev = _rv(f"ema{ema_period}_prev")
            if target == "ema":
                if target_ema_period not in [9, 21, 50, 100, 200]:
                    return False
                target_val = _rv(f"ema{target_ema_period}")
                target_prev = _rv(f"ema{target_ema_period}_prev")
            elif target == "open":
                target_val = _rv("open_curr")
                target_prev = _rv("open_prev")
            elif target == "high":
                target_val = _rv("high_curr")
                target_prev = _rv("high_prev")
            elif target == "low":
                target_val = _rv("low_curr")
                target_prev = _rv("low_prev")
            else:
                target_val = _rv("close_curr")
                target_prev = _rv("close_prev")
            if ema_curr is None or target_val is None:
                return False
            if condition == "above":
                return ema_curr > target_val
            if condition == "above_eq":
                return ema_curr >= target_val
            if condition == "below":
                return ema_curr < target_val
            if condition == "below_eq":
                return ema_curr <= target_val
            if condition == "crosses_up":
                return ema_prev is not None and target_prev is not None and ema_prev <= target_prev and ema_curr > target_val
            if condition == "crosses_down":
                return ema_prev is not None and target_prev is not None and ema_prev >= target_prev and ema_curr < target_val
            if condition == "above_pct":
                if target_val == 0:
                    return False
                pct_gap = ((ema_curr - target_val) / abs(target_val)) * 100
                return ema_curr > target_val and pct_gap <= pct_value
            if condition == "below_pct":
                if target_val == 0:
                    return False
                pct_gap = ((target_val - ema_curr) / abs(target_val)) * 100
                return ema_curr < target_val and pct_gap <= pct_value
            return False

        if ftype == "price":
            target = str(filter_def.get("target", "ema")).strip().lower()
            ema_period = int(filter_def.get("ema_period", 21))
            price_curr = _rv("close_curr")
            price_prev = _rv("close_prev")
            if price_curr is None or price_prev is None:
                return False
            if target == "open":
                tgt_curr, tgt_prev = _rv("open_curr"), _rv("open_prev")
            elif target == "high":
                tgt_curr, tgt_prev = _rv("high_curr"), _rv("high_prev")
            elif target == "low":
                tgt_curr, tgt_prev = _rv("low_curr"), _rv("low_prev")
            elif target == "ema" and ema_period in [9, 21, 50, 100, 200]:
                tgt_curr, tgt_prev = _rv(f"ema{ema_period}"), _rv(f"ema{ema_period}_prev")
            else:
                return False
            if tgt_curr is None or tgt_prev is None:
                return False
            if condition == "above":
                return price_curr > tgt_curr
            if condition == "above_eq":
                return price_curr >= tgt_curr
            if condition == "below":
                return price_curr < tgt_curr
            if condition == "below_eq":
                return price_curr <= tgt_curr
            if condition == "crosses_up":
                return price_prev <= tgt_prev and price_curr > tgt_curr
            if condition == "crosses_down":
                return price_prev >= tgt_prev and price_curr < tgt_curr
            if condition == "above_pct":
                return tgt_curr != 0 and price_curr > tgt_curr * (1 + pct_value / 100)
            if condition == "below_pct":
                return tgt_curr != 0 and price_curr < tgt_curr * (1 - pct_value / 100)
            return False

        if ftype == "macd":
            return _macd_filter_matches_snapshot_row(row, filter_def)

        if ftype == "macd_hist_chain":
            return _macd_hist_chain_matches_snapshot_row(row, filter_def)

        if ftype == "stochrsi":
            source = str(filter_def.get("source", "k")).strip().lower()
            target = str(filter_def.get("target", "value")).strip().lower()
            target_value = float(filter_def.get("target_value", 80) or 80)
            src_curr = _rv("stoch_k") if source == "k" else _rv("stoch_d")
            src_prev = _rv("stoch_k_prev") if source == "k" else _rv("stoch_d_prev")
            if src_curr is None:
                return False
            if target == "value":
                tgt_curr = target_value
                tgt_prev = target_value
            elif target == "k":
                tgt_curr = _rv("stoch_k")
                tgt_prev = _rv("stoch_k_prev")
            else:
                tgt_curr = _rv("stoch_d")
                tgt_prev = _rv("stoch_d_prev")
            if tgt_curr is None:
                return False
            if condition == "above":
                return src_curr > tgt_curr
            if condition == "above_eq":
                return src_curr >= tgt_curr
            if condition == "below":
                return src_curr < tgt_curr
            if condition == "below_eq":
                return src_curr <= tgt_curr
            if condition == "crosses_up":
                return src_prev is not None and tgt_prev is not None and src_prev <= tgt_prev and src_curr > tgt_curr
            if condition == "crosses_down":
                return src_prev is not None and tgt_prev is not None and src_prev >= tgt_prev and src_curr < tgt_curr
            if condition == "above_pct":
                return tgt_curr != 0 and src_curr > tgt_curr * (1 + pct_value / 100)
            if condition == "below_pct":
                return tgt_curr != 0 and src_curr < tgt_curr * (1 - pct_value / 100)
            return False
    except Exception:
        return False
    return False


def _combined_filter_symbols_snapshot_fast(filters: list, market_sectors: list) -> tuple[Optional[Set[str]], bool]:
    ordered_filters = sorted(filters, key=_filter_priority)
    snapshot_rows_by_key = {}
    combined = None
    for idx, filter_def in enumerate(ordered_filters, start=1):
        ftype = str(filter_def.get("filter_type", "ema")).strip().lower()
        if ftype in ("marketcap", "earnings", "annual_vs_ttm", "avg_volume"):
            return None, False
        tf_unit, tf_num = parse_timeframe(str(filter_def.get("timeframe", "1D")))
        snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)
        if not snapshot_key:
            return None, False
        if snapshot_key not in snapshot_rows_by_key:
            sect = _sector_allowed_symbols({"market_sectors": market_sectors or []})
            snapshot_rows_by_key[snapshot_key] = _load_filter_snapshots(snapshot_key, sect)
        rows = snapshot_rows_by_key[snapshot_key]
        if not rows:
            return None, False
        f_t0 = time_module.time()
        symbols = {row["symbol"] for row in rows if _evaluate_snapshot_filter_row(filter_def, row)}
        f_ms = int((time_module.time() - f_t0) * 1000)
        if f_ms >= 250:
            print(f"[perf] filter-step-fast {idx}/{len(ordered_filters)} type={ftype} -> {f_ms}ms ({len(symbols)} matches)")
        combined = symbols if combined is None else combined & symbols
        if not combined:
            return set(), True
    return (combined if combined is not None else set()), True


def _combined_filter_symbols(filters: list, market_sectors: list) -> Optional[Set[str]]:
    if not filters:
        return None
    cache_key = _combined_filter_cache_key(filters, market_sectors)
    cached = get_combined_filter_cache(cache_key)
    if cached is not None:
        print(f"[perf] filter-combine cache=hit ({len(cached)} symbols, {len(filters)} filters)")
        return cached
    started = time_module.time()
    ordered_filters = sorted(filters, key=_filter_priority)
    # Hybrid combined path: each chip uses its native filter_* evaluator (snapshot + live
    # where implemented), then intersect by symbol. Avoid authoritative snapshot-only fast
    # path so histogram, earnings, MACD add-ons, and multi-TF chips stay in sync.
    combined = None
    for idx, filter_def in enumerate(ordered_filters, start=1):
        f_t0 = time_module.time()
        symbols = _run_filter_symbols(filter_def, market_sectors)
        f_ms = int((time_module.time() - f_t0) * 1000)
        if f_ms >= 250:
            ftype = str(filter_def.get("filter_type", "ema")).strip().lower()
            print(f"[perf] filter-step {idx}/{len(ordered_filters)} type={ftype} -> {f_ms}ms ({len(symbols)} matches)")
        combined = symbols if combined is None else combined & symbols
        if not combined:
            total_ms = int((time_module.time() - started) * 1000)
            print(f"[perf] filter-combine early-exit cache=miss -> {total_ms}ms ({len(ordered_filters)} filters)")
            set_combined_filter_cache(cache_key, set())
            return set()
    total_ms = int((time_module.time() - started) * 1000)
    if total_ms >= 300:
        print(f"[perf] filter-combine total cache=miss -> {total_ms}ms ({len(ordered_filters)} filters)")
    result = combined if combined is not None else set()
    set_combined_filter_cache(cache_key, result)
    return result


def _load_indicator_snapshots(timeframe: str, sector_symbols: Optional[Set[str]] = None) -> list:
    conn = get_db_connection()
    try:
        query = "SELECT * FROM indicator_snapshots WHERE timeframe = ?"
        params = [timeframe]
        if sector_symbols is not None:
            symbols = sorted(sector_symbols)
            if not symbols:
                return []
            placeholders = ",".join(["?"] * len(symbols))
            query += f" AND symbol IN ({placeholders})"
            params.extend(symbols)
        query += " ORDER BY symbol ASC"
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


_SNAPSHOT_COVERAGE_CACHE_TTL_SEC = 45.0


def _indicator_snapshots_cover_universe(timeframe: str) -> bool:
    """
    Return True only if indicator_snapshots can drive filter/screener logic for this
    timeframe. Two ways it cannot: a tiny partial rebuild (a few symbols would cap
    results), or a fully populated snapshot that predates the newest daily bar, which
    silently answers today's filter with an older session's indicators. Either way the
    caller falls back to live candles.
    """
    now = time_module.time()
    cached = _app_caches.get_snapshot_coverage(timeframe)
    if cached and (now - cached.get("ts", 0)) <= _SNAPSHOT_COVERAGE_CACHE_TTL_SEC:
        return bool(cached.get("ok"))
    ok = False
    stale_note = ""
    if DB_PATH.exists():
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM screener")
            n_scr = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(DISTINCT symbol), MAX(updated_at) "
                "FROM indicator_snapshots WHERE timeframe = ?",
                (timeframe,),
            )
            row = cur.fetchone() or (0, None)
            n_snap = int(row[0] or 0)
            ok = n_scr > 0 and (n_snap / n_scr) >= SNAPSHOT_FILTER_MIN_COVERAGE
            if ok and timeframe in SNAPSHOT_FRESHNESS_TIMEFRAMES:
                cur.execute("SELECT MAX(SUBSTR(Date, 1, 10)) FROM historical_data")
                last_bar = str((cur.fetchone() or [None])[0] or "")
                snap_day = str(row[1] or "")[:10]
                if last_bar and (not snap_day or snap_day < last_bar):
                    ok = False
                    stale_note = (
                        f"{timeframe} snapshot is from {snap_day or 'unknown'} "
                        f"but bars run to {last_bar}"
                    )
        finally:
            conn.close()
    if stale_note:
        print(f"[filter] {stale_note}; using live candles until snapshots are rebuilt")
    _app_caches.set_snapshot_coverage(timeframe, ok)
    return ok


def _load_filter_snapshots(timeframe: str, sector_symbols: Optional[Set[str]] = None) -> list:
    """Like _load_indicator_snapshots but only when snapshot coverage is representative."""
    if not _indicator_snapshots_cover_universe(timeframe):
        return []
    return _load_indicator_snapshots(timeframe, sector_symbols)


def _snapshot_ema_column_coverage(snap_rows, ema_period: int) -> float:
    """Share of snapshot rows with a non-null ema{period} value."""
    if not snap_rows:
        return 0.0
    col = f"ema{ema_period}"
    populated = 0
    for row in snap_rows:
        try:
            if row[col] is not None:
                populated += 1
        except (KeyError, IndexError, TypeError):
            continue
    return populated / len(snap_rows)


def _snapshots_usable_for_ema_filter(
    snap_rows,
    ema_period: int,
    target: str,
    target_ema_period: int,
    min_coverage: float = SNAPSHOT_FILTER_MIN_COVERAGE,
) -> bool:
    """Reject snapshot rows when required EMA columns are mostly NULL (e.g. weekly EMA200)."""
    if not snap_rows:
        return False
    periods = {ema_period}
    if target == "ema":
        periods.add(target_ema_period)
    for period in periods:
        if _snapshot_ema_column_coverage(snap_rows, period) < min_coverage:
            return False
    return True


def _load_latest_two_daily_ohlc(conn, symbols=None) -> dict:
    """
    Latest and previous daily bars from historical_data, keyed by UPPER(symbol).

    Price filters vs open/high/low must use the same session OHLC the chart/list show.
    indicator_snapshots can lag a full session after daily scrape / live price refresh;
    overlaying these bars prevents false matches (e.g. yesterday's green bar while
    today closed below open).

    Seeks once per symbol on the (Symbol, Date) index — a window over the full
    historical_data table costs ~20s on a 7M-row DB for the same two bars.
    """
    cur = conn.cursor()
    if symbols is None:
        try:
            cur.execute("SELECT Symbol FROM screener")
            symbols = [r[0] for r in cur.fetchall()]
        except Exception:
            cur.execute(
                "SELECT DISTINCT Symbol FROM historical_data "
                "WHERE Symbol IS NOT NULL AND TRIM(Symbol) != ''"
            )
            symbols = [r[0] for r in cur.fetchall()]
    bars_by_symbol = price_lookback.load_recent_daily_bars(conn, symbols, 2)
    out: dict = {}
    for sym, bars in bars_by_symbol.items():
        if not bars:
            continue
        slot = out.setdefault(str(sym), {})
        last = bars[-1]
        slot["open_curr"], slot["high_curr"], slot["low_curr"], slot["close_curr"] = last
        if len(bars) > 1:
            prev = bars[-2]
            slot["open_prev"], slot["high_prev"], slot["low_prev"], slot["close_prev"] = prev
    return out


def _snapshot_row_as_dict(row) -> dict:
    if isinstance(row, dict):
        return dict(row)
    try:
        return {k: row[k] for k in row.keys()}
    except Exception:
        return dict(row)


def _overlay_daily_ohlc_on_price_snapshot_row(row: dict, ohlc: Optional[dict]) -> dict:
    """Patch 1D OHLC fields on a snapshot row from latest historical_data bars."""
    if not ohlc:
        return row
    out = dict(row)
    for key in (
        "open_curr",
        "high_curr",
        "low_curr",
        "close_curr",
        "open_prev",
        "high_prev",
        "low_prev",
        "close_prev",
    ):
        if key in ohlc and ohlc[key] is not None:
            out[key] = ohlc[key]
    return out


def _snapshot_timeframe_key(tf_unit: str, tf_num: int) -> Optional[str]:
    if tf_unit == "D":
        if tf_num == 1:
            return "1D"
        if 2 <= tf_num <= 6:
            return f"{tf_num}D"
        return None
    if tf_unit == "W":
        if tf_num == 1:
            return "1W"
        if tf_num == 2:
            return "2W"
        if tf_num == 4:
            return "4W"
        return None
    if tf_unit == "M":
        return "1M" if tf_num == 1 else None
    if tf_unit == "H" and tf_num == 4:
        return "4H"
    if tf_unit == "m" and tf_num == 30:
        return "30m"
    return None


def get_stock_df() -> pd.DataFrame:
    """Screener frame with Price/1D%/1M% refreshed at most every SCREENER_OHLC_REFRESH_TTL_SEC."""
    global _stock_df, _stock_df_ohlc, _stock_df_ohlc_ts
    with _stock_df_lock:
        if _stock_df is None:
            conn_b = get_db_connection()
            try:
                df = pd.read_sql_query("SELECT * FROM screener", conn_b)
            finally:
                conn_b.close()

            n = len(df)
            _map = market_sectors.load_mapping(DATA_DIR)
            se_col = df["nse_sector"] if "nse_sector" in df.columns else pd.Series([None] * n)
            ind_col = df["nse_industry"] if "nse_industry" in df.columns else pd.Series([None] * n)
            df["Market Sector"] = [
                market_sectors.resolve_market_sector(
                    str(s).strip().upper(),
                    None if pd.isna(se) else str(se),
                    None if pd.isna(ind) else str(ind),
                    _map,
                    data_dir=DATA_DIR,
                )
                for s, se, ind in zip(df["symbol"], se_col, ind_col)
            ]

            rename_map = {
                "symbol":                   "Symbol",
                "market_cap":               "Market Cap",
                "price":                    "Price",
                "change_percent":           "Change %",
                "change_percent_monthly":   "Monthly Change %",
                "pe":                       "PE",
                "revenue_growth_ttm":       "Revenue Growth TTM YoY",
                "revenue_growth_qoq":       "Revenue Growth Quarterly QoQ",
                "net_income_ttm":           "Net Income TTM YoY",
                "net_income_qoq":           "Net Income Quarterly QoQ",
                "ebitda_growth_qoq":        "EBITDA Growth Quarterly QoQ",
            }
            if "nse_sector" in df.columns:
                rename_map["nse_sector"] = "NSE Sector"
            if "nse_industry" in df.columns:
                rename_map["nse_industry"] = "NSE Industry"
            df.rename(columns=rename_map, inplace=True)

            df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()

            for col in NUMERIC_DISPLAY_COLUMNS:
                if col not in df.columns:
                    continue
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if col == "Market Cap":
                    df[col] = df[col].round(0)
                else:
                    df[col] = df[col].round(2)

            _stock_df = df
            _stock_df_ohlc = None
            _stock_df_ohlc_ts = 0.0

        now = time_module.time()
        cache_fresh = (
            _stock_df_ohlc is not None
            and (now - float(_stock_df_ohlc_ts or 0.0)) < SCREENER_OHLC_REFRESH_TTL_SEC
        )
        if cache_fresh:
            out = _stock_df_ohlc.copy()
        else:
            out = _stock_df.copy()
            conn = get_db_connection()
            try:
                _apply_live_screener_ohlc(out, conn)
                try:
                    market_cap_live.apply_live_market_cap(out, conn)
                except Exception:
                    pass
            finally:
                conn.close()
            _stock_df_ohlc = out.copy()
            _stock_df_ohlc_ts = now
            out = _stock_df_ohlc.copy()

    # Fresh ticks without re-running full-universe SQL.
    _apply_movers_live_prices_only(out)
    return out


# ──────────────────────────────────────────────
# SANITIZER
# ──────────────────────────────────────────────

def sanitize(val):
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val

def sanitize_records(records: list) -> list:
    return [{k: sanitize(v) for k, v in row.items()} for row in records]


# ──────────────────────────────────────────────
# TIMEFRAME AGGREGATION
# ──────────────────────────────────────────────

def assign_period_key(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    cfg = TIMEFRAME_CONFIG.get(timeframe)
    if cfg is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    df = df.copy()

    # Parse date — handle timezone-aware strings like '2008-10-06 00:00:00+05:30'
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_convert(None)

    df.sort_values("Date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    anchor = cfg["anchor"]

    if anchor == "day":
        # Absolute day anchor so N-day buckets are consistent across symbols.
        n = cfg["days"]
        day_anchor = pd.Timestamp("1970-01-01")
        days_from_anchor = (df["Date"] - day_anchor).dt.days
        df["period_key"] = (days_from_anchor // n).astype(int)

    elif anchor == "week":
        # Absolute Monday anchor to keep 2W/3W/4W aligned globally.
        weeks = cfg.get("weeks", 1)
        week_anchor = pd.Timestamp("1970-01-05")  # Monday
        week_start = df["Date"] - pd.to_timedelta(df["Date"].dt.weekday, unit="D")
        weeks_from_anchor = ((week_start - week_anchor).dt.days // 7).astype(int)
        df["period_key"] = (weeks_from_anchor // weeks).astype(int)

    elif anchor == "month":
        # Absolute month index so N-month buckets are consistent across symbols.
        months = cfg.get("months", 1)
        month_index = (df["Date"].dt.year * 12 + (df["Date"].dt.month - 1)).astype(int)
        df["period_key"] = (month_index // months).astype(int)

    return df


def aggregate_ohlcv(df: pd.DataFrame, timeframe: str) -> list:
    """Aggregate daily OHLCV into timeframe bars.

    Uses vectorized pandas groupby (not a Python per-bucket loop). A 1D path
    skips bucketing entirely — the old loop was ~3s on ~7k daily rows.
    """
    cfg = TIMEFRAME_CONFIG.get(timeframe)
    if cfg is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    if df is None or df.empty:
        return []

    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], utc=True).dt.tz_convert(None)
    work.sort_values("Date", inplace=True)
    work.reset_index(drop=True, inplace=True)

    # 1D: each daily row is already one bar — avoid groupby entirely.
    if cfg.get("anchor") == "day" and int(cfg.get("days") or 1) == 1:
        bars = []
        for row in work.itertuples(index=False):
            vol_raw = getattr(row, "Volume", None)
            try:
                vol = float(vol_raw) if vol_raw is not None and not pd.isna(vol_raw) else 0.0
            except (TypeError, ValueError):
                vol = 0.0
            if vol <= 0:
                vol = 0.0
            bars.append({
                "time":   str(row.Date)[:10],
                "open":   round(float(row.Open), 2),
                "high":   round(float(row.High), 2),
                "low":    round(float(row.Low), 2),
                "close":  round(float(row.Close), 2),
                "volume": round(vol, 2),
            })
        return bars

    work = assign_period_key(work, timeframe)
    grouped = work.groupby("period_key", sort=True).agg(
        Date=("Date", "first"),
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    )
    bars = []
    for row in grouped.itertuples(index=False):
        try:
            vol = float(row.Volume) if row.Volume is not None and not pd.isna(row.Volume) else 0.0
        except (TypeError, ValueError):
            vol = 0.0
        if vol <= 0:
            vol = 0.0
        bars.append({
            "time":   str(row.Date)[:10],
            "open":   round(float(row.Open), 2),
            "high":   round(float(row.High), 2),
            "low":    round(float(row.Low), 2),
            "close":  round(float(row.Close), 2),
            "volume": round(vol, 2),
        })
    return bars


def _chart_daily_row_budget(timeframe: str, bars_limit: Optional[int], ema_periods: list) -> Optional[int]:
    """Newest-first daily row cap for historical_data chart loads. None = full history."""
    cfg = TIMEFRAME_CONFIG.get(timeframe) or {}
    anchor = cfg.get("anchor")
    if anchor not in ("day", "week", "month"):
        return None
    limit = int(bars_limit) if bars_limit is not None else 2000
    max_req = max(int(p) for p in ema_periods) if ema_periods else 0
    warmup = max(120, max_req + 50, 26 + 9 + 15, 90)
    need_bars = limit + warmup
    if anchor == "day":
        return need_bars * int(cfg.get("days") or 1) + 10
    if anchor == "week":
        return need_bars * 5 * int(cfg.get("weeks") or 1) + 40
    return need_bars * 23 * int(cfg.get("months") or 1) + 60


# ──────────────────────────────────────────────
# INDICATOR CALCULATIONS
# ──────────────────────────────────────────────

def calculate_ema(closes: list, period: int) -> list:
    if len(closes) < period:
        return [None] * len(closes)

    k      = 2.0 / (period + 1)
    result = []
    ema    = None

    for price in closes:
        if ema is None:
            ema = price
        else:
            ema = price * k + ema * (1 - k)
        result.append(round(ema, 2))

    return result


def calculate_stochrsi(
    closes:       list,
    rsi_period:   int = 14,
    stoch_period: int = 14,
    k_smooth:     int = 3,
    d_smooth:     int = 3,
) -> dict:
    n = len(closes)
    if n < rsi_period + stoch_period + max(k_smooth, d_smooth):
        return {"k": [None] * n, "d": [None] * n}

    deltas   = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains    = [max(x, 0.0) for x in deltas]
    losses   = [abs(min(x, 0.0)) for x in deltas]

    avg_gain = sum(gains[:rsi_period]) / rsi_period
    avg_loss = sum(losses[:rsi_period]) / rsi_period

    rsi_vals = []
    for i in range(rsi_period, len(deltas)):
        avg_gain = (avg_gain * (rsi_period - 1) + gains[i])  / rsi_period
        avg_loss = (avg_loss * (rsi_period - 1) + losses[i]) / rsi_period
        rs       = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        rsi_vals.append(100.0 - (100.0 / (1 + rs)) if avg_loss != 0 else 100.0)

    raw_k = []
    for i in range(stoch_period - 1, len(rsi_vals)):
        window = rsi_vals[i - stoch_period + 1: i + 1]
        lo, hi = min(window), max(window)
        raw_k.append(((rsi_vals[i] - lo) / (hi - lo) * 100) if hi != lo else 50.0)

    def sma_smooth(data: list, period: int) -> list:
        out = []
        for i in range(len(data)):
            if i < period - 1:
                out.append(None)
            else:
                out.append(round(sum(data[i - period + 1: i + 1]) / period, 2))
        return out

    smoothed_k = sma_smooth(raw_k, k_smooth)
    valid_k    = [v for v in smoothed_k if v is not None]
    smoothed_d = sma_smooth(valid_k, d_smooth)

    k_pad = n - len(smoothed_k)
    d_pad = n - len(smoothed_d)

    return {
        "k": [None] * k_pad + smoothed_k,
        "d": [None] * d_pad + smoothed_d,
    }


def calculate_macd(
    closes: list,
    fast:   int = 12,
    slow:   int = 26,
    signal: int = 9,
) -> dict:
    n = len(closes)
    if n < slow + signal:
        return {
            "macd":      [None] * n,
            "signal":    [None] * n,
            "histogram": [None] * n,
        }

    def ema_full(data: list, period: int) -> list:
        k   = 2.0 / (period + 1)
        ema = data[0]
        out = [ema]
        for p in data[1:]:
            ema = p * k + ema * (1 - k)
            out.append(ema)
        return out

    fast_ema  = ema_full(closes, fast)
    slow_ema  = ema_full(closes, slow)
    macd_raw  = [round(f - s, 2) for f, s in zip(fast_ema, slow_ema)]

    sig_input = macd_raw[slow - 1:]
    sig_ema   = ema_full(sig_input, signal)

    macd_out  = [None] * (slow - 1) + macd_raw[slow - 1:]
    sig_out   = [None] * (slow - 1 + signal - 1) + [round(v, 2) for v in sig_ema[signal - 1:]]
    hist_out  = []

    for m, s in zip(macd_out, sig_out):
        if m is not None and s is not None:
            hist_out.append(round(m - s, 2))
        else:
            hist_out.append(None)

    return {
        "macd":      macd_out,
        "signal":    sig_out,
        "histogram": hist_out,
    }


# ──────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────

def _earnings_screener_symbol_candidates(sym: str) -> list[str]:
    """Lookup keys for screener.price — exact symbol plus known NSE variants."""
    s = str(sym or "").strip().upper()
    if not s:
        return []
    out: list[str] = [s]
    alias = SCREENER_COMPANY_SLUG_ALIASES.get(s)
    if alias and alias not in out:
        out.append(alias)
    if "_" in s:
        hyphen = s.replace("_", "-")
        if hyphen not in out:
            out.append(hyphen)
    return out


def _row_tv_close_price(row: dict) -> float | None:
    try:
        raw = row.get("price")
        if raw is None:
            return None
        px = round(float(raw), 2)
        return px if px > 0 else None
    except (TypeError, ValueError):
        return None


def _row_tv_change_1d(row: dict) -> float | None:
    try:
        raw = row.get("change_1d_pct")
        if raw is None:
            return None
        chg = round(float(raw), 2)
        return chg if math.isfinite(chg) else None
    except (TypeError, ValueError):
        return None


def _last_bar_change_pct_from_daily_df(df: pd.DataFrame, timeframe: str) -> Optional[float]:
    """
    % change of the last aggregated bar vs the prior bar on `timeframe`.
    Same math as the chart price legend on /api/chart-data (e.g. 2W last vs previous 2W).
    """
    if df is None or df.empty:
        return None
    work = df.copy()
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    if work.empty:
        return None
    try:
        bars = aggregate_ohlcv(work, timeframe)
    except Exception:
        return None
    if len(bars) < 2:
        return None
    last = bars[-1]
    prev = bars[-2]
    prev_c = prev.get("close")
    last_c = last.get("close")
    if prev_c is None or last_c is None or float(prev_c) == 0:
        return None
    pct = (float(last_c) - float(prev_c)) / float(prev_c) * 100.0
    if not math.isfinite(pct):
        return None
    return round(pct, 2)


def _pct_from_snapshot_closes(close_curr, close_prev) -> Optional[float]:
    try:
        curr = float(close_curr)
        prev = float(close_prev)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(curr) or not math.isfinite(prev) or prev == 0:
        return None
    pct = (curr - prev) / prev * 100.0
    if not math.isfinite(pct):
        return None
    return round(pct, 2)


def _batch_change_1m_pct(conn, symbols: list[str]) -> dict[str, float]:
    """
    1M % for earnings table: prefer indicator_snapshots (fast), else aggregate last
    daily tail from historical_data for symbols missing a 1M snapshot row.
    """
    wanted = list(
        dict.fromkeys(
            str(s or "").strip().upper() for s in symbols if str(s or "").strip()
        )
    )
    if not wanted:
        return {}
    query_syms: list[str] = []
    for sym in wanted:
        query_syms.extend(_earnings_screener_symbol_candidates(sym))
    query_syms = list(dict.fromkeys(query_syms))

    by_db_symbol: dict[str, float] = {}
    cur = conn.cursor()
    chunk_size = 400
    for i in range(0, len(query_syms), chunk_size):
        chunk = query_syms[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        try:
            cur.execute(
                f"""
                SELECT UPPER(TRIM(symbol)) AS sym, close_curr, close_prev
                FROM indicator_snapshots
                WHERE timeframe = '1M'
                  AND UPPER(TRIM(symbol)) IN ({placeholders})
                """,
                chunk,
            )
            for sym, close_curr, close_prev in cur.fetchall():
                if sym is None:
                    continue
                key = str(sym).strip().upper()
                if not key or key in by_db_symbol:
                    continue
                pct = _pct_from_snapshot_closes(close_curr, close_prev)
                if pct is not None:
                    by_db_symbol[key] = pct
        except Exception:
            continue

    remapped: dict[str, float] = {}
    missing_for_aggregate: list[str] = []
    for sym in wanted:
        for candidate in _earnings_screener_symbol_candidates(sym):
            hit = by_db_symbol.get(candidate)
            if hit is not None:
                remapped[sym] = hit
                break
        else:
            missing_for_aggregate.append(sym)

    # Skip heavy historical_data aggregation when many symbols miss 1M snapshots —
    # TV earnings scan already carries change|1M for most rows. Aggregating hundreds
    # of daily tails routinely blew past the client 120s timeout.
    MAX_1M_AGGREGATE = 40
    if len(missing_for_aggregate) > MAX_1M_AGGREGATE:
        return remapped

    if not missing_for_aggregate:
        return remapped

    agg_query: list[str] = []
    for sym in missing_for_aggregate:
        agg_query.extend(_earnings_screener_symbol_candidates(sym))
    agg_query = list(dict.fromkeys(agg_query))
    tail_days = 120
    agg_by_symbol: dict[str, float] = {}
    agg_chunk = 80
    for i in range(0, len(agg_query), agg_chunk):
        chunk = agg_query[i : i + agg_chunk]
        placeholders = ",".join("?" * len(chunk))
        try:
            raw = pd.read_sql_query(
                f"""
                SELECT Symbol, Date, Open, High, Low, Close, Volume
                FROM (
                    SELECT UPPER(TRIM(Symbol)) AS Symbol,
                           SUBSTR(Date, 1, 10) AS Date,
                           Open, High, Low, Close, Volume,
                           ROW_NUMBER() OVER (
                               PARTITION BY UPPER(TRIM(Symbol))
                               ORDER BY Date DESC
                           ) AS rn
                    FROM historical_data
                    WHERE UPPER(TRIM(Symbol)) IN ({placeholders})
                )
                WHERE rn <= ?
                ORDER BY Symbol, Date ASC
                """,
                conn,
                params=[*chunk, tail_days],
            )
        except Exception:
            continue
        if raw.empty:
            continue
        for sym, group in raw.groupby("Symbol", sort=False):
            sym_key = str(sym or "").strip().upper()
            if not sym_key:
                continue
            pct = _last_bar_change_pct_from_daily_df(group, "1M")
            if pct is not None:
                agg_by_symbol[sym_key] = pct

    for sym in missing_for_aggregate:
        if sym in remapped:
            continue
        for candidate in _earnings_screener_symbol_candidates(sym):
            hit = agg_by_symbol.get(candidate)
            if hit is not None:
                remapped[sym] = hit
                break
    return remapped


def _enrich_earnings_rows_with_screener_prices(payload: dict) -> dict:
    """Screener price/1D when available; P/E from TV; 1M % matches chart 1M bars (else TV).
    Also attaches resolved Market Sector from screener industry mapping.
    """
    rows = payload.get("rows") or []
    if not rows:
        return payload

    earn_symbols = list({
        str(r.get("symbol") or "").strip().upper()
        for r in rows
        if r.get("symbol")
    })
    if not earn_symbols:
        return payload

    price_by_symbol: dict[str, float | None] = {}
    change_1d_by_symbol: dict[str, float | None] = {}
    change_1m_by_symbol: dict[str, float] = {}
    sector_meta_by_symbol: dict[str, tuple[Optional[str], Optional[str]]] = {}
    if DB_PATH.exists():
        lookup_symbols: list[str] = []
        for sym in earn_symbols:
            lookup_symbols.extend(_earnings_screener_symbol_candidates(sym))
        lookup_symbols = list(dict.fromkeys(lookup_symbols))

        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                chunk_size = 400
                for i in range(0, len(lookup_symbols), chunk_size):
                    chunk = lookup_symbols[i : i + chunk_size]
                    placeholders = ",".join("?" * len(chunk))
                    cur.execute(
                        f"""
                        SELECT UPPER(TRIM(symbol)) AS sym, price, change_percent,
                               nse_sector, nse_industry
                        FROM screener
                        WHERE UPPER(TRIM(symbol)) IN ({placeholders})
                        """,
                        chunk,
                    )
                    for sym, price, chg_1d, nse_se, nse_ind in cur.fetchall():
                        if sym is None:
                            continue
                        key = str(sym)
                        try:
                            price_by_symbol[key] = (
                                round(float(price), 2) if price is not None else None
                            )
                        except (TypeError, ValueError):
                            price_by_symbol[key] = None
                        try:
                            change_1d_by_symbol[key] = (
                                round(float(chg_1d), 2)
                                if chg_1d is not None and math.isfinite(float(chg_1d))
                                else None
                            )
                        except (TypeError, ValueError):
                            change_1d_by_symbol[key] = None
                        sector_meta_by_symbol[key] = (
                            str(nse_se).strip() if nse_se else None,
                            str(nse_ind).strip() if nse_ind else None,
                        )
                change_1m_by_symbol = _batch_change_1m_pct(conn, earn_symbols)
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            print(f"[earnings-beats] screener price enrich skipped (db busy): {e}")
            # Fall through — TradingView prices on the row still render.

    sector_by_symbol: dict[str, list] = {}
    try:
        _map = market_sectors.load_mapping(DATA_DIR)
        for earn_sym in earn_symbols:
            pick = earn_sym
            se: Optional[str] = None
            ind: Optional[str] = None
            for candidate in _earnings_screener_symbol_candidates(earn_sym):
                if candidate in sector_meta_by_symbol:
                    pick = candidate
                    se, ind = sector_meta_by_symbol[candidate]
                    break
            sector_by_symbol[earn_sym] = market_sectors.resolve_market_sectors(
                pick, se, ind, _map, data_dir=DATA_DIR,
            )
    except Exception as exc:
        print(f"[earnings-beats] sector enrich skipped: {exc}")

    still_missing: list[str] = []
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        screener_price = None
        screener_chg_1d = None
        screener_chg_1m = None
        for candidate in _earnings_screener_symbol_candidates(sym):
            px = price_by_symbol.get(candidate)
            if px is not None and px > 0:
                screener_price = px
            ch1 = change_1d_by_symbol.get(candidate)
            if ch1 is not None:
                screener_chg_1d = ch1
            ch1m = change_1m_by_symbol.get(candidate)
            if ch1m is not None:
                screener_chg_1m = ch1m
            if (
                screener_price is not None
                and screener_chg_1d is not None
                and screener_chg_1m is not None
            ):
                break
        tv_price = _row_tv_close_price(row)
        tv_chg_1d = _row_tv_change_1d(row)
        if screener_price is not None:
            row["price"] = screener_price
        elif tv_price is not None:
            row["price"] = tv_price
        else:
            row["price"] = None
            still_missing.append(sym)

        if screener_chg_1d is not None:
            row["change_1d_pct"] = screener_chg_1d
        elif tv_chg_1d is not None:
            row["change_1d_pct"] = tv_chg_1d
        else:
            row["change_1d_pct"] = None

        # Prefer local 1M bars; keep TV change|1M from the earnings scan if present.
        if screener_chg_1m is not None:
            row["change_1m_pct"] = screener_chg_1m
        # else leave whatever the TV earnings scan already put on the row

        # P/E comes from TradingView (already on row when scan included it).
        pe = row.get("price_earnings_ttm")
        try:
            if pe is not None and math.isfinite(float(pe)):
                row["price_earnings_ttm"] = round(float(pe), 2)
            else:
                row["price_earnings_ttm"] = None
        except (TypeError, ValueError):
            row["price_earnings_ttm"] = None

        tags = sector_by_symbol.get(sym) or []
        row["market_sectors"] = list(tags) if tags else None
        if tags:
            row["market_sector"] = " · ".join(tags)
        else:
            row["market_sector"] = None

    # Second TradingView round-trip ONLY for missing price / 1D — never expand the
    # list for missing P/E or 1M (those are often null and would re-fetch every row
    # for 2+ minutes past the client 120s timeout).
    need_tv: list[str] = list(dict.fromkeys(still_missing))
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym or sym in need_tv:
            continue
        if row.get("price") is None or row.get("change_1d_pct") is None:
            need_tv.append(sym)

    # Hard cap — price fill is best-effort; do not hammer TradingView.
    MAX_TV_PRICE_FILL = 60
    if len(need_tv) > MAX_TV_PRICE_FILL:
        need_tv = need_tv[:MAX_TV_PRICE_FILL]

    if need_tv:
        tv_snap_by_symbol = lookup_tv_market_metrics(need_tv)
        for row in rows:
            sym = str(row.get("symbol") or "").strip().upper()
            snap = tv_snap_by_symbol.get(sym) or {}
            if not snap:
                continue
            if row.get("price") is None:
                px = snap.get("price")
                if px is not None and px > 0:
                    row["price"] = px
            if row.get("change_1d_pct") is None:
                ch = snap.get("change_1d_pct")
                if ch is not None:
                    row["change_1d_pct"] = ch
            if row.get("change_1m_pct") is None:
                ch1m = snap.get("change_1m_pct")
                if ch1m is not None:
                    row["change_1m_pct"] = ch1m
            if row.get("price_earnings_ttm") is None:
                pe = snap.get("price_earnings_ttm")
                if pe is not None:
                    row["price_earnings_ttm"] = pe

    # Drop legacy 2W field so clients don't show stale values.
    for row in rows:
        row.pop("change_2w_pct", None)

    return payload


_EARNINGS_BEATS_RESP_TTL_SEC = 120.0
_earnings_beats_resp_cache: dict[str, tuple[float, dict]] = {}
_earnings_beats_resp_lock = threading.Lock()


def _earnings_beats_resp_cache_get(key: str) -> Optional[dict]:
    now = time_module.time()
    with _earnings_beats_resp_lock:
        hit = _earnings_beats_resp_cache.get(key)
        if not hit:
            return None
        ts, payload = hit
        if now - ts > _EARNINGS_BEATS_RESP_TTL_SEC:
            _earnings_beats_resp_cache.pop(key, None)
            return None
        return payload


def _earnings_beats_resp_cache_set(key: str, payload: dict) -> None:
    with _earnings_beats_resp_lock:
        _earnings_beats_resp_cache[key] = (time_module.time(), payload)
        if len(_earnings_beats_resp_cache) > 64:
            # Drop oldest entries.
            oldest = sorted(_earnings_beats_resp_cache.items(), key=lambda kv: kv[1][0])
            for k, _ in oldest[: max(1, len(oldest) - 48)]:
                _earnings_beats_resp_cache.pop(k, None)


@app.get("/api/earnings-beats")
def get_earnings_beats(
    mode: str = Query("reported", description="reported | upcoming"),
    year: int | None = Query(None, ge=2024),
    month: int | None = Query(None, ge=0, le=12, description="1-12, 0=all months in year"),
    period: str = Query("this_month", description="upcoming: this_month|next_month|month_after|coming_week|rolling_30_days|rolling_20_days"),
    report_window: str | None = Query(
        None,
        description="reported: this_week|prev_week|month_range|rolling_10_days (portfolio/watchlist dual-beat)",
    ),
    mcap_min: float | None = Query(None, ge=0, description="market cap floor (full INR; UI uses 500M/50B/5T)"),
    mcap_max: float | None = Query(None, ge=0, description="market cap ceiling (full INR; UI uses 500M/50B/5T)"),
    eps_surprise_min: float | None = Query(None, description="reported: min EPS surprise %"),
    eps_surprise_max: float | None = Query(None, description="reported: max EPS surprise %"),
    revenue_surprise_min: float | None = Query(None, description="reported: min revenue surprise %"),
    revenue_surprise_max: float | None = Query(None, description="reported: max revenue surprise %"),
    earnings_plus: str = Query("all", description="reported only: all|only|exclude|tv_eps_rev_beat"),
    limit: int = Query(2000, ge=1, le=2000, description="max rows returned after NSE dedupe"),
    symbols: str | None = Query(
        None,
        description="reported: comma-separated NSE symbols for portfolio/watchlist lookup (bypasses scan row cap)",
    ),
    refresh: bool = Query(False),
):
    """
    TradingView India screener earnings calendar.
    reported: optional EPS/revenue surprise % min/max; empty bounds = all surprises (±).
    upcoming: next report date in the selected period window (IST).
    """
    _t0 = time_module.time()
    mode_norm = (mode or "reported").strip().lower()
    if mode_norm not in ("reported", "upcoming"):
        raise HTTPException(status_code=400, detail="mode must be 'reported' or 'upcoming'")
    earnings_plus_mode = str(earnings_plus or "all").strip().lower()
    if earnings_plus_mode not in EARNINGS_PLUS_FILTER_MODES:
        raise HTTPException(
            status_code=400,
            detail="earnings_plus must be one of: all, only, exclude, tv_eps_rev_beat",
        )
    symbol_list: list[str] | None = None
    if symbols and str(symbols).strip():
        symbol_list = []
        for part in str(symbols).split(","):
            sym = part.strip().upper()
            if sym and sym not in symbol_list:
                symbol_list.append(sym)
        if not symbol_list:
            symbol_list = None
    # Short TTL for full enriched payload — stops live-tick client storms from re-hitting TV.
    _resp_cache_key = None
    if not refresh and symbol_list:
        _resp_cache_key = (
            f"eb:{mode_norm}:{report_window}:{period}:{earnings_plus_mode}:"
            f"{mcap_min}:{mcap_max}:{eps_surprise_min}:{eps_surprise_max}:"
            f"{revenue_surprise_min}:{revenue_surprise_max}:{limit}:"
            f"{','.join(sorted(symbol_list))}"
        )
        hit = _earnings_beats_resp_cache_get(_resp_cache_key)
        if hit is not None:
            return hit
    try:
        _t_tv = time_module.time()
        payload = fetch_earnings_calendar(
            mode=mode_norm,  # type: ignore[arg-type]
            year=year,
            month=month,
            period=period,
            report_window=report_window,
            mcap_min=mcap_min,
            mcap_max=mcap_max,
            eps_surprise_min=eps_surprise_min,
            eps_surprise_max=eps_surprise_max,
            revenue_surprise_min=revenue_surprise_min,
            revenue_surprise_max=revenue_surprise_max,
            limit=limit,
            use_cache=not refresh,
            symbols=symbol_list,
        )
        tv_ms = int((time_module.time() - _t_tv) * 1000)
        if mode_norm == "reported":
            filtered_rows, earnings_plus_cache = _apply_reported_earnings_plus_filter(
                payload.get("rows") or [],
                earnings_plus_mode,
            )
            payload["earnings_plus_cache"] = earnings_plus_cache
            # Always write stamped rows back (earnings_plus flag per release).
            payload["rows"] = filtered_rows
            payload["count"] = len(filtered_rows)
            if earnings_plus_mode != "all":
                payload["total_matches"] = len(filtered_rows)
                if payload.get("matched_symbols") is not None:
                    payload["matched_symbols"] = len(filtered_rows)
                payload["truncated"] = False
            filters = payload.get("filters")
            if isinstance(filters, dict):
                filters["earnings_plus"] = earnings_plus_mode
        _t_en = time_module.time()
        out = _enrich_earnings_rows_with_screener_prices(payload)
        enrich_ms = int((time_module.time() - _t_en) * 1000)
        filters = out.get("filters")
        if isinstance(filters, dict):
            filters["earnings_plus"] = earnings_plus_mode if mode_norm == "reported" else "all"
        if _resp_cache_key:
            _earnings_beats_resp_cache_set(_resp_cache_key, out)
        elapsed_ms = int((time_module.time() - _t0) * 1000)
        if elapsed_ms >= 3000:
            n_rows = len(out.get("rows") or [])
            print(f"[perf] /api/earnings-beats -> {elapsed_ms}ms (mode={mode_norm}, rows={n_rows})")
        return out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except sqlite3.OperationalError as e:
        # Prefer returning TV rows without screener enrich over failing the page.
        print(f"[earnings-beats] sqlite busy, returning unenriched payload: {e}")
        try:
            if "payload" in locals() and isinstance(payload, dict):
                return payload
        except Exception:
            pass
        raise HTTPException(
            status_code=503,
            detail=f"Database busy while loading earnings (retry shortly): {e}",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TradingView screener failed: {e}") from e


@app.get("/api/earnings-plus-flags")
def get_earnings_plus_flags(
    symbols: str = Query(..., description="comma-separated NSE symbols"),
):
    """Bulk Earnings+ qualified flags from earnings_plus_cache (same source as chart/market map)."""
    symbol_list = list(dict.fromkeys(
        s.strip().upper() for s in str(symbols or "").split(",") if s.strip()
    ))
    if not symbol_list:
        return {"qualified": [], "count": 0}
    from earnings_plus_lookup import read_qualified_symbols

    conn = get_db_connection()
    try:
        qualified = read_qualified_symbols(conn, symbol_list)
    finally:
        conn.close()
    return {"qualified": sorted(qualified), "count": len(qualified)}


@app.get("/api/earnings-chart-events/{symbol}")
def get_earnings_chart_events(
    symbol: str,
    refresh_latest: bool = Query(True, description="Refresh the latest persisted report row before returning markers"),
):
    sym = _normalize_symbol_token(symbol)
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")
    conn = get_db_connection()
    try:
        try:
            ensure_earnings_chart_events_table(conn)
        except sqlite3.OperationalError as e:
            print(f"[earnings_chart_events] ensure table busy ({sym}): {e}")
        if refresh_latest:
            try:
                _refresh_symbol_earnings_chart_events(conn, sym)
                with _earnings_plus_db_write_lock:
                    conn.commit()
            except Exception as e:
                print(f"[earnings_chart_events] refresh warning ({sym}): {e}")
        try:
            rows = _read_symbol_earnings_chart_events(conn, sym)
        except sqlite3.OperationalError as e:
            print(f"[earnings_chart_events] read busy ({sym}): {e}")
            rows = []
        try:
            earnings_plus_entry = _read_earnings_plus_cache_entry(conn, sym)
        except sqlite3.OperationalError:
            earnings_plus_entry = None
        return {
            "symbol": sym,
            "count": len(rows),
            "rows": rows,
            "earnings_plus_helper": _build_earnings_plus_helper_from_cache_entry(earnings_plus_entry),
            "earnings_plus_status": {
                "decision": (earnings_plus_entry or {}).get("decision"),
                "basis_used": (earnings_plus_entry or {}).get("basis_used"),
                "latest_period": (earnings_plus_entry or {}).get("latest_period"),
                "note": (earnings_plus_entry or {}).get("note"),
                "is_stale": bool((earnings_plus_entry or {}).get("is_stale")),
            },
            "refresh_latest": refresh_latest,
            "historical_backfill": "forward_only_latest_quarter_snapshot",
        }
    finally:
        conn.close()


@app.get("/api/stocks")
def get_stocks(
    page:     int = Query(1,   ge=1),
    pageSize: int = Query(50,  ge=1, le=500),
    sortBy:   str = Query("Symbol"),
    sortDir:  str = Query("asc"),
    search:   str = Query(""),
    filters:  str = Query(""),
    marketSectors: str = Query(""),
):
    _t0 = time_module.time()
    try:
        df = get_stock_df().copy()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    active_filters = _parse_json_list_param(filters)
    selected_sectors = [str(x).strip() for x in _parse_json_list_param(marketSectors) if str(x).strip()]

    if search.strip():
        mask = df["Symbol"].str.contains(search.strip().upper(), na=False)
        df   = df[mask]

    if selected_sectors:
        allowed_sector_syms = market_sectors.symbol_set_for_market_sectors(
            DATA_DIR, DB_PATH, selected_sectors,
        )
        if allowed_sector_syms is not None:
            df = df[df["Symbol"].isin(allowed_sector_syms)]

    filter_symbols = _combined_filter_symbols(active_filters, selected_sectors)
    if filter_symbols is not None:
        df = df[df["Symbol"].isin(filter_symbols)]

    if sortBy not in VALID_SORT_COLUMNS:
        sortBy = "Symbol"

    ascending = sortDir.lower() != "desc"

    df = df.sort_values(sortBy, ascending=ascending, na_position="last")

    total   = len(df)
    start   = (page - 1) * pageSize
    end     = start + pageSize
    page_df = df.iloc[start:end]

    available = [c for c in OUTPUT_COLUMNS if c in page_df.columns]
    result_df = page_df[available]

    records = sanitize_records(result_df.to_dict(orient="records"))

    result = {
        "total":    total,
        "page":     page,
        "pageSize": pageSize,
        "pages":    math.ceil(total / pageSize) if total > 0 else 1,
        "data":     records,
    }
    elapsed_ms = int((time_module.time() - _t0) * 1000)
    if elapsed_ms >= 250:
        print(
            f"[perf] /api/stocks -> {elapsed_ms}ms "
            f"(filters={len(active_filters)}, sectors={len(selected_sectors)}, total={total})"
        )
    return result


@app.get("/api/stocks/search")
def search_stocks(q: str = Query("", min_length=1)):
    try:
        df = get_stock_df()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    q_upper = q.strip().upper()
    if not q_upper:
        return {"results": []}

    prefix_mask   = df["Symbol"].str.startswith(q_upper, na=False)
    contains_mask = df["Symbol"].str.contains(q_upper, na=False) & ~prefix_mask

    results = (
        df[prefix_mask]["Symbol"].tolist() +
        df[contains_mask]["Symbol"].tolist()
    )[:20]

    return {"results": results}


@app.get("/api/unified-search")
def unified_search(q: str = Query("", min_length=1)):
    """Stock symbols + index names/symbols for command palette / add dialogs."""
    qu = q.strip().upper()
    if not qu:
        return {"stocks": [], "indices": []}
    try:
        df = get_stock_df()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    prefix_mask   = df["Symbol"].str.startswith(qu, na=False)
    contains_mask = df["Symbol"].str.contains(qu, na=False) & ~prefix_mask
    stocks = (
        df[prefix_mask]["Symbol"].tolist() +
        df[contains_mask]["Symbol"].tolist()
    )[:16]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbol, name FROM indices
        WHERE UPPER(symbol) LIKE ? OR UPPER(COALESCE(name,'')) LIKE ?
        ORDER BY name
        LIMIT 12
        """,
        (f"%{qu}%", f"%{qu}%"),
    )
    indices = [{"symbol": r[0], "name": r[1] or r[0]} for r in cur.fetchall()]
    conn.close()
    return {"stocks": stocks, "indices": indices}


@app.get("/api/stock/{symbol}")
def get_stock_detail(symbol: str):
    try:
        df = get_stock_df()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    symbol = symbol.strip().upper()
    row    = df[df["Symbol"] == symbol]

    if row.empty:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    record = sanitize_records(row.iloc[0:1].to_dict(orient="records"))[0]
    return record


def _chart_payload_trim_start(num_bars: int, bars_limit: Optional[int], ema_request_periods: list) -> int:
    """
    First bar index to keep when trimming chart OHLC payload (tail slice).
    EMA / MACD / StochRSI are computed on the full aggregated series first so they
    match indicator_snapshots and filter semantics; only the returned bars list is trimmed.
    """
    if bars_limit is None or num_bars <= int(bars_limit):
        return 0
    max_req = max(int(p) for p in ema_request_periods) if ema_request_periods else 0
    warmup = max(120, max_req + 50, 26 + 9 + 15, 90)
    keep = int(bars_limit) + warmup
    return max(0, num_bars - keep)


@app.get("/api/chart-data/{symbol}")
def get_chart_data(
    symbol:    str,
    timeframe: str           = Query("1D"),
    ema1:      Optional[int] = Query(None),
    ema2:      Optional[int] = Query(None),
    ema3:      Optional[int] = Query(None),
    ema4:      Optional[int] = Query(None),
    bars_limit: Optional[int] = Query(None, ge=100, le=2000),
    live_today: bool         = Query(False),
):
    _t0 = time_module.time()
    _ema_periods = [p for p in [ema1, ema2, ema3, ema4] if p is not None]
    symbol = symbol.strip().upper()

    _cached      = get_chart_cache(symbol, timeframe, _ema_periods) if not live_today else None
    if _cached is not None:
        # Integrity is background-only — never block a cache hit (TF switches).
        if timeframe == "4H" and not live_today:
            _schedule_4h_integrity_check(symbol)
        return _cached

    if timeframe == "4H" and not live_today:
        _schedule_4h_integrity_check(symbol)

    if timeframe not in TIMEFRAME_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}'. Valid: {list(TIMEFRAME_CONFIG.keys())}"
        )

    if timeframe == "4H":
        try:
            conn = get_db_connection()
            from server.bars_4h import (
                format_4h_missing_detail,
                get_bars_4h_source,
                load_bars_4h_for_chart,
            )

            bars = load_bars_4h_for_chart(conn, symbol, limit=bars_limit or 2000)
            day_raw = _equity_day_change_pct_single(symbol, conn)
            intraday_source = get_bars_4h_source(conn, symbol)
            missing_detail = (
                format_4h_missing_detail(symbol, conn, is_index=False) if not bars else None
            )
            conn.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB query failed: {str(e)}")
        if not bars:
            raise HTTPException(status_code=404, detail=missing_detail)
        day_change_pct = round(float(day_raw), 2) if day_raw is not None and math.isfinite(day_raw) else None
        result = _assemble_chart_result(
            symbol,
            timeframe,
            bars,
            day_change_pct,
            _ema_periods,
            bars_limit,
            live_today=False,
        )
        if intraday_source:
            result["intraday_source"] = intraday_source
        if not live_today:
            set_chart_cache(symbol, timeframe, _ema_periods, result)
        return result

    if timeframe == "30m":
        try:
            conn = get_db_connection()
            from server.bars_30m import (
                format_30m_missing_detail,
                get_bars_30m_source,
                load_bars_30m_for_chart,
            )

            bars = load_bars_30m_for_chart(conn, symbol, limit=bars_limit or 2000)
            day_raw = _equity_day_change_pct_single(symbol, conn)
            intraday_source = get_bars_30m_source(conn, symbol)
            missing_detail = (
                format_30m_missing_detail(symbol, conn, is_index=False) if not bars else None
            )
            conn.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB query failed: {str(e)}")
        if not bars:
            raise HTTPException(status_code=404, detail=missing_detail)
        day_change_pct = round(float(day_raw), 2) if day_raw is not None and math.isfinite(day_raw) else None
        result = _assemble_chart_result(
            symbol,
            timeframe,
            bars,
            day_change_pct,
            _ema_periods,
            bars_limit,
            live_today=False,
        )
        if intraday_source:
            result["intraday_source"] = intraday_source
        if not live_today:
            set_chart_cache(symbol, timeframe, _ema_periods, result)
        return result

    try:
        conn = get_db_connection()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        row_budget = _chart_daily_row_budget(timeframe, bars_limit, _ema_periods)
        if row_budget is not None:
            raw_df = pd.read_sql_query(
                """
                SELECT Date, Open, High, Low, Close, Volume FROM (
                    SELECT SUBSTR(Date,1,10) as Date, Open, High, Low, Close, Volume
                    FROM historical_data
                    WHERE Symbol = ?
                    ORDER BY Date DESC
                    LIMIT ?
                ) newest
                ORDER BY Date ASC
                """,
                conn,
                params=(symbol, int(row_budget)),
            )
        else:
            raw_df = pd.read_sql_query(
                """
                SELECT SUBSTR(Date,1,10) as Date, Open, High, Low, Close, Volume
                FROM historical_data
                WHERE Symbol = ?
                ORDER BY Date ASC
                """,
                conn,
                params=(symbol,),
            )
        day_raw = _equity_day_change_pct_single(symbol, conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB query failed: {str(e)}")
    finally:
        conn.close()

    if raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No price data for '{symbol}'")

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce").round(2)

    raw_df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)

    if not raw_df.empty:
        raw_df["_day"] = raw_df["Date"].astype(str).str[:10]
        raw_df["_vol"] = pd.to_numeric(raw_df["Volume"], errors="coerce").fillna(0)
        raw_df.sort_values(["_day", "_vol", "Date"], ascending=[True, False, True], inplace=True)
        raw_df = raw_df.groupby("_day", as_index=False).last()
        raw_df.drop(columns=["_day", "_vol"], inplace=True, errors="ignore")

    if raw_df.empty:
        raise HTTPException(status_code=404, detail=f"All rows invalid for '{symbol}'")

    try:
        bars = aggregate_ohlcv(raw_df, timeframe)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Aggregation failed: {str(e)}")

    if not bars:
        raise HTTPException(status_code=404, detail=f"No bars for '{symbol}' on '{timeframe}'")

    live_day_chg = None
    if live_today:
        # Merge session O/H/L into today's bar. Showcase used to skip this and rely on
        # client overlay only — incomplete DB highs (e.g. FEDFINA 160.8 vs HOD 174.4)
        # never showed a wick when the overlay lag/failed.
        try:
            bars, live_day_chg = movers_live.merge_live_into_chart_bars(
                symbol, bars, timeframe, allow_fetch=True
            )
        except TypeError:
            # Older movers_live without allow_fetch kwarg (encrypted/runtime skew).
            try:
                bars, live_day_chg = movers_live.merge_live_into_chart_bars(
                    symbol, bars, timeframe
                )
            except Exception:
                pass
        except Exception:
            pass

    full_closes = [float(b["close"]) for b in bars]
    trim_start = _chart_payload_trim_start(len(bars), bars_limit, _ema_periods)

    day_change_pct = movers_data.resolve_chart_day_change_pct(day_raw, live_day_chg)

    trimmed_bars = bars[trim_start:]
    times = [b["time"] for b in trimmed_bars]

    def zip_with_time(values: list) -> list:
        return [
            {"time": times[i], "value": v}
            for i, v in enumerate(values)
            if v is not None and i < len(times)
        ]

    def zip_with_time_padded(values: list) -> list:
        """
        Same as zip_with_time but pads None entries with the correct
        timestamp so the series always starts at the same time as price bars.
        This ensures lightweight-charts aligns all panels by time correctly.
        """
        result = []
        for i, v in enumerate(values):
            if i >= len(times):
                break
            if v is not None:
                result.append({"time": times[i], "value": v})
        return result

    off = trim_start
    ema_out = {}
    for period in [p for p in [ema1, ema2, ema3, ema4] if p is not None]:
        ema_series = calculate_ema(full_closes, period)
        ema_out[str(period)] = zip_with_time(ema_series[off:])

    stoch_full = calculate_stochrsi(full_closes)
    stochrsi = {
        "k": zip_with_time(stoch_full["k"][off:]),
        "d": zip_with_time(stoch_full["d"][off:]),
    }

    macd_data = calculate_macd(full_closes)
    macd_out = {
        "macd":      zip_with_time_padded(macd_data["macd"][off:]),
        "signal":    zip_with_time_padded(macd_data["signal"][off:]),
        "histogram": zip_with_time_padded(macd_data["histogram"][off:]),
    }

    lineage_note = None
    try:
        if str(BASE_DIR) not in _sys.path:
            _sys.path.insert(0, str(BASE_DIR))
        from symbol_lineage import get_lineage_entry

        entry = get_lineage_entry(symbol)
        if entry:
            preds = entry.get("predecessors") or []
            names = [
                str(p.get("nse_symbol")).strip()
                for p in preds
                if isinstance(p, dict) and p.get("nse_symbol")
            ]
            if names:
                lineage_note = f"History includes pre-rename ticker(s): {', '.join(names)}"
    except Exception:
        pass

    except Exception:
        pass

    corp_markers: list = []
    try:
        from server.chart_corp_markers import load_corp_markers_for_chart

        conn_mk = get_db_connection()
        try:
            corp_markers = load_corp_markers_for_chart(conn_mk, symbol)
        finally:
            conn_mk.close()
    except Exception:
        corp_markers = []

    result = {
        "symbol":    symbol,
        "timeframe": timeframe,
        "bars":      trimmed_bars,
        "ema":       ema_out,
        "stochrsi":  stochrsi,
        "macd":      macd_out,
        "day_change_pct": day_change_pct,
        "live_today_bar": bool(live_today and live_day_chg is not None),
        "lineage_note": lineage_note,
        "corp_markers": corp_markers,
    }
    if not live_today:
        set_chart_cache(symbol, timeframe, _ema_periods, result)
    elapsed_ms = int((time_module.time() - _t0) * 1000)
    if elapsed_ms >= 500:
        print(f"[perf] /api/chart-data {symbol} {timeframe} -> {elapsed_ms}ms ({len(trimmed_bars)} bars)")
    return result


@app.get("/api/timeframes")
def get_timeframes():
    return {"timeframes": list(TIMEFRAME_CONFIG.keys())}



# ──────────────────────────────────────────────
# LAYOUT PERSISTENCE (legacy handlers — prefer server/routers/settings.py)
# ──────────────────────────────────────────────

LAYOUT_PATH = DATA_DIR / "layout.json"

DEFAULT_LAYOUT = {
    "stochrsi":           130,
    "macd":               130,
    "dashboardPaneWidth": 320,
    "maxChartTabs":       5,
}

# Routes moved to server/routers/settings.py


def _resolve_user_notes_session(request: Request | None = None):
    from server import license_client as _lc
    from server.product_config import is_web_host_mode
    from server.web_auth import get_request_session, load_browser_session

    session = get_request_session()
    if session:
        return session
    if request is not None and is_web_host_mode(BASE_DIR):
        _sid, loaded = load_browser_session(BASE_DIR, request)
        if loaded:
            return loaded
    return _lc.load_session(BASE_DIR)


try:
    from server import mf_routes as _mf_routes

    _mf_routes.configure(
        base_dir=BASE_DIR,
        db_path=DB_PATH,
        resolve_session=_resolve_user_notes_session,
    )
    app.include_router(_mf_routes.router)
except Exception as _mf_err:
    print(f"[mf] routes not loaded: {_mf_err}")


@app.get("/api/user-notes")
def get_user_notes(request: Request):
    """Universal notes doc (tabbed notepad); scoped to signed-in user + machine, or _local + machine."""
    from server import user_notes_store as _un

    session = _resolve_user_notes_session(request)
    return _un.load_doc(BASE_DIR, session=session)


@app.put("/api/user-notes")
def put_user_notes(request: Request, payload: dict = Body(...)):
    from server import user_notes_store as _un

    session = _resolve_user_notes_session(request)
    try:
        saved = _un.save_doc(BASE_DIR, payload, session=session)
    except ValueError as exc:
        detail = str(exc)
        status = 413 if "too large" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"status": "saved", "tabs": len(saved.get("tabs", []))}


@app.get("/api/user-basket")
def get_user_basket(request: Request):
    """Per-user interest basket; scoped like notes (email + machine)."""
    from server import user_basket_store as _ub

    session = _resolve_user_notes_session(request)
    doc = _ub.load_doc(BASE_DIR, session=session)
    return _enrich_user_basket_doc(doc)


def _enrich_user_basket_doc(doc: dict) -> dict:
    """Attach MCap / price / 1D% / 1M% / latest earnings badge / E+ for basket rows."""
    rows = list((doc or {}).get("symbols") or [])
    if not rows:
        return {"symbols": []}

    stock_syms = [
        str(r.get("symbol") or "").strip().upper()
        for r in rows
        if str(r.get("kind") or "stock").lower() != "index"
    ]
    index_syms = [
        str(r.get("symbol") or "").strip().upper()
        for r in rows
        if str(r.get("kind") or "stock").lower() == "index"
    ]
    stock_syms = [s for s in dict.fromkeys(stock_syms) if s]
    index_syms = [s for s in dict.fromkeys(index_syms) if s]

    stock_map: dict[str, dict] = {}
    index_map: dict[str, dict] = {}
    earnings_map: dict[str, dict] = {}
    plus_set: set[str] = set()
    try:
        conn = get_db_connection()
        try:
            if stock_syms:
                placeholders = ",".join("?" for _ in stock_syms)
                cur = conn.execute(
                    f"""
                    SELECT symbol, market_cap, price, change_percent, change_percent_monthly
                    FROM screener
                    WHERE UPPER(TRIM(symbol)) IN ({placeholders})
                    """,
                    stock_syms,
                )
                for row in cur.fetchall():
                    d = dict(row)
                    sym = str(d.get("symbol") or "").strip().upper()
                    if sym:
                        stock_map[sym] = d
                try:
                    ensure_earnings_chart_events_table(conn)
                    cur = conn.execute(
                        f"""
                        SELECT
                            e.symbol,
                            e.earnings_release_date,
                            e.outcome_kind,
                            e.comparison_status,
                            e.comparison_note
                        FROM earnings_chart_events e
                        INNER JOIN (
                            SELECT symbol, MAX(earnings_release_date) AS max_date
                            FROM earnings_chart_events
                            WHERE UPPER(TRIM(symbol)) IN ({placeholders})
                            GROUP BY symbol
                        ) latest
                          ON e.symbol = latest.symbol
                         AND e.earnings_release_date = latest.max_date
                        """,
                        stock_syms,
                    )
                    for row in cur.fetchall():
                        d = dict(row)
                        sym = str(d.get("symbol") or "").strip().upper()
                        if not sym:
                            continue
                        outcome = str(d.get("outcome_kind") or "").strip().lower()
                        earnings_map[sym] = {
                            "earnings_release_date": str(d.get("earnings_release_date") or "").strip()[:10],
                            "outcome_kind": "beat" if outcome == "beat" else "miss",
                            "comparison_status": d.get("comparison_status"),
                            "comparison_note": d.get("comparison_note") or "",
                        }
                except Exception as exc:
                    print(f"[user-basket] earnings enrich failed: {exc}")
                try:
                    from earnings_plus_lookup import read_qualified_symbols

                    plus_set = read_qualified_symbols(conn, stock_syms)
                except Exception as exc:
                    print(f"[user-basket] earnings+ enrich failed: {exc}")
            if index_syms:
                placeholders = ",".join("?" for _ in index_syms)
                cur = conn.execute(
                    f"""
                    SELECT symbol, last_price, change_pct, change_30d
                    FROM indices
                    WHERE UPPER(TRIM(symbol)) IN ({placeholders})
                    """,
                    index_syms,
                )
                for row in cur.fetchall():
                    d = dict(row)
                    sym = str(d.get("symbol") or "").strip().upper()
                    if sym:
                        index_map[sym] = d
        finally:
            conn.close()
    except Exception as exc:
        print(f"[user-basket] enrich failed: {exc}")

    enriched = []
    for raw in rows:
        entry = dict(raw) if isinstance(raw, dict) else {"symbol": str(raw), "kind": "stock"}
        sym = str(entry.get("symbol") or "").strip().upper()
        kind = str(entry.get("kind") or "stock").strip().lower()
        entry["symbol"] = sym
        entry["kind"] = "index" if kind == "index" else "stock"
        if entry["kind"] == "index":
            q = index_map.get(sym) or {}
            entry["market_cap"] = None
            entry["price"] = q.get("last_price")
            entry["change_1d_pct"] = q.get("change_pct")
            entry["change_1m_pct"] = q.get("change_30d")
            entry["earnings_latest"] = None
            entry["earnings_plus"] = False
        else:
            q = stock_map.get(sym) or {}
            entry["market_cap"] = q.get("market_cap")
            entry["price"] = q.get("price")
            entry["change_1d_pct"] = q.get("change_percent")
            entry["change_1m_pct"] = q.get("change_percent_monthly")
            latest = earnings_map.get(sym)
            entry["earnings_latest"] = latest if latest and latest.get("earnings_release_date") else None
            entry["earnings_plus"] = sym in plus_set
        enriched.append(entry)
    return {"symbols": enriched}


@app.put("/api/user-basket")
def put_user_basket(request: Request, payload: dict = Body(...)):
    from server import user_basket_store as _ub

    session = _resolve_user_notes_session(request)
    try:
        saved = _ub.save_doc(BASE_DIR, payload, session=session)
    except ValueError as exc:
        detail = str(exc)
        status = 413 if "too large" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"status": "saved", "count": len(saved.get("symbols") or [])}


@app.post("/api/user-basket/symbols")
def post_user_basket_symbol(request: Request, payload: dict = Body(...)):
    from server import user_basket_store as _ub

    session = _resolve_user_notes_session(request)
    try:
        saved = _ub.add_symbol(
            BASE_DIR,
            str(payload.get("symbol") or ""),
            kind=str(payload.get("kind") or "stock"),
            session=session,
        )
    except ValueError as exc:
        detail = str(exc)
        status = 413 if "too many" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return _enrich_user_basket_doc(saved)


@app.delete("/api/user-basket/symbols/{symbol}")
def delete_user_basket_symbol(
    symbol: str,
    request: Request,
    kind: str | None = Query(None),
):
    from server import user_basket_store as _ub

    session = _resolve_user_notes_session(request)
    try:
        saved = _ub.remove_symbol(BASE_DIR, symbol, kind=kind, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _enrich_user_basket_doc(saved)

@app.get("/api/user-alerts")
def get_user_alerts(request: Request):
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    doc = _ua.load_alerts(BASE_DIR, session=session)
    pending = _ua.browser_pending_alerts(doc)
    return {
        "alerts": doc.get("alerts") or [],
        "unread": _ua.unread_count(doc),
        "browser_pending": pending,
    }


@app.put("/api/user-alerts")
def put_user_alerts(request: Request, payload: dict = Body(...)):
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    ids = payload.get("ids")
    delete_ids = payload.get("delete_ids")
    if ids is not None and not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids must be a list")
    if delete_ids is not None and not isinstance(delete_ids, list):
        raise HTTPException(status_code=400, detail="delete_ids must be a list")

    if bool(payload.get("clear_all")) or delete_ids:
        doc = _ua.delete_alerts(
            BASE_DIR,
            ids=[str(x) for x in (delete_ids or [])],
            clear_all=bool(payload.get("clear_all")),
            session=session,
        )
    else:
        doc = _ua.mark_alerts(
            BASE_DIR,
            ids=[str(x) for x in (ids or [])],
            mark_all_read=bool(payload.get("mark_all_read")),
            clear_browser_pending=bool(payload.get("clear_browser_pending")),
            session=session,
        )
    return {
        "status": "ok",
        "alerts": doc.get("alerts") or [],
        "unread": _ua.unread_count(doc),
    }


@app.get("/api/alert-settings")
def get_alert_settings(request: Request):
    from server import telegram_notify
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    settings = _ua.load_settings(BASE_DIR, session=session)
    user_tg = _ua.refresh_telegram_bot_profile(BASE_DIR, session=session)
    return {
        **settings,
        "telegram": telegram_notify.telegram_status(user_status=user_tg),
    }


@app.put("/api/alert-settings")
def put_alert_settings(request: Request, payload: dict = Body(...)):
    from server import telegram_notify
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    current = _ua.load_settings(BASE_DIR, session=session)
    # Never accept plaintext Telegram secrets via the generic settings PUT.
    clean = dict(payload) if isinstance(payload, dict) else {}
    for banned in (
        "bot_token", "telegram_bot_token", "chat_id", "telegram_chat_id",
        "bot_token_enc", "chat_id_enc", "telegram",
    ):
        clean.pop(banned, None)
    merged = {**current, **clean}
    saved = _ua.save_settings(BASE_DIR, merged, session=session)
    user_tg = _ua.telegram_credentials_status(BASE_DIR, session=session)
    return {**saved, "telegram": telegram_notify.telegram_status(user_status=user_tg)}


@app.put("/api/alert-settings/upcoming-watch")
def put_upcoming_earnings_watch(request: Request, payload: dict = Body(...)):
    """Arm/disarm a per-symbol upcoming-earnings bell (Earnings page)."""
    from fastapi import HTTPException
    from server import telegram_notify
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    body = payload if isinstance(payload, dict) else {}
    symbol = str(body.get("symbol") or "").strip().upper()
    release = str(
        body.get("release_date") or body.get("earnings_release_next_date") or ""
    ).strip()[:10]
    enabled = bool(body.get("enabled"))
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if enabled and not release:
        raise HTTPException(status_code=400, detail="release_date is required when enabling")
    try:
        saved = _ua.set_upcoming_earnings_watch(
            BASE_DIR,
            symbol=symbol,
            release_date=release or "1970-01-01",
            enabled=enabled,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user_tg = _ua.telegram_credentials_status(BASE_DIR, session=session)
    return {**saved, "telegram": telegram_notify.telegram_status(user_status=user_tg)}


@app.get("/api/price-targets")
def get_price_targets(request: Request):
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    settings = _ua.load_settings(BASE_DIR, session=session)
    return {"price_targets": settings.get("price_targets") or []}


@app.post("/api/price-targets")
def post_price_target(request: Request, payload: dict = Body(...)):
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    body = payload if isinstance(payload, dict) else {}
    try:
        saved = _ua.upsert_price_target(
            BASE_DIR,
            symbol=str(body.get("symbol") or ""),
            direction=str(body.get("direction") or ""),
            level=float(body.get("level")),
            target_id=str(body.get("id") or "").strip() or None,
            session=session,
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok", "price_targets": saved.get("price_targets") or []}


@app.put("/api/price-targets/{target_id}/armed")
def put_price_target_armed(request: Request, target_id: str, payload: dict = Body(...)):
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    body = payload if isinstance(payload, dict) else {}
    try:
        saved = _ua.set_price_target_armed(
            BASE_DIR,
            target_id=target_id,
            armed=bool(body.get("armed")),
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "ok", "price_targets": saved.get("price_targets") or []}


@app.delete("/api/price-targets/{target_id}")
def delete_price_target_route(request: Request, target_id: str):
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    try:
        saved = _ua.delete_price_target(BASE_DIR, target_id=target_id, session=session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "ok", "price_targets": saved.get("price_targets") or []}


@app.put("/api/alert-settings/telegram")
def put_alert_telegram_credentials(request: Request, payload: dict = Body(...)):
    """Save per-user bot token + chat id (encrypted at rest). Never echoes secrets."""
    from fastapi import HTTPException
    from server import telegram_notify
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    body = payload if isinstance(payload, dict) else {}
    token = str(body.get("bot_token") or body.get("telegram_bot_token") or "").strip()
    chat = str(body.get("chat_id") or body.get("telegram_chat_id") or "").strip()
    try:
        status = _ua.save_telegram_credentials(
            BASE_DIR, bot_token=token, chat_id=chat, session=session
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"could not store credentials: {e}") from e
    return {"status": "ok", "telegram": telegram_notify.telegram_status(user_status=status)}


@app.delete("/api/alert-settings/telegram")
def delete_alert_telegram_credentials(request: Request):
    from server import telegram_notify
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    status = _ua.clear_telegram_credentials(BASE_DIR, session=session)
    return {"status": "ok", "telegram": telegram_notify.telegram_status(user_status=status)}


@app.post("/api/alert-settings/telegram-test")
def post_telegram_test(request: Request):
    from server import telegram_notify
    from server import user_alerts_store as _ua

    session = _resolve_user_notes_session(request)
    result = telegram_notify.send_for_user(
        BASE_DIR,
        session,
        "CiM test alert — Telegram is connected.",
        allow_host_fallback=True,
    )
    if result.get("ok"):
        _ua.append_alert(
            BASE_DIR,
            {
                "source": "system",
                "kind": "telegram_test",
                "symbol": "SYSTEM",
                "title": "Telegram test sent",
                "body": "Check your Telegram for the test message.",
                "dedup_key": f"SYSTEM|telegram_test|{_ua.ist_today_key()}|{int(time_module.time())}",
                "delivered_browser_pending": False,
            },
            session=session,
        )
    return result


# ──────────────────────────────────────────────
# BACKGROUND JOB STATE
# ──────────────────────────────────────────────

job_state = {
    "running":  False,
    "job":      None,
    "progress": 0,
    "total":    0,
    "message":  "",
    "error":    None,
    "meta":     {},
}

_split_scan_lock = threading.Lock()
_split_scan_running = False

def set_job(name, message, *, quiet: bool = False):
    from server.admin_job_control import clear_cancel
    from server import admin_job_queue as ajq

    clear_cancel()
    job_state["running"]  = True
    job_state["job"]      = name
    job_state["progress"] = 0
    job_state["total"]    = 0
    job_state["message"]  = message
    job_state["error"]    = None
    job_state["meta"]     = {"quiet": quiet}
    ajq.note_job_started()


def _pump_job_queue() -> None:
    try:
        from server import admin_job_queue as ajq

        ajq.on_job_idle()
    except Exception:
        pass


def finish_job(message="Done", meta=None):
    job_state["running"]  = False
    job_state["message"]  = message
    job_state["progress"] = job_state["total"]
    merged = dict(job_state.get("meta") or {})
    if meta:
        merged.update(meta)
    job_state["meta"] = merged
    _pump_job_queue()


def fail_job(error):
    from server.admin_job_control import clear_cancel

    clear_cancel()
    err = str(error)
    job_state["running"] = False
    job_state["error"]   = err
    job_state["message"] = f"Failed: {err}"
    prev = dict(job_state.get("meta") or {})
    job_state["meta"] = {**prev, "error": err}
    _pump_job_queue()


def cancel_job(message: str = "Update cancelled.") -> None:
    from server.admin_job_control import clear_cancel

    clear_cancel()
    job_state["running"] = False
    job_state["error"] = None
    job_state["message"] = message
    prev = dict(job_state.get("meta") or {})
    job_state["meta"] = {**prev, "cancelled": True}
    _pump_job_queue()


def _start_or_queue_job(
    key: str,
    starter,
    *,
    label: str = "",
    source: str = "manual",
    coalesce_key: str | None = None,
) -> dict:
    """Start a heavy admin job now, or enqueue if the slot is busy."""
    from server import admin_job_queue as ajq

    return ajq.submit(
        key,
        starter,
        label=label or key,
        source=source,  # type: ignore[arg-type]
        coalesce_key=coalesce_key,
    )


def _bump_market_data_version(*, bars: int = 0) -> None:
    """Notify clients that persisted OHLCV/screener changed (intraday or EOD)."""
    try:
        from server import market_data_version as mdv

        mdv.record_data_refresh(DB_PATH, bars=int(bars or 0))
    except Exception:
        pass


def _sched_start_ohlcv() -> bool:
    result = _start_or_queue_job(
        "ohlcv",
        lambda: threading.Thread(target=run_fetch_ohlcv, daemon=True).start(),
        label="Fetch chart data (OHLCV)",
        source="scheduled",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_filter_rebuild_instance(preset: dict) -> bool:
    if not preset:
        return False
    from server import snapshot_rebuild_guard as srg

    keys = [str(k).strip().lower() for k in (preset.get("keys") or []) if str(k).strip()]
    mode = str(preset.get("mode") or "incremental").strip().lower()
    timeframes = _parse_snapshot_timeframes_csv(
        ",".join(str(t) for t in (preset.get("timeframes") or []))
    )
    try:
        days_back = max(0, min(30, int(preset.get("days_back") or 1)))
    except (TypeError, ValueError):
        days_back = 1
    needs_hold = mode == "full" and any(k in {"price_ohlc", "ema", "macd", "stochrsi"} for k in keys)
    entry_id = str(preset.get("schedule_id") or preset.get("id") or "").strip()
    coalesce = f"filterRebuild:{entry_id}" if entry_id else "filter_rebuild"

    def _worker() -> None:
        if needs_hold:
            srg.acquire_full_rebuild_hold(reason="scheduled_filter_schedule")
        try:
            run_filter_rebuild_job(
                keys=keys,
                mode=mode,
                timeframes=timeframes,
                days_back=days_back,
            )
        finally:
            if needs_hold:
                srg.release_full_rebuild_hold()

    result = _start_or_queue_job(
        "filter_rebuild",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="Filter rebuild",
        source="scheduled",
        coalesce_key=coalesce,
    )
    return result.get("status") in ("started", "queued")


def _sched_start_eod_reconcile() -> bool:
    def _worker() -> None:
        try:
            import eod_reconcile as _eod_reconcile

            set_job("eod_reconcile", "Reconciling screener from NSE bhavcopy...")
            n = _eod_reconcile.run_eod_bhavcopy_reconcile(
                DB_PATH,
                log_fn=lambda m: job_state.update({"message": m}),
            )
            if n:
                invalidate_chart_cache()
                invalidate_stock_df()
            finish_job(f"EOD reconcile complete: {n} screener symbol(s) updated.")
        except Exception as e:
            fail_job(str(e))

    result = _start_or_queue_job(
        "eod_reconcile",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="EOD bhavcopy reconcile",
        source="scheduled",
        coalesce_key="eodReconcile",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_live_quotes_warm() -> bool:
    def _worker() -> None:
        try:
            set_job("live_quotes_warm", "Refreshing live NSE quotes...", quiet=True)
            movers_live.warm_cache_on_startup()
            finish_job("Live quotes warm complete.", meta={"quiet": True})
        except Exception as e:
            fail_job(str(e))

    result = _start_or_queue_job(
        "live_quotes_warm",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="Live quotes warm",
        source="scheduled",
        coalesce_key="liveQuotesWarm",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_split_watch() -> bool:
    import split_utils as _split_utils_mod

    def _worker() -> None:
        _run_scan_then_auto_apply(
            _split_utils_mod.SPLIT_MAINTENANCE_DAYS,
            backfill=False,
            trigger="scheduled",
        )

    result = _start_or_queue_job(
        "split_adjustments",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="Split watch",
        source="scheduled",
        coalesce_key="splitWatch",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_earnings_plus_warm() -> bool:
    def _worker() -> None:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        run_refresh_earnings_plus_cache(
            now.year,
            now.month,
            force=False,
            only_incomplete=False,
            quiet=True,
            trigger="scheduled",
        )

    result = _start_or_queue_job(
        "earnings_plus_cache",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="Earnings+ warm",
        source="scheduled",
        coalesce_key="earningsPlusWarm",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_fetch_financials() -> bool:
    result = _start_or_queue_job(
        "financials",
        lambda: threading.Thread(target=run_fetch_financials, daemon=True).start(),
        label="Fetch financials",
        source="scheduled",
        coalesce_key="fetchFinancials",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_screener_sectors() -> bool:
    result = _start_or_queue_job(
        "screener_sectors",
        lambda: threading.Thread(target=run_screener_sector_fallback, daemon=True).start(),
        label="Screener sectors",
        source="scheduled",
        coalesce_key="fetchScreenerSectors",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_expand_universe() -> bool:
    result = _start_or_queue_job(
        "expand_universe",
        lambda: threading.Thread(target=run_expand_screener_universe, daemon=True).start(),
        label="Expand universe",
        source="scheduled",
        coalesce_key="expandUniverse",
    )
    return result.get("status") in ("started", "queued")


def run_fetch_mf_nav():
    """Download AMFI open-ended NAVs into mf_schemes / mf_nav_history.

    Never part of live/session OHLCV Update. Allowed only after 15:30 IST on weekdays.
    """
    try:
        from server import mf_nav as _mf_nav

        ok, reason = _mf_nav.mf_nav_refresh_allowed()
        if not ok:
            set_job("mf_nav", reason)
            fail_job(reason)
            return

        set_job("mf_nav", "Refreshing AMFI mutual fund NAVs...")

        def _log(msg: str) -> None:
            job_state.update({"message": str(msg)})

        stats = _mf_nav.run(DB_PATH, log_fn=_log)
        finish_job(
            f"MF NAV refresh complete: {stats.get('schemes', 0)} schemes "
            f"({stats.get('direct_growth', 0)} Direct–Growth).",
            meta=stats,
        )
    except Exception as e:
        fail_job(str(e))


def _sched_start_mf_nav() -> bool:
    from server import mf_nav as _mf_nav

    ok, reason = _mf_nav.mf_nav_refresh_allowed()
    if not ok:
        print(f"[mfNav] skip scheduled run: {reason}")
        return False
    result = _start_or_queue_job(
        "mf_nav",
        lambda: threading.Thread(target=run_fetch_mf_nav, daemon=True).start(),
        label="AMFI mutual fund NAVs",
        source="scheduled",
        coalesce_key="mfNav",
    )
    return result.get("status") in ("started", "queued")


def run_refresh_sector_index_cores():
    """Scheduled/manual: refresh Nifty index cores for Market Sector tags."""
    try:
        set_job("sector_index_cores", "Refreshing Market Sector index cores...")
        result = market_sectors.refresh_index_sector_cores(DATA_DIR, DB_PATH)
        counts = result.get("counts") or {}
        nonempty = sum(1 for n in counts.values() if int(n or 0) > 0)
        total_links = sum(int(n or 0) for n in counts.values())
        err_n = len(result.get("errors") or {})
        invalidate_stock_df()
        finish_job(
            f"Sector index cores refreshed: {nonempty} tags, {total_links} symbol links"
            + (f" ({err_n} tag errors)" if err_n else "")
            + ".",
            meta=result,
        )
    except Exception as e:
        fail_job(str(e))


def run_sync_exchange_classification_job():
    """Scheduled/manual: sync exchange industry labels onto screener."""
    try:
        set_job("exchange_classification", "Syncing exchange industry classification...")
        cfg = exchange_classification_sync.load_sync_config(DATA_DIR)
        urls = cfg.get("nse_csv_urls") or list(
            exchange_classification_sync.DEFAULT_NSE_INDUSTRY_CSV_URLS
        )
        ua = str(cfg.get("user_agent") or exchange_classification_sync.DEFAULT_USER_AGENT)
        bse_key = cfg.get("bse_local_path")
        bse_path = Path(bse_key) if bse_key else None
        if bse_path is not None and not bse_path.is_file():
            bse_path = DATA_DIR / bse_path if not bse_path.is_absolute() else bse_path
        skip_el = bool(cfg.get("skip_equity_l"))
        ne_url = cfg.get("nse_equity_l_url")

        def _log(msg: str) -> None:
            job_state.update({"message": str(msg)})

        _log("Downloading / merging exchange industry maps...")
        result = exchange_classification_sync.run_sync(
            DATA_DIR,
            DB_PATH,
            nse_urls=urls if isinstance(urls, list) else list(urls),
            bse_local_path=bse_path if bse_path and bse_path.is_file() else None,
            user_agent=ua,
            refresh_canonical=True,
            skip_equity_l=skip_el,
            nse_equity_l_url=str(ne_url).strip() if ne_url else None,
        )
        invalidate_stock_df()
        updated = result.get("rows_updated") or result.get("updated") or 0
        finish_job(
            f"Exchange classification sync complete (rows updated: {updated}).",
            meta=result if isinstance(result, dict) else {"result": result},
        )
    except Exception as e:
        fail_job(str(e))


def _sched_start_sector_index_cores() -> bool:
    result = _start_or_queue_job(
        "sector_index_cores",
        lambda: threading.Thread(target=run_refresh_sector_index_cores, daemon=True).start(),
        label="Sector index cores",
        source="scheduled",
        coalesce_key="sectorIndexCores",
    )
    return result.get("status") in ("started", "queued")


def _sched_start_exchange_classification() -> bool:
    result = _start_or_queue_job(
        "exchange_classification",
        lambda: threading.Thread(target=run_sync_exchange_classification_job, daemon=True).start(),
        label="Exchange classification",
        source="scheduled",
        coalesce_key="exchangeClassification",
    )
    return result.get("status") in ("started", "queued")


def _configure_admin_job_scheduler() -> None:
    import admin_job_scheduler as ajs
    from server import admin_job_queue as ajq
    from server import snapshot_rebuild_guard as srg

    ajq.configure(is_running_fn=lambda: bool(job_state.get("running")))
    ajs.configure(
        start_fns={
            "ohlcv": _sched_start_ohlcv,
            "eodReconcile": _sched_start_eod_reconcile,
            "liveQuotesWarm": _sched_start_live_quotes_warm,
            "splitWatch": _sched_start_split_watch,
            "earningsPlusWarm": _sched_start_earnings_plus_warm,
            "earningsTvResync": _sched_start_earnings_tv_resync,
            "fetchFinancials": _sched_start_fetch_financials,
            "fetchScreenerSectors": _sched_start_screener_sectors,
            "expandUniverse": _sched_start_expand_universe,
            "mfNav": _sched_start_mf_nav,
            "sectorIndexCores": _sched_start_sector_index_cores,
            "exchangeClassification": _sched_start_exchange_classification,
        },
        filter_instance_start_fn=_sched_start_filter_rebuild_instance,
        job_running_fn=lambda: bool(job_state.get("running")),
        scheduler_blocked_fn=srg.scheduler_is_frozen,
        install_root=BASE_DIR,
    )
    ajs.start()


def _nse_equity_market_cap_rupees(quote: dict) -> Optional[float]:
    """
    Full market capitalisation in INR from NSE /api/quote-equity JSON.

    NSE often omits metadata.totalMarketCap / marketCap; in that case use
    listed issued size × last traded price (same definition as total mcap
    at LTP, not free-float ffmc from index APIs).
    """
    if not isinstance(quote, dict):
        return None
    meta = quote.get("metadata") or {}
    for key in ("totalMarketCap", "marketCap"):
        raw = meta.get(key)
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue

    sec = quote.get("securityInfo") or {}
    pi = quote.get("priceInfo") or {}
    issued = sec.get("issuedSize")
    price = pi.get("lastPrice")
    if price is None:
        price = pi.get("close") or pi.get("finalPrice")
    if issued is None or price is None:
        return None
    try:
        return float(issued) * float(price)
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────
# PRICE FETCHER
# ──────────────────────────────────────────────

def run_fetch_prices():
    from server.admin_job_control import JobCancelled, is_cancel_requested, raise_if_cancelled
    from server.product_config import yahoo_primary_pipeline
    from server.universe_price_refresh import (
        recalculate_screener_change_from_bars,
        refresh_screener_from_upstox_quotes,
        refresh_universe_nse_prices,
        should_skip_live_nse_quote_refresh,
    )

    yahoo_primary = yahoo_primary_pipeline(BASE_DIR)

    try:
        set_job("prices", "Initialising price update...")

        def on_message(msg: str):
            job_state["message"] = msg

        def on_progress(done: int, total: int):
            job_state["progress"] = done
            job_state["total"] = total

        if yahoo_primary:
            on_message(
                "Market-data primary mode — syncing screener from latest bars "
                "(Upstox when configured; no NSE universe scrape)."
            )
            try:
                stats = refresh_screener_from_upstox_quotes(
                    DB_PATH,
                    message_callback=on_message,
                )
                if stats.get("skipped"):
                    stats = {
                        "skipped": True,
                        "reason": "yahoo_primary",
                        "source": "bars",
                        "upstox_quote": stats,
                    }
                else:
                    stats = {
                        **stats,
                        "reason": "yahoo_primary",
                        "skipped": False,
                    }
            except Exception as ue:
                on_message(f"Upstox screener quote warning: {ue}")
                stats = {"skipped": True, "reason": "yahoo_primary", "source": "upstox_or_yfinance"}
            raise_if_cancelled()
        else:
            skip_live_nse, skip_live_msg = should_skip_live_nse_quote_refresh()
            if skip_live_nse:
                on_message(skip_live_msg)
                stats = {"skipped": True, "reason": "post_close"}
            else:
                stats = refresh_universe_nse_prices(
                    DB_PATH,
                    message_callback=on_message,
                    progress_callback=on_progress,
                    cancel_check=is_cancel_requested,
                )
            raise_if_cancelled()

        invalidate_stock_df()
        invalidate_chart_cache()

        job_state["message"] = "Recalculating change % from historical data..."
        try:
            conn3 = _connect_sqlite(DB_PATH)
            try:
                if yahoo_primary:
                    import importlib.util

                    spec_sd = importlib.util.spec_from_file_location("scrape_daily", SCRAPE_DAILY_PATH)
                    mod_sd = importlib.util.module_from_spec(spec_sd)
                    spec_sd.loader.exec_module(mod_sd)
                    if hasattr(mod_sd, "sync_screener_prices_from_latest_bars"):
                        mod_sd.sync_screener_prices_from_latest_bars(conn3, log_fn=on_message)
                recalc = recalculate_screener_change_from_bars(conn3, include_monthly=True)
                if recalc.get("skipped"):
                    job_state["message"] = "Live session — kept NSE day % (skipped bar recalc)."
            finally:
                conn3.close()
        except Exception as ce:
            job_state["message"] = f"Change % recalc warning: {ce}"
            time_module.sleep(1)

        try:
            cached = market_cap_live.sync_market_cap_cache(DB_PATH)
            job_state["message"] = f"Cached market_cap for {cached} rows (shares × price)…"
        except Exception:
            pass

        job_state["message"] = "Updating index prices..."
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("scrape_indices", SCRAPE_INDICES_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            conn2 = _connect_sqlite(DB_PATH)
            try:
                module.setup_db(conn2)
                usd_inr = module.get_usd_inr()
                module.update_live_prices(usd_inr, conn2)
                module.sync_nse_index_history(conn2)
            finally:
                conn2.close()
        except Exception as ie:
            job_state["message"] = f"Index update warning: {ie}"
            time_module.sleep(1)

        job_state["message"] = "Updating non-chartable indices..."
        try:
            import importlib.util as ilu

            spec3 = ilu.spec_from_file_location("scrape_indices", SCRAPE_INDICES_PATH)
            mod3 = ilu.module_from_spec(spec3)
            spec3.loader.exec_module(mod3)
            conn4 = _connect_sqlite(DB_PATH)
            try:
                mod3.fetch_all_nse_indices(conn4)
            finally:
                conn4.close()
        except Exception as nie:
            job_state["message"] = f"Non-chartable indices warning: {nie}"
            time_module.sleep(1)

        try:
            import movers_live as _ml

            _ml.refresh_after_data_update_sync(include_quotes=True)
        except Exception:
            pass

        job_state["message"] = "Reconciling EOD bars from NSE bhavcopy..."
        try:
            import eod_reconcile as _eod_reconcile

            n_bhav = _eod_reconcile.run_eod_bhavcopy_reconcile(
                DB_PATH,
                log_fn=lambda m: job_state.update({"message": m}),
            )
            if n_bhav:
                invalidate_chart_cache()
                conn_bh = _connect_sqlite(DB_PATH)
                try:
                    recalculate_screener_change_from_bars(conn_bh, include_monthly=True, force=True)
                finally:
                    conn_bh.close()
        except Exception as be:
            job_state["message"] = f"NSE bhavcopy reconcile warning: {be}"
            time_module.sleep(1)

        failed = int(stats.get("failed") or 0)
        quote_updated = int(stats.get("quote_updated") or 0)
        total = int(stats.get("total") or 0)
        if stats.get("reason") == "yahoo_primary":
            finish_job(
                "Prices synced from OHLCV bars (Upstox only).",
                meta={"price_refresh": stats},
            )
        elif stats.get("skipped"):
            finish_job(
                "Price update skipped after market close (use Update price and volume or run during session).",
                meta={"price_refresh": stats},
            )
        elif failed > 0:
            finish_job(
                f"Prices updated: {quote_updated}/{total} symbols from NSE. Failed: {failed}.",
                meta={"price_refresh": stats},
            )
        else:
            finish_job(
                f"Prices updated: {quote_updated}/{total} symbols from NSE (full universe).",
                meta={"price_refresh": stats},
            )

    except JobCancelled:
        cancel_job("Price update cancelled.")
    except Exception as e:
        fail_job(str(e))


def run_fetch_financials():
    import importlib.util as ilu
    try:
        set_job("financials", "Initialising financials scraper...")

        spec   = ilu.spec_from_file_location(
            "scrape_financials",
            SCRAPE_FINANCIALS_PATH
        )
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)

        def on_progress(done, total):
            job_state["progress"] = done
            job_state["total"]    = total

        def on_message(msg):
            job_state["message"] = msg

        updated = module.run(
            progress_callback=on_progress,
            message_callback=on_message,
        )

        # Invalidate stock cache
        invalidate_stock_df()

        finish_job(f"Financials updated: {updated} stocks.")
    except Exception as e:
        fail_job(str(e))


@app.get("/api/admin/status")
def admin_status():
    sched = {}
    try:
        from server.product_config import is_showcase_host

        if is_showcase_host(BASE_DIR):
            import admin_job_scheduler as ajs

            st = ajs.get_status()
            sched = {
                "waitingTask": st.get("waitingTask"),
                "waitingReason": st.get("waitingReason"),
            }
    except Exception:
        pass
    from server.admin_job_control import is_cancel_requested
    from server import admin_job_queue as ajq

    return {
        "running":  job_state["running"],
        "job":      job_state["job"],
        "progress": job_state["progress"],
        "total":    job_state["total"],
        "message":  job_state["message"],
        "error":    job_state["error"],
        "meta":     job_state.get("meta") or {},
        "cancel_requested": is_cancel_requested(),
        "percent":  round(job_state["progress"] / job_state["total"] * 100, 1)
                    if job_state["total"] > 0 else 0,
        "queued": ajq.snapshot(),
        **sched,
    }


@app.post("/api/admin/cancel-job")
def admin_cancel_job():
    from server.admin_job_control import is_cancel_requested, request_cancel

    if not job_state.get("running"):
        return {"status": "idle", "cancel_requested": False, "message": "No job is running."}
    if is_cancel_requested():
        return {
            "status": "cancelling",
            "cancel_requested": True,
            "job": job_state.get("job"),
            "message": job_state.get("message") or "Cancellation already requested.",
        }
    request_cancel()
    job_state["message"] = "Cancellation requested — stopping at next safe point…"
    return {
        "status": "cancelling",
        "cancel_requested": True,
        "job": job_state.get("job"),
        "message": job_state["message"],
    }


@app.post("/api/admin/job-queue/cancel")
def admin_job_queue_cancel(body: dict = Body(default_factory=dict)):
    """Drop one queued job by id, or clear the whole backlog. Does not stop the running job."""
    from server import admin_job_queue as ajq

    body = body or {}
    if body.get("clear"):
        n = ajq.clear_queue()
        return {"status": "cleared", "removed": n, "queued": ajq.snapshot()}
    entry_id = str(body.get("id") or "").strip()
    if not entry_id:
        raise HTTPException(status_code=400, detail="Provide id or clear=true.")
    ok = ajq.cancel_queued(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Queued job not found.")
    return {"status": "removed", "id": entry_id, "queued": ajq.snapshot()}


def _require_showcase_host_install():
    from server.product_config import is_showcase_host

    if not is_showcase_host(BASE_DIR):
        raise HTTPException(
            status_code=404,
            detail="Admin scheduler is only available on the showcase host install.",
        )


def _admin_schedules_status():
    import admin_job_scheduler as ajs

    status = ajs.get_status()
    if job_state.get("running"):
        status["activeTask"] = job_state.get("job")
    return status


@app.get("/api/admin/schedules")
def get_admin_schedules():
    return _admin_schedules_status()


@app.get("/api/admin/live-watchdog-status")
def get_live_watchdog_status():
    """Host-only: read live-watchdog-status.json written by Start-CiMLiveWatchdogLoop.ps1."""
    _require_showcase_host_install()
    status_path = BASE_DIR / "runtime" / "logs" / "live-watchdog-status.json"
    if not status_path.is_file():
        # No active watchdog on this install — not an error (live Funnel may run on another root).
        return {
            "available": False,
            "overallOk": None,
            "stale": True,
            "message": None,
        }
    try:
        raw = json.loads(status_path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raw = {}
    except Exception as exc:
        return {
            "available": False,
            "overallOk": None,
            "stale": True,
            "message": f"Could not read watchdog status: {exc}",
        }

    interval_min = raw.get("intervalMinutes")
    try:
        interval_min = int(interval_min) if interval_min is not None else 5
    except (TypeError, ValueError):
        interval_min = 5
    # Treat status as stale when the loop has not checked for ~3 intervals (min 20m).
    stale_after = timedelta(minutes=max(20, interval_min * 3))
    last_check_raw = raw.get("lastCheckAt")
    stale = False
    if last_check_raw:
        try:
            last_check = datetime.fromisoformat(str(last_check_raw).replace("Z", "+00:00"))
            now = datetime.now(last_check.tzinfo) if last_check.tzinfo else datetime.now()
            stale = (now - last_check) > stale_after
        except (TypeError, ValueError):
            stale = True
    else:
        stale = True

    overall_ok = raw.get("overallOk")
    if stale:
        # Frozen failure from a dead/stopped loop must not red-banner the scheduler.
        overall_ok = None

    return {
        "available": True,
        "overallOk": overall_ok,
        "stale": stale,
        "lastCheckAt": raw.get("lastCheckAt"),
        "webLocalOk": raw.get("webLocalOk"),
        "webPublicOk": raw.get("webPublicOk"),
        "mobileLocalOk": raw.get("mobileLocalOk"),
        "mobilePublicOk": raw.get("mobilePublicOk"),
        "consecutiveFailures": raw.get("consecutiveFailures"),
        "lastHealAction": raw.get("lastHealAction"),
        "lastError": raw.get("lastError"),
        "publicWebUrl": raw.get("publicWebUrl"),
        "publicMobileUrl": raw.get("publicMobileUrl"),
        "logPath": str(status_path.parent / "live-watchdog.log"),
    }


@app.put("/api/admin/schedules")
def put_admin_schedules(payload: dict = Body(...)):
    import admin_job_scheduler as ajs

    ajs.save_config(payload or {})
    return _admin_schedules_status()


@app.post("/api/admin/schedules/run-now")
def post_admin_schedules_run_now(payload: dict = Body(...)):
    import admin_job_scheduler as ajs

    task = str((payload or {}).get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="task is required")
    result = ajs.run_task_now(task)
    if not result.get("ok"):
        detail = result.get("error") or "Failed to start task"
        if "already running" in str(detail).lower():
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
    return {**result, "status": _admin_schedules_status()}


@app.get("/api/admin/showcase-schedules")
def get_showcase_admin_schedules():
    return _admin_schedules_status()


@app.put("/api/admin/showcase-schedules")
def put_showcase_admin_schedules(payload: dict = Body(...)):
    import admin_job_scheduler as ajs

    # Accept legacy indicatorIncremental key from older UI payloads
    body = dict(payload or {})
    if "indicatorIncremental" in body and "filterSchedules" not in body:
        body.setdefault("filterSchedules", [])
        if not any(isinstance(s, dict) and s.get("id") == "indicatorIncremental" for s in body["filterSchedules"]):
            body["filterSchedules"].append(body.pop("indicatorIncremental"))
    ajs.save_config(body)
    return _admin_schedules_status()


@app.get("/api/admin/cache-settings")
def get_cache_settings():
    return {
        "aggressiveCacheRam": AGGRESSIVE_CACHE_RAM,
        "chartCacheTtlSec": CHART_CACHE_TTL,
        "chartCacheMaxEntries": CHART_CACHE_MAX_ENTRIES,
        "filterCacheTtlSec": FILTER_CACHE_TTL,
        "filterCacheMaxEntries": FILTER_CACHE_MAX_ENTRIES,
        "chartCacheEntries": _app_caches.chart_entries,
        "filterCacheEntries": _app_caches.filter_entries,
    }


@app.post("/api/admin/cache-settings")
def set_cache_settings(payload: dict = Body(...)):
    enabled = bool(payload.get("aggressiveCacheRam", False))
    set_cache_mode(enabled)
    try:
        _save_layout_merge({"aggressiveCacheRam": AGGRESSIVE_CACHE_RAM})
    except Exception:
        # Non-fatal: runtime mode is already applied.
        pass
    return {
        "status": "saved",
        "aggressiveCacheRam": AGGRESSIVE_CACHE_RAM,
        "chartCacheTtlSec": CHART_CACHE_TTL,
        "chartCacheMaxEntries": CHART_CACHE_MAX_ENTRIES,
        "filterCacheTtlSec": FILTER_CACHE_TTL,
        "filterCacheMaxEntries": FILTER_CACHE_MAX_ENTRIES,
    }


@app.post("/api/admin/cache-clear")
def clear_cache():
    invalidate_chart_cache()
    return {
        "status": "cleared",
        "chartCacheEntries": _app_caches.chart_entries,
        "filterCacheEntries": _app_caches.filter_entries,
    }


@app.post("/api/admin/stop-app")
def stop_app():
    """
    Phase 1: stop backend service only.
    Use a short delayed shutdown so the HTTP response reaches the client first.
    """
    def _shutdown():
        time_module.sleep(0.35)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return {"status": "stopping", "scope": "backend"}


@app.post("/api/admin/stop-all")
def stop_all():
    """
    Full multi-process stop parity (Phase 2 equivalent to stop_cim.bat).
    Runs the stop script asynchronously after returning an HTTP response.
    """
    stop_script = BASE_DIR / "stop_cim.bat"

    def _stop_all_async():
        time_module.sleep(0.35)
        if stop_script.exists():
            try:
                subprocess.Popen(
                    ["cmd.exe", "/c", str(stop_script)],
                    cwd=str(BASE_DIR),
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
            except Exception:
                pass
        # Fallback: ensure this backend process exits even if script launch failed.
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    threading.Thread(target=_stop_all_async, daemon=True).start()
    return {"status": "stopping", "scope": "all"}


@app.post("/api/feedback")
def submit_feedback(payload: dict = Body(...)):
    fb_type = str(payload.get("type", "")).strip().lower()
    subject = str(payload.get("subject", "")).strip()
    message = str(payload.get("message", "")).strip()
    contact_email = str(payload.get("contact_email", "")).strip()
    app_context = payload.get("app_context") or {}

    if fb_type not in {"issue", "feature"}:
        raise HTTPException(status_code=400, detail="type must be 'issue' or 'feature'")
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    if len(message) < 10:
        raise HTTPException(status_code=400, detail="Message should be at least 10 characters")

    if not FEEDBACK_SMTP_HOST:
        feedback_path = DATA_DIR / "feedback.json"
        feedback_path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if feedback_path.exists():
            try:
                with open(feedback_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.append(
            {
                "type": fb_type,
                "subject": subject,
                "message": message,
                "contact_email": contact_email,
                "app_context": app_context,
                "saved_at": datetime.utcnow().isoformat() + "Z",
            }
        )
        with open(feedback_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        return {"status": "saved_local", "path": str(feedback_path)}

    email_msg = EmailMessage()
    email_msg["Subject"] = f"[Charts In Motion] {fb_type.title()} - {subject}"
    email_msg["From"] = FEEDBACK_FROM_EMAIL
    email_msg["To"] = FEEDBACK_TO_EMAIL
    body_lines = [
        f"Type: {fb_type}",
        f"Subject: {subject}",
        f"Contact: {contact_email or 'Not provided'}",
        "",
        "Message:",
        message,
        "",
        "Context:",
        json.dumps(app_context, indent=2, ensure_ascii=False),
    ]
    email_msg.set_content("\n".join(body_lines))

    try:
        with smtplib.SMTP(FEEDBACK_SMTP_HOST, FEEDBACK_SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if FEEDBACK_SMTP_USER:
                smtp.login(FEEDBACK_SMTP_USER, FEEDBACK_SMTP_PASS)
            smtp.send_message(email_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send feedback: {e}")

    return {"status": "sent"}

def run_fetch_ohlcv():
    import importlib.util, sys
    from server.admin_job_control import JobCancelled, is_cancel_requested, raise_if_cancelled
    from server.product_config import yahoo_primary_pipeline

    yahoo_primary = yahoo_primary_pipeline(BASE_DIR)
    yahoo_phase_done = False
    stocks_updated = 0
    bhav_screener_written = 0
    price_stats: dict = {}
    index_ohlcv_error = None
    total_idx = None
    bars_4h_stats: dict = {}
    bars_4h_deferred = False
    bars_30m_stats: dict = {}
    bars_30m_deferred = False

    try:
        set_job("ohlcv", "Loading daily OHLCV updater...")
        # Preflight dependency check so users get a clear actionable message.
        try:
            import yfinance  # noqa: F401
        except Exception:
            py_exe = sys.executable
            raise RuntimeError(
                "Missing dependency: yfinance. "
                f"Install into this Python runtime ({py_exe}) using "
                "\"python -m pip install yfinance\" or restart via start_cim.bat "
                "to auto-repair runtime packages."
            )
        spec   = importlib.util.spec_from_file_location(
            "scrape_daily",
            SCRAPE_DAILY_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def on_progress(done, total):
            job_state["progress"] = done
            job_state["total"]    = total

        def _set_sources(phase: str, patch: dict) -> None:
            meta = dict(job_state.get("meta") or {})
            sources = dict(meta.get("sources") or {})
            cur = dict(sources.get(phase) or {})
            for k, v in (patch or {}).items():
                cur[k] = v
            sources[phase] = cur
            meta["sources"] = sources
            job_state["meta"] = meta

        def on_message(msg):
            job_state["message"] = msg
            text = str(msg or "")
            # Prefer Upstox-only totals; keep legacy Yahoo= parser for old log lines.
            m = re.search(
                r"totals Upstox=(\d+)(?:\s+none=(\d+))?(?:\s+Yahoo=(\d+))?(?:\s+NSE=(\d+))?\s+failed=(\d+)",
                text,
            )
            if m:
                phase = "bars_4h" if ("4H bars:" in text or "Source batch:" in text) else "daily"
                patch = {
                    "upstox": int(m.group(1)),
                    "none": int(m.group(2) or 0),
                    "failed": int(m.group(5)),
                }
                sc = re.search(r"skipped_current=(\d+)", text)
                if sc:
                    patch["skipped_current"] = int(sc.group(1))
                _set_sources(phase, patch)

        run_result = _call_scrape_daily_run(
            module,
            progress_callback=on_progress,
            message_callback=on_message,
            cancel_check=is_cancel_requested,
        )
        yahoo_phase_done = True
        updated = int(run_result.get("updated") or 0)
        stocks_updated = updated
        bhav_screener_written = int(run_result.get("bhav_screener_written") or 0)
        daily_fetch = run_result.get("fetch_stats") or {}
        _set_sources(
            "daily",
            {
                "upstox": int(daily_fetch.get("upstox") or 0),
                "failed": int(daily_fetch.get("failed") or 0),
                "skipped_current": int(run_result.get("skipped_current") or 0),
            },
        )
        raise_if_cancelled()

        # ── Update index OHLCV candles ────────────────────────────────────────
        total_idx = None
        index_ohlcv_error = None
        job_state["message"] = "Updating index chart data..."
        try:
            import importlib.util as ilu
            spec2   = ilu.spec_from_file_location(
                "scrape_indices",
                SCRAPE_INDICES_PATH
            )
            mod2 = ilu.module_from_spec(spec2)
            spec2.loader.exec_module(mod2)
            conn3   = _connect_sqlite(DB_PATH)
            mod2.setup_db(conn3)
            usd_inr = mod2.get_usd_inr()
            total_idx = 0
            for symbol, name, category in mod2.INDICES:
                raise_if_cancelled()
                total_idx += mod2.scrape_history(symbol, name, category, usd_inr, conn3)
            nse_synced = mod2.sync_nse_index_history(conn3)
            if nse_synced:
                total_idx += nse_synced
                on_message(f"NSE-only index history: {nse_synced} bar(s) extended.")
            conn3.close()
            on_message(f"Index OHLCV: {total_idx} new candles added.")
        except Exception as ie:
            index_ohlcv_error = str(ie)
            on_message(f"Index OHLCV warning: {ie}")
            time_module.sleep(1)

        # ── Build 4H session bars (stocks + indices) ───────────────────────────
        # During live session: skip full-universe 4H DB rebuild (live 4H uses quote overlay).
        # After 15:30 IST on a session day (or non-session): build as usual. Upstox is primary 5m source.
        try:
            from server.bars_4h import should_defer_bars_4h_build

            defer_4h, defer_reason = should_defer_bars_4h_build(BASE_DIR)
        except Exception:
            defer_4h, defer_reason = False, "4H defer check failed — building"

        if defer_4h:
            bars_4h_deferred = True
            bars_30m_deferred = True
            bars_4h_stats = {"deferred": True, "reason": defer_reason}
            bars_30m_stats = {"deferred": True, "reason": defer_reason}
            on_message(defer_reason)
            on_message("30m DB rebuild skipped (live session) — full build after 15:30 IST")
            job_state["message"] = "4H/30m DB rebuild skipped (live session)"
            # Limited catch-up so symbols with no/shallow 4H get a base for live overlay.
            try:
                import importlib.util as ilu4

                from server.bars_4h import pick_live_session_4h_catchup

                spec4 = ilu4.spec_from_file_location("scrape_4h", SCRAPE_4H_PATH)
                mod4 = ilu4.module_from_spec(spec4)
                spec4.loader.exec_module(mod4)
                conn_cu = get_db_connection()
                try:
                    universe = mod4.get_all_screener_symbols(conn_cu)
                    catchup = pick_live_session_4h_catchup(conn_cu, universe)
                finally:
                    conn_cu.close()
                if catchup:
                    job_state["message"] = (
                        f"4H limited catch-up ({len(catchup)} symbols missing history)..."
                    )
                    on_message(
                        f"live session — limited 4H catch-up for {len(catchup)} symbols "
                        f"(full rebuild after 15:30 IST)"
                    )

                    def on_4h_cu_progress(done, total):
                        job_state["progress"] = done
                        job_state["total"] = total

                    cu_stats = mod4.run(
                        symbols=catchup,
                        backfill=True,
                        progress_callback=on_4h_cu_progress,
                        message_callback=on_message,
                        cancel_check=is_cancel_requested,
                        also_30m=False,
                    )
                    bars_4h_stats["live_catchup"] = {
                        "symbols": len(catchup),
                        **(cu_stats or {}),
                    }
                    try:
                        src = (cu_stats or {}).get("sources") or {}
                        _set_sources(
                            "bars_4h",
                            {
                                "upstox": int(src.get("upstox") or 0),
                                "yahoo": int(src.get("yahoo") or 0),
                                "nse": int(src.get("nse") or 0),
                                "failed": int(src.get("failed") or 0),
                                "skipped_current": 0,
                            },
                        )
                    except Exception:
                        pass
                    on_message(
                        f"4H catch-up: updated={cu_stats.get('updated', 0)}, "
                        f"skipped={cu_stats.get('skipped', 0)}"
                    )
                else:
                    on_message("live session — no 4H history catch-up needed")
                    bars_4h_stats["live_catchup"] = {"symbols": 0, "skipped": True}
            except Exception as e_cu:
                on_message(f"4H live catch-up warning: {e_cu}")
                bars_4h_stats["live_catchup_error"] = str(e_cu)
        else:
            job_state["message"] = "Building 4H (+30m) session bars (Upstox only)..."
            on_message(defer_reason)
            try:
                import importlib.util as ilu4

                spec4 = ilu4.spec_from_file_location("scrape_4h", SCRAPE_4H_PATH)
                mod4 = ilu4.module_from_spec(spec4)
                spec4.loader.exec_module(mod4)

                def on_4h_progress(done, total):
                    job_state["progress"] = done
                    job_state["total"] = total

                stock_4h = mod4.run(
                    backfill=False,
                    progress_callback=on_4h_progress,
                    message_callback=on_message,
                    cancel_check=is_cancel_requested,
                    also_30m=True,
                )
                raise_if_cancelled()

                index_syms = []
                try:
                    spec_idx = ilu4.spec_from_file_location("scrape_indices", SCRAPE_INDICES_PATH)
                    mod_idx = ilu4.module_from_spec(spec_idx)
                    spec_idx.loader.exec_module(mod_idx)
                    index_syms = [s for s, _, _ in mod_idx.INDICES]
                except Exception:
                    index_syms = []

                index_4h = {"updated": 0, "failed": 0, "skipped": 0}
                if index_syms:
                    job_state["message"] = "Building 4H (+30m) session bars for indices..."
                    index_4h = mod4.run(
                        symbols=index_syms,
                        backfill=False,
                        progress_callback=on_4h_progress,
                        message_callback=on_message,
                        cancel_check=is_cancel_requested,
                        also_30m=True,
                    )
                bars_4h_stats = {
                    "stocks": stock_4h,
                    "indices": index_4h,
                    "deferred": False,
                }
                try:
                    src_merge = {"upstox": 0, "none": 0, "failed": 0}
                    for part in (stock_4h, index_4h):
                        for k, v in ((part or {}).get("sources") or {}).items():
                            if k in src_merge:
                                src_merge[k] = int(src_merge.get(k) or 0) + int(v or 0)
                    skipped_4h = int((stock_4h or {}).get("skipped_current") or 0) + int(
                        (index_4h or {}).get("skipped_current") or 0
                    )
                    _set_sources(
                        "bars_4h",
                        {
                            "upstox": src_merge.get("upstox", 0),
                            "none": src_merge.get("none", 0),
                            "failed": src_merge.get("failed", 0),
                            "skipped_current": skipped_4h,
                        },
                    )
                except Exception:
                    pass
                on_message(
                    f"4H bars: stocks updated={stock_4h.get('updated', 0)}, "
                    f"indices updated={index_4h.get('updated', 0)}"
                    + (
                        f", skipped_current={int((stock_4h or {}).get('skipped_current') or 0)}"
                        if (stock_4h or {}).get("skipped_current")
                        else ""
                    )
                    + " (30m co-written from same 5m fetch when 4H refreshed)"
                )
                raise_if_cancelled()
                job_state["message"] = "Scanning 4H bar integrity…"
                try:
                    from server.bars_4h_integrity import audit_and_repair_after_4h_build

                    conn_4h_int = get_db_connection()
                    try:
                        integrity = audit_and_repair_after_4h_build(
                            conn_4h_int,
                            BASE_DIR,
                            auto_repair=True,
                            log_fn=on_message,
                            cancel_check=is_cancel_requested,
                        )
                        bars_4h_stats["integrity"] = integrity
                        qn = int(integrity.get("pending_repair_count") or integrity.get("quarantined_count") or 0)
                        if qn:
                            on_message(
                                f"4H integrity: {integrity.get('symbol_count', 0)} flagged, "
                                f"{qn} on host repair queue (charts still served)"
                            )
                    finally:
                        conn_4h_int.close()
                except Exception as ie4h:
                    on_message(f"4H integrity warning: {ie4h}")

                # Gap-fill 30m for symbols where 4H was already current (no co-write).
                raise_if_cancelled()
                job_state["message"] = "Refreshing 30m filter bars (gap fill)..."
                try:
                    spec30 = ilu4.spec_from_file_location("scrape_30m", SCRAPE_30M_PATH)
                    mod30 = ilu4.module_from_spec(spec30)
                    spec30.loader.exec_module(mod30)

                    def on_30m_progress(done, total):
                        job_state["progress"] = done
                        job_state["total"] = total

                    stock_30m = mod30.run(
                        backfill=False,
                        progress_callback=on_30m_progress,
                        message_callback=on_message,
                        cancel_check=is_cancel_requested,
                    )
                    index_30m = {"updated": 0, "failed": 0, "skipped": 0}
                    if index_syms:
                        index_30m = mod30.run(
                            symbols=index_syms,
                            backfill=False,
                            progress_callback=on_30m_progress,
                            message_callback=on_message,
                            cancel_check=is_cancel_requested,
                        )
                    bars_30m_stats = {
                        "stocks": stock_30m,
                        "indices": index_30m,
                        "deferred": False,
                        "co_written_with_4h": True,
                    }
                    on_message(
                        f"30m bars: stocks updated={stock_30m.get('updated', 0)}, "
                        f"indices updated={index_30m.get('updated', 0)}"
                        + (
                            f", skipped_current={int((stock_30m or {}).get('skipped_current') or 0)}"
                            if (stock_30m or {}).get("skipped_current")
                            else ""
                        )
                    )
                except Exception as e30:
                    on_message(f"30m session bars warning: {e30}")
                    bars_30m_stats = {"error": str(e30)}
            except Exception as e4:
                on_message(f"4H session bars warning: {e4}")
                time_module.sleep(1)

        # Invalidate chart cache so new candles are served
        invalidate_chart_cache()

        from server.universe_price_refresh import (
            recalculate_screener_change_from_bars,
            refresh_screener_from_upstox_quotes,
            refresh_universe_nse_prices,
            should_skip_live_nse_quote_refresh,
        )

        price_stats = {}
        if yahoo_primary:
            on_message(
                "Market-data primary mode — charts and screener from OHLCV bars "
                "(Upstox only); live movers use Upstox polling."
            )
            try:
                ux_stats = refresh_screener_from_upstox_quotes(
                    DB_PATH,
                    message_callback=on_message,
                )
            except Exception as ue:
                ux_stats = {"skipped": True, "error": str(ue)}
                on_message(f"Upstox screener quote warning: {ue}")
            price_stats = {
                "skipped": bool(ux_stats.get("skipped")),
                "reason": "yahoo_primary",
                "source": ux_stats.get("source") or "upstox_or_yfinance",
                "bhav_screener_written": bhav_screener_written,
                "upstox_quote": ux_stats,
                "quote_updated": int(ux_stats.get("quote_updated") or 0),
                "total": int(ux_stats.get("total") or 0),
                "failed": int(ux_stats.get("failed") or 0),
            }
        else:
            skip_live_nse, skip_live_msg = should_skip_live_nse_quote_refresh(
                bhav_screener_written=bhav_screener_written,
            )
            if skip_live_nse:
                on_message(skip_live_msg)
                price_stats = {
                    "skipped": True,
                    "reason": "post_close",
                    "bhav_screener_written": bhav_screener_written,
                }
            else:
                job_state["message"] = "Refreshing full-universe NSE live quotes..."
                try:
                    price_stats = refresh_universe_nse_prices(
                        DB_PATH,
                        message_callback=on_message,
                        progress_callback=on_progress,
                        cancel_check=is_cancel_requested,
                    )
                except JobCancelled:
                    raise
                except Exception as pe:
                    on_message(f"Universe price refresh warning: {pe}")

        job_state["message"] = "Syncing screener prices from latest bars..."
        try:
            if hasattr(module, "sync_screener_prices_from_latest_bars"):
                from server import movers_data as _md

                conn_sync = _connect_sqlite(DB_PATH)
                try:
                    if yahoo_primary or not _md._session_day_intraday_active():
                        module.sync_screener_prices_from_latest_bars(conn_sync, log_fn=on_message)
                    else:
                        on_message("Live session — skipped bar-based screener price sync.")
                finally:
                    conn_sync.close()
        except Exception as se:
            on_message(f"Screener sync warning: {se}")

        try:
            if yahoo_primary:
                on_message("Warming movers live cache (Upstox only)...")
                movers_live.refresh_after_data_update_sync(include_quotes=True)
            elif price_stats.get("skipped"):
                on_message("Post-close — skipped movers NSE cache warm.")
            else:
                movers_live.refresh_after_data_update_sync(include_quotes=True)
        except Exception as me:
            on_message(f"Movers live cache warning: {me}")

        job_state["message"] = "Recalculating stock change %..."
        try:
            conn6 = _connect_sqlite(DB_PATH)
            try:
                recalculate_screener_change_from_bars(conn6, include_monthly=True)
            finally:
                conn6.close()
        except Exception:
            pass

        # Recalculate index change % from fresh index history
        job_state["message"] = "Recalculating index change %..."
        try:
            conn7   = _connect_sqlite(DB_PATH)
            cursor7 = conn7.cursor()
            cursor7.execute("SELECT symbol FROM indices WHERE category IN ('equity', 'commodity')")
            idx_syms = [r[0] for r in cursor7.fetchall()]
            for sym in idx_syms:
                raise_if_cancelled()
                try:
                    cursor7.execute("SELECT Close FROM index_history WHERE Symbol=? ORDER BY Date DESC LIMIT 1", (sym,))
                    row = cursor7.fetchone()
                    if not row: continue
                    last = row[0]
                    cursor7.execute("SELECT Close FROM index_history WHERE Symbol=? ORDER BY Date DESC LIMIT 1 OFFSET 1", (sym,))
                    row_prev = cursor7.fetchone()
                    cursor7.execute("SELECT Close FROM index_history WHERE Symbol=? AND SUBSTR(Date,1,7) < SUBSTR((SELECT MAX(Date) FROM index_history WHERE Symbol=?),1,7) ORDER BY Date DESC LIMIT 1", (sym, sym))
                    row_1m = cursor7.fetchone()
                    cursor7.execute("SELECT Close FROM index_history WHERE Symbol=? AND SUBSTR(Date,1,4) < SUBSTR((SELECT MAX(Date) FROM index_history WHERE Symbol=?),1,4) ORDER BY Date DESC LIMIT 1", (sym, sym))
                    row_1y = cursor7.fetchone()
                    chg_pct = round((last - row_prev[0]) / row_prev[0] * 100, 2) if row_prev else None
                    chg_1m  = round((last - row_1m[0])  / row_1m[0]  * 100, 2) if row_1m  else None
                    chg_1y  = round((last - row_1y[0])  / row_1y[0]  * 100, 2) if row_1y  else None
                    fields, vals = [], []
                    if chg_pct is not None: fields.append("change_pct = ?"); vals.append(chg_pct)
                    if chg_1m  is not None: fields.append("change_30d = ?"); vals.append(chg_1m)
                    if chg_1y  is not None: fields.append("change_1y = ?");  vals.append(chg_1y)
                    if fields:
                        vals.append(sym)
                        cursor7.execute(f"UPDATE indices SET {', '.join(fields)} WHERE symbol=?", vals)
                except Exception:
                    continue
            conn7.commit()
            conn7.close()
        except Exception:
            pass

        # Invalidate stock df cache so dashboard reloads fresh data
        invalidate_stock_df()

        # Also run price fetch to update non-chartable indices and live prices
        job_state["message"] = "Updating live prices and non-chartable indices..."
        try:
            import importlib.util as ilu2
            spec_idx = ilu2.spec_from_file_location(
                "scrape_indices",
                SCRAPE_INDICES_PATH
            )
            mod_idx = ilu2.module_from_spec(spec_idx)
            spec_idx.loader.exec_module(mod_idx)
            conn9 = _connect_sqlite(DB_PATH)
            mod_idx.setup_db(conn9)
            usd_inr = mod_idx.get_usd_inr()
            mod_idx.update_live_prices(usd_inr, conn9)
            mod_idx.fetch_all_nse_indices(conn9)
            mod_idx.sync_nse_index_history(conn9)
            mod_idx.recalculate_index_changes(conn9)
            conn9.close()
        except Exception as pie:
            job_state["message"] = f"Price update warning: {pie}"
            time_module.sleep(1)

        stocks_n = int(updated or 0)
        if index_ohlcv_error:
            idx_part = f"index OHLCV failed ({index_ohlcv_error})"
        elif total_idx is None:
            idx_part = "index OHLCV not run"
        else:
            idx_part = f"{total_idx} index candles added"

        quote_n = int(price_stats.get("quote_updated") or 0)
        quote_total = int(price_stats.get("total") or 0)
        quote_failed = int(price_stats.get("failed") or 0)
        if price_stats.get("reason") == "yahoo_primary":
            price_part = "OHLCV bars synced to screener; live movers via Upstox"
        elif price_stats.get("skipped"):
            price_part = "NSE live quotes skipped (post-close; bhavcopy/EOD bars used)"
        elif quote_total:
            price_part = f"NSE quotes: {quote_n}/{quote_total}"
            if quote_failed:
                price_part += f" ({quote_failed} failed)"
        else:
            price_part = "NSE quotes not refreshed"

        summary = (
            f"Chart data updated. {stocks_n} stock symbols, {idx_part}. "
            f"{price_part}. Change % recalculated."
        )
        try:
            src = ((job_state.get("meta") or {}).get("sources") or {})
            daily_src = src.get("daily") or {}
            if daily_src:
                summary += (
                    f" Daily: Upstox={int(daily_src.get('upstox') or 0)} "
                    f"failed={int(daily_src.get('failed') or 0)}"
                    f" (skipped_current={int(daily_src.get('skipped_current') or 0)})."
                )
            b4 = src.get("bars_4h") or {}
            if b4 and not bars_4h_deferred:
                summary += (
                    f" 4H: Upstox={int(b4.get('upstox') or 0)} "
                    f"miss={int(b4.get('none') or 0)} failed={int(b4.get('failed') or 0)}"
                    f" (skipped_current={int(b4.get('skipped_current') or 0)})."
                )
        except Exception:
            pass
        if bars_4h_deferred:
            cu = (bars_4h_stats or {}).get("live_catchup") or {}
            cu_n = int(cu.get("symbols") or 0)
            if cu_n:
                summary += (
                    f" 4H DB rebuild skipped (live session); catch-up for {cu_n} symbols. "
                    "Live 4H from quotes; full 4H/30m build after 15:30 IST on Update."
                )
            else:
                summary += (
                    " 4H/30m DB rebuild skipped (live session) — live 4H from quotes; "
                    "full 4H/30m build after 15:30 IST on Update."
                )
        elif bars_4h_stats and not bars_4h_stats.get("deferred"):
            st = (bars_4h_stats.get("stocks") or {})
            if st.get("skipped_current") and int(st.get("updated") or 0) == 0 and int(st.get("processed") or 0) == 0:
                summary += " 4H already current — skipped."
            else:
                summary += (
                    f" 4H bars: stocks updated={int(st.get('updated') or 0)}."
                )
            st30 = ((bars_30m_stats or {}).get("stocks") or {})
            if st30:
                if st30.get("skipped_current") and int(st30.get("updated") or 0) == 0 and int(st30.get("processed") or 0) == 0:
                    summary += " 30m already current — skipped."
                else:
                    summary += f" 30m bars: stocks updated={int(st30.get('updated') or 0)}."
        if total_idx == 0 and not index_ohlcv_error:
            summary += (
                " No new index bars were written — Indices charts may still "
                "show the last stored session."
            )

        # Split/dividend maintenance — part of every chart data update (no separate step).
        split_maint: dict = {}
        try:
            job_state["message"] = "Checking stock splits (90 days) and applying adjustments…"
            on_message("Split maintenance: scanning history + universe…")
            split_maint = run_split_maintenance_for_update(
                quiet=False,
                cancel_check=is_cancel_requested,
                on_message=on_message,
            )
            pn = int(split_maint.get("pending_count") or 0)
            fn = int(split_maint.get("failed_count") or 0)
            if pn or fn:
                on_message(f"Split maintenance: {pn} pending, {fn} failed (will retry next update).")
            else:
                on_message("Split maintenance complete.")
        except Exception as se:
            on_message(f"Split maintenance warning: {se}")

        try:
            sm = split_maint if isinstance(split_maint, dict) else {}
            ap = int(sm.get("applied_count") or 0)
            pend = int(sm.get("pending_count") or 0)
            if ap or pend or int(sm.get("db_discontinuity_hits") or 0):
                summary += f" Splits: {ap} applied in ledger"
                if int(sm.get("db_discontinuity_hits") or 0):
                    summary += f", {int(sm['db_discontinuity_hits'])} gap(s) detected"
                if pend:
                    summary += f", {pend} still pending"
                summary += "."
        except Exception:
            pass

        # Final cache clear after live-price / index sync so chart API serves post-job data.
        invalidate_chart_cache()
        _bump_market_data_version(bars=stocks_n)

        finish_job(
            summary,
            meta={
                "stocks_updated": stocks_n,
                "index_candles_added": total_idx,
                "index_ohlcv_error": index_ohlcv_error,
                "price_refresh": price_stats or None,
                "bars_4h": bars_4h_stats or None,
                "bars_4h_deferred": bars_4h_deferred,
                "bars_30m": bars_30m_stats or None,
                "bars_30m_deferred": bars_30m_deferred,
                "split_maintenance": split_maint or None,
            },
        )
    except JobCancelled:
        if yahoo_phase_done:
            stocks_n = int(stocks_updated or 0)
            invalidate_chart_cache()
            _bump_market_data_version(bars=stocks_n)
            finish_job(
                f"Chart data updated ({stocks_n} stock symbols). Cancelled before remaining steps finished.",
                meta={
                    "cancelled": True,
                    "partial": True,
                    "stocks_updated": stocks_n,
                    "bhav_screener_written": bhav_screener_written,
                    "price_refresh": price_stats or None,
                    "index_ohlcv_error": index_ohlcv_error,
                },
            )
        else:
            cancel_job("Update cancelled.")
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/fetch-ohlcv")
def admin_fetch_ohlcv():
    result = _start_or_queue_job(
        "ohlcv",
        lambda: threading.Thread(target=run_fetch_ohlcv, daemon=True).start(),
        label="Update price and volume data",
        source="manual",
    )
    try:
        import admin_job_scheduler as ajs

        ajs.record_external_manual_run("ohlcv")
    except Exception:
        pass
    return result


@app.post("/api/admin/fetch-mf-nav")
def admin_fetch_mf_nav():
    from server import mf_nav as _mf_nav

    ok, reason = _mf_nav.mf_nav_refresh_allowed()
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    result = _start_or_queue_job(
        "mf_nav",
        lambda: threading.Thread(target=run_fetch_mf_nav, daemon=True).start(),
        label="AMFI mutual fund NAVs",
        source="manual",
        coalesce_key="mfNav",
    )
    try:
        import admin_job_scheduler as ajs

        ajs.record_external_manual_run("mfNav")
    except Exception:
        pass
    return result


def run_build_bars_4h():
    """Explicit full-universe 4H session bar build (ignores live-session deferral)."""
    from server.admin_job_control import JobCancelled, is_cancel_requested, raise_if_cancelled

    try:
        set_job("bars_4h_build", "Building 4H (+30m) session bars (Upstox only)...")

        def on_message(msg: str) -> None:
            job_state["message"] = msg

        def on_4h_progress(done, total):
            job_state["progress"] = done
            job_state["total"] = total

        import importlib.util as ilu4

        spec4 = ilu4.spec_from_file_location("scrape_4h", SCRAPE_4H_PATH)
        mod4 = ilu4.module_from_spec(spec4)
        spec4.loader.exec_module(mod4)

        on_message("4H full-universe build — Upstox only (30m co-written)")
        stock_4h = mod4.run(
            backfill=True,
            progress_callback=on_4h_progress,
            message_callback=on_message,
            cancel_check=is_cancel_requested,
            also_30m=True,
        )
        raise_if_cancelled()

        index_syms = []
        try:
            spec_idx = ilu4.spec_from_file_location("scrape_indices", SCRAPE_INDICES_PATH)
            mod_idx = ilu4.module_from_spec(spec_idx)
            spec_idx.loader.exec_module(mod_idx)
            index_syms = [s for s, _, _ in mod_idx.INDICES]
        except Exception:
            index_syms = []

        index_4h = {"updated": 0, "failed": 0, "skipped": 0}
        if index_syms:
            job_state["message"] = "Building 4H (+30m) session bars for indices..."
            index_4h = mod4.run(
                symbols=index_syms,
                backfill=True,
                progress_callback=on_4h_progress,
                message_callback=on_message,
                cancel_check=is_cancel_requested,
                also_30m=True,
            )
        raise_if_cancelled()

        integrity = None
        job_state["message"] = "Scanning 4H bar integrity…"
        try:
            from server.bars_4h_integrity import audit_and_repair_after_4h_build

            conn_4h_int = get_db_connection()
            try:
                integrity = audit_and_repair_after_4h_build(
                    conn_4h_int,
                    BASE_DIR,
                    auto_repair=True,
                    log_fn=on_message,
                    cancel_check=is_cancel_requested,
                )
            finally:
                conn_4h_int.close()
        except Exception as ie4h:
            on_message(f"4H integrity warning: {ie4h}")

        invalidate_chart_cache()
        finish_job(
            f"4H bars built. Stocks updated={stock_4h.get('updated', 0)}, "
            f"indices updated={index_4h.get('updated', 0)} (30m co-written).",
            meta={
                "stocks": stock_4h,
                "indices": index_4h,
                "integrity": integrity,
            },
        )
    except JobCancelled:
        cancel_job("4H build cancelled.")
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/build-bars-4h")
def admin_build_bars_4h():
    """Host-only: full-universe 4H rebuild (runs during live session too)."""
    return _start_or_queue_job(
        "bars_4h_build",
        lambda: threading.Thread(target=run_build_bars_4h, daemon=True).start(),
        label="Build 4H session bars",
        source="manual",
    )


def run_build_bars_30m():
    """Explicit full-universe 30m session bar build (ignores live-session deferral)."""
    from server.admin_job_control import JobCancelled, is_cancel_requested, raise_if_cancelled

    try:
        set_job("bars_30m_build", "Building 30m session bars (Upstox only)...")

        def on_message(msg: str) -> None:
            job_state["message"] = msg

        def on_30m_progress(done, total):
            job_state["progress"] = done
            job_state["total"] = total

        import importlib.util as ilu30

        spec30 = ilu30.spec_from_file_location("scrape_30m", SCRAPE_30M_PATH)
        mod30 = ilu30.module_from_spec(spec30)
        spec30.loader.exec_module(mod30)

        on_message("30m full-universe build — Upstox only")
        stock_30m = mod30.run(
            backfill=True,
            progress_callback=on_30m_progress,
            message_callback=on_message,
            cancel_check=is_cancel_requested,
        )
        raise_if_cancelled()

        index_syms = []
        try:
            spec_idx = ilu30.spec_from_file_location("scrape_indices", SCRAPE_INDICES_PATH)
            mod_idx = ilu30.module_from_spec(spec_idx)
            spec_idx.loader.exec_module(mod_idx)
            index_syms = [s for s, _, _ in mod_idx.INDICES]
        except Exception:
            index_syms = []

        index_30m = {"updated": 0, "failed": 0, "skipped": 0}
        if index_syms:
            job_state["message"] = "Building 30m session bars for indices..."
            index_30m = mod30.run(
                symbols=index_syms,
                backfill=True,
                progress_callback=on_30m_progress,
                message_callback=on_message,
                cancel_check=is_cancel_requested,
            )

        invalidate_chart_cache()
        finish_job(
            f"30m bars built. Stocks updated={stock_30m.get('updated', 0)}, "
            f"indices updated={index_30m.get('updated', 0)}.",
            meta={
                "stocks": stock_30m,
                "indices": index_30m,
            },
        )
    except JobCancelled:
        cancel_job("30m build cancelled.")
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/build-bars-30m")
def admin_build_bars_30m():
    """Host-only: full-universe 30m rebuild (runs during live session too)."""
    return _start_or_queue_job(
        "bars_30m_build",
        lambda: threading.Thread(target=run_build_bars_30m, daemon=True).start(),
        label="Build 30m session bars",
        source="manual",
    )


def run_repair_index_chart_gaps():
    """On-demand backfill for calendar gaps in index_history (all chartable indices)."""
    from server.admin_job_control import JobCancelled, raise_if_cancelled
    from server.index_history_integrity import (
        format_integrity_report,
        repair_index_gaps,
        scan_index_history,
    )

    conn = None
    try:
        set_job(
            "indexChartGapRepair",
            f"Scanning index chart history for gaps ({DB_PATH})...",
        )
        conn = get_db_connection()

        def on_progress(done: int, total: int, msg: str) -> None:
            job_state["progress"] = done
            job_state["total"] = max(total, 1)
            job_state["message"] = msg

        raise_if_cancelled()
        scan = scan_index_history(conn)
        symbols_with_gaps = [s for s in scan.get("symbols", []) if s.get("gap_count")]
        if not symbols_with_gaps:
            invalidate_chart_cache()
            _bump_market_data_version()
            finish_job(
                "No index chart gaps detected in database. Chart cache cleared — "
                "hard refresh the chart (Ctrl+Shift+R) if it still looks wrong."
            )
            return

        on_progress(0, len(scan.get("symbols") or []), format_integrity_report(scan))
        result = repair_index_gaps(
            conn,
            log_fn=lambda m: on_progress(
                job_state.get("progress") or 0,
                job_state.get("total") or 1,
                m,
            ),
            progress_cb=on_progress,
            cancel_check=raise_if_cancelled,
        )
        raise_if_cancelled()
        invalidate_chart_cache()
        for sym in result.get("repaired_symbols") or []:
            invalidate_chart_cache(sym)
        _bump_market_data_version(bars=int(result.get("rows_inserted") or 0))
        summary = format_integrity_report(result)
        finish_job(
            f"{summary}\nHard refresh open index charts (Ctrl+Shift+R) to load repaired bars.",
            meta={"index_gap_repair": result},
        )
    except JobCancelled:
        cancel_job("Index chart gap repair cancelled.")
    except Exception as e:
        fail_job(str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@app.post("/api/admin/repair-index-chart-gaps")
def admin_repair_index_chart_gaps():
    return _start_or_queue_job(
        "indexChartGapRepair",
        lambda: threading.Thread(target=run_repair_index_chart_gaps, daemon=True).start(),
        label="Repair Index Chart Gaps",
        source="manual",
    )


@app.post("/api/admin/backfill-symbol-lineage/{symbol}")
def admin_backfill_symbol_lineage(symbol: str):
    """
    Merge predecessor-ticker Yahoo history into historical_data for a canonical symbol.
  See data/symbol_lineage.json and docs/SYMBOL_LINEAGE.md.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol required")
    if str(BASE_DIR) not in _sys.path:
        _sys.path.insert(0, str(BASE_DIR))
    try:
        from symbol_lineage import get_lineage_entry, run_lineage_backfill
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"symbol_lineage module missing: {e}") from e
    if not get_lineage_entry(sym):
        raise HTTPException(
            status_code=404,
            detail=f"No lineage config for '{sym}'. Add an entry to data/symbol_lineage.json.",
        )
    try:
        conn = get_db_connection()
        result = run_lineage_backfill(conn, sym)
        conn.close()
        invalidate_chart_cache(sym)
        invalidate_filter_cache()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error") or "backfill failed")
    return {"status": "ok", **result}


@app.post("/api/admin/clear-indicator-snapshots")
def admin_clear_indicator_snapshots():
    """
    Full clear of indicator_snapshots for all symbols and timeframes.
    Intended for use before a full rebuild of indicator snapshots
    (e.g. after changing indicator logic or fixing data).
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM indicator_snapshots")
        cleared = cur.rowcount
        conn.commit()
        conn.close()
        invalidate_filter_cache()
        return {"status": "ok", "rows_cleared": cleared}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear indicator_snapshots: {e}")


def _load_scrape_daily_module():
    scrape_path = Path(SCRAPE_DAILY_PATH)
    if not scrape_path.exists():
        raise RuntimeError(
            f"Cannot load scrape_daily from install root: {scrape_path}"
        )
    spec = importlib.util.spec_from_file_location("nse_pulse_scrape_daily", scrape_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load scrape_daily from {scrape_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call_scrape_daily_run(module, **kwargs):
    """Call scrape_daily.run, omitting kwargs the installed script does not support."""
    import inspect

    params = inspect.signature(module.run).parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        result = module.run(**kwargs)
    else:
        filtered = {k: v for k, v in kwargs.items() if k in params}
        result = module.run(**filtered)
    return _normalize_scrape_daily_result(result)


def _normalize_scrape_daily_result(result) -> dict:
    if isinstance(result, dict):
        return {
            "updated": int(result.get("updated") or 0),
            "bhav_screener_written": int(result.get("bhav_screener_written") or 0),
        }
    return {"updated": int(result or 0), "bhav_screener_written": 0}


def run_rebuild_indicator_snapshots(
    *,
    timeframes: Optional[Tuple[str, ...]] = None,
    families_override=None,
):
    """Background: full clear+rebuild for all screener symbols."""
    from server import snapshot_rebuild_guard as srg

    try:
        set_job("indicator_snapshots", "Loading snapshot builder…")
        requested_timeframes = tuple(timeframes or SNAPSHOT_TIMEFRAMES)
        job_state["meta"] = {
            "scope": "full",
            "mode": "full",
            "force": True,
            "timeframes_requested": list(requested_timeframes),
            "timeframes_processed": [],
        }
        mod = _load_scrape_daily_module()
        job_state["message"] = (
            "Rebuilding indicator snapshots — loading OHLC in batches, then computing "
            "(progress advances during the database read)…"
        )

        def on_prog(done: int, total: int) -> None:
            job_state["progress"] = done
            job_state["total"] = max(total, 1)

        def on_msg(msg: str) -> None:
            job_state["message"] = msg

        n = mod.rebuild_indicator_snapshots_universe(
            clear_first=True,
            progress_callback=on_prog,
            message_callback=on_msg,
            timeframes_override=requested_timeframes,
            families_override=families_override,
        )
        invalidate_filter_cache()
        job_state["meta"] = {
            "scope": "full",
            "mode": "full",
            "force": True,
            "timeframes_requested": list(requested_timeframes),
            "timeframes_processed": list(requested_timeframes),
            "symbols_total": n,
            "symbols_recomputed": n,
            "symbols_skipped_fingerprint": 0,
        }
        finish_job(
            f"Indicator snapshots rebuilt for {n} symbols ({', '.join(requested_timeframes)})."
        )
    except Exception as e:
        fail_job(str(e))
    finally:
        srg.release_full_rebuild_hold()


def _full_snapshot_rebuild_preflight(*, allow_scheduler_overlap: bool = False) -> None:
    from server import snapshot_rebuild_guard as srg

    if allow_scheduler_overlap:
        return
    conflicts = srg.collect_scheduler_conflicts(
        job_running_fn=lambda: bool(job_state.get("running")),
    )
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Cannot start full snapshot rebuild while scheduled admin tasks are "
                    "active or due soon. Wait for them to finish, disable them in Admin "
                    "Scheduler, or pass allow_scheduler_overlap=1."
                ),
                "conflicts": conflicts,
            },
        )


def _start_full_snapshot_rebuild_thread(
    *,
    timeframes: Optional[Tuple[str, ...]] = None,
    allow_scheduler_overlap: bool = False,
) -> dict:
    from server import snapshot_rebuild_guard as srg

    _full_snapshot_rebuild_preflight(allow_scheduler_overlap=allow_scheduler_overlap)
    requested_timeframes = tuple(timeframes or SNAPSHOT_TIMEFRAMES)

    def _starter() -> None:
        srg.acquire_full_rebuild_hold()
        try:
            threading.Thread(
                target=run_rebuild_indicator_snapshots,
                kwargs={"timeframes": requested_timeframes},
                daemon=True,
            ).start()
        except Exception:
            srg.release_full_rebuild_hold()
            raise

    result = _start_or_queue_job(
        "indicator_snapshots",
        _starter,
        label="Full indicator snapshot rebuild",
        source="manual",
        coalesce_key="indicator_snapshots_full",
    )
    return {
        **result,
        "job": "indicator_snapshots",
        "mode": "full",
        "scope": "full",
        "force": True,
        "timeframes": list(requested_timeframes),
        "watchdogPaused": True,
        "schedulerFrozen": True,
    }


def run_rebuild_indicator_snapshots_incremental(
    days_back: int = 1,
    *,
    timeframes: Optional[Tuple[str, ...]] = None,
    force: bool = False,
    families_override=None,
):
    """Background: rebuild snapshots only for symbols with recent candles."""
    try:
        set_job("indicator_snapshots", "Resolving recently changed symbols…")
        requested_timeframes = tuple(timeframes or SNAPSHOT_LIGHT_TIMEFRAMES)
        job_state["meta"] = {
            "scope": "incremental",
            "mode": "incremental",
            "force": bool(force),
            "timeframes_requested": list(requested_timeframes),
            "timeframes_processed": [],
            "incremental_safe": True,
        }
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT Symbol FROM historical_data WHERE Date >= date('now', ?) ORDER BY Symbol ASC",
            (f"-{max(0, int(days_back))} day",),
        )
        symbols = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
        conn.close()
        if not symbols:
            finish_job("No recently changed symbols found; incremental rebuild skipped.")
            return
        mod = _load_scrape_daily_module()
        job_state["message"] = (
            f"Incremental snapshot rebuild for {len(symbols)} symbol(s) "
            f"(safe path: bounded OHLC, delete-after-compute)…"
        )

        def on_prog(done: int, total: int) -> None:
            job_state["progress"] = done
            job_state["total"] = max(total, 1)

        def on_msg(msg: str) -> None:
            job_state["message"] = msg

        n = mod.rebuild_indicator_snapshots_universe(
            clear_first=False,
            symbols_override=symbols,
            progress_callback=on_prog,
            message_callback=on_msg,
            timeframes_override=requested_timeframes,
            families_override=families_override,
        )
        invalidate_filter_cache()
        job_state["meta"] = {
            "scope": "incremental",
            "mode": "incremental",
            "force": bool(force),
            "timeframes_requested": list(requested_timeframes),
            "timeframes_processed": list(requested_timeframes),
            "symbols_total": len(symbols),
            "symbols_recomputed": n,
            "symbols_skipped_fingerprint": 0,
        }
        finish_job(
            f"Incremental indicator snapshots rebuilt for {n} symbols "
            f"(changed in last {max(0, int(days_back))} day(s), timeframes: {', '.join(requested_timeframes)})."
        )
    except Exception as e:
        fail_job(str(e))


def run_split_maintenance_for_update(
    *,
    quiet: bool = False,
    cancel_check: Optional[Callable[[], bool]] = None,
    on_message: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Part of every OHLCV update: detect splits (DB gaps + Yahoo 90d), apply all pending.
    No separate manual catch-up or apply-pending step.
    """
    import split_utils as su
    from server.chart_corp_markers import detect_unapplied_splits_from_history

    lookback = su.SPLIT_CATCHUP_DAYS
    applied_total = 0
    db_hits = 0

    def _msg(text: str) -> None:
        if on_message:
            on_message(text)
        if not quiet:
            job_state["message"] = text

    conn = get_db_connection()
    try:
        su.ensure_stock_split_events_table(conn)
        _msg(f"Checking chart history for unadjusted splits ({lookback} days)…")
        for hit in detect_unapplied_splits_from_history(conn, lookback_days=lookback):
            if cancel_check and cancel_check():
                break
            if su.mark_pending(
                conn,
                symbol=hit["symbol"],
                split_date=hit["split_date"],
                ratio=hit["ratio"],
                source=hit.get("source") or "db_discontinuity",
            ):
                db_hits += 1
    finally:
        conn.close()

    max_rounds = 40
    last_summary: dict = {}
    for round_i in range(max_rounds):
        if cancel_check and cancel_check():
            break
        pending_n = 0
        conn = get_db_connection()
        try:
            counts = su.count_by_status(conn)
            pending_n = int(counts.get(su.STATUS_PENDING, 0)) + int(counts.get(su.STATUS_FAILED, 0))
        finally:
            conn.close()
        if pending_n <= 0 and round_i > 0:
            break
        if pending_n > 0:
            _msg(f"Applying {pending_n} split adjustment(s) (batch {round_i + 1})…")
            run_apply_pending_stock_splits(
                trigger="post_ohlcv",
                quiet=True,
                auto=True,
                max_batch=su.SPLIT_AUTO_APPLY_BATCH_CAP,
            )
            applied_total += min(pending_n, su.SPLIT_AUTO_APPLY_BATCH_CAP)
        if round_i == 0:
            _msg(f"Scanning universe for splits ({lookback} days, Yahoo)…")
            last_summary = run_scan_stock_splits(
                lookback,
                trigger="post_ohlcv",
                quiet=True,
                backfill_applied=False,
                sleep_sec=0,
                cancel_check=cancel_check,
            )
        elif pending_n <= 0:
            break

    conn = get_db_connection()
    try:
        counts = su.count_by_status(conn)
    finally:
        conn.close()

    out = {
        "lookback_days": lookback,
        "db_discontinuity_hits": db_hits,
        "applied_total": applied_total,
        "pending_count": int(counts.get(su.STATUS_PENDING, 0)),
        "failed_count": int(counts.get(su.STATUS_FAILED, 0)),
        "applied_count": int(counts.get(su.STATUS_APPLIED, 0)),
        "yahoo_scan": last_summary,
    }
    if not quiet:
        meta = dict(job_state.get("meta") or {})
        meta["split_maintenance"] = out
        job_state["meta"] = meta
    return out


def run_scan_stock_splits(
    days_back: int = 20,
    *,
    trigger: str = "manual",
    quiet: bool = False,
    backfill_applied: bool = False,
    sleep_sec: Optional[float] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    Light scan: detect splits in lookback window, upsert pending ledger rows.
    Skips fingerprints already marked applied. Optional backfill marks applied when
    historical_data already exists (upgrade path — no re-download).
    """
    global _split_scan_running
    import split_utils as su

    lookback = max(1, int(days_back))
    cutoff = datetime.utcnow() - timedelta(days=lookback)
    if not _split_scan_lock.acquire(blocking=False):
        return {"skipped": "scan_already_running", "trigger": trigger}

    try:
        _split_scan_running = True
        conn = get_db_connection()
        su.ensure_stock_split_events_table(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT symbol FROM screener WHERE symbol IS NOT NULL AND TRIM(symbol) != '' ORDER BY symbol ASC"
        )
        symbols = [str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]]
        total = len(symbols)
        pending_new = 0
        backfilled = 0
        detected_symbols = []
        scan_sleep = su.SPLIT_SCAN_SLEEP_SEC if sleep_sec is None else max(0.0, float(sleep_sec))

        for idx, sym in enumerate(symbols, start=1):
            if cancel_check and cancel_check():
                break
            if not quiet and job_state.get("job") in ("split_adjustments", "ohlcv"):
                job_state["progress"] = idx
                job_state["total"] = total
                job_state["message"] = f"Split scan {idx}/{total}: {sym}"
                meta = dict(job_state.get("meta") or {})
                meta["split_scan_line"] = f"Split scan {idx}/{total}: {sym}"
                job_state["meta"] = meta

            if scan_sleep > 0:
                time_module.sleep(scan_sleep)
            try:
                hit = su.detect_recent_split(sym, cutoff)
                if not hit:
                    continue
                if su.is_split_applied(
                    conn, hit["symbol"], hit["split_date"], hit["ratio"]
                ):
                    continue
                if sym not in detected_symbols:
                    detected_symbols.append(sym)
                if backfill_applied and su.symbol_has_historical_bars(conn, sym):
                    if not su.history_has_split_discontinuity(
                        conn, hit["symbol"], hit["split_date"], hit["ratio"]
                    ):
                        su.mark_applied(
                            conn,
                            symbol=hit["symbol"],
                            split_date=hit["split_date"],
                            ratio=hit["ratio"],
                            source=hit.get("source") or "backfill",
                        )
                        backfilled += 1
                        continue
                if su.mark_pending(
                    conn,
                    symbol=hit["symbol"],
                    split_date=hit["split_date"],
                    ratio=hit["ratio"],
                    source=hit.get("source") or "scan",
                ):
                    pending_new += 1
            except Exception:
                continue

        counts = su.count_by_status(conn)
        conn.close()
        summary = {
            "trigger": trigger,
            "days_back": lookback,
            "symbols_scanned": total,
            "pending_new": pending_new,
            "backfilled_applied": backfilled,
            "pending_count": counts.get(su.STATUS_PENDING, 0),
            "failed_count": counts.get(su.STATUS_FAILED, 0),
            "applied_count": counts.get(su.STATUS_APPLIED, 0),
            "detected_symbols": detected_symbols[-200:],
        }
        try:
            import split_watch_scheduler as sws

            sws.write_watch_log(summary)
        except Exception:
            pass
        return summary
    finally:
        _split_scan_running = False
        _split_scan_lock.release()


def run_apply_pending_stock_splits(
    symbols: Optional[list[str]] = None,
    *,
    trigger: str = "manual",
    quiet: bool = False,
    auto: bool = False,
    max_batch: Optional[int] = None,
) -> None:
    """Heavy apply: refresh historical_data for pending/failed ledger rows only."""
    import split_utils as su

    try:
        cap = max_batch if max_batch is not None else su.SPLIT_AUTO_APPLY_BATCH_CAP
        conn = get_db_connection()
        su.ensure_stock_split_events_table(conn)
        pending = su.list_pending(conn, symbols=symbols, limit=int(cap))
        if not pending:
            conn.close()
            if not quiet:
                finish_job("No pending split adjustments.")
            return

        if not quiet:
            set_job(
                "split_adjustments",
                f"Applying {len(pending)} pending split adjustment(s)…",
            )
        job_state["progress"] = 0
        job_state["total"] = len(pending)
        job_state["meta"] = {
            "split_scan_line": None,
            "split_detected_count": len(pending),
            "split_detected_symbols": [p["symbol"] for p in pending],
            "split_refresh_failed_count": 0,
            "split_refresh_failed_symbols": [],
            "pending_applied_count": 0,
            "trigger": trigger,
            "auto": auto,
            "quiet": quiet,
        }

        affected = []
        failed_refresh = []
        refreshed = 0

        for idx, row in enumerate(pending, start=1):
            sym = row["symbol"]
            split_date = row["split_date"]
            ratio = row["ratio"]
            if not quiet:
                job_state["progress"] = idx
                job_state["message"] = (
                    f"Applying split {idx}/{len(pending)}: {sym} "
                    f"({split_date} ratio={ratio:g})…"
                )
            try:
                if su.is_split_applied(conn, sym, split_date, ratio):
                    continue
                ok, err = su.apply_symbol_history_refresh(
                    conn,
                    sym,
                    split_date=split_date,
                    split_ratio=ratio,
                )
                if not ok:
                    failed_refresh.append(f"{sym}: {err}")
                    su.mark_failed(
                        conn,
                        symbol=sym,
                        split_date=split_date,
                        ratio=ratio,
                        error=err,
                    )
                    job_state["meta"]["split_refresh_failed_count"] = len(failed_refresh)
                    job_state["meta"]["split_refresh_failed_symbols"] = failed_refresh[-200:]
                    continue
                su.mark_applied(
                    conn,
                    symbol=sym,
                    split_date=split_date,
                    ratio=ratio,
                    source=row.get("source"),
                )
                su.recalc_screener_change_for_symbol(conn, sym)
                try:
                    from server.bars_4h_integrity import rebuild_bars_4h_after_corp_action

                    def _log_4h(msg: str) -> None:
                        if not quiet:
                            job_state["message"] = msg

                    rebuild_bars_4h_after_corp_action(
                        conn,
                        BASE_DIR,
                        sym,
                        log_fn=_log_4h if not quiet else None,
                    )
                except Exception as bars4h_err:
                    job_state.setdefault("meta", {})
                    warns = job_state["meta"].setdefault("bars_4h_rebuild_warnings", [])
                    warns.append(f"{sym}: {bars4h_err}")
                if sym not in affected:
                    affected.append(sym)
                refreshed += 1
                job_state["meta"]["pending_applied_count"] = refreshed
            except Exception as sym_err:
                err = type(sym_err).__name__
                failed_refresh.append(f"{sym}: {err}")
                su.mark_failed(
                    conn,
                    symbol=sym,
                    split_date=split_date,
                    ratio=ratio,
                    error=err,
                )
                job_state["meta"]["split_refresh_failed_count"] = len(failed_refresh)
                job_state["meta"]["split_refresh_failed_symbols"] = failed_refresh[-200:]

        conn.close()

        if not affected:
            if not quiet:
                finish_job(
                    f"No split symbols applied; failed {len(failed_refresh)}.",
                    meta=job_state.get("meta"),
                )
            return

        if not quiet:
            job_state["message"] = "Refreshing indicator snapshots for split-adjusted symbols…"
        mod = _load_scrape_daily_module()
        mod.rebuild_indicator_snapshots_universe(
            clear_first=False,
            symbols_override=affected,
        )

        invalidate_chart_cache()
        invalidate_filter_cache()
        invalidate_stock_df()
        sample = ", ".join(affected[:10])
        suffix = "..." if len(affected) > 10 else ""
        if not quiet:
            finish_job(
                f"Split adjustment complete. Refreshed {refreshed} symbol(s); "
                f"failed {len(failed_refresh)}; snapshots rebuilt. Symbols: {sample}{suffix}",
                meta=job_state.get("meta"),
            )
        else:
            try:
                import split_watch_scheduler as sws

                sws.write_watch_log(
                    {
                        "last_apply_at": datetime.utcnow().isoformat(),
                        "applied_count": refreshed,
                        "failed_count": len(failed_refresh),
                        "trigger": trigger,
                    }
                )
            except Exception:
                pass
    except Exception as e:
        if not quiet:
            fail_job(str(e))


def run_apply_split_adjustments(
    days_back: int = 20,
    *,
    apply_only: bool = False,
    scan_only: bool = False,
    scan_first: bool = False,
    symbols: Optional[list[str]] = None,
    quiet: bool = False,
):
    """
    Orchestrator: optional scan (maintenance/catch-up), then apply pending rows.
    apply_only skips scan; scan_only skips apply.
    """
    import split_utils as su

    try:
        if apply_only:
            run_apply_pending_stock_splits(symbols=symbols, quiet=quiet)
            return

        if scan_only or scan_first:
            lookback = max(1, int(days_back))
            backfill = lookback >= su.SPLIT_CATCHUP_DAYS
            if not quiet:
                set_job(
                    "split_adjustments",
                    f"Scanning universe for splits in last {lookback} day(s)…",
                )
                job_state["meta"] = {
                    "split_scan_line": "Split scan starting…",
                    "split_detected_count": 0,
                    "split_detected_symbols": [],
                }
            summary = run_scan_stock_splits(
                lookback,
                trigger="manual",
                quiet=quiet,
                backfill_applied=backfill,
            )
            if scan_only:
                if not quiet:
                    pn = summary.get("pending_new", 0)
                    finish_job(
                        f"Split scan complete. New pending: {pn}; "
                        f"total pending: {summary.get('pending_count', 0)}; "
                        f"backfilled as applied: {summary.get('backfilled_applied', 0)}.",
                        meta={
                            **(job_state.get("meta") or {}),
                            "split_scan_summary": summary,
                        },
                    )
                return

        run_apply_pending_stock_splits(symbols=symbols, quiet=quiet)
    except Exception as e:
        if not quiet:
            fail_job(str(e))


def _run_scan_then_auto_apply(days_back: int, *, backfill: bool, trigger: str) -> None:
    """Thread target for manual scan API (scan then apply pending)."""
    import split_utils as su

    try:
        summary = run_scan_stock_splits(
            days_back,
            trigger=trigger,
            quiet=True,
            backfill_applied=backfill,
        )
        pending = int(summary.get("pending_count") or 0)
        if pending <= 0:
            return
        if job_state.get("running"):
            try:
                import split_watch_scheduler as sws

                sws.write_watch_log(
                    {
                        "last_apply_deferred_at": datetime.utcnow().isoformat(),
                        "pending_count": pending,
                        "trigger": trigger,
                    }
                )
            except Exception:
                pass
            return
        run_apply_pending_stock_splits(
            trigger=trigger,
            quiet=True,
            auto=True,
            max_batch=su.SPLIT_AUTO_APPLY_BATCH_CAP,
        )
    except Exception:
        pass


@app.get("/api/admin/filter-rebuild/options")
def admin_filter_rebuild_options():
    return public_options_payload()


def run_filter_rebuild_job(
    *,
    keys: list[str],
    mode: str = "full",
    timeframes: Optional[Tuple[str, ...]] = None,
    days_back: int = 1,
):
    from filter_rebuild_runner import run_filter_rebuild
    from server.admin_job_control import JobCancelled

    try:
        set_job("filter_rebuild", "Starting selective filter rebuild…")
        job_state["meta"] = {
            "scope": mode,
            "mode": mode,
            "keys": list(keys or []),
            "timeframes_requested": list(timeframes or []),
        }
        job_state["total"] = 100

        run_filter_rebuild(
            keys=keys,
            mode=mode,
            timeframes=timeframes,
            days_back=days_back,
            get_db_connection=get_db_connection,
            load_scrape_daily_module=_load_scrape_daily_module,
            set_job=set_job,
            finish_job=finish_job,
            fail_job=fail_job,
            invalidate_filter_cache=invalidate_filter_cache,
            job_state=job_state,
        )
    except JobCancelled:
        cancel_job("Filter rebuild cancelled.")
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/filter-rebuild")
def admin_filter_rebuild(body: dict):
    keys = body.get("keys") or []
    if not isinstance(keys, list) or not keys:
        raise HTTPException(status_code=400, detail="Provide keys: non-empty list of registry ids.")
    mode = str(body.get("mode") or "full").strip().lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode must be full or incremental.")
    days_back = max(0, min(30, int(body.get("days_back") or 1)))
    tf_raw = body.get("timeframes")
    requested_timeframes = None
    if isinstance(tf_raw, str) and tf_raw.strip():
        requested_timeframes = _parse_snapshot_timeframes_csv(tf_raw)
    elif isinstance(tf_raw, list) and tf_raw:
        requested_timeframes = _parse_snapshot_timeframes_csv(",".join(str(t) for t in tf_raw))

    normalized_keys = [str(k).strip().lower() for k in keys if str(k).strip()]
    needs_full_hold = False
    if mode == "full":
        snap_keys = [k for k in normalized_keys if k in {
            "price_ohlc", "ema", "macd", "stochrsi",
        }]
        needs_full_hold = bool(snap_keys)
        if snap_keys:
            from server import snapshot_rebuild_guard as srg

            conflicts = srg.collect_scheduler_conflicts(
                job_running_fn=lambda: bool(job_state.get("running")),
            )
            if conflicts:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": (
                            "Cannot start full indicator snapshot rebuild while scheduled admin "
                            "tasks are active or due soon."
                        ),
                        "conflicts": conflicts,
                    },
                )

    def _worker() -> None:
        if needs_full_hold:
            from server import snapshot_rebuild_guard as srg

            srg.acquire_full_rebuild_hold(reason="manual_filter_rebuild_full")
        try:
            run_filter_rebuild_job(
                keys=normalized_keys,
                mode=mode,
                timeframes=requested_timeframes,
                days_back=days_back,
            )
        finally:
            if needs_full_hold:
                from server import snapshot_rebuild_guard as srg

                srg.release_full_rebuild_hold()

    result = _start_or_queue_job(
        "filter_rebuild",
        lambda: threading.Thread(target=_worker, daemon=True).start(),
        label="Filter rebuild",
        source="manual",
    )
    return {
        **result,
        "job": "filter_rebuild",
        "mode": mode,
        "keys": normalized_keys,
        "days_back": days_back,
        "timeframes": list(requested_timeframes or []),
        "watchdogPaused": needs_full_hold,
        "schedulerFrozen": needs_full_hold,
    }


@app.get("/api/admin/rebuild-indicator-snapshots/preflight")
def admin_rebuild_indicator_snapshots_preflight():
    from server import snapshot_rebuild_guard as srg

    conflicts = srg.collect_scheduler_conflicts(
        job_running_fn=lambda: bool(job_state.get("running")),
    )
    return {
        "ok": not conflicts and not job_state.get("running"),
        "jobRunning": bool(job_state.get("running")),
        "holdActive": srg.scheduler_is_frozen(),
        "conflicts": conflicts,
    }


@app.post("/api/admin/rebuild-indicator-snapshots")
def admin_rebuild_indicator_snapshots(
    confirm_full: str = Query(""),
    timeframes: str = Query(""),
    allow_scheduler_overlap: bool = Query(False),
):
    # Backward-compatible route: guarded full rebuild.
    if str(confirm_full or "").strip() != FULL_REBUILD_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"confirm_full must equal {FULL_REBUILD_CONFIRM_TOKEN}",
        )
    requested_timeframes = _parse_snapshot_timeframes_csv(timeframes) or SNAPSHOT_TIMEFRAMES
    return _start_full_snapshot_rebuild_thread(
        timeframes=requested_timeframes,
        allow_scheduler_overlap=allow_scheduler_overlap,
    )


@app.post("/api/admin/rebuild-indicator-snapshots-incremental")
def admin_rebuild_indicator_snapshots_incremental(
    days_back: int = Query(1, ge=0, le=30),
    timeframes: str = Query(""),
    force: bool = Query(False),
    defer_heavy: bool = Query(True),
    scope: str = Query("incremental"),
):
    scope_norm = str(scope or "incremental").strip().lower()
    if scope_norm != "incremental":
        raise HTTPException(status_code=400, detail="scope=full is not allowed on incremental endpoint")
    requested_timeframes = _parse_snapshot_timeframes_csv(timeframes)
    if requested_timeframes is None:
        requested_timeframes = SNAPSHOT_LIGHT_TIMEFRAMES if defer_heavy else SNAPSHOT_TIMEFRAMES
    result = _start_or_queue_job(
        "indicator_snapshots",
        lambda: threading.Thread(
            target=run_rebuild_indicator_snapshots_incremental,
            args=(days_back,),
            kwargs={
                "timeframes": requested_timeframes,
                "force": bool(force),
            },
            daemon=True,
        ).start(),
        label="Indicator snapshots (incremental)",
        source="manual",
        coalesce_key="indicator_snapshots_incremental",
    )
    return {
        **result,
        "job": "indicator_snapshots",
        "mode": "incremental",
        "scope": "incremental",
        "days_back": days_back,
        "force": bool(force),
        "defer_heavy": bool(defer_heavy),
        "timeframes": list(requested_timeframes),
    }


@app.post("/api/admin/rebuild-indicator-snapshots-full")
def admin_rebuild_indicator_snapshots_full(
    confirm_full: str = Query(""),
    timeframes: str = Query(""),
    force: bool = Query(True),
    allow_scheduler_overlap: bool = Query(False),
):
    if str(confirm_full or "").strip() != FULL_REBUILD_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"confirm_full must equal {FULL_REBUILD_CONFIRM_TOKEN}",
        )
    requested_timeframes = _parse_snapshot_timeframes_csv(timeframes) or SNAPSHOT_TIMEFRAMES
    result = _start_full_snapshot_rebuild_thread(
        timeframes=requested_timeframes,
        allow_scheduler_overlap=allow_scheduler_overlap,
    )
    result["force"] = bool(force)
    return result


@app.post("/api/admin/rebuild-indicator-snapshots-heavy-now")
def admin_rebuild_indicator_snapshots_heavy_now(
    days_back: int = Query(1, ge=0, le=30),
):
    result = _start_or_queue_job(
        "indicator_snapshots",
        lambda: threading.Thread(
            target=run_rebuild_indicator_snapshots_incremental,
            args=(days_back,),
            kwargs={
                "timeframes": ("4W", "1M"),
                "force": True,
            },
            daemon=True,
        ).start(),
        label="Indicator snapshots (heavy)",
        source="manual",
        coalesce_key="indicator_snapshots_heavy",
    )
    return {
        **result,
        "job": "indicator_snapshots",
        "mode": "incremental",
        "scope": "incremental",
        "days_back": days_back,
        "force": True,
        "timeframes": ["4W", "1M"],
    }


@app.get("/api/admin/split-watch-status")
def admin_split_watch_status():
    import split_utils as su

    try:
        import split_watch_scheduler as sws
    except Exception:
        sws = None
    conn = get_db_connection()
    try:
        su.ensure_stock_split_events_table(conn)
        counts = su.count_by_status(conn)
        pending = su.list_pending(conn, limit=100)
    finally:
        conn.close()
    log = sws.read_watch_log() if sws else {}
    return {
        "pending_count": counts.get(su.STATUS_PENDING, 0),
        "failed_count": counts.get(su.STATUS_FAILED, 0),
        "applied_count": counts.get(su.STATUS_APPLIED, 0),
        "pending": pending,
        "watch_log": log,
        "scan_running": bool(_split_scan_running),
    }


@app.post("/api/admin/scan-stock-splits")
def admin_scan_stock_splits(
    days_back: int = Query(20, ge=1, le=3650),
    auto_apply: bool = Query(True),
):
    import split_utils as su

    backfill = int(days_back) >= su.SPLIT_CATCHUP_DAYS

    def _go() -> None:
        if auto_apply:
            _run_scan_then_auto_apply(
                int(days_back),
                backfill=backfill,
                trigger="manual_scan",
            )
        else:
            run_scan_stock_splits(
                int(days_back),
                trigger="manual_scan",
                quiet=True,
                backfill_applied=backfill,
            )

    result = _start_or_queue_job(
        "split_scan",
        lambda: threading.Thread(target=_go, name="scan-stock-splits", daemon=True).start(),
        label="Stock split scan",
        source="manual",
    )
    return {
        **result,
        "job": "split_scan",
        "days_back": days_back,
        "auto_apply": bool(auto_apply),
        "backfill_applied": backfill,
    }


@app.post("/api/admin/apply-split-adjustments")
def admin_apply_split_adjustments(
    days_back: int = Query(20, ge=1, le=3650),
    apply_only: bool = Query(True),
    scan_only: bool = Query(False),
    scan_first: bool = Query(False),
    symbols: str = Query(""),
):
    sym_list = None
    raw = str(symbols or "").strip()
    if raw:
        sym_list = [s.strip().upper() for s in raw.split(",") if s.strip()]
    result = _start_or_queue_job(
        "split_adjustments",
        lambda: threading.Thread(
            target=run_apply_split_adjustments,
            kwargs={
                "days_back": int(days_back),
                "apply_only": bool(apply_only),
                "scan_only": bool(scan_only),
                "scan_first": bool(scan_first),
                "symbols": sym_list,
            },
            daemon=True,
        ).start(),
        label="Split adjustments",
        source="manual",
    )
    return {
        **result,
        "job": "split_adjustments",
        "days_back": days_back,
        "apply_only": bool(apply_only),
        "scan_only": bool(scan_only),
        "scan_first": bool(scan_first),
        "symbols": sym_list or [],
    }


@app.get("/api/admin/snapshot-consistency")
def admin_snapshot_consistency(
    symbol: str = Query(..., min_length=1),
    timeframe: str = Query("2W"),
    ema_period: int = Query(21, ge=1, le=500),
):
    """
    Compare last-bar OHLC + EMA between chart endpoint and indicator_snapshots row.
    Useful for diagnosing chart/filter mismatch quickly.
    """
    sym = symbol.strip().upper()
    tf_unit, tf_num = parse_timeframe(timeframe)
    snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)
    if not snapshot_key:
        raise HTTPException(status_code=400, detail=f"No snapshot timeframe mapping for '{timeframe}'")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM indicator_snapshots WHERE symbol = ? AND timeframe = ? LIMIT 1",
        (sym, snapshot_key),
    )
    snap = cur.fetchone()
    conn.close()
    if snap is None:
        raise HTTPException(status_code=404, detail=f"No snapshot row for {sym} {snapshot_key}")
    chart = get_chart_data(sym, timeframe=timeframe, ema1=ema_period, bars_limit=900)
    bars = chart.get("bars") or []
    if not bars:
        raise HTTPException(status_code=404, detail=f"No chart bars for {sym} {timeframe}")
    last_bar = bars[-1]
    ema_points = (chart.get("ema") or {}).get(str(ema_period), [])
    chart_ema_last = ema_points[-1]["value"] if ema_points else None
    snap_ema_key = f"ema{ema_period}"
    result = {
        "symbol": sym,
        "timeframe": timeframe,
        "snapshot_key": snapshot_key,
        "chart_last": {
            "time": last_bar.get("time"),
            "open": last_bar.get("open"),
            "high": last_bar.get("high"),
            "low": last_bar.get("low"),
            "close": last_bar.get("close"),
            "ema": chart_ema_last,
        },
        "snapshot_last": {
            "open": snap["open_curr"],
            "high": snap["high_curr"],
            "low": snap["low_curr"],
            "close": snap["close_curr"],
            "ema": snap[snap_ema_key] if snap_ema_key in snap.keys() else None,
            "updated_at": snap["updated_at"],
        },
    }
    c = result["chart_last"]
    s = result["snapshot_last"]
    result["delta"] = {
        "open": None if c["open"] is None or s["open"] is None else round(float(c["open"]) - float(s["open"]), 6),
        "high": None if c["high"] is None or s["high"] is None else round(float(c["high"]) - float(s["high"]), 6),
        "low": None if c["low"] is None or s["low"] is None else round(float(c["low"]) - float(s["low"]), 6),
        "close": None if c["close"] is None or s["close"] is None else round(float(c["close"]) - float(s["close"]), 6),
        "ema": None if c["ema"] is None or s["ema"] is None else round(float(c["ema"]) - float(s["ema"]), 6),
    }
    return result


@app.post("/api/admin/fetch-prices")
def admin_fetch_prices():
    return _start_or_queue_job(
        "prices",
        lambda: threading.Thread(target=run_fetch_prices, daemon=True).start(),
        label="Fetch prices",
        source="manual",
    )


@app.post("/api/admin/fetch-issued-shares")
def admin_fetch_issued_shares():
    """Refresh issued share counts (Yahoo → Screener.in; NSE on desktop only)."""

    def _run():
        from server.admin_job_control import JobCancelled, is_cancel_requested

        try:
            market_cap_live.run_fetch_issued_shares(
                DB_PATH,
                base_dir=BASE_DIR,
                set_job=set_job,
                job_state=job_state,
                fail_job=fail_job,
                invalidate_stock_df=invalidate_stock_df,
                finish_job=finish_job,
                cancel_check=is_cancel_requested,
            )
        except JobCancelled:
            cancel_job("Share count refresh cancelled.")
        except Exception as e:
            fail_job(str(e))

    return _start_or_queue_job(
        "issued_shares",
        lambda: threading.Thread(target=_run, daemon=True).start(),
        label="Refresh share counts",
        source="manual",
    )


@app.get("/api/admin/market-cap-status")
def admin_market_cap_status():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM screener")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM screener WHERE issued_shares IS NOT NULL")
        with_shares = cur.fetchone()[0]
        from server.issued_shares_fetch import count_issued_shares_sources

        sources = count_issued_shares_sources(conn)
        return {
            "total_symbols": total,
            "with_issued_shares": with_shares,
            "without_issued_shares": total - with_shares,
            "method": (
                "Market cap on screen = issued_shares × live price. "
                "Share counts refreshed via Yahoo → Screener.in (NSE on desktop only)."
            ),
            "sources": sources,
            "refresh_job": "POST /api/admin/fetch-issued-shares",
        }
    finally:
        conn.close()


def _earnings_plus_period_label(year: int, month: int) -> str:
    if month == 0:
        return str(year)
    try:
        return datetime(year, month, 1).strftime("%b %Y")
    except ValueError:
        return f"{month:02d}/{year}"


def _record_earnings_plus_warm_run(
    *,
    trigger: str,
    success: bool,
    started_at: str,
    year: int,
    month: int,
    message: str,
    meta: dict | None = None,
    error: str | None = None,
) -> None:
    try:
        import earnings_plus_scheduler as eps_scheduler

        record = {
            "started_at": started_at,
            "finished_at": datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S"),
            "success": success,
            "trigger": trigger,
            "year": year,
            "month": month,
            "message": message,
            "error": error,
        }
        if meta:
            record.update({
                k: meta[k]
                for k in (
                    "total_symbols",
                    "refreshed",
                    "skipped",
                    "qualified_in_run",
                    "force",
                    "only_incomplete",
                )
                if k in meta
            })
        eps_scheduler.write_warm_log(record)
    except Exception:
        pass


def _refresh_earnings_plus_symbol_worker(sym: str, *, refresh_stale: bool, force_refresh: bool = False) -> dict:
    conn = get_db_connection()
    try:
        entry = _refresh_earnings_plus_cache_for_symbol(
            conn,
            sym,
            fetch_if_missing=True,
            refresh_stale=refresh_stale,
            force_refresh=force_refresh,
        )
        with _earnings_plus_db_write_lock:
            conn.commit()
        return entry
    finally:
        conn.close()


def run_sync_earnings_plus_cache_from_local(
    *,
    symbols: list[str] | None = None,
    quiet: bool = False,
    trigger: str = "local_sync",
) -> dict:
    """
    Recompute Earnings+ for every symbol that has local Screener quarterly data.
    Does not scrape Screener — uses DB cache only so badges match the quarters already stored.
    """
    started_at = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    try:
        ensure_earnings_plus_cache_table(conn)
        if symbols:
            target = [
                sym for sym in dict.fromkeys(_normalize_symbol_token(s) for s in symbols) if sym
            ]
        else:
            try:
                rows = conn.execute(
                    "SELECT DISTINCT symbol FROM screener_quarterly ORDER BY symbol"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            target = [
                _normalize_symbol_token(r[0] if not isinstance(r, sqlite3.Row) else r["symbol"])
                for r in rows
            ]
            target = [s for s in dict.fromkeys(target) if s]
    finally:
        conn.close()

    if not target:
        return {
            "ok": True,
            "trigger": trigger,
            "started_at": started_at,
            "total": 0,
            "qualified": 0,
            "not_qualified": 0,
            "insufficient_data": 0,
        }

    set_job(
        "earnings_plus_cache",
        f"Recomputing Earnings+ from local Screener quarters ({len(target)} symbols)...",
        quiet=quiet,
    )
    qualified = 0
    not_qualified = 0
    insufficient = 0
    errors = 0
    for i, sym in enumerate(target, start=1):
        try:
            conn = get_db_connection()
            try:
                entry = _refresh_earnings_plus_cache_for_symbol(
                    conn,
                    sym,
                    fetch_if_missing=False,
                    refresh_stale=False,
                )
                conn.commit()
            finally:
                conn.close()
            decision = str(entry.get("decision") or "").strip().lower()
            if decision == "qualified":
                qualified += 1
            elif decision == "not_qualified":
                not_qualified += 1
            else:
                insufficient += 1
        except Exception:
            errors += 1
        if i % 100 == 0 or i == len(target):
            set_job(
                "earnings_plus_cache",
                f"Local Earnings+ sync {i}/{len(target)} "
                f"(qualified={qualified}, not={not_qualified}, insufficient={insufficient})...",
                quiet=quiet,
            )

    summary = {
        "ok": errors == 0,
        "trigger": trigger,
        "started_at": started_at,
        "finished_at": datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(target),
        "qualified": qualified,
        "not_qualified": not_qualified,
        "insufficient_data": insufficient,
        "errors": errors,
    }
    finish_job(
        f"Earnings+ local sync: {qualified} qualified / {not_qualified} not / "
        f"{insufficient} insufficient of {len(target)}.",
        meta=summary,
    )
    return summary


def run_refresh_earnings_plus_cache(
    year: int,
    month: int,
    *,
    force: bool = False,
    only_incomplete: bool = False,
    quiet: bool = False,
    trigger: str = "manual",
) -> None:
    started_at = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    period_label = _earnings_plus_period_label(year, month)
    refresh_stale = bool(force)
    try:
        set_job(
            "earnings_plus_cache",
            f"Loading reported earnings symbols for {period_label}...",
            quiet=quiet,
        )
        job_state["meta"] = {
            "year": year,
            "month": month,
            "force": force,
            "only_incomplete": only_incomplete,
            "quiet": quiet,
            "trigger": trigger,
        }
        payload = fetch_earnings_calendar(
            mode="reported",
            year=year,
            month=month,
            limit=2000,
            use_cache=True,
        )
        rows = list(payload.get("rows") or [])
        # One day before TV upcoming prints, start Screener/E+ so data is ready.
        upcoming_rows = _upcoming_prescan_symbols()
        if upcoming_rows:
            existing = {
                _normalize_symbol_token(r.get("symbol"))
                for r in rows
                if _normalize_symbol_token(r.get("symbol"))
            }
            for urow in upcoming_rows:
                sym = _normalize_symbol_token(urow.get("symbol"))
                if sym and sym not in existing:
                    rows.append(urow)
                    existing.add(sym)
        symbols = list(dict.fromkeys(
            sym for sym in (
                _normalize_symbol_token(row.get("symbol"))
                for row in rows
            )
            if sym
        ))
        if not symbols:
            finish_job(
                f"No reported earnings symbols found for {period_label}.",
                meta={
                    "year": year,
                    "month": month,
                    "force": force,
                    "only_incomplete": only_incomplete,
                    "quiet": quiet,
                    "trigger": trigger,
                },
            )
            _record_earnings_plus_warm_run(
                trigger=trigger,
                success=True,
                started_at=started_at,
                year=year,
                month=month,
                message=job_state["message"],
                meta=job_state.get("meta"),
            )
            return

        conn = get_db_connection()
        try:
            ensure_earnings_plus_cache_table(conn)
            entries = _read_earnings_plus_cache_entries(conn, symbols)
            local_period_keys = _read_local_screener_latest_period_keys(conn, symbols)
            to_refresh, skipped = _plan_earnings_plus_cache_refresh(
                entries,
                rows,
                force=force,
                only_incomplete=only_incomplete,
                local_period_keys=local_period_keys,
            )
        finally:
            conn.close()

        if not to_refresh:
            finish_job(
                f"Earnings+ cache for {period_label}: all {len(symbols)} symbols already up to date.",
                meta={
                    "year": year,
                    "month": month,
                    "force": force,
                    "only_incomplete": only_incomplete,
                    "quiet": quiet,
                    "trigger": trigger,
                    "total_symbols": len(symbols),
                    "refreshed": 0,
                    "skipped": skipped,
                },
            )
            _record_earnings_plus_warm_run(
                trigger=trigger,
                success=True,
                started_at=started_at,
                year=year,
                month=month,
                message=job_state["message"],
                meta=job_state.get("meta"),
            )
            return

        job_state["total"] = len(to_refresh)
        qualified_count = 0
        completed = 0
        stalled_pending = 0
        from concurrent.futures import ThreadPoolExecutor, as_completed

        pool = ThreadPoolExecutor(max_workers=EARNINGS_PLUS_REFRESH_WORKERS)
        try:
            futures = {
                pool.submit(
                    _refresh_earnings_plus_symbol_worker,
                    sym,
                    refresh_stale=refresh_stale,
                    force_refresh=bool(force),
                ): sym
                for sym in to_refresh
            }
            pending = set(futures.keys())
            while pending:
                try:
                    fut = next(as_completed(pending, timeout=EARNINGS_PLUS_REFRESH_STALL_SEC))
                except TimeoutError:
                    stalled_pending = len(pending)
                    with _earnings_plus_progress_lock:
                        job_state["message"] = (
                            f"Earnings+ refresh stalled at {completed}/{len(to_refresh)} "
                            f"({stalled_pending} pending symbols skipped after "
                            f"{EARNINGS_PLUS_REFRESH_STALL_SEC}s — often Screener.in slow/rate-limited)"
                        )
                    break
                pending.discard(fut)
                sym = futures[fut]
                try:
                    entry = fut.result()
                    if entry.get("decision") == "qualified":
                        qualified_count += 1
                except Exception:
                    pass
                completed += 1
                with _earnings_plus_progress_lock:
                    job_state["progress"] = completed
                    job_state["message"] = (
                        f"Refreshing Earnings+ cache {completed}/{len(to_refresh)}: {sym}"
                        + (f" ({skipped} skipped)" if skipped else "")
                    )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        skip_note = f", {skipped} skipped (already up to date)" if skipped else ""
        stall_note = (
            f", {stalled_pending} stalled (skipped after {EARNINGS_PLUS_REFRESH_STALL_SEC}s)"
            if stalled_pending
            else ""
        )
        finish_meta = {
            "year": year,
            "month": month,
            "force": force,
            "only_incomplete": only_incomplete,
            "quiet": quiet,
            "trigger": trigger,
            "total_symbols": len(symbols),
            "refreshed": completed,
            "skipped": skipped,
            "stalled": stalled_pending,
            "qualified_in_run": qualified_count,
        }
        finish_job(
            f"Earnings+ cache for {period_label}: refreshed {completed} of {len(to_refresh)} symbols"
            f"{skip_note}{stall_note}, {qualified_count} qualified in this run.",
            meta=finish_meta,
        )
        _record_earnings_plus_warm_run(
            trigger=trigger,
            success=True,
            started_at=started_at,
            year=year,
            month=month,
            message=job_state["message"],
            meta=finish_meta,
        )
    except Exception as e:
        fail_job(str(e))
        _record_earnings_plus_warm_run(
            trigger=trigger,
            success=False,
            started_at=started_at,
            year=year,
            month=month,
            message=job_state.get("message") or str(e),
            meta=dict(job_state.get("meta") or {}),
            error=str(e),
        )


@app.get("/api/admin/earnings-plus-warm-status")
def admin_earnings_plus_warm_status():
    try:
        import earnings_plus_scheduler as eps_scheduler

        return eps_scheduler.read_warm_log()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/refresh-earnings-plus-cache")
def admin_refresh_earnings_plus_cache(
    year: int | None = Query(None, ge=2024),
    month: int | None = Query(None, ge=0, le=12),
    force: bool = Query(False, description="Recompute all reported symbols even if cache is fresh"),
    only_incomplete: bool = Query(
        False,
        description="Only symbols with no cache row or insufficient_data decision",
    ),
):
    now = datetime.now()
    year = year or now.year
    month = month if month is not None else now.month
    result = _start_or_queue_job(
        "earnings_plus_cache",
        lambda: threading.Thread(
            target=run_refresh_earnings_plus_cache,
            args=(year, month),
            kwargs={"force": force, "only_incomplete": only_incomplete, "quiet": False, "trigger": "manual"},
            daemon=True,
        ).start(),
        label="Earnings+ cache refresh",
        source="manual",
    )
    return {
        **result,
        "job": "earnings_plus_cache",
        "year": year,
        "month": month,
        "force": force,
        "only_incomplete": only_incomplete,
    }


@app.post("/api/admin/sync-earnings-plus-from-local")
def admin_sync_earnings_plus_from_local():
    """Recompute Earnings+ badges from local Screener quarterly cache (no scrape)."""
    result = _start_or_queue_job(
        "earnings_plus_cache",
        lambda: threading.Thread(
            target=run_sync_earnings_plus_cache_from_local,
            kwargs={"quiet": False, "trigger": "manual_local_sync"},
            daemon=True,
        ).start(),
        label="Earnings+ local sync",
        source="manual",
    )
    return {**result, "job": "earnings_plus_cache", "mode": "local_sync"}


@app.post("/api/admin/fetch-financials")
def admin_fetch_financials():
    return _start_or_queue_job(
        "financials",
        lambda: threading.Thread(target=run_fetch_financials, daemon=True).start(),
        label="Fetch financials",
        source="manual",
    )


def run_screener_sector_fallback():
    """Background: fill empty nse_industry from Screener.in peer breadcrumb HTML."""
    try:
        set_job("screener_sectors", "Screener.in sector fill (empty rows only)…")
        spec = importlib.util.spec_from_file_location(
            "screener_sector_fallback",
            _sibling_module_path("screener_sector_fallback"),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load screener_sector_fallback")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def on_prog(done: int, tot: int) -> None:
            job_state["progress"] = done
            job_state["total"] = tot

        def on_msg(msg: str) -> None:
            job_state["message"] = msg

        stats = mod.fill_unclassified_from_screener(
            DB_PATH,
            DATA_DIR,
            only_empty_industry=True,
            progress_callback=on_prog,
            message_callback=on_msg,
        )
        exchange_classification_sync.refresh_canonical_sectors_from_db(DATA_DIR, DB_PATH)
        invalidate_stock_df()
        finish_job(
            f"Screener.in sectors: updated {stats['updated']} / {stats['symbols_considered']}, "
            f"no peer data {stats['no_peer_data']}, HTTP errors {stats['failed_http']}."
        )
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/fetch-screener-sectors")
def admin_fetch_screener_sectors():
    return _start_or_queue_job(
        "screener_sectors",
        lambda: threading.Thread(target=run_screener_sector_fallback, daemon=True).start(),
        label="Screener sectors",
        source="manual",
    )


def run_refresh_screener_market_sets():
    """Background: refresh Automobile / Auto Components symbol lists from Screener.in market pages."""
    try:
        set_job("screener_market_sets", "Screener.in market sets (auto sectors)…")
        spec = importlib.util.spec_from_file_location(
            "screener_market_sets",
            _sibling_module_path("screener_market_sets"),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load screener_market_sets")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def on_msg(msg: str) -> None:
            job_state["message"] = msg

        result = mod.refresh_market_sets(DATA_DIR, log=on_msg)
        sets = result.get("sets") or {}
        summary = ", ".join(f"{k}: {len(v)}" for k, v in sets.items())

        expand_spec = importlib.util.spec_from_file_location(
            "screener_universe_expand",
            _sibling_module_path("screener_universe_expand"),
        )
        expand_note = ""
        if expand_spec and expand_spec.loader:
            expand_mod = importlib.util.module_from_spec(expand_spec)
            expand_spec.loader.exec_module(expand_mod)
            expanded = expand_mod.expand_screener_from_market_sets(DATA_DIR, DB_PATH)
            expand_note = f"; universe +{expanded.get('inserted', 0)} NSE symbols"
            invalidate_stock_df()

        finish_job(f"Screener market sets refreshed — {summary}{expand_note}")
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/refresh-screener_market-sets")
def admin_refresh_screener_market_sets():
    return _start_or_queue_job(
        "screener_market_sets",
        lambda: threading.Thread(target=run_refresh_screener_market_sets, daemon=True).start(),
        label="Screener market sets",
        source="manual",
    )


def run_expand_screener_universe():
    """Background: add NSE-listed symbols from market sets missing in screener."""
    try:
        set_job("expand_universe", "Expanding screener universe from market sets…")
        spec = importlib.util.spec_from_file_location(
            "screener_universe_expand",
            _sibling_module_path("screener_universe_expand"),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load screener_universe_expand")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.expand_screener_from_market_sets(DATA_DIR, DB_PATH)
        invalidate_stock_df()
        finish_job(
            f"Universe expand: inserted {result.get('inserted', 0)} symbol(s) "
            f"({len(result.get('skipped_not_nse') or [])} not on NSE EQ/BE/BZ)."
        )
    except Exception as e:
        fail_job(str(e))


@app.post("/api/admin/expand-screener-universe")
def admin_expand_screener_universe():
    return _start_or_queue_job(
        "expand_universe",
        lambda: threading.Thread(target=run_expand_screener_universe, daemon=True).start(),
        label="Expand universe",
        source="manual",
    )


# ──────────────────────────────────────────────
# INDEX ROUTES
# ──────────────────────────────────────────────

@app.get("/api/indices")
def get_indices():
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, name, category, last_price, change_pct, change_30d, change_1y, updated_at
            FROM indices
            ORDER BY
                CASE category
                    WHEN 'equity'     THEN 1
                    WHEN 'commodity'  THEN 2
                    WHEN 'equity_nse' THEN 3
                    ELSE 4
                END,
                name
        """)
        rows = cursor.fetchall()
        syms = [r[0] for r in rows]
        live_map = _index_live_day_change_map(conn, syms)
        conn.close()

        result = []
        for row in rows:
            sym = row[0]
            chg = row[4]
            lk = live_map.get(str(sym).strip())
            if lk is not None:
                chg = lk
            result.append({
                "symbol":      sym,
                "name":        row[1],
                "category":    row[2],
                "last_price":  row[3],
                "change_pct":  chg,
                "change_30d":  row[5],
                "change_1y":   row[6],
                "updated_at":  row[7],
                "chartable":   row[2] in ("equity", "commodity"),
            })
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/index-chart/{symbol:path}")
def get_index_chart(
    symbol:    str,
    timeframe: str           = Query("1D"),
    ema1:      Optional[int] = Query(None),
    ema2:      Optional[int] = Query(None),
    ema3:      Optional[int] = Query(None),
    ema4:      Optional[int] = Query(None),
):
    _ema_periods = [p for p in [ema1, ema2, ema3, ema4] if p is not None]
    _cached      = get_chart_cache(symbol, timeframe, _ema_periods)
    if _cached is not None:
        return _cached
    """Returns OHLCV + indicators for an index."""
    if timeframe not in TIMEFRAME_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe: {timeframe}")

    if timeframe == "4H":
        try:
            conn = get_db_connection()
            from server.bars_4h import (
                format_4h_missing_detail,
                get_bars_4h_source,
                load_bars_4h_for_chart,
            )
            from server.bars_4h_integrity import (
                rescan_rescale_symbol_if_needed,
            )

            rescan_rescale_symbol_if_needed(conn, symbol)
            bars = load_bars_4h_for_chart(conn, symbol, limit=2000)
            day_raw = _index_day_change_pct_single(symbol, conn)
            intraday_source = get_bars_4h_source(conn, symbol)
            missing_detail = (
                format_4h_missing_detail(symbol, conn, is_index=True) if not bars else None
            )
            conn.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        if not bars:
            raise HTTPException(status_code=404, detail=missing_detail)
        day_change_pct = round(float(day_raw), 2) if day_raw is not None and math.isfinite(day_raw) else None
        result = _assemble_chart_result(
            symbol,
            timeframe,
            bars,
            day_change_pct,
            _ema_periods,
            None,
        )
        if intraday_source:
            result["intraday_source"] = intraday_source
        set_chart_cache(symbol, timeframe, _ema_periods, result)
        return result

    if timeframe == "30m":
        try:
            conn = get_db_connection()
            from server.bars_30m import (
                format_30m_missing_detail,
                get_bars_30m_source,
                load_bars_30m_for_chart,
            )

            bars = load_bars_30m_for_chart(conn, symbol, limit=2000)
            day_raw = _index_day_change_pct_single(symbol, conn)
            intraday_source = get_bars_30m_source(conn, symbol)
            missing_detail = (
                format_30m_missing_detail(symbol, conn, is_index=True) if not bars else None
            )
            conn.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        if not bars:
            raise HTTPException(status_code=404, detail=missing_detail)
        day_change_pct = round(float(day_raw), 2) if day_raw is not None and math.isfinite(day_raw) else None
        result = _assemble_chart_result(
            symbol,
            timeframe,
            bars,
            day_change_pct,
            _ema_periods,
            None,
        )
        if intraday_source:
            result["intraday_source"] = intraday_source
        set_chart_cache(symbol, timeframe, _ema_periods, result)
        return result

    try:
        conn   = get_db_connection()
        raw_df = pd.read_sql_query(
            "SELECT SUBSTR(Date,1,10) as Date, Open, High, Low, Close, Volume FROM index_history WHERE Symbol = ? ORDER BY Date ASC",
            conn, params=(symbol,)
        )
        day_raw = _index_day_change_pct_single(symbol, conn)
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No data for index '{symbol}'")

    # Drop non-session daily rows (weekend clones) before weekly/other aggregation.
    try:
        from movers_data import _is_nse_session_day as _session_ok
    except Exception:
        try:
            from server.movers_data import _is_nse_session_day as _session_ok
        except Exception:
            _session_ok = lambda d: d.weekday() < 5  # noqa: E731
    try:
        _days = pd.to_datetime(raw_df["Date"], errors="coerce").dt.date
        raw_df = raw_df[_days.map(lambda d: bool(d and _session_ok(d)))].copy()
    except Exception:
        pass
    if raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No session-day data for index '{symbol}'")

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce").round(2)
    raw_df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)

    try:
        bars = aggregate_ohlcv(raw_df, timeframe)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Aggregation failed: {str(e)}")

    if not bars:
        raise HTTPException(status_code=404, detail=f"No bars for '{symbol}'")

    closes = [b["close"] for b in bars]
    times  = [b["time"]  for b in bars]

    day_change_pct = None
    if day_raw is not None and math.isfinite(day_raw):
        day_change_pct = round(float(day_raw), 2)

    def zip_with_time(values):
        return [{"time": times[i], "value": v} for i, v in enumerate(values) if v is not None and i < len(times)]

    ema_out = {}
    for period in [p for p in [ema1, ema2, ema3, ema4] if p is not None]:
        ema_out[str(period)] = zip_with_time(calculate_ema(closes, period))

    stoch    = calculate_stochrsi(closes)
    macd_data = calculate_macd(closes)

    result = {
        "symbol":    symbol,
        "timeframe": timeframe,
        "bars":      bars,
        "ema":       ema_out,
        "stochrsi":  {"k": zip_with_time(stoch["k"]), "d": zip_with_time(stoch["d"])},
        "macd":      {
            "macd":      zip_with_time(macd_data["macd"]),
            "signal":    zip_with_time(macd_data["signal"]),
            "histogram": zip_with_time(macd_data["histogram"]),
        },
        "day_change_pct": day_change_pct,
    }
    set_chart_cache(symbol, timeframe, _ema_periods, result)
    return result


@app.get("/api/index-constituents/{symbol:path}")
def get_index_constituents(symbol: str):
    import sqlite3 as sq
    from urllib.parse import unquote

    try:
        from server.nse_constituents import NSE_INDEX_MAP, fetch_constituents_for_symbol
    except Exception:
        from nse_constituents import NSE_INDEX_MAP, fetch_constituents_for_symbol

    sym = unquote(str(symbol or "")).strip()
    nse_name = NSE_INDEX_MAP.get(sym)
    if not nse_name:
        return {"data": [], "message": "Constituents not available for this index"}

    conn = sq.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT symbol, market_cap, change_percent, change_percent_monthly FROM screener"
        )
        screener_map = {str(r[0] or "").upper().strip(): r for r in cur.fetchall()}

        rows, _source, err = fetch_constituents_for_symbol(sym, conn)
        if err and not rows:
            raise HTTPException(status_code=502, detail=err)

        stocks = []
        for row in rows:
            row_sym = row["symbol"]
            sc = screener_map.get(str(row_sym).upper().strip())
            ch30 = round(float(sc[3]), 2) if sc and sc[3] is not None else None
            stocks.append({
                "symbol": row_sym,
                "company_name": row.get("company_name", row_sym),
                "market_cap": row.get("market_cap") if row.get("market_cap") is not None else (sc[1] if sc else None),
                "last_price": row.get("last_price"),
                "change_pct": row.get("change_pct"),
                "change_30d": ch30,
                "change_1y": None,
                "volume": None,
                "year_high": None,
                "year_low": None,
            })

        return {"index": nse_name, "data": stocks, "source": _source}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/admin/refresh-indices")
def admin_refresh_indices():
    """Refresh live index prices in background."""

    def run():
        import subprocess as sp
        import sys
        try:
            set_job("indices", "Refreshing index prices...")
            sp.run(
                [sys.executable, str(SCRAPE_INDICES_PATH)],
                timeout=120
            )
            invalidate_stock_df()
            finish_job("Index prices refreshed.")
        except Exception as e:
            fail_job(str(e))

    return _start_or_queue_job(
        "indices",
        lambda: threading.Thread(target=run, daemon=True).start(),
        label="Refresh indices",
        source="manual",
    )


# ──────────────────────────────────────────────
# SCREENER QUARTERLY (Earnings expand panel)
# ──────────────────────────────────────────────

@app.get("/api/screener-quarters/{symbol}")
def get_screener_quarters_api(
    symbol: str,
    basis: str = Query("standalone", description="standalone | consolidated"),
    fetch_if_missing: bool = Query(
        False,
        description="If true and no DB row exists, fetch once from Screener and persist",
    ),
):
    """Read persisted Screener quarterly table; optional lazy fetch when empty."""
    try:
        payload, status = screener_quarters.get_quarters(
            DB_PATH,
            DATA_DIR,
            symbol,
            basis,
            fetch_if_missing=fetch_if_missing,
            force_refresh=False,
        )
        if status == "missing":
            raise HTTPException(
                status_code=404,
                detail="No quarterly data in database. Expand the row to load from Screener.",
            )
        if status == "error":
            err = (payload or {}).get("error", "Failed to fetch from Screener")
            raise HTTPException(status_code=502, detail=str(err))
        conn = get_db_connection()
        try:
            cache_entry = _refresh_earnings_plus_cache_for_symbol(
                conn,
                symbol,
                fetch_if_missing=False,
                refresh_stale=False,
            )
            conn.commit()
        finally:
            conn.close()
        payload = _attach_tv_quarterly_overlay(symbol, payload)
        return {
            "status": status,
            "data": payload,
            "earnings_plus_helper": _build_earnings_plus_helper_from_cache_entry(cache_entry),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener-quarters/{symbol}/refresh")
def refresh_screener_quarters_api(
    symbol: str,
    basis: str = Query("standalone", description="standalone | consolidated"),
):
    """Force refresh quarterly figures for this symbol only."""
    try:
        payload, status = screener_quarters.get_quarters(
            DB_PATH,
            DATA_DIR,
            symbol,
            basis,
            fetch_if_missing=True,
            force_refresh=True,
        )
        if status == "error":
            err = (payload or {}).get("error", "Failed to refresh from Screener")
            raise HTTPException(status_code=502, detail=str(err))
        conn = get_db_connection()
        try:
            cache_entry = _refresh_earnings_plus_cache_for_symbol(
                conn,
                symbol,
                fetch_if_missing=False,
                refresh_stale=False,
            )
            conn.commit()
        finally:
            conn.close()
        payload = _attach_tv_quarterly_overlay(symbol, payload)
        return {
            "status": status,
            "data": payload,
            "earnings_plus_helper": _build_earnings_plus_helper_from_cache_entry(cache_entry),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# FINANCIALS ENDPOINT
# ──────────────────────────────────────────────

@app.get("/api/financials/{symbol}")
def get_financials(symbol: str):
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()

        # Company info
        cursor.execute("""
            SELECT ci.symbol, ci.bse_code, ci.company_name, ci.about,
                   ci.sector, ci.industry,
                   s.market_cap, s.price, s.pe,
                   s.change_percent
            FROM company_info ci
            LEFT JOIN screener s ON s.symbol = ci.symbol
            WHERE ci.symbol = ?
        """, (symbol.upper(),))
        info_row = cursor.fetchone()

        if not info_row:
            # Return basic info from screener even if no financials yet
            cursor.execute("""
                SELECT symbol, NULL, symbol, NULL, NULL, NULL,
                       market_cap, price, pe, change_percent
                FROM screener WHERE symbol = ?
            """, (symbol.upper(),))
            info_row = cursor.fetchone()

        if not info_row:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

        # 52 week high/low from historical_data
        cursor.execute("""
            SELECT MAX(High), MIN(Low)
            FROM historical_data
            WHERE Symbol = ?
            AND Date >= date('now', '-365 days')
        """, (symbol.upper(),))
        hl_row = cursor.fetchone()

        # Quarterly results — latest 8 quarters
        cursor.execute("""
            SELECT period, period_sort, revenue, other_income, total_income,
                   expenditure, interest, pbdt, depreciation, pbt,
                   tax, net_profit, equity, eps, ceps, opm_percent, npm_percent
            FROM quarterly_results
            WHERE symbol = ?
            ORDER BY period_sort DESC
            LIMIT 8
        """, (symbol.upper(),))
        q_rows = cursor.fetchall()

        # Peers — from same sector/index constituents
        cursor.execute("""
            SELECT p.peer_symbol, p.peer_name, p.cmp, p.market_cap, p.pe
            FROM peers p
            WHERE p.symbol = ?
            ORDER BY p.market_cap DESC NULLS LAST
            LIMIT 10
        """, (symbol.upper(),))
        peer_rows = cursor.fetchall()

        conn.close()

        quarterly = []
        for row in q_rows:
            quarterly.append({
                "period":       row[0],
                "period_sort":  row[1],
                "revenue":      row[2],
                "other_income": row[3],
                "total_income": row[4],
                "expenditure":  row[5],
                "interest":     row[6],
                "pbdt":         row[7],
                "depreciation": row[8],
                "pbt":          row[9],
                "tax":          row[10],
                "net_profit":   row[11],
                "equity":       row[12],
                "eps":          row[13],
                "ceps":         row[14],
                "opm_percent":  row[15],
                "npm_percent":  row[16],
            })

        peers = []
        for row in peer_rows:
            peers.append({
                "symbol":     row[0],
                "name":       row[1],
                "cmp":        row[2],
                "market_cap": row[3],
                "pe":         row[4],
            })

        return {
            "symbol":       info_row[0],
            "bse_code":     info_row[1],
            "company_name": info_row[2] or symbol,
            "about":        info_row[3],
            "sector":       info_row[4],
            "industry":     info_row[5],
            "market_cap":   info_row[6],
            "price":        info_row[7],
            "pe":           info_row[8],
            "change_pct":   info_row[9],
            "year_high":    round(float(hl_row[0]), 2) if hl_row and hl_row[0] else None,
            "year_low":     round(float(hl_row[1]), 2) if hl_row and hl_row[1] else None,
            "quarterly":    quarterly,
            "peers":        peers,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# EMA FILTER ENDPOINT
# ──────────────────────────────────────────────

@app.post("/api/filter/ema")
def filter_ema(body: dict):
    """
    Filter stocks by EMA condition.
    body = {
        ema_period: int,          # e.g. 21
        timeframe: str,           # "D", "W", "M"
        condition: str,           # "above"|"above_eq"|"below"|"below_eq"|"crosses_up"|"crosses_down"|"above_pct"|"below_pct"
        pct_value: float,         # only for above_pct/below_pct
        target: str,              # "open"|"high"|"low"|"price"|"ema"
        target_ema_period: int,   # only when target == "ema"
        market_sectors: list,     # optional — restrict to these resolved market sectors
    }
    """
    _cached = get_filter_cache("/api/filter/ema", body)
    if _cached is not None:
        return _cached
    try:
        _t0 = time_module.time()
        sect = _sector_allowed_symbols(body)
        ema_period       = int(body.get("ema_period", 21))
        timeframe        = body.get("timeframe", "1D")
        condition        = body.get("condition", "above")
        pct_value        = float(body.get("pct_value", 0) or 0)
        target           = body.get("target", "price")
        target_ema_period = int(body.get("target_ema_period", 50))

        conn   = get_db_connection()
        cursor = conn.cursor()

        # For daily timeframe use pre-computed values from screener
        tf_unit, tf_num = parse_timeframe(timeframe)

        snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)
        rows = []
        if snapshot_key and ema_period in [9, 21, 50, 100, 200] and (target != "ema" or target_ema_period in [9, 21, 50, 100, 200]):
            snap_rows = _load_filter_snapshots(snapshot_key, sect)
            if not snap_rows or not _snapshots_usable_for_ema_filter(
                snap_rows, ema_period, target, target_ema_period
            ):
                snapshot_key = None
            else:
                rows = []
                for row in snap_rows:
                    ema_curr = row[f"ema{ema_period}"]
                    ema_prev = row[f"ema{ema_period}_prev"]
                    target_curr = None
                    target_prev = None
                    if target == "ema":
                        target_curr = row[f"ema{target_ema_period}"]
                        target_prev = row[f"ema{target_ema_period}_prev"]
                    elif target == "open":
                        target_curr = row["open_curr"]
                        target_prev = row["open_prev"]
                    elif target == "high":
                        target_curr = row["high_curr"]
                        target_prev = row["high_prev"]
                    elif target == "low":
                        target_curr = row["low_curr"]
                        target_prev = row["low_prev"]
                    else:
                        target_curr = row["close_curr"]
                        target_prev = row["close_prev"]
                    rows.append((
                        row["symbol"],
                        row["close_curr"],
                        ema_curr,
                        ema_prev,
                        row["open_curr"],
                        row["high_curr"],
                        row["low_curr"],
                        target_curr,
                        target_prev,
                    ))
        if not snapshot_key:
            # On-demand calculation for non-standard periods or weekly/monthly
            min_period = ema_period
            if target == "ema":
                min_period = max(ema_period, target_ema_period)
            min_bars = min_period + 2
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            symbols = [r[0] for r in cursor.fetchall()]
            rows    = []
            for sym in symbols:
                su = str(sym).strip().upper()
                if sect is not None and su not in sect:
                    continue
                cursor.execute("""
                    SELECT SUBSTR(Date,1,10) as dt, Open, High, Low, Close
                    FROM historical_data
                    WHERE Symbol = ?
                    ORDER BY Date ASC
                """, (sym,))
                candles = cursor.fetchall()
                if len(candles) < min_bars:
                    continue

                candles = apply_filter_timeframe_agg(candles, tf_unit, tf_num)
                candles = [c for c in candles if all(v is not None for v in c)]

                if len(candles) < min_bars:
                    continue

                closes = [c[4] for c in candles]
                ema_vals = calc_ema_series(closes, ema_period)
                if not ema_vals or ema_vals[-1] is None:
                    continue

                last   = candles[-1]
                price  = last[4]
                o, h, l = last[1], last[2], last[3]

                if target == "ema":
                    target_ema = calc_ema_series(closes, target_ema_period)
                    t_curr = target_ema[-1] if target_ema else None
                    t_prev = target_ema[-2] if target_ema and len(target_ema) > 1 else None
                else:
                    t_curr = {"open": o, "high": h, "low": l, "price": price}.get(target, price)
                    t_prev = t_curr

                ema_curr_val = ema_vals[-1] if ema_vals else None
                ema_prev_val = ema_vals[-2] if len(ema_vals) > 1 else None
                if ema_curr_val is None or price is None:
                    continue
                rows.append((sym, price, ema_curr_val, ema_prev_val, o, h, l, t_curr, t_prev))

        conn.close()

        # Apply condition filter
        results = []
        for row in rows:
            try:
                sym, price, ema_curr, ema_prev, o, h, l, t_curr, t_prev = row
                if any(v is None for v in [ema_curr, price, t_curr]):
                    continue
            except Exception:
                continue

            if ema_curr is None or t_curr is None:
                continue

            # Get target value for pre-computed path
            if tf_unit == "D" and tf_num == 1 and ema_period in [9, 21, 50, 100, 200]:
                target_val      = {"open": o, "high": h, "low": l, "price": price, "ema": t_curr}.get(target, price)
                target_val_prev = t_prev if target == "ema" else target_val
            else:
                target_val      = t_curr
                target_val_prev = t_prev

            if ema_curr is None or target_val is None:
                continue

            try:
                matched = False
                if condition == "above":
                    matched = ema_curr > target_val
                elif condition == "above_eq":
                    matched = ema_curr >= target_val
                elif condition == "below":
                    matched = ema_curr < target_val
                elif condition == "below_eq":
                    matched = ema_curr <= target_val
                elif condition == "crosses_up":
                    matched = (ema_prev is not None and target_val_prev is not None and
                              ema_prev <= target_val_prev and ema_curr > target_val)
                elif condition == "crosses_down":
                    matched = (ema_prev is not None and target_val_prev is not None and
                              ema_prev >= target_val_prev and ema_curr < target_val)
                elif condition == "above_pct":
                    # "Above %" means EMA is above target but not more than pct_value away.
                    # This avoids returning symbols that are excessively far from the threshold.
                    if target_val != 0:
                        pct_gap = ((ema_curr - target_val) / abs(target_val)) * 100
                        matched = (ema_curr > target_val) and (pct_gap <= pct_value)
                elif condition == "below_pct":
                    # "Below %" means EMA is below target but not more than pct_value away.
                    if target_val != 0:
                        pct_gap = ((target_val - ema_curr) / abs(target_val)) * 100
                        matched = (ema_curr < target_val) and (pct_gap <= pct_value)
            except (TypeError, ZeroDivisionError):
                continue

            if matched:
                su = str(sym).strip().upper()
                if sect is not None and su not in sect:
                    continue
                results.append(sym)

        elapsed_ms = int((time_module.time() - _t0) * 1000)
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/ema", body, result)
        if elapsed_ms >= 500:
            print(f"[perf] /api/filter/ema -> {elapsed_ms}ms ({len(results)} matches)")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def calc_ema_series(closes, period):
    if len(closes) < period:
        return []
    k      = 2.0 / (period + 1)
    result = [closes[0]]
    for i in range(1, len(closes)):
        result.append(closes[i] * k + result[-1] * (1 - k))
    return result


def aggregate_to_nday(candles, n):
    result = []
    for i in range(0, len(candles), n):
        group = [x for x in candles[i:i+n] if all(v is not None for v in x)]
        if not group:
            continue
        result.append((
            group[0][0],
            group[0][1],
            max(x[2] for x in group),
            min(x[3] for x in group),
            group[-1][4]
        ))
    return result


def _parse_bucket_date(raw_dt):
    s = str(raw_dt)
    # Monthly aggregated keys are "YYYY-MM"
    if len(s) >= 7 and s[4] == "-" and len(s) < 10:
        return datetime.strptime(s[:7] + "-01", "%Y-%m-%d")
    return datetime.strptime(s[:10], "%Y-%m-%d")


def aggregate_to_nperiod(candles, n, unit: str):
    """
    Aggregate candles into fixed calendar buckets so the latest forming bar
    is always the active "last bar" for that timeframe.
    """
    if n <= 1:
        return candles
    groups = {}
    for c in candles:
        try:
            if not all(v is not None for v in c):
                continue
            dt = _parse_bucket_date(c[0])
            if unit == "week":
                # Anchor bi-/multi-week buckets to an absolute Monday baseline.
                anchor = datetime(1970, 1, 5)
                weeks_from_anchor = (dt - anchor).days // 7
                bucket_weeks = (weeks_from_anchor // n) * n
                bucket_start = anchor + timedelta(weeks=bucket_weeks)
            elif unit == "month":
                # Anchor multi-month buckets to absolute month index.
                month_index = dt.year * 12 + (dt.month - 1)
                bucket_index = (month_index // n) * n
                bucket_start = datetime(bucket_index // 12, (bucket_index % 12) + 1, 1)
            else:
                # Day buckets anchored to epoch day.
                anchor = datetime(1970, 1, 1)
                days_from_anchor = (dt - anchor).days
                bucket_days = (days_from_anchor // n) * n
                bucket_start = anchor + timedelta(days=bucket_days)
            key = bucket_start.strftime("%Y-%m-%d")
            groups.setdefault(key, []).append(c)
        except Exception:
            continue
    result = []
    for key in sorted(groups.keys()):
        g = groups[key]
        if not g:
            continue
        result.append((key, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]))
    return result


def aggregate_to_weekly(candles):
    from datetime import datetime, timedelta
    groups = {}
    for c in candles:
        try:
            dt  = datetime.strptime(str(c[0])[:10], "%Y-%m-%d")
            mon = dt - timedelta(days=dt.weekday())
            key = mon.strftime("%Y-%m-%d")
            if key not in groups:
                groups[key] = []
            groups[key].append(c)
        except Exception:
            continue
    result = []
    for key in sorted(groups.keys()):
        g = [x for x in groups[key] if all(v is not None for v in x)]
        if not g:
            continue
        result.append((key, g[0][1], max(x[2] for x in g),
                      min(x[3] for x in g), g[-1][4]))
    return result


def aggregate_to_monthly(candles):
    groups = {}
    for c in candles:
        try:
            key = str(c[0])[:7]
            if key not in groups:
                groups[key] = []
            groups[key].append(c)
        except Exception:
            continue
    result = []
    for key in sorted(groups.keys()):
        g = [x for x in groups[key] if all(v is not None for v in x)]
        if not g:
            continue
        result.append((key, g[0][1], max(x[2] for x in g),
                      min(x[3] for x in g), g[-1][4]))
    return result


def parse_timeframe(timeframe: str) -> tuple:
    """
    Parse timeframe string into (unit, num).
    unit: 'D' | 'W' | 'M' | 'H' | 'm' (minutes). Legacy other minute/hour
    suffixes (e.g. 15m, 1h) map to daily. Canonical 30m is session bars.
    """
    tf = (timeframe or "1D").strip()
    if len(tf) < 2:
        return "D", 1
    # Explicit EOD 30m token — must not be treated as months or legacy daily.
    if tf.lower() == "30m":
        return "m", 30
    suf_raw = tf[-1]
    pre = tf[:-1]
    if not pre.isdigit():
        return "D", 1
    n = int(pre)
    # Lowercase only — avoids treating month "3M" as intraday.
    if suf_raw in ("m", "h"):
        return "D", 1
    suf = suf_raw.upper()
    if suf == "H":
        return "H", n
    if suf == "M":
        return "M", n
    if suf == "W":
        return "W", n
    if suf == "D":
        return "D", n
    return "D", 1


def apply_filter_timeframe_agg(candles, tf_unit: str, tf_num: int):
    """Apply the same timeframe aggregation as chart endpoints for filter candle lists."""
    if tf_unit in ("H", "m"):
        return candles
    if tf_unit == "W":
        c = aggregate_to_weekly(candles)
        return aggregate_to_nperiod(c, tf_num, "week") if tf_num > 1 else c
    if tf_unit == "M":
        c = aggregate_to_monthly(candles)
        return aggregate_to_nperiod(c, tf_num, "month") if tf_num > 1 else c
    if tf_unit == "D" and tf_num > 1:
        return aggregate_to_nperiod(candles, tf_num, "day")
    return candles


def _load_candles_for_symbols(cursor, symbols, chunk_size: int = 400):
    """
    Batch-load historical candles for many symbols in chunks.
    Returns: {SYMBOL: [(dt, open, high, low, close), ...]}
    """
    result = {s: [] for s in symbols}
    if not symbols:
        return result
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        cursor.execute(
            f"SELECT Symbol, SUBSTR(Date,1,10) as dt, Open, High, Low, Close "
            f"FROM historical_data WHERE Symbol IN ({placeholders}) ORDER BY Symbol ASC, Date ASC",
            chunk
        )
        for row in cursor.fetchall():
            sym = row[0]
            if sym in result:
                result[sym].append((row[1], row[2], row[3], row[4], row[5]))
    return result


def _load_filter_candles(cursor, symbols, tf_unit: str, tf_num: int, chunk_size: int = 400):
    if tf_unit == "H" and tf_num == 4:
        from server.bars_4h import load_bars_4h_candles_batch

        conn = cursor.connection
        return load_bars_4h_candles_batch(conn, symbols)
    if tf_unit == "m" and tf_num == 30:
        from server.bars_30m import load_bars_30m_candles_batch

        conn = cursor.connection
        return load_bars_30m_candles_batch(conn, symbols)
    candles = _load_candles_for_symbols(cursor, symbols, chunk_size=chunk_size)
    out = {}
    for sym, rows in candles.items():
        out[sym] = apply_filter_timeframe_agg(rows, tf_unit, tf_num)
    return out


def _assemble_chart_result(
    symbol: str,
    timeframe: str,
    bars: list,
    day_change_pct,
    ema_periods: list,
    bars_limit,
    *,
    lineage_note=None,
    live_today: bool = False,
):
    """Shared chart payload builder for daily-aggregated and 4H bar series."""
    if not bars:
        raise HTTPException(status_code=404, detail=f"No bars for '{symbol}' on '{timeframe}'")

    full_closes = [float(b["close"]) for b in bars]
    trim_start = _chart_payload_trim_start(len(bars), bars_limit, ema_periods)
    trimmed_bars = bars[trim_start:]
    times = [b["time"] for b in trimmed_bars]
    off = trim_start

    def zip_with_time(values: list) -> list:
        return [
            {"time": times[i], "value": v}
            for i, v in enumerate(values)
            if v is not None and i < len(times)
        ]

    def zip_with_time_padded(values: list) -> list:
        result = []
        for i, v in enumerate(values):
            if i >= len(times):
                break
            if v is not None:
                result.append({"time": times[i], "value": v})
        return result

    ema_out = {}
    for period in ema_periods:
        ema_series = calculate_ema(full_closes, period)
        ema_out[str(period)] = zip_with_time(ema_series[off:])

    stoch_full = calculate_stochrsi(full_closes)
    stochrsi = {
        "k": zip_with_time(stoch_full["k"][off:]),
        "d": zip_with_time(stoch_full["d"][off:]),
    }

    macd_data = calculate_macd(full_closes)
    macd_out = {
        "macd":      zip_with_time_padded(macd_data["macd"][off:]),
        "signal":    zip_with_time_padded(macd_data["signal"][off:]),
        "histogram": zip_with_time_padded(macd_data["histogram"][off:]),
    }

    return {
        "symbol":           symbol,
        "timeframe":        timeframe,
        "bars":             trimmed_bars,
        "ema":              ema_out,
        "stochrsi":         stochrsi,
        "macd":             macd_out,
        "day_change_pct":   day_change_pct,
        "live_today_bar":   bool(live_today),
        "lineage_note":     lineage_note,
    }


# ──────────────────────────────────────────────
# MACD FILTER ENDPOINT
# ──────────────────────────────────────────────

@app.post("/api/filter/macd")
def filter_macd(body: dict):
    """
    Filter stocks by MACD condition.
    body = {
        source:       "macd" | "signal" | "histogram",
        timeframe:    str,
        condition:    "above"|"above_eq"|"below"|"below_eq"|"crosses_up"|"crosses_down"|"above_pct"|"below_pct",
        pct_value:    float,
        target:       "value" | "macd" | "signal",
        target_value: float,   # used when target == "value"
        # when source == "histogram":
        chain_mode, histogram_side, bars_to_compare, allowed_stragglers, allow_cross_zero, ...
        market_sectors: list,  # optional
    }
    MACD parameters fixed at fast=12, slow=26, signal=9.
    """
    _cached = get_filter_cache("/api/filter/macd", body)
    if _cached is not None:
        return _cached
    try:
        _t0 = time_module.time()
        sect = _sector_allowed_symbols(body)
        if _macd_filter_hist_chain_only(body):
            return filter_macd_hist_chain(body)
        source       = str(body.get("source",       "macd") or "macd").strip().lower()
        if source not in ("macd", "signal"):
            source = "macd"
        timeframe    = body.get("timeframe",     "1D")
        condition    = body.get("condition",     "above")
        pct_value    = float(body.get("pct_value",    0) or 0)
        target       = body.get("target",        "value")
        target_value = float(body.get("target_value", 0) or 0)

        tf_unit, tf_num = parse_timeframe(timeframe)
        snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)

        MIN_BARS = 26 + 9 + 2  # slow + signal + prev bar buffer

        results = []
        conn = None
        if snapshot_key:
            rows = _load_filter_snapshots(snapshot_key, sect)
            if not rows:
                snapshot_key = None
        if snapshot_key:
            for row in rows:
                try:
                    src_curr = row["macd"] if source == "macd" else row["macd_signal"]
                    src_prev = row["macd_prev"] if source == "macd" else row["macd_signal_prev"]
                    if src_curr is None:
                        continue
                    if target == "value":
                        tgt_curr = target_value
                        tgt_prev = target_value
                    elif target == "macd":
                        tgt_curr = row["macd"]
                        tgt_prev = row["macd_prev"]
                    else:
                        tgt_curr = row["macd_signal"]
                        tgt_prev = row["macd_signal_prev"]
                    if tgt_curr is None:
                        continue
                    matched = False
                    if condition == "above":
                        matched = src_curr > tgt_curr
                    elif condition == "above_eq":
                        matched = src_curr >= tgt_curr
                    elif condition == "below":
                        matched = src_curr < tgt_curr
                    elif condition == "below_eq":
                        matched = src_curr <= tgt_curr
                    elif condition == "crosses_up":
                        matched = (src_prev is not None and tgt_prev is not None and src_prev <= tgt_prev and src_curr > tgt_curr)
                    elif condition == "crosses_down":
                        matched = (src_prev is not None and tgt_prev is not None and src_prev >= tgt_prev and src_curr < tgt_curr)
                    elif condition == "above_pct":
                        matched = tgt_curr != 0 and src_curr > tgt_curr * (1 + pct_value / 100)
                    elif condition == "below_pct":
                        matched = tgt_curr != 0 and src_curr < tgt_curr * (1 - pct_value / 100)
                    if matched and _macd_filter_hist_chain_enabled(body):
                        matched = _macd_hist_chain_matches_snapshot_row(row, body)
                    if matched:
                        results.append(row["symbol"])
                except Exception:
                    continue
        if not snapshot_key:
            conn   = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            symbols = [r[0] for r in cursor.fetchall()]
            if sect is not None:
                symbols = [s for s in symbols if str(s).strip().upper() in sect]
            candles_by_symbol = _load_filter_candles(cursor, symbols, tf_unit, tf_num)

            for sym in symbols:
                try:
                    candles = candles_by_symbol.get(sym, [])
                    if len(candles) < MIN_BARS:
                        continue

                    if not (tf_unit == "H" and tf_num == 4):
                        tf_label = str(timeframe or "1D").strip().upper()
                        candles = chart_candles_for_timeframe(candles, tf_label)

                    if len(candles) < MIN_BARS:
                        continue

                    closes = [float(c[4]) for c in candles]

                    # Calculate MACD series
                    macd_data = calculate_macd(closes, fast=12, slow=26, signal=9)
                    macd_line = macd_data["macd"]
                    sig_line  = macd_data["signal"]

                    # Get last two non-None values for source
                    def last_two(series):
                        valid = [(i, v) for i, v in enumerate(series) if v is not None]
                        if len(valid) < 2:
                            return None, None
                        return valid[-2][1], valid[-1][1]

                    src_prev, src_curr = last_two(macd_line if source == "macd" else sig_line)
                    if src_curr is None:
                        continue

                    # Resolve target value
                    if target == "value":
                        tgt_curr = target_value
                        tgt_prev = target_value
                    elif target == "macd":
                        tgt_prev, tgt_curr = last_two(macd_line)
                    else:  # signal
                        tgt_prev, tgt_curr = last_two(sig_line)

                    if tgt_curr is None:
                        continue

                    # Apply condition
                    matched = False
                    if condition == "above":
                        matched = src_curr > tgt_curr
                    elif condition == "above_eq":
                        matched = src_curr >= tgt_curr
                    elif condition == "below":
                        matched = src_curr < tgt_curr
                    elif condition == "below_eq":
                        matched = src_curr <= tgt_curr
                    elif condition == "crosses_up":
                        matched = (src_prev is not None and tgt_prev is not None
                                   and src_prev <= tgt_prev and src_curr > tgt_curr)
                    elif condition == "crosses_down":
                        matched = (src_prev is not None and tgt_prev is not None
                                   and src_prev >= tgt_prev and src_curr < tgt_curr)
                    elif condition == "above_pct":
                        matched = tgt_curr != 0 and src_curr > tgt_curr * (1 + pct_value / 100)
                    elif condition == "below_pct":
                        matched = tgt_curr != 0 and src_curr < tgt_curr * (1 - pct_value / 100)

                    if matched and _macd_filter_hist_chain_enabled(body):
                        hist = [h for h in macd_data["histogram"] if h is not None]
                        bars_needed = bars_needed_for_filter_def(body)
                        if len(hist) < bars_needed or not evaluate_macd_hist_chain(hist, body):
                            matched = False

                    if matched:
                        results.append(sym)

                except Exception:
                    continue
        if conn is not None:
            conn.close()
        elapsed_ms = int((time_module.time() - _t0) * 1000)
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/macd", body, result)
        if elapsed_ms >= 500:
            print(f"[perf] /api/filter/macd -> {elapsed_ms}ms ({len(results)} matches)")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))




@app.post("/api/filter/macd-hist-chain")
def filter_macd_hist_chain(body: dict):
    """
    Filter symbols by MACD histogram chain over a timeframe.
    """
    _cached = get_filter_cache("/api/filter/macd-hist-chain", body)
    if _cached is not None:
        return _cached
    try:
        _t0 = time_module.time()
        sect = _sector_allowed_symbols(body)
        timeframe = str(body.get("timeframe", "1D") or "1D").strip().upper()
        params = normalize_macd_hist_chain_params(body)
        bars_needed = bars_needed_for_filter_def(body)

        tf_unit, tf_num = parse_timeframe(timeframe)
        snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)

        results = []
        symbols_needing_live = None
        if snapshot_key:
            rows = _load_filter_snapshots(snapshot_key, sect)
            if rows:
                symbols_needing_live = []
                for row in rows:
                    sym = row["symbol"]
                    chain_all = _macd_hist_chain_row_chain(row)
                    if not chain_all or len(chain_all) < bars_needed:
                        symbols_needing_live.append(sym)
                        continue
                    if evaluate_macd_hist_chain(chain_all, body):
                        results.append(sym)
                if not symbols_needing_live:
                    elapsed_ms = int((time_module.time() - _t0) * 1000)
                    result = {"symbols": results, "count": len(results)}
                    set_filter_cache("/api/filter/macd-hist-chain", body, result)
                    if elapsed_ms >= 500:
                        print(f"[perf] /api/filter/macd-hist-chain snapshot -> {elapsed_ms}ms ({len(results)} matches)")
                    return result
            else:
                snapshot_key = None

        if not snapshot_key:
            symbols_needing_live = None

        min_required_agg_bars = 26 + 9 + bars_needed + 4
        conn = get_db_connection()
        cursor = conn.cursor()
        if symbols_needing_live is None:
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            symbols = [r[0] for r in cursor.fetchall()]
            if sect is not None:
                symbols = [s for s in symbols if str(s).strip().upper() in sect]
            live_results = []
        else:
            symbols = symbols_needing_live
            live_results = list(results)
        candles_by_symbol = _load_filter_candles(cursor, symbols, tf_unit, tf_num)
        for sym in symbols:
            try:
                candles = candles_by_symbol.get(sym, [])
                if not candles:
                    continue
                if len(candles) < min_required_agg_bars:
                    continue

                closes = [float(c[4]) for c in candles]
                hist = [h for h in calculate_macd(closes, fast=12, slow=26, signal=9)["histogram"] if h is not None]
                if len(hist) < bars_needed:
                    continue
                if not evaluate_macd_hist_chain(hist, body):
                    continue

                live_results.append(sym)
            except Exception:
                continue
        conn.close()
        results = live_results

        elapsed_ms = int((time_module.time() - _t0) * 1000)
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/macd-hist-chain", body, result)
        if elapsed_ms >= 500:
            print(f"[perf] /api/filter/macd-hist-chain -> {elapsed_ms}ms ({len(results)} matches)")
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# STOCHRSI FILTER ENDPOINT
# ──────────────────────────────────────────────

@app.post("/api/filter/stochrsi")
def filter_stochrsi(body: dict):
    """
    Filter stocks by StochRSI condition.
    body = {
        source:       "k" | "d",
        timeframe:    str,
        condition:    "above"|"above_eq"|"below"|"below_eq"|"crosses_up"|"crosses_down"|"above_pct"|"below_pct",
        pct_value:    float,
        target:       "value" | "k" | "d",
        target_value: float,   # used when target == "value", range 0-100
        market_sectors: list,  # optional
    }
    StochRSI parameters fixed: RSI=14, Stoch=14, K smooth=3, D smooth=3, source=Close.
    """
    _cached = get_filter_cache("/api/filter/stochrsi", body)
    if _cached is not None:
        return _cached
    try:
        _t0 = time_module.time()
        sect = _sector_allowed_symbols(body)
        source       = body.get("source",       "k")
        timeframe    = body.get("timeframe",     "1D")
        condition    = body.get("condition",     "above")
        pct_value    = float(body.get("pct_value",    0) or 0)
        target       = body.get("target",        "value")
        target_value = float(body.get("target_value", 80) or 80)

        tf_unit, tf_num = parse_timeframe(timeframe)
        snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)

        # Minimum bars needed: rsi_period + stoch_period + max(k_smooth, d_smooth) + prev bar
        MIN_BARS = 14 + 14 + 3 + 2

        results = []
        conn = None
        if snapshot_key:
            rows = _load_filter_snapshots(snapshot_key, sect)
            if not rows:
                snapshot_key = None
        if snapshot_key:
            for row in rows:
                try:
                    src_curr = row["stoch_k"] if source == "k" else row["stoch_d"]
                    src_prev = row["stoch_k_prev"] if source == "k" else row["stoch_d_prev"]
                    if src_curr is None:
                        continue
                    if target == "value":
                        tgt_curr = target_value
                        tgt_prev = target_value
                    elif target == "k":
                        tgt_curr = row["stoch_k"]
                        tgt_prev = row["stoch_k_prev"]
                    else:
                        tgt_curr = row["stoch_d"]
                        tgt_prev = row["stoch_d_prev"]
                    if tgt_curr is None:
                        continue
                    matched = False
                    if condition == "above":
                        matched = src_curr > tgt_curr
                    elif condition == "above_eq":
                        matched = src_curr >= tgt_curr
                    elif condition == "below":
                        matched = src_curr < tgt_curr
                    elif condition == "below_eq":
                        matched = src_curr <= tgt_curr
                    elif condition == "crosses_up":
                        matched = (src_prev is not None and tgt_prev is not None and src_prev <= tgt_prev and src_curr > tgt_curr)
                    elif condition == "crosses_down":
                        matched = (src_prev is not None and tgt_prev is not None and src_prev >= tgt_prev and src_curr < tgt_curr)
                    elif condition == "above_pct":
                        matched = tgt_curr != 0 and src_curr > tgt_curr * (1 + pct_value / 100)
                    elif condition == "below_pct":
                        matched = tgt_curr != 0 and src_curr < tgt_curr * (1 - pct_value / 100)
                    if matched:
                        results.append(row["symbol"])
                except Exception:
                    continue
        if not snapshot_key:
            conn   = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            symbols = [r[0] for r in cursor.fetchall()]
            if sect is not None:
                symbols = [s for s in symbols if str(s).strip().upper() in sect]
            candles_by_symbol = _load_filter_candles(cursor, symbols, tf_unit, tf_num)

            for sym in symbols:
                try:
                    candles = candles_by_symbol.get(sym, [])
                    if len(candles) < MIN_BARS:
                        continue

                    closes = [float(c[4]) for c in candles]

                    # Calculate StochRSI (fixed params: RSI=14, Stoch=14, K=3, D=3)
                    stoch = calculate_stochrsi(closes, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3)
                    k_series = stoch["k"]
                    d_series = stoch["d"]

                    # Get last two non-None values for source series
                    def last_two(series):
                        valid = [(i, v) for i, v in enumerate(series) if v is not None]
                        if len(valid) < 2:
                            return None, None
                        return valid[-2][1], valid[-1][1]

                    src_prev, src_curr = last_two(k_series if source == "k" else d_series)
                    if src_curr is None:
                        continue

                    # Resolve target
                    if target == "value":
                        tgt_curr = target_value
                        tgt_prev = target_value
                    elif target == "k":
                        tgt_prev, tgt_curr = last_two(k_series)
                    else:  # d
                        tgt_prev, tgt_curr = last_two(d_series)

                    if tgt_curr is None:
                        continue

                    # Apply condition
                    matched = False
                    if condition == "above":
                        matched = src_curr > tgt_curr
                    elif condition == "above_eq":
                        matched = src_curr >= tgt_curr
                    elif condition == "below":
                        matched = src_curr < tgt_curr
                    elif condition == "below_eq":
                        matched = src_curr <= tgt_curr
                    elif condition == "crosses_up":
                        matched = (src_prev is not None and tgt_prev is not None
                                   and src_prev <= tgt_prev and src_curr > tgt_curr)
                    elif condition == "crosses_down":
                        matched = (src_prev is not None and tgt_prev is not None
                                   and src_prev >= tgt_prev and src_curr < tgt_curr)
                    elif condition == "above_pct":
                        matched = tgt_curr != 0 and src_curr > tgt_curr * (1 + pct_value / 100)
                    elif condition == "below_pct":
                        matched = tgt_curr != 0 and src_curr < tgt_curr * (1 - pct_value / 100)

                    if matched:
                        results.append(sym)

                except Exception:
                    continue
        if conn is not None:
            conn.close()
        elapsed_ms = int((time_module.time() - _t0) * 1000)
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/stochrsi", body, result)
        if elapsed_ms >= 500:
            print(f"[perf] /api/filter/stochrsi -> {elapsed_ms}ms ({len(results)} matches)")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))




# ──────────────────────────────────────────────
# PRICE FILTER ENDPOINT
# ──────────────────────────────────────────────

@app.post("/api/filter/price")
def filter_price(body: dict):
    """
    Filter stocks where price (last close) meets condition vs target.
    body = {
        timeframe:  str,
        condition:  str,
        pct_value:  float,
        target:     "open" | "high" | "low" | "ema",
        ema_period: int,
        market_sectors: list,  # optional
    }
    """
    _cached = get_filter_cache("/api/filter/price", body)
    if _cached is not None:
        return _cached
    try:
        _t0 = time_module.time()
        sect = _sector_allowed_symbols(body)
        timeframe  = body.get("timeframe",  "1D")
        condition  = body.get("condition",  "above")
        pct_value  = float(body.get("pct_value", 0) or 0)
        target     = body.get("target",     "ema")
        ema_period = int(body.get("ema_period", 21))
        tf_unit, tf_num = parse_timeframe(timeframe)
        snapshot_key = _snapshot_timeframe_key(tf_unit, tf_num)

        conn   = get_db_connection()
        cursor = conn.cursor()
        results = []

        # Multi-day price vs open/high/low is a lookback, not a calendar bucket.
        rolling_sessions = (
            price_lookback.rolling_lookback_sessions(tf_unit, tf_num)
            if target in price_lookback.ROLLING_TARGETS
            else None
        )
        if rolling_sessions:
            snapshot_key = None
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            rolling_symbols = [r[0] for r in cursor.fetchall()]
            if sect is not None:
                rolling_symbols = [
                    s for s in rolling_symbols if str(s).strip().upper() in sect
                ]
            results = price_lookback.filter_symbols(
                conn, rolling_symbols, rolling_sessions, target, condition, pct_value
            )

        # Fast path for daily / weekly / monthly filters using precomputed snapshots.
        if snapshot_key and (
            target in {"open", "high", "low"} or
            (target == "ema" and ema_period in [9, 21, 50, 100, 200])
        ):
            rows = _load_filter_snapshots(snapshot_key, sect)
            if not rows:
                snapshot_key = None
            else:
                # 1D price vs open/high/low: always evaluate on latest historical bars.
                # Snapshots often lag a session; list/chart already show fresh OHLC.
                daily_ohlc = None
                if snapshot_key == "1D" and target in {"open", "high", "low"}:
                    daily_ohlc = _load_latest_two_daily_ohlc(conn)
                for row in rows:
                    row = _snapshot_row_as_dict(row)
                    sym = str(row.get("symbol") or "").strip().upper()
                    if daily_ohlc is not None:
                        row = _overlay_daily_ohlc_on_price_snapshot_row(
                            row, daily_ohlc.get(sym)
                        )
                    price_curr = row.get("close_curr")
                    price_prev = row.get("close_prev")
                    if price_curr is None or price_prev is None:
                        continue

                    if target == "open":
                        tgt_curr, tgt_prev = row.get("open_curr"), row.get("open_prev")
                    elif target == "high":
                        tgt_curr, tgt_prev = row.get("high_curr"), row.get("high_prev")
                    elif target == "low":
                        tgt_curr, tgt_prev = row.get("low_curr"), row.get("low_prev")
                    else:  # ema
                        tgt_curr, tgt_prev = row.get(f"ema{ema_period}"), row.get(f"ema{ema_period}_prev")

                    if tgt_curr is None or tgt_prev is None:
                        continue

                    if price_lookback.condition_matches(
                        condition, price_curr, price_prev, tgt_curr, tgt_prev, pct_value
                    ):
                        results.append(sym)
        if not snapshot_key and not rolling_sessions:
            min_bars = ema_period + 2 if target == "ema" else 3
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            symbols = [r[0] for r in cursor.fetchall()]
            if sect is not None:
                symbols = [s for s in symbols if str(s).strip().upper() in sect]
            candles_by_symbol = _load_filter_candles(cursor, symbols, tf_unit, tf_num)

            for sym in symbols:
                try:
                    candles = candles_by_symbol.get(sym, [])
                    if len(candles) < min_bars:
                        continue

                    closes     = [float(c[4]) for c in candles]
                    last       = candles[-1]
                    prev       = candles[-2]
                    price_curr = closes[-1]
                    price_prev = float(prev[4])

                    if target == "ema":
                        ema_vals = calc_ema_series(closes, ema_period)
                        if len(ema_vals) < 2:
                            continue
                        tgt_curr = ema_vals[-1]
                        tgt_prev = ema_vals[-2]
                    elif target == "open":
                        tgt_curr = float(last[1]); tgt_prev = float(prev[1])
                    elif target == "high":
                        tgt_curr = float(last[2]); tgt_prev = float(prev[2])
                    elif target == "low":
                        tgt_curr = float(last[3]); tgt_prev = float(prev[3])
                    else:
                        continue

                    if price_curr is None or tgt_curr is None:
                        continue

                    if price_lookback.condition_matches(
                        condition, price_curr, price_prev, tgt_curr, tgt_prev, pct_value
                    ):
                        results.append(sym)
                except Exception:
                    continue

        conn.close()
        elapsed_ms = int((time_module.time() - _t0) * 1000)
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/price", body, result)
        if elapsed_ms >= 500:
            print(f"[perf] /api/filter/price -> {elapsed_ms}ms ({len(results)} matches)")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter/marketcap")
def filter_marketcap(body: dict):
    """
    Filter stocks by market cap range.
    body = {
        from_value: float | null,
        to_value:   float | null,
        market_sectors: list,  # optional
    }
    """
    _cached = get_filter_cache("/api/filter/marketcap", body)
    if _cached is not None:
        return _cached
    try:
        sect = _sector_allowed_symbols(body)
        from_value = body.get("from_value")
        to_value   = body.get("to_value")

        if from_value is None and to_value is None:
            raise HTTPException(status_code=400, detail="Provide at least one of from_value or to_value")

        conn   = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params     = []
        if from_value is not None:
            conditions.append(f"({_MCAP_SQL}) >= ?")
            params.append(float(from_value))
        if to_value is not None:
            conditions.append(f"({_MCAP_SQL}) <= ?")
            params.append(float(to_value))

        where = " AND ".join(conditions)
        cursor.execute(
            f"SELECT symbol FROM screener WHERE ({_MCAP_SQL}) IS NOT NULL AND {where} ORDER BY {_MCAP_SQL} DESC",
            params
        )
        results = [r[0] for r in cursor.fetchall()]
        conn.close()
        if sect is not None:
            results = [s for s in results if str(s).strip().upper() in sect]
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/marketcap", body, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter/earnings")
def filter_earnings(body: dict):
    """
    Dashboard filter: earnings activity in an IST window.
    body = {
        report_window: 'current_trading_day' | 'previous_day' | 'previous_5_days'
                       | 'this_week' | 'prev_week' | 'next_week' | 'next_day' | 'next_5_days'
                       | 'month_range' | legacy today/yesterday,
        from_year, from_month, to_year, to_month  # required for month_range
        earnings_scope: 'reported' | 'upcoming' | 'both',  # default 'reported'
        eps_surprise_min/max, revenue_surprise_min/max  # reported leg only
        market_sectors: list  # optional
    }
    Current trading day spans last NSE session→today on weekends/holidays so Sat/Sun
    TV prints are included. Previous/next 5 days are calendar days from that anchor.
    Reported matches the last release date, upcoming matches the next one, and both
    unions the two so a window that straddles today catches either side.
    """
    _cached = get_filter_cache("/api/filter/earnings", body)
    if _cached is not None:
        return _cached
    try:
        sect = _sector_allowed_symbols(body)
        report_window = str(body.get("report_window") or "month_range").strip().lower()
        scope = str(body.get("earnings_scope") or "reported").strip().lower()
        if scope not in ("reported", "upcoming", "both"):
            scope = "reported"

        def _opt_float(key: str):
            v = body.get(key)
            if v is None or v == "":
                return None
            return float(v)

        window_kwargs = {
            "report_window": report_window,
            "limit": 2000,
            "use_cache": True,
        }
        if report_window == "month_range":
            window_kwargs["range_from_year"] = int(body.get("from_year"))
            window_kwargs["range_from_month"] = int(body.get("from_month"))
            window_kwargs["range_to_year"] = int(body.get("to_year"))
            window_kwargs["range_to_month"] = int(body.get("to_month"))
        else:
            window_kwargs["year"] = current_year_ist()
            window_kwargs["month"] = current_month_ist()

        results = []
        seen = set()
        for mode in (("reported", "upcoming") if scope == "both" else (scope,)):
            kwargs = {**window_kwargs, "mode": mode}
            if mode == "reported":
                # Surprise % only exists once a quarter is out, so upcoming ignores it.
                kwargs["eps_surprise_min"] = _opt_float("eps_surprise_min")
                kwargs["eps_surprise_max"] = _opt_float("eps_surprise_max")
                kwargs["revenue_surprise_min"] = _opt_float("revenue_surprise_min")
                kwargs["revenue_surprise_max"] = _opt_float("revenue_surprise_max")
            payload = fetch_earnings_calendar(**kwargs)
            for row in payload.get("rows") or []:
                sym = str(row.get("symbol") or "").strip().upper()
                if not sym or sym in seen:
                    continue
                if sect is not None and sym not in sect:
                    continue
                seen.add(sym)
                results.append(sym)
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/earnings", body, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter/annual-vs-ttm")
def filter_annual_vs_ttm(body: dict):
    """
    Dashboard filter: TTM vs last completed FY annual for revenue and/or net income.
    body = {
        metrics: ['total_revenue' | 'net_income', ...],  # one or both; AND when both
        condition: 'ttm_gt_annual' | 'ttm_lt_annual',
        basis: 'consolidated' | 'standalone',  # preferred; falls back to other if missing
        market_sectors: list  # optional
    }
    Uses cached Screener quarterly rows only (no live scrape).
    """
    _cached = get_filter_cache("/api/filter/annual-vs-ttm", body)
    if _cached is not None:
        return _cached
    try:
        normalize_annual_vs_ttm_params(body)
        sect = _sector_allowed_symbols(body)
        conn = get_db_connection()
        try:
            results = query_annual_vs_ttm_symbols(conn, body, sect)
        finally:
            conn.close()
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/annual-vs-ttm", body, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter/screener")
def filter_screener(body: dict):
    """
    Dashboard filter: symbol universe from a saved Screener.in screen URL.
    body = {
        screen_url: str,
        screen_name: str | null,   # optional chip label
        force_refresh: bool,      # bypass SQLite cache
        market_sectors: list,      # optional
    }
    """
    _cached = get_filter_cache("/api/filter/screener", body)
    if _cached is not None:
        return _cached
    try:
        screen_url = str(body.get("screen_url") or "").strip()
        if not screen_url:
            raise HTTPException(status_code=400, detail="screen_url is required")
        screen_name = str(body.get("screen_name") or "").strip() or None
        force_refresh = bool(body.get("force_refresh"))
        sect = _sector_allowed_symbols(body)
        conn = get_db_connection()
        try:
            payload = query_screener_screen_symbols(
                conn,
                screen_url,
                screen_name=screen_name,
                data_dir=DATA_DIR,
                force_refresh=force_refresh,
                sector_symbols=sect,
            )
        finally:
            conn.close()
        result = {
            "symbols": payload.get("symbols") or [],
            "count": int(payload.get("count") or 0),
            "screen_url": payload.get("screen_url"),
            "screen_name": screen_name,
            "fetched_at": payload.get("fetched_at"),
            "source": payload.get("source"),
        }
        set_filter_cache("/api/filter/screener", body, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter/range-channel")
def filter_range_channel(body: dict):
    """
    Horizontal price channel with sustained MACD line above signal.
    Histogram spikes (breakout signature) immediately disqualify — never stragglers.
    """
    _cached = get_filter_cache("/api/filter/range-channel", body)
    if _cached is not None:
        return _cached
    try:
        _t0 = time_module.time()
        sect = _sector_allowed_symbols(body)

        conn = get_db_connection()
        try:
            from range_channel_snapshots_rebuild import query_range_channel_from_snapshots

            snapshot_results = query_range_channel_from_snapshots(conn, body, sect)
            if snapshot_results is not None:
                elapsed_ms = int((time_module.time() - _t0) * 1000)
                result = {"symbols": snapshot_results, "count": len(snapshot_results), "source": "snapshot"}
                set_filter_cache("/api/filter/range-channel", body, result)
                if elapsed_ms >= 500:
                    print(f"[perf] /api/filter/range-channel (snapshot) -> {elapsed_ms}ms ({len(snapshot_results)} matches)")
                return result

            timeframe = str(body.get("timeframe", "3D") or "3D").strip().upper()
            min_bars = bars_needed_for_range_channel(body)
            cursor = conn.cursor()
            cursor.execute(f"SELECT Symbol FROM screener ORDER BY {_MCAP_SQL} DESC NULLS LAST")
            symbols = [r[0] for r in cursor.fetchall()]
            if sect is not None:
                symbols = [s for s in symbols if str(s).strip().upper() in sect]

            candles_by_symbol = _load_candles_for_symbols(cursor, symbols)
            results = []
            eval_body = {**body, "timeframe": timeframe}
            for sym in symbols:
                try:
                    daily = candles_by_symbol.get(sym, [])
                    if len(daily) < min_bars:
                        continue
                    if evaluate_range_channel(daily, eval_body):
                        results.append(sym)
                except Exception:
                    continue
        finally:
            conn.close()

        elapsed_ms = int((time_module.time() - _t0) * 1000)
        result = {"symbols": results, "count": len(results), "source": "live"}
        set_filter_cache("/api/filter/range-channel", body, result)
        if elapsed_ms >= 500:
            print(f"[perf] /api/filter/range-channel -> {elapsed_ms}ms ({len(results)} matches)")
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter/avg-volume")
def filter_avg_volume(body: dict):
    """
    Filter by average daily share volume over the last N sessions.
    body = { period: int, min_volume: float | null, max_volume: float | null, condition, market_sectors }
    """
    _cached = get_filter_cache("/api/filter/avg-volume", body)
    if _cached is not None:
        return _cached
    try:
        sect = _sector_allowed_symbols(body)
        min_volume = body.get("min_volume")
        max_volume = body.get("max_volume")
        if min_volume is None and max_volume is None:
            raise HTTPException(status_code=400, detail="Provide at least min_volume or max_volume")

        conn = get_db_connection()
        try:
            from volume_stats_rebuild import query_avg_volume_from_stats

            results = query_avg_volume_from_stats(conn, body, sect)
            if results is None:
                results = query_avg_volume_symbols(conn, body, sect)
        finally:
            conn.close()
        result = {"symbols": results, "count": len(results)}
        set_filter_cache("/api/filter/avg-volume", body, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _load_movers_data():
    return _load_module_from_path(
        "nse_pulse_movers_data",
        _sibling_module_path("movers_data"),
    )


movers_data = _load_movers_data()
if hasattr(movers_data, "configure_paths"):
    movers_data.configure_paths(data_dir=DATA_DIR)


def _load_movers_live():
    return _load_module_from_path(
        "nse_pulse_movers_live",
        _sibling_module_path("movers_live"),
    )


movers_live = _load_movers_live()


def _load_market_map():
    mod = _load_module_from_path(
        "nse_pulse_market_map",
        _sibling_module_path("market_map"),
    )
    mod.configure(
        get_db_connection,
        _index_live_day_change_map,
        _index_day_change_pct_single,
    )
    return mod


market_map = _load_market_map()


_MOVER_LIMITS = frozenset({20, 50, 100, 200, 400})


def _normalize_movers_limit(limit: int) -> int:
    return limit if limit in _MOVER_LIMITS else 50


def _movers_sector_symbols(market_sectors: str = Query("")) -> Optional[Set[str]]:
    sectors = _parse_json_list_param(market_sectors)
    if not sectors:
        return None
    return _sector_allowed_symbols({"market_sectors": sectors})


def _movers_allowed_symbols(
    market_sectors: str = "",
    *,
    earnings_today: bool = False,
) -> Optional[Set[str]]:
    """
    Optional allow-list for movers ranking.
    None = no symbol filter. Empty set = explicitly no matches.
    """
    sect = _movers_sector_symbols(market_sectors)
    if not earnings_today:
        return sect
    try:
        today_syms = symbols_with_earnings_today()
    except Exception as e:
        print(f"[movers] earnings_today lookup failed: {e}")
        today_syms = set()
    if sect is None:
        return set(today_syms)
    return set(sect) & set(today_syms)


@app.get("/api/market-map/catalog")
def api_market_map_catalog():
    return market_map.catalog_payload()


@app.get("/api/market-map/summary")
def api_market_map_summary(
    period: str = Query("1D"),
    force: bool = Query(False),
):
    period_n = str(period or "1D").strip().upper()
    if period_n != "1D":
        raise HTTPException(status_code=400, detail="Only 1D period is supported in v1")
    try:
        return market_map.get_summary(period=period_n, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market-map/index/{symbol:path}")
def api_market_map_index(
    symbol: str,
    period: str = Query("1D"),
    layout: str = Query("equal"),
    sort: str = Query("major"),
    magnitude: Optional[float] = Query(None),
    force: bool = Query(False),
):
    period_n = str(period or "1D").strip().upper()
    if period_n != "1D":
        raise HTTPException(status_code=400, detail="Only 1D period is supported in v1")
    layout_n = str(layout or "equal").strip().lower()
    if layout_n not in ("equal",):
        layout_n = "equal"
    sort_n = str(sort or "major").strip().lower()
    if sort_n not in ("major", "alpha", "alpha_desc"):
        sort_n = "major"
    try:
        return market_map.get_index_detail(
            symbol,
            period=period_n,
            layout=layout_n,
            magnitude=magnitude,
            sort=sort_n,
            force=force,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/market-map/invalidate-cache")
def api_market_map_invalidate_cache():
    market_map.invalidate_cache()
    return {"status": "ok"}


@app.get("/api/movers/meta")
def api_movers_meta():
    try:
        conn = get_db_connection()
        try:
            return movers_data.movers_meta(conn, _MCAP_SQL)
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/movers/day-change")
def api_movers_day_change(
    side: str = Query("gainers"),
    limit: int = Query(50),
    min_market_cap: Optional[float] = Query(None),
    max_market_cap: Optional[float] = Query(None),
    market_sectors: str = Query(""),
    earnings_today: bool = Query(False),
):
    side_n = str(side or "gainers").strip().lower()
    if side_n not in ("gainers", "losers"):
        side_n = "gainers"
    lim = _normalize_movers_limit(limit)
    allowed = _movers_allowed_symbols(market_sectors, earnings_today=bool(earnings_today))
    try:
        conn = get_db_connection()
        try:
            result = movers_data.query_day_change(
                conn,
                mcap_sql=_MCAP_SQL,
                side=side_n,
                limit=lim,
                min_mcap=min_market_cap,
                max_mcap=max_market_cap,
                allowed_symbols=allowed,
            )
            return result
        finally:
            conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/movers/volume")
def api_movers_volume(
    volume_mode: str = Query("absolute"),
    limit: int = Query(50),
    min_market_cap: Optional[float] = Query(None),
    max_market_cap: Optional[float] = Query(None),
    market_sectors: str = Query(""),
    earnings_today: bool = Query(False),
):
    mode = str(volume_mode or "absolute").strip().lower()
    if mode not in ("absolute", "surge", "rvol"):
        mode = "absolute"
    lim = _normalize_movers_limit(limit)
    allowed = _movers_allowed_symbols(market_sectors, earnings_today=bool(earnings_today))
    try:
        conn = get_db_connection()
        try:
            result = movers_data.query_volume(
                conn,
                mcap_sql=_MCAP_SQL,
                volume_mode=mode,
                limit=lim,
                min_mcap=min_market_cap,
                max_mcap=max_market_cap,
                allowed_symbols=allowed,
            )
            return result
        finally:
            conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/movers/live/status")
def api_movers_live_status():
    try:
        return movers_live.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/movers/live/configure")
def api_movers_live_configure(body: dict = Body(default={})):
    try:
        sec = int(body.get("interval_seconds", body.get("interval", 0)))
        return movers_live.configure_poll_interval(sec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/movers/live/meta")
def api_movers_live_meta():
    try:
        conn = get_db_connection()
        try:
            return movers_live.movers_meta_live(conn, _MCAP_SQL)
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/movers/live/day-change")
def api_movers_live_day_change(
    side: str = Query("gainers"),
    limit: int = Query(50),
    min_market_cap: Optional[float] = Query(None),
    max_market_cap: Optional[float] = Query(None),
    market_sectors: str = Query(""),
    light: bool = Query(False),
    earnings_today: bool = Query(False),
):
    side_n = str(side or "gainers").strip().lower()
    if side_n not in ("gainers", "losers"):
        side_n = "gainers"
    lim = _normalize_movers_limit(limit)
    allowed = _movers_allowed_symbols(market_sectors, earnings_today=bool(earnings_today))
    try:
        conn = get_db_connection()
        try:
            result = movers_live.query_day_change_live(
                conn,
                mcap_sql=_MCAP_SQL,
                side=side_n,
                limit=lim,
                min_mcap=min_market_cap,
                max_mcap=max_market_cap,
                allowed_symbols=allowed,
                refresh_quotes=not light,
            )
            return result
        finally:
            conn.close()
    except TimeoutError as e:
        raise HTTPException(status_code=503, detail="Movers list busy — retry shortly")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/movers/live/volume")
def api_movers_live_volume(
    volume_mode: str = Query("absolute"),
    limit: int = Query(50),
    min_market_cap: Optional[float] = Query(None),
    max_market_cap: Optional[float] = Query(None),
    market_sectors: str = Query(""),
    light: bool = Query(False),
    earnings_today: bool = Query(False),
):
    mode = str(volume_mode or "absolute").strip().lower()
    if mode not in ("absolute", "surge", "rvol"):
        mode = "absolute"
    lim = _normalize_movers_limit(limit)
    allowed = _movers_allowed_symbols(market_sectors, earnings_today=bool(earnings_today))
    try:
        conn = get_db_connection()
        try:
            return movers_live.query_volume_live(
                conn,
                mcap_sql=_MCAP_SQL,
                volume_mode=mode,
                limit=lim,
                min_mcap=min_market_cap,
                max_mcap=max_market_cap,
                allowed_symbols=allowed,
                refresh_quotes=not light,
            )
        finally:
            conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scans/potential-swings")
def scan_potential_swings(body: dict = Body(default={})):
    """
    Potential swing scanners (MACD + StochRSI):
      snapshot timeframe (e.g. 2W): MACD histogram negative and receding, near crossover (epsilon),
      StochRSI K > D (+ optional spread); from ``indicator_snapshots``.
    """
    try:
        screener_key = str(body.get("screener_key", "swing_2w_default")).strip().lower() or "swing_2w_default"
        scan_tf = str(body.get("timeframe", "2W")).strip().upper() or "2W"
        epsilon = float(body.get("epsilon", 0.35) or 0.35)
        min_hist_improve = float(body.get("min_hist_improve", 0.0) or 0.0)
        limit = int(body.get("limit", 300) or 300)
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000

        sector_symbols = _sector_allowed_symbols(body)

        df = get_stock_df().copy()
        stock_by_symbol = {}
        if "Symbol" in df.columns:
            df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
            stock_by_symbol = {str(r["Symbol"]).upper(): r for _, r in df.iterrows()}

        out = []
        stoch_min_spread = float(body.get("stoch_min_spread", 0.0) or 0.0)
        rows = _load_filter_snapshots(scan_tf, sector_symbols)
        for row in rows:
            try:
                sym = str(row["symbol"]).upper().strip()
                macd_curr = row["macd"]
                macd_prev = row["macd_prev"]
                sig_curr = row["macd_signal"]
                sig_prev = row["macd_signal_prev"]
                stoch_k = row["stoch_k"]
                stoch_d = row["stoch_d"]
                if (
                    macd_curr is None
                    or macd_prev is None
                    or sig_curr is None
                    or sig_prev is None
                    or stoch_k is None
                    or stoch_d is None
                ):
                    continue

                hist_prev = float(macd_prev) - float(sig_prev)
                hist_curr = float(macd_curr) - float(sig_curr)
                hist_improve = hist_curr - hist_prev

                if hist_prev >= 0:
                    continue
                if hist_curr >= 0:
                    continue
                if hist_improve < min_hist_improve:
                    continue
                if abs(hist_curr) > epsilon:
                    continue
                if float(stoch_k) <= float(stoch_d) + stoch_min_spread:
                    continue

                stock = stock_by_symbol.get(sym)
                out.append(
                    {
                        "symbol": sym,
                        "timeframe": scan_tf,
                        "hist_prev": round(hist_prev, 6),
                        "hist_curr": round(hist_curr, 6),
                        "hist_improve": round(hist_improve, 6),
                        "near_cross_distance": round(abs(hist_curr), 6),
                        "macd": round(float(macd_curr), 6),
                        "macd_signal": round(float(sig_curr), 6),
                        "stoch_k": round(float(stoch_k), 4),
                        "stoch_d": round(float(stoch_d), 4),
                        "price": float(row["close_curr"]) if row["close_curr"] is not None else None,
                        "change_pct": (float(stock["Change %"]) if stock is not None and pd.notna(stock.get("Change %")) else None),
                        "monthly_change_pct": (float(stock["Monthly Change %"]) if stock is not None and pd.notna(stock.get("Monthly Change %")) else None),
                        "market_cap": (float(stock["Market Cap"]) if stock is not None and pd.notna(stock.get("Market Cap")) else None),
                    }
                )
            except Exception:
                continue
        out.sort(key=lambda x: (x["near_cross_distance"], -x["hist_improve"], x["symbol"]))
        resp_params = {
            "epsilon": epsilon,
            "min_hist_improve": min_hist_improve,
            "stoch_min_spread": stoch_min_spread,
            "limit": limit,
        }

        sliced = out[:limit]
        return {
            "preset": screener_key,
            "timeframe": scan_tf,
            "count": len(sliced),
            "total_matches": len(out),
            "params": resp_params,
            "symbols": sliced,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# FILTER PRESETS ENDPOINTS
# ──────────────────────────────────────────────

def _user_prefs_path(filename: str) -> Path:
    from server.product_config import is_web_host_mode
    from server.user_data_paths import maybe_migrate_legacy_user_files, user_file
    from server.web_auth import get_request_session

    if is_web_host_mode(BASE_DIR):
        session = get_request_session()
        if session:
            maybe_migrate_legacy_user_files(BASE_DIR, session)
            return user_file(BASE_DIR, filename, session)
    return DATA_DIR / filename


def _presets_path() -> Path:
    return _user_prefs_path("saved_filters.json")


def _watchlists_path() -> Path:
    return _user_prefs_path("watchlists.json")


def _portfolio_path() -> Path:
    return _user_prefs_path("portfolio.json")


def _pnl_ledger_path() -> Path:
    return _user_prefs_path("pnl_ledger.json")


def _layout_prefs_path() -> Path:
    return _user_prefs_path("layout.json")


def _user_prefs_lock():
    from server.user_data_paths import user_lock
    return user_lock(BASE_DIR)


_WATCHLISTS_LOCK = threading.Lock()

def _load_presets():
    path = _presets_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_presets(presets):
    path = _presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2, ensure_ascii=False)

@app.get("/api/filter-presets")
def get_filter_presets():
    return {"presets": _load_presets()}

@app.post("/api/filter-presets")
def save_filter_preset(payload: dict):
    name    = payload.get("name", "").strip()
    filters = payload.get("filters", [])
    if not name:
        raise HTTPException(status_code=400, detail="Preset name required")
    if not filters:
        raise HTTPException(status_code=400, detail="No filters to save")
    presets = _load_presets()
    # Replace if name already exists
    presets = [p for p in presets if p["name"] != name]
    presets.append({"name": name, "filters": filters})
    _save_presets(presets)
    return {"status": "saved", "name": name}

@app.delete("/api/filter-presets/{name}")
def delete_filter_preset(name: str):
    presets = _load_presets()
    presets = [p for p in presets if p["name"] != name]
    _save_presets(presets)
    return {"status": "deleted", "name": name}

@app.patch("/api/filter-presets/{name}")
def rename_filter_preset(name: str, payload: dict):
    old_name = str(name or "").strip()
    new_name = str(payload.get("new_name") or "").strip()
    if not old_name:
        raise HTTPException(status_code=400, detail="Preset name required")
    if not new_name:
        raise HTTPException(status_code=400, detail="new_name is required")
    presets = _load_presets()
    if any(
        p["name"].lower() == new_name.lower() and p["name"].lower() != old_name.lower()
        for p in presets
    ):
        raise HTTPException(status_code=409, detail="Preset name already exists")
    found = False
    for p in presets:
        if p["name"] == old_name:
            p["name"] = new_name
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Preset not found")
    _save_presets(presets)
    return {"status": "renamed", "name": new_name}


def _normalize_watchlist_name(name: str) -> str:
    return str(name or "").strip()


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _load_watchlists():
    path = _watchlists_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    cleaned = []
                    for w in data:
                        nm = _normalize_watchlist_name(w.get("name")) if isinstance(w, dict) else ""
                        items = w.get("items", []) if isinstance(w, dict) else []
                        if not nm:
                            continue
                        normalized_items = []
                        for it in items:
                            if not isinstance(it, dict):
                                continue
                            sym = _normalize_symbol(it.get("symbol"))
                            typ = str(it.get("type", "")).strip().lower()
                            if not sym or typ not in ("stock", "index"):
                                continue
                            normalized_items.append({"symbol": sym, "type": typ})
                        dedup = {}
                        for it in normalized_items:
                            dedup[(it["symbol"], it["type"])] = it
                        cleaned.append({
                            "name": nm,
                            "items": list(dedup.values()),
                            "notifications_enabled": bool(w.get("notifications_enabled")),
                        })
                    if cleaned:
                        # Migrate legacy "Default" display name; persist once if changed
                        used_lower = {w["name"].lower() for w in cleaned}
                        changed = False
                        for w in cleaned:
                            if w["name"] != "Default":
                                continue
                            new_name = "My watchlist"
                            suffix = 2
                            while new_name.lower() in used_lower:
                                new_name = f"My watchlist ({suffix})"
                                suffix += 1
                            used_lower.discard("default")
                            used_lower.add(new_name.lower())
                            w["name"] = new_name
                            changed = True
                        if changed:
                            try:
                                _save_watchlists(cleaned)
                            except Exception:
                                pass
                        return cleaned
        except Exception:
            pass
    return []


def _save_watchlists(watchlists):
    path = _watchlists_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(watchlists, f, indent=2, ensure_ascii=False)


def _parse_watchlist_entries(raw_lists) -> list[dict]:
    """Normalize import payload into [{name, items}] (same shape as _load_watchlists)."""
    if not isinstance(raw_lists, list):
        return []
    cleaned: list[dict] = []
    seen_lower: set[str] = set()
    for w in raw_lists:
        if not isinstance(w, dict):
            continue
        nm = _normalize_watchlist_name(w.get("name"))
        if not nm:
            continue
        key = nm.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        items = w.get("items", [])
        normalized_items = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                sym = _normalize_symbol(it.get("symbol"))
                typ = str(it.get("type", "")).strip().lower()
                if not sym or typ not in ("stock", "index"):
                    continue
                normalized_items.append({"symbol": sym, "type": typ})
        dedup: dict[tuple[str, str], dict] = {}
        for it in normalized_items:
            dedup[(it["symbol"], it["type"])] = it
        cleaned.append({
            "name": nm,
            "items": list(dedup.values()),
            "notifications_enabled": bool(w.get("notifications_enabled")),
        })
    return cleaned


def _merge_watchlists_on_import(existing: list[dict], imported: list[dict]) -> list[dict]:
    by_lower = {w["name"].lower(): dict(w) for w in existing}
    for imp in imported:
        key = imp["name"].lower()
        if key in by_lower:
            by_lower[key]["name"] = imp["name"]
            by_lower[key]["items"] = imp["items"]
            if "notifications_enabled" in imp:
                by_lower[key]["notifications_enabled"] = bool(imp.get("notifications_enabled"))
        else:
            by_lower[key] = dict(imp)
    result: list[dict] = []
    seen: set[str] = set()
    for w in existing:
        key = w["name"].lower()
        if key in by_lower and key not in seen:
            result.append(by_lower[key])
            seen.add(key)
    for imp in imported:
        key = imp["name"].lower()
        if key not in seen:
            result.append(by_lower[key])
            seen.add(key)
    return result


def _apply_watchlist_item_order_import(
    existing_order: dict,
    imported_order: dict | None,
    watchlist_names: list[str],
    *,
    replace: bool,
) -> dict:
    names = [_normalize_watchlist_name(n) for n in watchlist_names if _normalize_watchlist_name(n)]
    name_by_lower = {n.lower(): n for n in names}
    if replace:
        out: dict = {}
    else:
        out = {
            k: v for k, v in (existing_order or {}).items()
            if _normalize_watchlist_name(k).lower() in name_by_lower
        }
    if not isinstance(imported_order, dict):
        return out
    for raw_key, raw_val in imported_order.items():
        canon = name_by_lower.get(_normalize_watchlist_name(raw_key).lower())
        if not canon or not isinstance(raw_val, list):
            continue
        cleaned = [str(x).strip() for x in raw_val if str(x).strip()]
        if cleaned:
            out[canon] = cleaned
    return out


def _read_layout_watchlist_item_order() -> dict:
    path = _layout_prefs_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        order = data.get("watchlistItemOrder") if isinstance(data, dict) else None
        return order if isinstance(order, dict) else {}
    except Exception:
        return {}


def _write_layout_watchlist_item_order(order: dict) -> None:
    path = _layout_prefs_path()
    current: dict = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                current = loaded
        except Exception:
            current = {}
    current["watchlistItemOrder"] = order
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)


@app.get("/api/watchlists")
@app.get("/api/watchlists/")
def get_watchlists():
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        return {"watchlists": watchlists}


@app.post("/api/watchlists")
@app.post("/api/watchlists/")
def create_watchlist(payload: dict):
    name = _normalize_watchlist_name(payload.get("name"))
    if not name:
        raise HTTPException(status_code=400, detail="Watchlist name required")
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        if any(w["name"].lower() == name.lower() for w in watchlists):
            raise HTTPException(status_code=409, detail="Watchlist already exists")
        watchlists.append({"name": name, "items": [], "notifications_enabled": False})
        _save_watchlists(watchlists)
    return {"status": "created", "name": name}


@app.post("/api/watchlists/reorder")
@app.post("/api/watchlists/reorder/")
def reorder_watchlists(payload: dict):
    ordered_names = payload.get("ordered_names")
    if not isinstance(ordered_names, list) or not ordered_names:
        raise HTTPException(status_code=400, detail="ordered_names must be a non-empty list")
    normalized = [_normalize_watchlist_name(n) for n in ordered_names if _normalize_watchlist_name(n)]
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        if not watchlists:
            return {"status": "ok", "watchlists": []}
        by_lower = {w["name"].lower(): w for w in watchlists}
        used = set()
        reordered = []
        for name in normalized:
            key = name.lower()
            if key in by_lower and key not in used:
                reordered.append(by_lower[key])
                used.add(key)
        for w in watchlists:
            key = w["name"].lower()
            if key not in used:
                reordered.append(w)
        _save_watchlists(reordered)
    return {"status": "ok", "watchlists": reordered}


@app.post("/api/watchlists/{name:path}/items")
def add_watchlist_item(name: str, payload: dict):
    target = _normalize_watchlist_name(name)
    symbol = _normalize_symbol(payload.get("symbol"))
    item_type = str(payload.get("type", "")).strip().lower()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if item_type not in ("stock", "index"):
        raise HTTPException(status_code=400, detail="type must be 'stock' or 'index'")
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        wl = next((w for w in watchlists if w["name"].lower() == target.lower()), None)
        if not wl:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        exists = any(it["symbol"] == symbol and it["type"] == item_type for it in wl["items"])
        if not exists:
            wl["items"].append({"symbol": symbol, "type": item_type})
            _save_watchlists(watchlists)
    return {"status": "ok", "name": target, "symbol": symbol, "type": item_type}


@app.delete("/api/watchlists/{name:path}/items/{symbol}")
def remove_watchlist_item(name: str, symbol: str, type: Optional[str] = Query(None)):
    target = _normalize_watchlist_name(name)
    symbol_norm = _normalize_symbol(symbol)
    item_type = str(type or "").strip().lower()
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        wl = next((w for w in watchlists if w["name"].lower() == target.lower()), None)
        if not wl:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        before = len(wl["items"])
        if item_type in ("stock", "index"):
            wl["items"] = [it for it in wl["items"] if not (it["symbol"] == symbol_norm and it["type"] == item_type)]
        else:
            wl["items"] = [it for it in wl["items"] if it["symbol"] != symbol_norm]
        if len(wl["items"]) != before:
            _save_watchlists(watchlists)
    return {"status": "ok", "name": target, "symbol": symbol_norm}


# Must be declared AFTER .../items routes: {name:path} would otherwise swallow ".../items/SYM".
@app.delete("/api/watchlists/{name:path}")
def delete_watchlist(name: str):
    target = _normalize_watchlist_name(name)
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        next_watchlists = [w for w in watchlists if w["name"].lower() != target.lower()]
        if len(next_watchlists) == len(watchlists):
            raise HTTPException(status_code=404, detail="Watchlist not found")
        if not next_watchlists:
            next_watchlists = []
        _save_watchlists(next_watchlists)
    return {"status": "deleted", "name": target}


@app.patch("/api/watchlists/{name:path}")
def rename_watchlist(name: str, payload: dict):
    old_name = _normalize_watchlist_name(name)
    new_name = _normalize_watchlist_name(payload.get("new_name"))
    # Settings-only update (notifications_enabled) without rename
    if not new_name and "notifications_enabled" in (payload or {}):
        with _user_prefs_lock():
            watchlists = _load_watchlists()
            found = False
            for w in watchlists:
                if w["name"].lower() == old_name.lower():
                    w["notifications_enabled"] = bool(payload.get("notifications_enabled"))
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            _save_watchlists(watchlists)
        return {"status": "updated", "name": old_name, "notifications_enabled": bool(payload.get("notifications_enabled"))}
    if not new_name:
        raise HTTPException(status_code=400, detail="new_name is required")
    with _user_prefs_lock():
        watchlists = _load_watchlists()
        if any(w["name"].lower() == new_name.lower() and w["name"].lower() != old_name.lower() for w in watchlists):
            raise HTTPException(status_code=409, detail="Watchlist name already exists")
        found = False
        for w in watchlists:
            if w["name"].lower() == old_name.lower():
                w["name"] = new_name
                if "notifications_enabled" in payload:
                    w["notifications_enabled"] = bool(payload.get("notifications_enabled"))
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        _save_watchlists(watchlists)
    return {"status": "renamed", "name": new_name}


@app.post("/api/watchlists/import")
@app.post("/api/watchlists/import/")
def import_watchlists(payload: dict):
    mode = str(payload.get("mode") or "merge").strip().lower()
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="mode must be 'merge' or 'replace'")
    imported = _parse_watchlist_entries(payload.get("watchlists"))
    if not imported:
        raise HTTPException(status_code=400, detail="No valid watchlists found in import")
    imported_order = payload.get("watchlist_item_order")
    if imported_order is not None and not isinstance(imported_order, dict):
        raise HTTPException(status_code=400, detail="watchlist_item_order must be an object")
    with _user_prefs_lock():
        existing = _load_watchlists()
        if mode == "replace":
            merged = imported
        else:
            merged = _merge_watchlists_on_import(existing, imported)
        _save_watchlists(merged)
        names = [w["name"] for w in merged]
        layout_order = _apply_watchlist_item_order_import(
            _read_layout_watchlist_item_order(),
            imported_order,
            names,
            replace=(mode == "replace"),
        )
        _write_layout_watchlist_item_order(layout_order)
    return {
        "status": "imported",
        "mode": mode,
        "count": len(merged),
        "watchlists": merged,
        "watchlist_item_order": layout_order,
    }


# ──────────────────────────────────────────────
# PORTFOLIO (single list — stocks + indices)
# ──────────────────────────────────────────────

_PORTFOLIO_LOCK = threading.Lock()


def _default_portfolio():
    return {"items": []}


def _load_portfolio():
    from server.portfolio_entry import parse_entry_price

    path = _portfolio_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return _default_portfolio()
            raw = data.get("items", [])
            if not isinstance(raw, list):
                return _default_portfolio()
            out = []
            seen = set()
            for it in raw:
                if not isinstance(it, dict):
                    continue
                sym = _normalize_symbol(it.get("symbol"))
                typ = str(it.get("type", "stock")).strip().lower()
                if not sym or typ not in ("stock", "index"):
                    continue
                key = (sym, typ)
                if key in seen:
                    continue
                seen.add(key)
                row = {"symbol": sym, "type": typ}
                entry = parse_entry_price(it.get("entry_price"))
                if entry is not None:
                    row["entry_price"] = entry
                out.append(row)
            return {"items": out}
        except Exception:
            pass
    return _default_portfolio()


def _save_portfolio(data: dict):
    path = _portfolio_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@app.get("/api/portfolio")
def get_portfolio():
    from server.pnl_ledger import reconcile_pnl_portfolio_sync

    with _user_prefs_lock():
        data = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = data.get("items", [])
        sync = reconcile_pnl_portfolio_sync(items, ledger)
        if sync.get("ledger_changed"):
            _save_pnl_ledger(ledger)
        if sync.get("portfolio_changed"):
            _save_portfolio(data)
        return data


@app.post("/api/portfolio/items")
def add_portfolio_item(payload: dict):
    symbol = _normalize_symbol(payload.get("symbol"))
    item_type = str(payload.get("type", "stock")).strip().lower()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if item_type not in ("stock", "index"):
        raise HTTPException(status_code=400, detail="type must be 'stock' or 'index'")
    with _user_prefs_lock():
        data = _load_portfolio()
        exists = any(it["symbol"] == symbol and it["type"] == item_type for it in data["items"])
        if not exists:
            data["items"].append({"symbol": symbol, "type": item_type})
            _save_portfolio(data)
    return {"status": "ok", "symbol": symbol, "type": item_type}


@app.delete("/api/portfolio/items/{symbol:path}")
def remove_portfolio_item(symbol: str, type: str = Query("stock")):
    symbol_norm = _normalize_symbol(symbol)
    item_type = str(type or "stock").strip().lower()
    if item_type not in ("stock", "index"):
        raise HTTPException(status_code=400, detail="type must be stock or index")
    with _user_prefs_lock():
        data = _load_portfolio()
        before = len(data["items"])
        data["items"] = [it for it in data["items"] if not (it["symbol"] == symbol_norm and it["type"] == item_type)]
        if len(data["items"]) != before:
            _save_portfolio(data)
    return {"status": "ok", "symbol": symbol_norm, "type": item_type}


@app.get("/api/portfolio/stocks")
def get_portfolio_stocks(
    page:     int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=500),
    sortBy:   str = Query("Symbol"),
    sortDir:  str = Query("asc"),
    search:   str = Query(""),
    filters:  str = Query(""),
    marketSectors: str = Query(""),
):
    """Screener-shaped rows for portfolio symbols (stocks from screener + index quotes)."""
    _t0 = time_module.time()
    try:
        with _user_prefs_lock():
            items = _load_portfolio()["items"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    stock_syms = [it["symbol"] for it in items if it.get("type") == "stock"]
    index_syms = [it["symbol"] for it in items if it.get("type") == "index"]

    rows_out = []
    active_filters = _parse_json_list_param(filters)
    selected_sectors = [str(x).strip() for x in _parse_json_list_param(marketSectors) if str(x).strip()]

    if stock_syms:
        try:
            df = get_stock_df().copy()
            df = df[df["Symbol"].isin(stock_syms)]
            if search.strip():
                mask = df["Symbol"].str.contains(search.strip().upper(), na=False)
                df = df[mask]
            for col in NUMERIC_DISPLAY_COLUMNS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        for _, row in df.iterrows():
            d = {c: row[c] for c in OUTPUT_COLUMNS if c in df.columns}
            d["instrumentType"] = "stock"
            rows_out.append(d)

    if index_syms:
        conn = get_db_connection()
        cur = conn.cursor()
        idx_live_chg = _index_live_day_change_map(conn, index_syms)
        q = search.strip().upper() if search.strip() else ""
        for sym in index_syms:
            cur.execute(
                "SELECT symbol, name, category, last_price, change_pct, change_30d FROM indices WHERE symbol = ?",
                (sym,),
            )
            r = cur.fetchone()
            if not r:
                continue
            _, name, cat, lp, chg, ch30 = r
            lk = idx_live_chg.get(str(sym).strip())
            if lk is not None:
                chg = lk
            if q:
                blob = f"{sym} {(name or '')}".upper()
                if q not in blob and not sym.upper().startswith(q):
                    continue
            base = {c: None for c in OUTPUT_COLUMNS}
            base["Symbol"] = sym
            base["Market Cap"] = None
            base["Price"] = round(float(lp), 2) if lp is not None else None
            base["Change %"] = round(float(chg), 2) if chg is not None else None
            base["Monthly Change %"] = round(float(ch30), 2) if ch30 is not None else None
            base["PE"] = None
            base["Revenue Growth TTM YoY"] = None
            base["Revenue Growth Quarterly QoQ"] = None
            base["Net Income TTM YoY"] = None
            base["Net Income Quarterly QoQ"] = None
            base["EBITDA Growth Quarterly QoQ"] = None
            base["Market Sector"] = "Index"
            base["instrumentType"] = "index"
            base["indexName"] = name or sym
            base["indexCategory"] = cat or "equity"
            rows_out.append(base)
        conn.close()

    pdf = pd.DataFrame(rows_out)
    if pdf.empty:
        return {"total": 0, "page": page, "pageSize": pageSize, "pages": 1, "data": []}

    if selected_sectors and "Symbol" in pdf.columns:
        allowed_sector_syms = market_sectors.symbol_set_for_market_sectors(
            DATA_DIR, DB_PATH, selected_sectors,
        )
        if allowed_sector_syms is not None:
            pdf = pdf[pdf["Symbol"].isin(allowed_sector_syms)]

    filter_symbols = _combined_filter_symbols(active_filters, selected_sectors)
    if filter_symbols is not None and "Symbol" in pdf.columns:
        pdf = pdf[pdf["Symbol"].isin(filter_symbols)]

    if pdf.empty:
        return {"total": 0, "page": page, "pageSize": pageSize, "pages": 1, "data": []}

    if sortBy not in VALID_SORT_COLUMNS:
        sortBy = "Symbol"
    ascending = sortDir.lower() != "desc"

    pdf = pdf.sort_values(sortBy, ascending=ascending, na_position="last")

    total = len(pdf)
    start = (page - 1) * pageSize
    end = start + pageSize
    page_df = pdf.iloc[start:end]
    records = sanitize_records(page_df.to_dict(orient="records"))
    result = {
        "total":    total,
        "page":     page,
        "pageSize": pageSize,
        "pages":    math.ceil(total / pageSize) if total > 0 else 1,
        "data":     records,
    }
    elapsed_ms = int((time_module.time() - _t0) * 1000)
    if elapsed_ms >= 250:
        print(
            f"[perf] /api/portfolio/stocks -> {elapsed_ms}ms "
            f"(filters={len(active_filters)}, sectors={len(market_sectors)}, total={total})"
        )
    return result


def _load_pnl_ledger():
    from server.pnl_ledger import load_ledger

    return load_ledger(_pnl_ledger_path())


def _save_pnl_ledger(data: dict):
    from server.pnl_ledger import save_ledger

    save_ledger(_pnl_ledger_path(), data)


@app.get("/api/pnl/open")
def get_pnl_open():
    from server.pnl_ledger import build_open_rows, reconcile_pnl_portfolio_sync
    from server.stored_quotes import get_stored_quote_map

    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = portfolio.get("items", [])
        sync = reconcile_pnl_portfolio_sync(items, ledger)
        if sync.get("ledger_changed"):
            _save_pnl_ledger(ledger)
        if sync.get("portfolio_changed"):
            _save_portfolio(portfolio)
    symbols = [
        str(it["symbol"]).strip().upper()
        for it in items
        if isinstance(it, dict) and str(it.get("type", "stock")).strip().lower() == "stock"
    ]
    conn = get_db_connection()
    try:
        quote_map = get_stored_quote_map(conn, symbols, db_path=str(DB_PATH))
    finally:
        conn.close()
    rows = build_open_rows(items, ledger, quote_map)
    as_of_dates = [r.get("as_of_date") for r in rows if r.get("as_of_date")]
    as_of = max(as_of_dates) if as_of_dates else None
    from server.pnl_cash import get_available_cash

    return {
        "data": rows,
        "as_of_date": as_of,
        "available_cash": get_available_cash(ledger),
    }


@app.get("/api/pnl/closed")
def get_pnl_closed():
    from server.pnl_ledger import build_closed_rows, repair_closed_qty_bought

    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        if repair_closed_qty_bought(ledger):
            _save_pnl_ledger(ledger)
    return build_closed_rows(ledger.get("closed_trades", []))


@app.post("/api/pnl/cash/deposit")
def post_pnl_cash_deposit(payload: dict):
    from server.pnl_cash import get_available_cash, record_bank_deposit

    amount = payload.get("amount")
    note = payload.get("note")
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        try:
            record_bank_deposit(ledger, amount, note=note)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
        bal = get_available_cash(ledger)
    return {"status": "ok", "available_cash": bal}


@app.post("/api/pnl/cash/withdraw")
def post_pnl_cash_withdraw(payload: dict):
    from server.pnl_cash import get_available_cash, record_bank_withdrawal

    amount = payload.get("amount")
    note = payload.get("note")
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        try:
            record_bank_withdrawal(ledger, amount, note=note)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
        bal = get_available_cash(ledger)
    return {"status": "ok", "available_cash": bal}


@app.patch("/api/pnl/cash")
def patch_pnl_cash_balance(payload: dict):
    from server.pnl_cash import get_available_cash, set_available_cash_balance

    if "available_cash" not in payload:
        raise HTTPException(status_code=400, detail="available_cash required")
    note = payload.get("note")
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        try:
            set_available_cash_balance(ledger, payload.get("available_cash"), note=note)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
        bal = get_available_cash(ledger)
    return {"status": "ok", "available_cash": bal}


@app.post("/api/pnl/positions")
def post_pnl_position(payload: dict):
    from server.pnl_ledger import add_position

    symbol = payload.get("symbol")
    entry_price = payload.get("entry_price")
    qty = payload.get("qty")
    entry_date = payload.get("entry_date")
    broker = payload.get("broker")
    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        try:
            pos = add_position(
                ledger,
                symbol=symbol,
                entry_price=entry_price,
                qty=qty,
                portfolio_items=portfolio.get("items", []),
                entry_date=entry_date,
                broker=broker,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)
    return {"status": "ok", "position": pos}


@app.patch("/api/pnl/positions/{position_id}")
def patch_pnl_position(position_id: str, payload: dict):
    from server.pnl_ledger import patch_placeholder_or_position, patch_position

    entry_price = payload.get("entry_price") if "entry_price" in payload else None
    qty = payload.get("qty") if "qty" in payload else None
    entry_date = payload.get("entry_date") if "entry_date" in payload else None
    broker = payload.get("broker") if "broker" in payload else None
    if entry_price is None and qty is None and entry_date is None and broker is None:
        raise HTTPException(
            status_code=400,
            detail="entry_price, qty, entry_date, and/or broker required",
        )
    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        pid = str(position_id or "").strip()
        try:
            if pid.startswith("placeholder-"):
                if entry_price is None and qty is None:
                    raise HTTPException(
                        status_code=400,
                        detail="entry_price and/or qty required",
                    )
                pos = patch_placeholder_or_position(
                    ledger,
                    pid,
                    entry_price=entry_price,
                    qty=qty,
                    portfolio_items=portfolio.get("items", []),
                    entry_date=entry_date,
                )
                if broker is not None:
                    from server.pnl_ledger import set_record_broker

                    set_record_broker(pos, broker)
            else:
                pos = patch_position(
                    ledger,
                    pid,
                    entry_price=entry_price,
                    qty=qty,
                    entry_date=entry_date,
                    broker=broker,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)
    return {"status": "ok", "position": pos}


@app.delete("/api/pnl/positions/{position_id}")
def delete_pnl_position(position_id: str):
    from server.pnl_ledger import delete_position, sync_portfolio_entry_from_pnl

    pid = str(position_id or "").strip()
    if pid.startswith("placeholder-"):
        raise HTTPException(status_code=400, detail="cannot delete placeholder row")
    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        sym = None
        for p in ledger.get("positions", []):
            if isinstance(p, dict) and str(p.get("id")) == pid:
                sym = str(p.get("symbol", "")).strip().upper()
                break
        try:
            delete_position(ledger, pid)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if sym:
            sync_portfolio_entry_from_pnl(portfolio.get("items", []), ledger, sym)
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)
    return {"status": "ok"}


@app.post("/api/pnl/broker/symbol")
def post_pnl_symbol_broker(payload: dict):
    """Bulk-tag open lots (and optionally closed trades) for one symbol."""
    from server.pnl_ledger import set_symbol_broker

    symbol = payload.get("symbol")
    broker = payload.get("broker")
    scope = payload.get("scope") or "open"
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        try:
            result = set_symbol_broker(ledger, symbol, broker, scope=scope)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
    return {"status": "ok", **result}


@app.post("/api/pnl/broker/position")
def post_pnl_position_broker(payload: dict):
    """Set broker on one open lot (POST — avoids PATCH/CORS issues on showcase)."""
    from server.pnl_ledger import patch_position

    position_id = payload.get("position_id") or payload.get("id")
    broker = payload.get("broker")
    if not position_id:
        raise HTTPException(status_code=400, detail="position_id required")
    if broker is None:
        raise HTTPException(status_code=400, detail="broker required")
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        try:
            pos = patch_position(ledger, str(position_id), broker=broker)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
    return {"status": "ok", "position": pos}


@app.patch("/api/pnl/closed/{trade_id}")
def patch_pnl_closed_trade(trade_id: str, payload: dict):
    from server.pnl_ledger import set_closed_trade_broker

    if "broker" not in payload:
        raise HTTPException(status_code=400, detail="broker required")
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        try:
            trade = set_closed_trade_broker(ledger, trade_id, payload.get("broker"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_pnl_ledger(ledger)
    return {"status": "ok", "trade": trade}


@app.post("/api/pnl/book")
def post_pnl_book(payload: dict):
    from server.pnl_ledger import (
        book_fifo,
        book_position,
        finalize_symbol_after_book,
        parse_sale_date,
        symbol_open_qty,
        today_sale_date_ist,
    )
    from server.stored_quotes import get_stored_quote_map

    position_id = payload.get("position_id")
    symbol = payload.get("symbol")
    exit_price = payload.get("exit_price")
    qty_sold = payload.get("qty_sold")
    entry_price = payload.get("entry_price")
    sale_date_raw = payload.get("sale_date")
    sale_date = parse_sale_date(sale_date_raw) or today_sale_date_ist()

    if not symbol and not position_id:
        raise HTTPException(status_code=400, detail="symbol or position_id required")

    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        sym = str(symbol or "").strip().upper()
        if not sym and position_id:
            for p in ledger.get("positions", []):
                if isinstance(p, dict) and str(p.get("id")) == str(position_id):
                    sym = str(p.get("symbol", "")).strip().upper()
                    break
        if not sym:
            raise HTTPException(status_code=404, detail="position not found")
        conn = get_db_connection()
        try:
            quote_map = get_stored_quote_map(conn, [sym], db_path=str(DB_PATH))
        finally:
            conn.close()
        try:
            if symbol:
                trades = book_fifo(
                    ledger,
                    symbol=sym,
                    exit_price=exit_price,
                    qty_sold=qty_sold,
                    sale_date=sale_date,
                    quote_snapshot=quote_map.get(sym, {}),
                    portfolio_items=portfolio.get("items", []),
                )
                trade = trades[-1] if trades else None
            else:
                trade = book_position(
                    ledger,
                    position_id=position_id,
                    exit_price=exit_price,
                    qty_sold=qty_sold,
                    sale_date=sale_date,
                    entry_price_override=entry_price,
                    quote_snapshot=quote_map.get(sym, {}),
                    portfolio_items=portfolio.get("items", []),
                )
                trades = [trade]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        portfolio_removed = finalize_symbol_after_book(
            ledger,
            portfolio.get("items", []),
            sym,
        )
        if portfolio_removed or symbol_open_qty(ledger, sym) > 0:
            _save_portfolio(portfolio)
        _save_pnl_ledger(ledger)
    return {
        "status": "ok",
        "trade": trade,
        "trades": trades,
        "portfolio_removed": portfolio_removed,
    }


@app.post("/api/pnl/add-stock")
def post_pnl_add_stock(payload: dict):
    from server.pnl_ledger import add_stock

    symbol = payload.get("symbol")
    entry_price = payload.get("entry_price")
    qty = payload.get("qty")
    entry_date = payload.get("entry_date")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        try:
            pos = add_stock(
                ledger,
                symbol=symbol,
                entry_price=entry_price,
                qty=qty,
                portfolio_items=portfolio.get("items", []),
                entry_date=entry_date,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_portfolio(portfolio)
        _save_pnl_ledger(ledger)
    return {"status": "ok", "position": pos, "symbol": str(symbol).strip().upper()}


@app.post("/api/pnl/import/zerodha/preview")
def post_pnl_import_zerodha_preview(payload: dict):
    from server.zerodha_import import preview_zerodha_import, validate_zerodha_import_inputs

    csv_text = str(payload.get("csv") or payload.get("text") or "")
    rebuild = payload.get("rebuild", False)
    if isinstance(rebuild, str):
        rebuild = rebuild.strip().lower() not in ("0", "false", "no")
    holdings_csv = payload.get("holdings_csv") or payload.get("holdings") or ""
    positions_csv = payload.get("positions_csv") or payload.get("positions") or ""
    reconcile_holdings = payload.get("reconcile_holdings", True)
    import_todays_positions = payload.get("import_todays_positions", False)
    validate_positions_pnl = payload.get("validate_positions_pnl", True)
    apply_corp_actions = payload.get("apply_corp_actions", True)

    reconcile_holdings_b = (
        bool(reconcile_holdings)
        if not isinstance(reconcile_holdings, str)
        else reconcile_holdings.strip().lower() not in ("0", "false", "no")
    )
    import_todays_positions_b = (
        bool(import_todays_positions)
        if not isinstance(import_todays_positions, str)
        else import_todays_positions.strip().lower() not in ("0", "false", "no")
    )
    err = validate_zerodha_import_inputs(
        csv_text,
        str(holdings_csv) if holdings_csv else None,
        str(positions_csv) if positions_csv else None,
        reconcile_holdings=reconcile_holdings_b,
        import_todays_positions=import_todays_positions_b,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        portfolio = _load_portfolio()
        summary = preview_zerodha_import(
            ledger,
            portfolio.get("items", []),
            csv_text=csv_text,
            holdings_csv=str(holdings_csv) if holdings_csv else None,
            positions_csv=str(positions_csv) if positions_csv else None,
            rebuild=bool(rebuild),
            reconcile_holdings=reconcile_holdings_b,
            import_todays_positions=import_todays_positions_b,
            validate_positions_pnl=bool(validate_positions_pnl) if not isinstance(validate_positions_pnl, str) else validate_positions_pnl.strip().lower() not in ("0", "false", "no"),
            apply_corp_actions=bool(apply_corp_actions) if not isinstance(apply_corp_actions, str) else apply_corp_actions.strip().lower() not in ("0", "false", "no"),
            data_dir=DATA_DIR,
        )
    return summary


def _zerodha_import_quote_symbols(
    csv_text: str,
    holdings_csv: str,
    positions_csv: str,
) -> list[str]:
    from server.zerodha_holdings import parse_zerodha_holdings_csv
    from server.zerodha_import import parse_zerodha_tradebook_csv
    from server.zerodha_positions import parse_zerodha_positions_csv

    symbols: set[str] = set()
    if str(csv_text or "").strip():
        rows, _ = parse_zerodha_tradebook_csv(csv_text)
        symbols |= {r["symbol"] for r in rows if r.get("symbol")}
    if str(holdings_csv or "").strip():
        rows, _ = parse_zerodha_holdings_csv(holdings_csv)
        symbols |= {r["symbol"] for r in rows if r.get("symbol")}
    if str(positions_csv or "").strip():
        rows, _ = parse_zerodha_positions_csv(positions_csv)
        symbols |= {r["symbol"] for r in rows if r.get("symbol")}
    return sorted(symbols)


@app.post("/api/pnl/import/zerodha")
def post_pnl_import_zerodha(payload: dict):
    from server.pnl_ledger import consolidate_open_lots, reconcile_pnl_portfolio_sync
    from server.stored_quotes import get_stored_quote_map
    from server.zerodha_import import run_zerodha_import_pipeline, validate_zerodha_import_inputs

    csv_text = str(payload.get("csv") or payload.get("text") or "")
    rebuild = payload.get("rebuild", False)
    if isinstance(rebuild, str):
        rebuild = rebuild.strip().lower() not in ("0", "false", "no")
    holdings_csv = payload.get("holdings_csv") or payload.get("holdings") or ""
    positions_csv = payload.get("positions_csv") or payload.get("positions") or ""
    reconcile_holdings = payload.get("reconcile_holdings", True)
    import_todays_positions = payload.get("import_todays_positions", False)
    validate_positions_pnl = payload.get("validate_positions_pnl", True)
    apply_corp_actions = payload.get("apply_corp_actions", True)

    reconcile_holdings_b = (
        bool(reconcile_holdings)
        if not isinstance(reconcile_holdings, str)
        else reconcile_holdings.strip().lower() not in ("0", "false", "no")
    )
    import_todays_positions_b = (
        bool(import_todays_positions)
        if not isinstance(import_todays_positions, str)
        else import_todays_positions.strip().lower() not in ("0", "false", "no")
    )
    err = validate_zerodha_import_inputs(
        csv_text,
        str(holdings_csv) if holdings_csv else None,
        str(positions_csv) if positions_csv else None,
        reconcile_holdings=reconcile_holdings_b,
        import_todays_positions=import_todays_positions_b,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = portfolio.get("items", [])

        symbols = _zerodha_import_quote_symbols(csv_text, str(holdings_csv), str(positions_csv))
        quote_map: dict = {}
        if symbols:
            conn = get_db_connection()
            try:
                quote_map = get_stored_quote_map(conn, symbols, db_path=str(DB_PATH))
            finally:
                conn.close()

        summary = run_zerodha_import_pipeline(
            ledger,
            items,
            csv_text=csv_text,
            holdings_csv=str(holdings_csv) if holdings_csv else None,
            positions_csv=str(positions_csv) if positions_csv else None,
            quote_map=quote_map,
            dry_run=False,
            rebuild=bool(rebuild),
            reconcile_holdings=reconcile_holdings_b,
            import_todays_positions=import_todays_positions_b,
            validate_positions_pnl=bool(validate_positions_pnl) if not isinstance(validate_positions_pnl, str) else validate_positions_pnl.strip().lower() not in ("0", "false", "no"),
            apply_corp_actions=bool(apply_corp_actions) if not isinstance(apply_corp_actions, str) else apply_corp_actions.strip().lower() not in ("0", "false", "no"),
            data_dir=DATA_DIR,
        )
        if not summary.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=summary.get("errors") or summary.get("parse_errors") or "import failed",
            )

        reconcile_pnl_portfolio_sync(items, ledger)
        consolidated = consolidate_open_lots(ledger)
        if consolidated:
            summary["lots_consolidated"] = summary.get("lots_consolidated", 0) + consolidated
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)

    return {"status": "ok", **summary}


@app.post("/api/pnl/import/zerodha/holdings/preview")
def post_pnl_import_zerodha_holdings_preview(payload: dict):
    from server.zerodha_import import reconcile_holdings_only

    holdings_csv = str(payload.get("holdings_csv") or payload.get("csv") or payload.get("text") or "")
    if not holdings_csv.strip():
        raise HTTPException(status_code=400, detail="holdings_csv text required")
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        portfolio = _load_portfolio()
        summary = reconcile_holdings_only(
            ledger,
            portfolio.get("items", []),
            holdings_csv,
            dry_run=True,
        )
    return summary


@app.post("/api/pnl/import/zerodha/holdings")
def post_pnl_import_zerodha_holdings(payload: dict):
    from server.zerodha_import import reconcile_holdings_only

    holdings_csv = str(payload.get("holdings_csv") or payload.get("csv") or payload.get("text") or "")
    if not holdings_csv.strip():
        raise HTTPException(status_code=400, detail="holdings_csv text required")
    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = portfolio.get("items", [])
        summary = reconcile_holdings_only(
            ledger,
            items,
            holdings_csv,
            dry_run=False,
        )
        if not summary.get("ok"):
            raise HTTPException(status_code=400, detail=summary.get("holdings_parse_errors") or "holdings sync failed")
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)
    return {"status": "ok", **summary}


@app.post("/api/pnl/import/zerodha/tax-pnl/preview")
def post_pnl_import_zerodha_tax_pnl_preview(payload: dict):
    """Preview a full Zerodha broker replacement (no write)."""
    from server.excel_table import resolve_tax_pnl_csv_from_payload
    from server.zerodha_tax_pnl import preview_zerodha_tax_pnl

    try:
        csv_text = resolve_tax_pnl_csv_from_payload(payload or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    holdings_csv = payload.get("holdings_csv") or payload.get("holdings") or ""
    reconcile_holdings = payload.get("reconcile_holdings", False)

    def _as_bool(v, default=False):
        if v is None:
            return default
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no")
        return bool(v)

    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        portfolio = _load_portfolio()
        summary = preview_zerodha_tax_pnl(
            ledger,
            portfolio.get("items", []),
            csv_text,
            replace_zerodha_closed=True,
            apply_open_from_file=True,
            full_broker_replace=True,
            holdings_csv=str(holdings_csv) if holdings_csv else None,
            reconcile_holdings=_as_bool(reconcile_holdings, False),
        )
    if payload.get("_resolved_sheet"):
        summary["excel_sheet"] = payload["_resolved_sheet"]
    return summary


@app.post("/api/pnl/import/zerodha/tax-pnl")
def post_pnl_import_zerodha_tax_pnl(payload: dict):
    """Atomically replace all Zerodha P&L from Tax/Console P&L CSV or Excel."""
    from server.excel_table import resolve_tax_pnl_csv_from_payload
    from server.pnl_ledger import consolidate_open_lots, reconcile_pnl_portfolio_sync
    from server.zerodha_tax_pnl import run_zerodha_tax_pnl_import

    try:
        csv_text = resolve_tax_pnl_csv_from_payload(payload or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    holdings_csv = payload.get("holdings_csv") or payload.get("holdings") or ""
    reconcile_holdings = payload.get("reconcile_holdings", False)
    confirmation = str(payload.get("confirm_broker_replace") or "").strip().lower()
    if confirmation != "zerodha":
        raise HTTPException(
            status_code=400,
            detail="Confirm full Zerodha broker replacement before importing",
        )

    def _as_bool(v, default=False):
        if v is None:
            return default
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no")
        return bool(v)

    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = portfolio.get("items", [])
        summary = run_zerodha_tax_pnl_import(
            ledger,
            items,
            csv_text,
            replace_zerodha_closed=True,
            apply_open_from_file=True,
            full_broker_replace=True,
            holdings_csv=str(holdings_csv) if holdings_csv else None,
            reconcile_holdings=_as_bool(reconcile_holdings, False),
        )
        if not summary.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=summary.get("errors") or summary.get("parse_errors") or "Tax P&L import failed",
            )
        reconcile_pnl_portfolio_sync(items, ledger)
        consolidated = consolidate_open_lots(ledger)
        if consolidated:
            summary["lots_consolidated"] = consolidated
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)
    if isinstance(payload, dict) and payload.get("_resolved_sheet"):
        summary["excel_sheet"] = payload["_resolved_sheet"]
    return {"status": "ok", **summary}


@app.post("/api/pnl/repair/duplicate-closes")
def post_pnl_repair_duplicate_closes(payload: dict | None = None):
    """Remove double-booked closed trades (manual/positions + Zerodha re-import)."""
    from server.pnl_repair_duplicates import repair_duplicate_closed_trades

    dry_run = bool((payload or {}).get("dry_run"))
    with _user_prefs_lock():
        ledger = _load_pnl_ledger()
        if dry_run:
            import copy

            summary = repair_duplicate_closed_trades(copy.deepcopy(ledger))
            return {"status": "ok", "dry_run": True, **summary}
        summary = repair_duplicate_closed_trades(ledger)
        _save_pnl_ledger(ledger)
    return {"status": "ok", "dry_run": False, **summary}


@app.post("/api/pnl/repair/consolidate-lots")
def post_pnl_repair_consolidate_lots(payload: dict | None = None):
    """Fold duplicate open lots (same symbol, entry date, entry price). Repairs post-import clutter."""
    from server.pnl_ledger import consolidate_open_lots, reconcile_pnl_portfolio_sync

    payload = payload or {}
    symbol = str(payload.get("symbol") or "").strip().upper() or None

    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = portfolio.get("items", [])
        removed = consolidate_open_lots(ledger, symbol=symbol)
        reconcile_pnl_portfolio_sync(items, ledger)
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)

    return {"status": "ok", "lots_consolidated": removed, "symbol": symbol}


@app.post("/api/pnl/repair/bonus-1-2")
def post_pnl_repair_bonus_1_2(payload: dict | None = None):
    """Apply 1:2 bonus to open lots for one symbol (qty up, entry price down)."""
    from server.pnl_ledger import apply_bonus_1_2, reconcile_pnl_portfolio_sync

    payload = payload or {}
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")

    with _user_prefs_lock():
        portfolio = _load_portfolio()
        ledger = _load_pnl_ledger()
        items = portfolio.get("items", [])
        result = apply_bonus_1_2(ledger, symbol)
        reconcile_pnl_portfolio_sync(items, ledger)
        _save_pnl_ledger(ledger)
        _save_portfolio(portfolio)

    return {"status": "ok", "symbol": symbol, **result}


@app.get("/api/sector-mapping")
def get_sector_mapping():
    """Rules + symbol overrides + canonical list for UI editors."""
    market_sectors.ensure_default_mapping_file(DATA_DIR)
    data = market_sectors.load_mapping(DATA_DIR)
    try:
        try:
            from server import index_industry_sectors as _iis
        except ImportError:
            import index_industry_sectors as _iis

        cores_meta = _iis.index_cores_meta()
    except Exception:
        cores_meta = {}
    return {
        "canonical_sectors": data.get("canonical_sectors") or market_sectors.canonical_sectors_for_ui(),
        "sector_groups": market_sectors.sector_dropdown_groups_for_ui(),
        "rules":             data.get("rules") or [],
        "symbol_overrides":  data.get("symbol_overrides") or {},
        "use_exchange_labels": bool(data.get("use_exchange_labels", True)),
        "macro_sector_schema_version": int(data.get("macro_sector_schema_version") or 0),
        "index_cores_meta": cores_meta,
    }


@app.post("/api/sector-mapping")
def post_sector_mapping(payload: dict):
    """Replace rules and symbol_overrides (validated lightly)."""
    rules = payload.get("rules")
    overrides = payload.get("symbol_overrides")
    canon = payload.get("canonical_sectors")
    use_ex = payload.get("use_exchange_labels")
    if rules is None and overrides is None and canon is None and use_ex is None:
        raise HTTPException(
            status_code=400,
            detail="Provide rules, symbol_overrides, canonical_sectors, and/or use_exchange_labels",
        )
    current = market_sectors.load_mapping(DATA_DIR)
    if rules is not None:
        if not isinstance(rules, list):
            raise HTTPException(status_code=400, detail="rules must be a list")
        clean = []
        for r in rules:
            if not isinstance(r, dict):
                continue
            field = str(r.get("field", "industry")).strip().lower()
            if field not in ("sector", "industry"):
                field = "industry"
            rtype = str(r.get("type", "contains")).strip().lower()
            if rtype not in ("contains", "equals", "regex"):
                rtype = "contains"
            pattern = str(r.get("pattern", "")).strip()
            sector_raw = str(r.get("sector", "")).strip()
            if not pattern or not sector_raw:
                continue
            sector = market_sectors.remap_to_macro_sector(sector_raw)
            clean.append({"field": field, "type": rtype, "pattern": pattern, "sector": sector})
        current["rules"] = clean
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise HTTPException(status_code=400, detail="symbol_overrides must be an object")
        coerced_ov: dict = {}
        for k, v in overrides.items():
            ku = str(k).strip().upper()
            vv = str(v).strip() if v is not None else ""
            if not ku or not vv:
                continue
            coerced_ov[ku] = market_sectors.remap_to_macro_sector(vv)
        current["symbol_overrides"] = coerced_ov
    if canon is not None:
        if not isinstance(canon, list):
            raise HTTPException(status_code=400, detail="canonical_sectors must be a list")
        allowed = set(market_sectors.MACRO_ECONOMIC_SECTORS) | {market_sectors.UNCLASSIFIED}
        filtered = [x for x in (str(s).strip() for s in canon) if x in allowed]
        current["canonical_sectors"] = (
            filtered
            if filtered
            else list(market_sectors.MACRO_ECONOMIC_SECTORS) + [market_sectors.UNCLASSIFIED]
        )
    if use_ex is not None:
        current["use_exchange_labels"] = bool(use_ex)
    market_sectors.save_mapping(DATA_DIR, current)
    invalidate_stock_df()
    return {"status": "saved"}


@app.post("/api/sector-index-cores/refresh")
def post_refresh_sector_index_cores():
    """Fetch Nifty index constituents for hybrid Market Sector tags and cache them."""
    try:
        result = market_sectors.refresh_index_sector_cores(DATA_DIR, DB_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    invalidate_stock_df()
    return result


@app.post("/api/sync-exchange-classification")
def post_sync_exchange_classification(payload: dict = Body(default_factory=dict)):
    """
    Download NSE official index CSVs (Industry column), optionally merge a local BSE table,
    update screener.nse_sector / nse_industry, and refresh canonical_sectors when requested.
    """
    cfg = exchange_classification_sync.load_sync_config(DATA_DIR)
    urls = payload.get("nse_csv_urls") or cfg.get("nse_csv_urls") or list(
        exchange_classification_sync.DEFAULT_NSE_INDUSTRY_CSV_URLS
    )
    ua = str(payload.get("user_agent") or cfg.get("user_agent") or exchange_classification_sync.DEFAULT_USER_AGENT)
    bse_key = payload.get("bse_local_path") or cfg.get("bse_local_path")
    bse_path = Path(bse_key) if bse_key else None
    if bse_path is not None and not bse_path.is_file():
        bse_path = DATA_DIR / bse_path if not bse_path.is_absolute() else bse_path
    refresh = bool(payload.get("refresh_canonical", True))
    skip_el = bool(payload.get("skip_equity_l") or cfg.get("skip_equity_l"))
    ne_url = payload.get("nse_equity_l_url") or cfg.get("nse_equity_l_url")
    try:
        result = exchange_classification_sync.run_sync(
            DATA_DIR,
            DB_PATH,
            nse_urls=urls if isinstance(urls, list) else list(urls),
            bse_local_path=bse_path if bse_path and bse_path.is_file() else None,
            user_agent=ua,
            refresh_canonical=refresh,
            skip_equity_l=skip_el,
            nse_equity_l_url=str(ne_url).strip() if ne_url else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    invalidate_stock_df()
    return result


@app.post("/api/screener-classification")
def post_screener_classification(payload: dict):
    """Set nse_sector / nse_industry for one or more symbols (feeds mapping rules)."""
    updates = payload.get("updates")
    if not updates and payload.get("symbol"):
        updates = [{
            "symbol":       payload.get("symbol"),
            "nse_sector":   payload.get("nse_sector"),
            "nse_industry": payload.get("nse_industry"),
        }]
    if not updates or not isinstance(updates, list):
        raise HTTPException(status_code=400, detail="Provide updates array or symbol + fields")
    conn = get_db_connection()
    cur = conn.cursor()
    n = 0
    for u in updates:
        if not isinstance(u, dict):
            continue
        sym = str(u.get("symbol", "")).strip().upper()
        if not sym:
            continue
        ns = u.get("nse_sector")
        ni = u.get("nse_industry")
        if ns is not None and not isinstance(ns, (str, type(None))):
            continue
        if ni is not None and not isinstance(ni, (str, type(None))):
            continue
        cur.execute(
            "UPDATE screener SET nse_sector = ?, nse_industry = ? WHERE symbol = ?",
            (ns, ni, sym),
        )
        if cur.rowcount:
            n += 1
    conn.commit()
    conn.close()
    invalidate_stock_df()
    return {"status": "ok", "rows_updated": n}


def _require_dev_tree_for_kb_edit():
    from server import app_code_crypto as _app_code_crypto

    if not _app_code_crypto.is_development_tree(BASE_DIR):
        raise HTTPException(
            status_code=403,
            detail="Knowledge Base editing is only available in the development tree.",
        )


@app.get("/api/knowledge-base/pages")
def knowledge_base_list_pages():
    return {"pages": knowledge_base.list_pages_meta()}


@app.get("/api/knowledge-base/{guide_id}")
def knowledge_base_get_page(guide_id: str):
    try:
        page = knowledge_base.get_page(DATA_DIR, guide_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return page


@app.put("/api/dev/knowledge-base/{guide_id}")
def knowledge_base_put_page(guide_id: str, payload: dict = Body(...)):
    _require_dev_tree_for_kb_edit()
    try:
        page = knowledge_base.put_page(DATA_DIR, guide_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "page": page}


@app.get("/api/market-data-version")
def get_market_data_version_api():
    """Signed-in clients poll to invalidate local intraday patches after host EOD."""
    from server import market_data_version as mdv

    ver = mdv.get_version(DB_PATH)
    ver["session_intraday_allowed"] = movers_data._session_day_intraday_active()
    return ver


@app.get("/api/intraday-patch")
def get_intraday_patch_api(
    symbols: str = Query("", description="Comma-separated NSE symbols"),
):
    from server.intraday_overlay import fetch_patch

    sym_list = [s.strip() for s in str(symbols or "").split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(status_code=400, detail="symbols query parameter required")
    return fetch_patch(sym_list)


@app.post("/api/intraday-patch")
async def post_intraday_patch_api(payload: dict = Body(...)):
    from datetime import datetime, timedelta, timezone

    from fastapi.concurrency import run_in_threadpool
    from server.intraday_overlay import fetch_patch

    raw = payload.get("symbols")
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=400, detail="symbols array required")
    try:
        return await run_in_threadpool(fetch_patch, raw)
    except Exception as e:
        ist = timezone(timedelta(hours=5, minutes=30))
        return {
            "as_of": datetime.now(ist).isoformat(),
            "symbols": {},
            "requested": len(raw),
            "returned": 0,
            "nse_error": str(e),
            "session_intraday": False,
        }


@app.post("/api/admin/run-eod-reconcile")
def run_eod_reconcile_admin():
    """Host-only: overlay screener price/1D% from NSE bhavcopy (does not modify chart OHLC)."""
    import eod_reconcile as _eod_reconcile

    screener_updated = _eod_reconcile.run_eod_bhavcopy_reconcile(
        DB_PATH,
        log_fn=lambda m: print(m, flush=True),
    )
    st = _eod_reconcile.last_reconcile_status()
    from server import market_data_version as mdv

    return {
        "bars": screener_updated,
        "screener_updated": screener_updated,
        "reconcile": st,
        "market_data_version": mdv.get_version(DB_PATH),
    }


def run_repair_ohlc_anomalies_job(
    symbols: Optional[list[str]] = None,
    *,
    lookback_days: int = 30,
):
    """Background: Yahoo-refresh symbols with OHLC scale discontinuities."""
    try:
        from server.ohlc_integrity import repair_ohlc_anomalies

        set_job("ohlc_repair", "Scanning for OHLC scale discontinuities…")
        conn = get_db_connection()
        try:

            def on_msg(msg: str) -> None:
                job_state["message"] = msg

            result = repair_ohlc_anomalies(
                conn,
                symbols=symbols,
                lookback_calendar_days=max(7, int(lookback_days)),
                log_fn=on_msg,
                apply_bhav_screener_overlay=True,
            )
        finally:
            conn.close()
        invalidate_chart_cache()
        invalidate_filter_cache()
        invalidate_stock_df()
        finish_job(
            f"OHLC repair complete: {result.get('repaired_count', 0)} symbol(s) refreshed; "
            f"{result.get('failed_count', 0)} failed.",
            meta=result,
        )
    except Exception as e:
        fail_job(str(e))


@app.get("/api/admin/ohlc-integrity")
def admin_ohlc_integrity(
    lookback_days: int = Query(30, ge=7, le=90),
    rescan: bool = Query(False),
):
    """Host-only: last OHLC integrity scan summary; optional live rescan."""
    from server.ohlc_integrity import last_integrity_summary, scan_ohlc_discontinuities

    if rescan:
        conn = get_db_connection()
        try:
            anomalies = scan_ohlc_discontinuities(conn, lookback_calendar_days=lookback_days)
        finally:
            conn.close()
        summary = last_integrity_summary()
        return {
            "rescan": True,
            "lookback_days": lookback_days,
            "anomaly_count": len(anomalies),
            "symbol_count": len({a["symbol"] for a in anomalies}),
            "anomalies": anomalies[:100],
            **summary,
        }
    return {"rescan": False, "lookback_days": lookback_days, **last_integrity_summary()}


@app.post("/api/admin/repair-ohlc-anomalies")
def admin_repair_ohlc_anomalies(
    lookback_days: int = Query(30, ge=7, le=90),
    symbols: str = Query(""),
):
    """Host-only: Yahoo-refresh symbols with chart OHLC scale cliffs."""
    sym_list = None
    raw = str(symbols or "").strip()
    if raw:
        sym_list = [s.strip().upper() for s in raw.split(",") if s.strip()]
    result = _start_or_queue_job(
        "ohlc_repair",
        lambda: threading.Thread(
            target=run_repair_ohlc_anomalies_job,
            kwargs={"symbols": sym_list, "lookback_days": int(lookback_days)},
            daemon=True,
        ).start(),
        label="OHLC anomaly repair",
        source="manual",
    )
    return {
        **result,
        "job": "ohlc_repair",
        "lookback_days": lookback_days,
        "symbols": sym_list or [],
    }


def run_repair_bars_4h_anomalies_job(
    symbols: Optional[list[str]] = None,
    *,
    lookback_days: int = 45,
):
    """Background: rebuild 4H bars for symbols with scale anomalies."""
    try:
        from server.bars_4h_integrity import repair_bars_4h_anomalies

        set_job("bars_4h_repair", "Scanning 4H bar integrity…")
        conn = get_db_connection()
        try:

            def on_msg(msg: str) -> None:
                job_state["message"] = msg

            result = repair_bars_4h_anomalies(
                conn,
                BASE_DIR,
                symbols=symbols,
                lookback_calendar_days=max(7, int(lookback_days)),
                log_fn=on_msg,
            )
        finally:
            conn.close()
        invalidate_chart_cache()
        invalidate_filter_cache()
        finish_job(
            f"4H repair complete: {result.get('repaired_count', 0)} symbol(s) rebuilt; "
            f"{result.get('pending_repair_count', result.get('quarantined_count', 0))} on host queue; "
            f"{result.get('failed_count', 0)} failed.",
            meta=result,
        )
    except Exception as e:
        fail_job(str(e))


@app.get("/api/admin/bars-4h-integrity")
def admin_bars_4h_integrity(
    lookback_days: int = Query(45, ge=7, le=90),
    rescan: bool = Query(False),
):
    """Host-only: 4H integrity scan summary and quarantine list."""
    from server.bars_4h_integrity import (
        last_bars_4h_integrity_summary,
        list_quarantined_symbols,
        scan_bars_4h_anomalies,
    )

    conn = get_db_connection()
    try:
        quarantine = list_quarantined_symbols(conn)
        if rescan:
            anomalies = scan_bars_4h_anomalies(conn, lookback_calendar_days=lookback_days)
            summary = last_bars_4h_integrity_summary()
            return {
                "rescan": True,
                "lookback_days": lookback_days,
                "anomaly_count": len(anomalies),
                "symbol_count": len({a["symbol"] for a in anomalies}),
                "anomalies": anomalies[:100],
                "quarantine": quarantine,
                **summary,
            }
    finally:
        conn.close()
    return {
        "rescan": False,
        "lookback_days": lookback_days,
        "quarantine": quarantine,
        **last_bars_4h_integrity_summary(),
    }


@app.post("/api/admin/repair-bars-4h-anomalies")
def admin_repair_bars_4h_anomalies(
    lookback_days: int = Query(45, ge=7, le=90),
    symbols: str = Query(""),
):
    """Host-only: rebuild 4H bars for symbols with scale cliffs or daily mismatch."""
    sym_list = None
    raw = str(symbols or "").strip()
    if raw:
        sym_list = [s.strip().upper() for s in raw.split(",") if s.strip()]
    result = _start_or_queue_job(
        "bars_4h_repair",
        lambda: threading.Thread(
            target=run_repair_bars_4h_anomalies_job,
            kwargs={"symbols": sym_list, "lookback_days": int(lookback_days)},
            daemon=True,
        ).start(),
        label="4H anomaly repair",
        source="manual",
    )
    return {
        **result,
        "job": "bars_4h_repair",
        "lookback_days": lookback_days,
        "symbols": sym_list or [],
    }


@app.get("/api/health")
async def health():
    return {
        "status":     "ok",
        "db":         str(DB_PATH),
        "db_exists":  DB_PATH.exists(),
    }


@app.get("/")
def serve_frontend_root():
    index_file = FRONTEND_BUILD_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "status": "ok",
        "message": "Frontend build not found. Run frontend dev server (npm start) or create a production build.",
    }


@app.get("/{full_path:path}")
def serve_frontend_spa(full_path: str):
    # Keep API routes untouched; this fallback is only for built frontend assets/routes.
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if FRONTEND_BUILD_DIR.exists():
        asset = (FRONTEND_BUILD_DIR / full_path).resolve()
        build_root = FRONTEND_BUILD_DIR.resolve()
        if str(asset).startswith(str(build_root)) and asset.is_file():
            return FileResponse(str(asset))
    index_file = FRONTEND_BUILD_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="Frontend build not found")
