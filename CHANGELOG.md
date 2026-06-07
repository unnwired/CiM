# FlowX Changelog

**Updated:** 05 Jun 26

## 05 Jun 26 (GitHub Release updates, UPDATE folder fixes)
- **GitHub Release updates:** FlowX now uses [unnwired/flowx-updates](https://github.com/unnwired/flowx-updates) as the sole remote update source. Latest release asset `FlowX-Update-{version}.zip` is downloaded to `%LOCALAPPDATA%\FlowX\update-staging\`, extracted to `{install}\UPDATE\FlowX-Update-{version}\`, then applied via existing `FlowXApplyUpdate.ps1`. Legacy `config\update_manifest_url.json` HTTPS manifest remote is deprecated.
- **Update check priority:** Local `{install}\UPDATE\FlowX-Update-*` first; GitHub `releases/latest` second. Same version → local wins.
- **New backend module:** `server\github_updates.py` (Releases API, asset pick, version normalize, ZIP download/extract, logging to `runtime\logs\update-download.log`). Wired through `server\update_apply.py` with `GET /api/update/settings`, `GET /api/update/check` (optional `?background=true`), `POST /api/update/download`, `POST /api/update/apply`.
- **Config:** `config\github_updates.json` — owner, repo, asset prefix/suffix, `checkIntervalMinutes` (default 90), `backgroundCheckEnabled`. Copied by `export_flowx.ps1`, `Sync-ExportDistributionFixes.ps1`, and update payload. Optional env: `FLOWX_GITHUB_OWNER`, `FLOWX_GITHUB_REPO`.
- **Frontend (App.js):** Shared `runFlowXUpdateApply()` for cogwheel **Apply update** and background prompt. GitHub flow: confirm → download → apply → quit. Background poll: ~30s after load, then every 90 minutes; dismiss per version via `sessionStorage` (`flowx.dismissedUpdateVersion`).
- **Build output:** `build_update_package.ps1` now creates `installer\output\FlowX-Update-{version}.zip` for GitHub upload alongside the folder package. Ships `github_updates.py` / encrypted `.pyc.enc` and config in update payload.
- **UPDATE folder detection:** Fixed install-path resolution when clients place packages under `{install}\UPDATE\FlowX-Update-{version}\` — `FlowXInstallLocator.ps1`, `Install-Client-Update.ps1`, `FlowXUpdatePackage.ps1`, `Apply-LocalUpdate-Entry.ps1`, and `update_apply._local_update_package_roots()`. No manual install path typing for standard layout.
- **Docs:** `docs\UPDATE.md`, `docs\CLIENT_UPDATE.md` updated for GitHub + 90-minute prompt + `UPDATE\` workflow.
- **Tests:** `scripts\test_github_updates.py` — version parse, asset pick, ZIP extract layout (run: `python scripts\test_github_updates.py`).
- **Build verification:** Full `Build-FlowX.ps1` pipeline completed successfully (export smoke test, 30-file encryption, license chain, Inno Setup, update package + ZIP). Log: `runtime\logs\build-distribution.log`.
- **Rollout:** Bump `installer\output\version.txt` before shipping to clients on 1.0.3+; publish ZIP to GitHub with tag `v{version}`. Clients need one manual/bat update to receive GitHub code before cogwheel/background remote pull works.

## 05 Jun 26 (FlowX installer, licensing, encrypted runtime, updates)
- **Windows installer + offline activation:** Added Inno Setup installer (`installer\FlowX.iss`) with machine-code + install-key wizard, silent `/INSTALLKEY=` support, installer output at `installer\output\FlowXSetup-1.0.3.exe`, and no app version bump for the latest fixes (`version.txt` remains `1.0.3`).
- **Machine-code licensing chain:** Runtime licensing lives in `server\app_code_crypto.py`; support scripts generate/verify keys via `Generate-FlowXInstallKey.ps1`, `Show-FlowXInstallKey.ps1`, `Repair-FlowXLicense.ps1`, and `Verify-FlowXLicenseChain.ps1`. The chain now prefers the shipped config file over stale `FLOWX_LICENSE_SECRET` env values so installer, Repair, and runtime agree.
- **Discreet distribution profile name:** Replaced client-visible `config\.flowx_vendor_secret` with neutral `config\.fx-dist.cfg`; legacy installs still fall back to the old filename if the new file is missing. Build/export/update scripts now use the new name.
- **Installer/export layout cleanup:** Distribution export moved from sibling `!Export\FlowX` to `installer\output\FlowX`; generated build artifacts (`FlowXSetup-*.exe`, update folders, `generated_license_secret.pas`, `license_validate.pas`, `version.txt`, docs) are organized under `installer\output\`.
- **Encrypted app-code runtime:** Distribution builds encrypt server bytecode (`server\*.pyc.enc`) and frontend JS (`frontend\build\static\js\*.js.enc`). `server\flowx_bootstrap.py` decrypts into `%LOCALAPPDATA%\FlowX\app-cache\{version}` after license validation, while data/scripts/frontend assets remain rooted at the install folder.
- **Blank Electron shell fixed:** `/static/js/main.*.js` was being handled by the SPA fallback and returning `index.html`, causing Electron to throw `Uncaught SyntaxError: Unexpected token '<'` and leave an empty shell. Static route ordering now mounts decrypted `/static` before the catch-all route; cache sync also copies CSS into app-cache.
- **Visible backend console restored:** Normal `start_flowx.bat` opens a `FlowX Backend` command window with live uvicorn/job output. Automation can still set `FLOWX_NO_PAUSE=1` for hidden/non-interactive runs.
- **Encrypted runtime install-root path fixes:** Fixed app-cache path leaks where encrypted `server.pyc.__file__` caused jobs to look under `%LOCALAPPDATA%\FlowX\app-cache\1.0.3` instead of the install root. `Update stock split adjustments` now loads `scrape_daily.py` via `SCRAPE_DAILY_PATH` (`C:\FlowX\scrape_daily.py` on client installs), not app-cache. Update scripts/log paths and movers calendar paths are also repointed to the install root.
- **Update package flow:** `build_update_package.ps1` now writes `installer\output\FlowX-Update-1.0.3`; client update package includes `Install-Client-Update.bat`, manifest, payload, and updated repair/diagnostic scripts.
- **Full build gate and diagnostics:** Added/updated `Run-FlowXFullGate.ps1`, `Test-FlowXInstallE2E.ps1`, `Sync-ExportDistributionFixes.ps1`, and `build_distribution_full.ps1` to verify export, encryption, installer build, license chain, silent install, backend health, frontend root, Electron presence, and update package creation.
- **Client network diagnostic clarified:** Yahoo/yfinance failures such as `curl: (7) Failed to connect to fc.yahoo.com port 443` are client network/proxy/firewall issues, not delisted NSE tickers. The backend already backs off after consecutive OHLCV failures.

## 03 Jun 26 (Market Map)
- **Market Map page:** New top-level **Market Map** tab with 25 NSE indices (Nifty 50 through Nifty Smallcap 50, plus **Nifty India Defence**), left-rail advance/decline bars, draggable ⋮⋮ reorder (`marketMapIndexOrder` in layout), and constituent heatmap (1D % color tiles). Click a tile opens a chart tab.
- **Market Map API:** `GET /api/market-map/catalog`, `/summary`, `/index/{symbol}` with 5-minute cache; five new index symbols (`^CNXNXT50`, `^CNX100`, `^CNX200`, `^CRSLDX`, `^CNXSMLCP50`) in `scrape_indices.py` and constituents map.
- **Market Map NSE fallback:** When NSE `equity-stockIndices` returns 404 (common off-session or bot-block), constituents load from official NSE archive CSVs (`nsearchives.nseindia.com`) with 1D % from screener, live movers cache, or `historical_data`. Index Constituents tab uses the same path (`server/nse_constituents.py`).
- **Market Map treemap (TradingView-style):** **Heatmap** layout uses `d3-hierarchy` squarified treemap — **tile area ∝ market cap**, **color = 1D %**. **Sectors** groups by `nse_sector`; **Stocks** is a flat cap map. **Grid** keeps equal tiles with **% high→low** sort. Dependency: `d3-hierarchy`.
- **Market Map Earnings+ (Grid / Heatmap):** **Grid** — gold **E+** corner badge when `earnings_plus_cache` is **qualified**. **Heatmap** — same gold (`#d29922`) **2px border** on the tile (no badge on small cells).
- **Market Map dual beat (Grid only):** Green **E** beside gold **E+** when the stock beat **EPS and revenue vs estimates** on its **latest reported quarter** (Surprise vs Estimates — same rules as the Earnings tab, not the Portfolio 10-day row highlight). Flag from `earnings_beat_lookup.py` on `/api/market-map/index/{symbol}`.
- **Market Map sort & filters:** **≥+5% / ≥+3% / ≥+1%** gainers only; **≤−1% / ≤−3% / ≤−5%** losers only. Grid default sort: signed 1D % high→low.
- **Market Map Nifty India Defence:** Added **^CNXINDDEF** to catalog, `scrape_indices.py`, and `nse_constituents.py` (NSE `NIFTY INDIA DEFENCE`, archive `ind_niftyindiadefence_list.csv`; live index level from NSE `allIndices` when Yahoo has no series).
- **Indices page — Nifty India Defence:** Same **^CNXINDDEF** symbol in `scrape_indices.py`; missing equity rows are inserted on backend startup via `ensure_equity_index_rows()` (NSE live level + session %).
- **Market Map default layout:** **Grid** is the default view and appears **left** of **Heatmap** in the toolbar.
- **Export (`distribution -HardenAll`):** Reuses existing `runtime\python` when valid (no re-download each export). Use `-RefreshEmbeddedPython` only when you need a clean embed rebuild; build goes to `python.export-build` so a running FlowX does not lock `runtime\python`.
- **v1 scope:** Period tabs beyond **1D** and **Sectors** view are visible but disabled; sort/layout/magnitude filters on the detail pane.

## 03 Jun 26
- **Indices 1D % list vs chart alignment:** Index list and chart header now share the same **last-two `index_history` closes** for 1D %. `/api/indices` applies `_index_live_day_change_map`; chart API sets `day_change_pct` from `_index_day_change_pct_single`. Indices page reloads the list on `CHART_DATA_UPDATED_EVENT` and Market Pulse refresh; selected row `%` syncs from the chart when it loads.
- **Index `change_pct` vs NSE session %:** `update_live_prices` updates `last_price` only when `index_history` has at least two closes; NSE `percentChange` no longer overwrites stored 1D % (recalc from history remains authoritative).
- **Chart cached-bar guard:** On 1D index/stock charts, when cached bars disagree with server `day_change_pct` by ≥0.05%, the UI uses the server value (matches the index list API).
- **Index OHLCV on Windows:** `scrape_indices.py` uses `_log()` with ASCII `[OK]`/`[X]` instead of Unicode checkmarks so the index scrape step does not abort with `charmap` errors on cp1252 consoles.
- **Update job finish message:** OHLCV job summary states stock symbol count plus either **`N index candles added`**, **`index OHLCV failed (...)`**, or **`index OHLCV not run`**; adds an explicit note when zero index bars were written.
- **Regression tests:** `server/tests/test_indices_alignment.py` — equity index live % vs history, Update summary strings, dashboard live-% guard (`_should_apply_live_day_change`), safe `_log` on Unicode; re-run with `python -m unittest server.tests.test_indices_alignment server.tests.test_earnings_plus`.

## 27 May 26
- **Earnings+ (DB-backed quality badge):** Added Screener-derived **Earnings+** rules (OPM, Net Profit, EPS vs prior quarter and year-ago quarter) with results stored in SQLite table `earnings_plus_cache` (`data/nse_data.db`). Consolidated quarterly data is preferred when it qualifies; otherwise standalone is used.
- **Earnings+ chart helper:** Gold **Earnings+** label on charts reads from cache via `/api/earnings-chart-events/{symbol}` (no live Screener scrape on chart open).
- **Reported earnings Earnings+ filter:** Reported Earnings page supports tri-state filter **All** / **Earnings+ only** / **Exclude Earnings+** using cache only (no per-row Screener during filter). Cache summary (`ready`, `qualified`, `missing`, `stale`) is returned on `/api/earnings-beats`.
- **Earnings+ cache refresh job:** `POST /api/admin/refresh-earnings-plus-cache` warms cache for the selected reported month; progress via existing admin job panel. Triggers from Reported Earnings (**Refresh Earnings+ cache**, **Retry incomplete**, **Force all**) and settings cog (**Refresh Earnings+ Cache (This Month)**).
- **Incremental Earnings+ refresh:** Refresh processes only symbols that need work (missing row, `insufficient_data`, or release-period mismatch). Stable `qualified` / `not_qualified` rows for the current release are skipped (no redundant DB upsert or Screener scrape).
- **Earnings+ filter stability fix:** `qualified` / `not_qualified` cache rows are no longer treated as time-stale when `source_fetched_at` ages past 18 hours, so **Earnings+ only** for a month (e.g. May) no longer drops early reporters after a partial refresh.
- **Earnings+ performance:** Normal refresh uses cached `screener_quarterly` when present (`refresh_stale` only when `force=true`). Symbol refresh runs in parallel (4 workers). **Force all** re-scrapes stale quarterly data and recomputes every reported symbol (confirm dialog in UI).
- **Earnings+ basis selection fix:** Evaluation loads both consolidated and standalone, then picks the best result (qualified consolidated → qualified standalone → not_qualified → insufficient), fixing symbols stuck on `insufficient_data` when only standalone had usable data (e.g. ENRIN → `not_qualified`).
- **Work-hours background Earnings+ warm:** `server/earnings_plus_scheduler.py` runs incremental warm while the backend is up, **08:00–20:00 IST** only: startup pass after 2–5 min jitter, then every 45–90 min (random). Skips when another admin job is running or a run completed within the last 30 minutes. Scheduled runs are **quiet** (no Update panel toast).
- **Earnings+ warm status:** Last run persisted to `data/earnings_plus_warm.json`; `GET /api/admin/earnings-plus-warm-status`. Reported Earnings footer shows **Last background warm** (time, trigger, updated/skipped counts). Requires backend running (FlowX desktop or server); UI need not be open.
- **Earnings+ API params:** `force` (full recompute + Screener stale refresh), `only_incomplete` (missing / `insufficient_data` only).
- **Earnings+ tests:** `server/tests/test_earnings_plus.py` — staleness, filter matching, consolidated/standalone pick order.
- **Dashboard 1D % cold-start fix:** `_apply_live_screener_ohlc` no longer shows **0.00%** for the universe when `screener.price` equals yesterday’s close on session days; uses two-bar historical % until price differs materially. Live movers overlay avoids replacing a real historical % with stale live **0%**. One-shot NSE movers cache warm on backend startup.

## 25 May 26
- **Portfolio/Watchlist earnings callouts:** Added direct earnings highlighting in Portfolio and Watchlist with amber upcoming-report badges (`E <date>`), green `Beat EPS+Rev` badges, row tinting, and click-through access to quarterly results plus company profile in the earnings modal.
- **Earnings highlight reliability:** Fixed upcoming/beat detection so recent dual beats use the latest reported quarter, upcoming highlights no longer disappear when the reported feed fails, and beat detection works reliably for visible Portfolio/Watchlist symbols instead of depending on a capped market-wide scan.
- **Earnings-priority sorting:** Added default-on earnings-priority ordering in Portfolio and Watchlist so upcoming reporters appear first, followed by the most recently reported `Beat EPS+Rev` names; the footer control now toggles date direction and column-header sorting temporarily returns the list to normal sort mode.

## 22 May 26
- **Symbol lineage (rename-aware history):** Documented and implemented config-driven merge of predecessor NSE tickers into canonical symbols (first case: `MCDOWELL-N` → `UNITDSPR`). See `docs/SYMBOL_LINEAGE.md`, `data/symbol_lineage.json`, `scripts/backfill_symbol_history.py`, daily job hook in `scrape_daily.py`, and `POST /api/admin/backfill-symbol-lineage/{symbol}`.

**Updated:** 26 April 26

**Document naming convention:** keep stable filenames without date ranges/timestamps; keep all date/time metadata inside the file using `DD Month YY`.

## 23 April 26
- **Potential Swings UX compaction:** Consolidated `Watchlist` + `Find screener` controls into one compact row, moved screener selection to a slide-out drawer, and surfaced the active screener name in the top row.
- **Potential Swings screener cleanup:** Removed the older `2W EMA Pullback` screener branch and corresponding frontend screener option.
- **New Potential Swings presets:** Added `2W` EMA structure/pullback presets with two low-structure modes: **symmetric median band** and **downside-only median band**.
- **2W structure parameter overrides:** Added optional refine overrides for `low_window_bars`, `ref_high_bars_back`, and pullback bounds (`high_pullback_min_pct`, `high_pullback_max_pct`) and wired them end-to-end into scan payloads.
- **2W backend screening logic:** Implemented robust 2W low-band checks around median lows, configurable lookback/bar reference logic, history-shortfall skipping, and positional high-reference pullback checks.
- **Dashboard filter menu expansion:** Added `MACD Hist Receding` filter builder in Dashboard with configurable timeframe, bars-to-compare, straggler tolerance, side mode (negative/positive/both), and `Allow Cross-Zero Chain`.
- **Histogram direction support:** Extended MACD histogram chain filter to support both **receding** and **increasing** chain modes in the same filter type.
- **Snapshot integration for histogram chain filter:** Added `macd_hist_chain` storage in `indicator_snapshots`, populated during rebuild, and enabled snapshot-fast evaluation for this filter on snapshot-supported timeframes with candle fallback for unsupported timeframes.
- **Snapshot rebuild controls hardened:** Added guarded full rebuild flow with confirmation token (`REBUILD_FULL_UNIVERSE`), added explicit full endpoint, incremental endpoint options (`timeframes`, `force`, `defer_heavy`, `scope`), and a `heavy-now` shortcut endpoint for `4W/1M`.
- **Admin UX copy update:** Updated rebuild menu text to `Rebuild Indicator Snapshots (may take time)` for clearer operator expectations.
- **OHLCV vs snapshot decoupling:** Decoupled automatic snapshot refresh from chart/OHLCV update flow; snapshot rebuild now runs via explicit snapshot rebuild actions/endpoints.

## 25 April 26
- **Global type-anywhere search overlay (NSE/Indices/Watchlist/Portfolio):** Added a centralized semi-transparent command-palette search that opens from first keystroke on supported pages, with unified symbol/index lookup via `/api/unified-search`.
- **Keyboard-first search interaction:** Implemented overlay controls for `ArrowUp`/`ArrowDown` (result navigation), `Enter` (confirm), `Backspace` (edit query), and `Esc` (close), with deterministic key handling to prevent first-character lockups.
- **Overlay key isolation:** While overlay search is open, key events are now consumed at app level so page-level list navigation no longer reacts to the same arrow/enter keys.
- **Selection behavior cleanup:** Selecting from overlay no longer writes the chosen symbol into local page search fields; selection directly updates chart focus context.
- **Selection persistence fix:** Removed unintended fallback that reset selected symbol to first table row (for example `RELIANCE`) when the selected symbol was temporarily outside visible loaded rows.
- **Left-list focus/visibility improvements:** Added auto-scroll-to-selected behavior across Dashboard, Indices, and Watchlist left panels; for paged NSE/Portfolio lists, selected symbols from overlay are materialized into the left list when missing so focus row is visible immediately.

## 26 April 26
- **Dev restart action consolidation:** Combined cogwheel actions into a single `Restart Backend + Frontend (Dev)` flow to reduce operator friction during development resets.
- **Watchlist ordering controls:** Added persistent watchlist order support with `manual`, `A-Z`, and `Z-A` modes; backend now accepts explicit watchlist order updates via `POST /api/watchlists/reorder`.
- **Watchlist reorder UX iteration:** Manual watchlist ordering behavior was refined to support drag-oriented workflows while preserving existing watchlist selection and creation flows.
- **Embedded runtime dependency hardening (`yfinance`):** Added `yfinance` to runtime requirements and hardened startup/export scripts to repair missing embedded dependencies with fallback install behavior.
- **Price update preflight diagnostics:** Added explicit backend preflight error handling when `yfinance` is unavailable to avoid opaque update failures.
- **Split-adjust refresh reliability:** Fixed split-adjust refresh path for `yfinance` MultiIndex downloads by flattening columns, validating OHLCV shape, and adding per-symbol failure diagnostics instead of silent skips.
- **Snapshot parallelism resilience on Windows:** Hardened snapshot rebuild parallel mode to gracefully fall back from process workers to thread workers when pickling/module constraints are encountered, reducing user-facing rebuild failures.

## 22 April 26
- **Potential Swings scanner:** Added new backend endpoint `POST /api/scans/potential-swings` (snapshot-driven, default `2W`) to detect setups where MACD histogram is still negative but receding, near crossover (`epsilon`), and confirmed by `StochRSI K > D`; returns ranked symbols with scan metrics.
- **New page:** Added **Potential Swings** workspace and top-tab entry in the app; layout mirrors NSE-style chart workflow with Drawing Tools, Financials link, Indicators menu, View (single/2/3 panel), Open Full Chart, and Save Layout.
- **Preset conditions:** Added `2W Potential Swing`, `2W Tight Setup`, and `2W Early Build` presets with different strictness (`epsilon`, histogram improvement, and K-D spread thresholds).
- **Manual refine filters:** Added client-side refine layer on Potential Swings results for symbol search, min/max price, min/max market cap, max histogram distance, and min K-D spread; includes live refined counts, empty-state feedback, and clear-all.
- **Market-cap input format:** Refine filters now parse market cap using `M`, `B`, and `T` units (for example `250M`, `1.2B`, `0.8T`) with inline validation.
- **Watchlist parity on Potential Swings:** Added NSE-style Watchlist dropdown flow after scans/presets, including add selected symbol and add-all refined symbols to a chosen watchlist; wired to existing watchlist handlers and navigation fallback.
- **Screener library scaling:** Replaced flat preset list with grouped screener library + search on Potential Swings to support multiple strategy families without crowding.
- **Second screener family:** Added `EMA Stack Transition (2W/1W)` presets (Balanced/Tight/Early) using snapshot fields for EMA proximity, 2W trend gate (`EMA50 > EMA100`), 2W receding MACD histogram, and 1W potential crossover.
- **EMA proximity rule refinement:** Updated EMA Stack logic so `2W` price can be close to **EMA21 OR EMA50** (±10%), and `1W` price can be close to **EMA21 OR EMA50** (instead of requiring both), matching intended screening behavior.

## 21 April 26
- **Indicator snapshots:** Full clear + rebuild via admin (`Rebuild Indicator Snapshots`), background job with progress; snapshots expanded to **1D–6D**, **1W**, **2W**, **4W**, **1M**; robust handling of incomplete OHLC rows; **calendar-anchored** multi-period bars (last bar consistent across D/W/M).
- **Filters & screener:** Filtered views fetch the full result set (within API page limits) for correct counts/sort; **enabled** filter chips only; multi-filter results are **intersection** of per-filter symbol sets.
- **Charts vs filters:** Chart OHLC aggregation for N-day / N-week / N-month timeframes aligned with **filter and snapshot** bucketing (same absolute anchors), so chart “last bar” matches filter logic.
- **Dashboard / NSE UI:** Filter chip layout (edit / enable / delete on hover); Watchlist menu refinements (e.g. add focused / add all when filtered); **Drawing Tools** design-only (floating panel, all chart pages **except** Market Pulse); NSE search: **typing still filters the table** — **autocomplete dropdown removed**.
- **Backup:** Comprehensive project backup merged into **`srcBackup_Restore.py`** (optional full backup excluding heavy DB/data as configured).
- **Performance roadmap (Phases 0–5) implemented:**
  - Phase 0: added end-to-end perf instrumentation for filter combination, list endpoints, and snapshot rebuild stages (load/compute/write/total).
  - Phase 1: added filter execution prioritization + stronger early-exit path for empty intersections.
  - Phase 2: added snapshot-aware multi-filter fast path (reuses timeframe snapshot rows across filters instead of repeated per-filter passes).
  - Phase 3: added process-based parallel snapshot row computation with centralized batched SQLite writes.
  - Phase 4: added incremental snapshot rebuild endpoint for recently changed symbols (`/api/admin/rebuild-indicator-snapshots-incremental`).
  - Phase 5: added snapshot-vs-chart consistency diagnostics endpoint (`/api/admin/snapshot-consistency`) for last-bar parity checks.

## 14 April 26
- Added event-driven chart refresh after background OHLCV updates (no hard browser refresh required).
- Fixed chart flashing/refetch loop by stabilizing refresh callbacks.
- Removed commodities section from Market Pulse and excluded Gold/Silver from Indices page listings.
- Reworked top toolbar: added centered `FlowX` title, `Update` button with progress fill, status panel, and new settings dropdown actions.
- Implemented feedback flow via Google Forms (Issue/Feature) with auto-prepended context and prefilled form values.
- Added export modes in `export_flowx.ps1`:
  - `standard` (full state/source export)
  - `distribution` (clean state, source omitted, distribution defaults)
- Distribution profile now defaults to:
  - single-chart layout (Dashboard, Indices, Watchlist, Movers)
  - MACD + StochRSI disabled; volume off
  - EMA 100/200 enabled, 21/50 disabled
  - empty watchlists, portfolio, and filter presets
  - Earnings page: current month/year, no MCap bounds, Earnings+ = All, surprise fields empty
  - **Potential Swings** tab omitted from distribution builds
- Replaced legacy naming with FlowX naming across runtime/export scripts and docs:
  - `start_flowx.bat`, `stop_flowx.bat`, `export_flowx.ps1`
- Improved list loading performance with chunked incremental loading (150 rows/page with near-end prefetch).
- Rebuilt EMA UX:
  - stable period-based colors (no color remap when toggling)
  - compact persistent EMA control
  - editable dropdown rows, per-EMA color editing, HEX/RGB/HSL copy support
  - expanded EMA switch click hit area
- Aligned toolbar control heights to consistent `28px` (Volume + EMA matched with other action buttons).

## 13 April 26
- No major tracked feature changes in this build output.

## 12 April 26
- Dashboard filter-bar layout hardening and narrow-width behavior improvements (chip rail/actions rail split).
