# Symbol lineage (rename-aware history)

## Problem

NSE occasionally **renames tickers** while the issuer stays the same (e.g. `MCDOWELL-N` → `UNITDSPR`, effective 2024-06-07).  
FlowX stores OHLC in `historical_data` keyed by **current** `screener.symbol` and loads charts via `yfinance` as `{symbol}.NS`.

Yahoo history for the **new** ticker only exists from the rename date onward. TradingView shows a **continuous** series because it maps the instrument to one identity across renames.

## Goals

| Priority | Goal |
|----------|------|
| P0 | Charts for a renamed symbol show full available history under the **canonical** symbol (e.g. `UNITDSPR`). |
| P0 | One-off and scheduled backfill without manual DB edits. |
| P1 | Config-driven lineage (add renames without code changes). |
| P1 | Daily updater backfills **new** screener symbols and re-runs lineage when history is still shallow. |
| P2 | Admin UI / API to trigger backfill and show lineage status. |
| P2 | ISIN-based auto-discovery of predecessors (from NSE master / exchange sync). |
| P3 | Corporate actions at rename boundary (price ratio adjustment) when NSE publishes adjustment factors. |

## Non-goals (v1)

- Continuous futures-style roll for **different** ISINs (mergers where the listed entity changes).
- BSE-only legacy tickers unless listed in config.
- Changing `screener.symbol` rows to old tickers.

## Data model

### Config: `data/symbol_lineage.json`

```json
{
  "version": 1,
  "symbols": {
    "UNITDSPR": {
      "isin": "INE854D01024",
      "notes": "United Spirits; NSE rename from MCDOWELL-N effective 2024-06-07",
      "predecessors": [
        {
          "nse_symbol": "MCDOWELL-N",
          "effective_until": "2024-06-06"
        }
      ]
    }
  }
}
```

| Field | Meaning |
|-------|---------|
| `canonical` | Key in `symbols` — must match `screener.symbol` / chart symbol. |
| `predecessors[].nse_symbol` | Old NSE code for `yfinance` (`{nse_symbol}.NS`). |
| `predecessors[].effective_until` | Last calendar day of old ticker (inclusive). New ticker from next session. |
| `isin` | Documentation / future auto-linking. |
| `historical_yahoo` | Full OHLC source when NSE/Yahoo predecessor is delisted (e.g. `UNITDSPR.BO`). |
| `import_bse_volume` | Default `false` — BSE volume scale ≠ NSE; use BSE for OHLC only, NSE `.NS` for volume. |

Order: predecessors listed **oldest chain first** if multiple (rare).

### Storage rule (write-time merge)

All daily bars are stored as:

`historical_data.Symbol = <canonical>` (e.g. `UNITDSPR`)

Pre-rename bars are ingested from `MCDOWELL-N.NS` but **written under** `UNITDSPR`.  
Overlap dates: **canonical ticker wins** (delete-then-insert or skip older on conflict).

### Meta: `updater_meta` keys

| Key | Value |
|-----|--------|
| `lineage_backfill:<SYMBOL>` | ISO timestamp when lineage backfill last succeeded |

## Architecture

```
data/symbol_lineage.json
        │
        ▼
symbol_lineage.py  ←── scrape_daily.py (gap + shallow detection)
        │              scripts/backfill_symbol_history.py (manual)
        ▼
historical_data (canonical Symbol only)
        │
        ▼
GET /api/chart-data/{symbol}  (unchanged query; optional read-time merge fallback)
```

## yfinance contract

- Current: `{canonical}.NS`
- Predecessor: `{nse_symbol}.NS` (hyphens preserved, e.g. `MCDOWELL-N.NS`)
- Use `auto_adjust=True` for both; same as `scrape_daily.py`
- Backfill window: predecessor `start` → `effective_until`; canonical `effective_until + 1 day` → today

## Detection: when to backfill

1. **Explicit**: `python scripts/backfill_symbol_history.py UNITDSPR` or `--all`
2. **Daily job** (`scrape_daily.run`):
   - Screener symbol with **no** `historical_data` → full `period=max` for canonical + predecessors
   - Symbol in lineage config with `MIN(Date)` after first predecessor era (e.g. after 2024-06-07 for `UNITDSPR`) → run lineage backfill once (meta key)

## Edge cases

| Case | Handling |
|------|----------|
| Multiple predecessors | Fetch in order; merge into canonical; later segment overwrites overlap |
| Yahoo missing old ticker | Log warning; keep partial history; meta not set |
| Symbol delisted | No further appends; history frozen |
| User still has old ticker in watchlist | Out of scope v1; search uses canonical only |
| Split on rename boundary | v1: rely on Yahoo adjusted prices; v3: NSE ratio table |
| Distribution export | Ship `data/symbol_lineage.json`; backfill on target machine |

## Verification

For `UNITDSPR` / 1M chart:

1. `SELECT MIN(substr(Date,1,10)) FROM historical_data WHERE Symbol='UNITDSPR'` → before 2024-06-07
2. Chart first monthly bar ≈ TradingView range (2006+ depending on Yahoo depth for `MCDOWELL-N.NS`)
3. Latest bar OHLC still matches TV (sanity)

## Implementation phases

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | This doc + `symbol_lineage.json` + `symbol_lineage.py` + `backfill_symbol_history.py` | Current |
| 2 | `scrape_daily` integration (gaps + shallow lineage) | Current |
| 3 | `export_flowx.ps1` copies config; optional admin endpoint | Partial |
| 4 | ISIN-linked auto lineage from exchange master | Planned |
| 5 | UI: chart footnote “includes history as MCDOWELL-N” | Planned |

## Adding a new rename

1. Confirm Yahoo still serves `{old}.NS` history.
2. Add entry to `data/symbol_lineage.json` with `effective_until` from NSE circular.
3. Run: `runtime\python\python.exe scripts\backfill_symbol_history.py <CANONICAL>`
4. Rebuild indicator snapshots if needed (`scrape_daily` snapshot job or admin).

## Reference: UNITDSPR

- NSE rename: `MCDOWELL-N` → `UNITDSPR`, effective **2024-06-07** (Zerodha / NSE circular, Jun 2024).
- BSE: `532432` (unchanged).
