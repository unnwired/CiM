# CiM — Engineering Improvement Plan
> **Branch:** `jay/dev-workspace`  
> **Version:** 1.0.6  
> **Date:** June 2026  
> **Author:** Jay  

This document catalogues every identified improvement across the CiM codebase — backend, frontend,
database, developer experience, testing, data pipeline, and product. Each item includes the exact
problem, the file(s) affected (with line numbers), a concrete fix, and implementation steps.

---

## Table of Contents

1. [Backend Architecture](#1-backend-architecture)
2. [Frontend Architecture](#2-frontend-architecture)
3. [Performance](#3-performance)
4. [Developer Experience](#4-developer-experience)
5. [Testing](#5-testing)
6. [Database & Data Pipeline](#6-database--data-pipeline)
7. [Security](#7-security)
8. [Product & UX](#8-product--ux)

---

## 1. Backend Architecture

---

### 1.1 `server.py` must be split into feature routers

**Severity:** 🔴 Critical  
**File:** `server/server.py` — 8,351 lines, 316 KB  

#### Problem

The entire backend is a single Python file. It handles every concern:
- Database connection management
- OHLCV chart aggregation
- Screener filtering and pagination
- Earnings / Earnings+ logic
- Market map
- Movers (live + daily)
- Watchlists and portfolio
- Admin job orchestration
- Split detection and adjustment
- Knowledge base
- Update pipeline
- SMTP feedback
- Caching (chart, filter, snapshot)
- Startup migration (schema `ALTER TABLE` calls)

This creates several real engineering problems:
- A bug in the filter system requires reading 8,000 lines to find context
- Any two developers working on different features will have merge conflicts
- The file takes 3–5 seconds to parse in IDEs, making autocomplete sluggish
- A single `import` error anywhere in the file kills the entire server

#### Fix: FastAPI `APIRouter` decomposition

Proposed file structure:

```
server/
  core/
    __init__.py
    config.py          ← BASE_DIR, DATA_DIR, DB_PATH, all constants
    db.py              ← get_db_connection(), _connect_sqlite(), WAL setup
    cache.py           ← _chart_cache, _filter_cache, TTL logic, LRU eviction
    install_root.py    ← get_install_root() guard (see §1.3)
    scheduler.py       ← threading helpers, background task wrappers
  routers/
    __init__.py
    charts.py          ← /api/chart-data/{symbol}, aggregate_ohlcv()
    stocks.py          ← /api/stocks, /api/stock/{symbol}, /api/stocks/search
    earnings.py        ← /api/earnings-beats, /api/earnings-chart-events/{symbol}
    earnings_plus.py   ← /api/earnings-plus/*, cache refresh admin route
    admin.py           ← /api/admin/*, job_state, run_*() job functions
    watchlists.py      ← /api/watchlists, /api/watchlist/*
    portfolio.py       ← /api/portfolio
    indices.py         ← /api/indices, /api/index-chart/{symbol}
    market_map.py      ← /api/market-map/*
    movers.py          ← /api/movers/*, live movers integration
    splits.py          ← /api/admin/split-*, split event management
    updates.py         ← already extracted (update_apply.py) ✅
    knowledge.py       ← /api/dev/knowledge-base/*
    settings.py        ← /api/admin/cache-settings, /api/layout
  server.py            ← Only: app = FastAPI(), include_router() calls, startup hook
```

#### Implementation steps

1. Create `server/core/config.py` — move all constants (lines 92–189 of current `server.py`)
2. Create `server/core/db.py` — move `get_db_connection()`, `_connect_sqlite()`, WAL helpers
3. Create `server/core/cache.py` — move `_chart_cache`, `_filter_cache`, all cache functions (lines 1507–1600)
4. Create `server/routers/charts.py` — move `/api/chart-data/` endpoint and `aggregate_ohlcv()` (lines 3296–3460)
5. Create `server/routers/stocks.py` — move `/api/stocks`, `/api/stock/{symbol}` (search screener sections)
6. Create `server/routers/admin.py` — move all `/api/admin/*` routes and `job_state` dict
7. Continue for each router, one at a time, running `python -m pytest server/tests/` after each move
8. Final `server.py` becomes ~100 lines: imports + `include_router()` + `startup` hook

---

### 1.2 In-memory caches are not thread-safe

**Severity:** 🔴 Critical  
**File:** `server/server.py` lines 1507–1595  

#### Problem

```python
# Line 1508
_chart_cache: dict = {}
_filter_cache: dict = {}

# Line 1574 — cache eviction scans the entire dict
oldest_key = min(_chart_cache, key=lambda k: _chart_cache[k].get("ts", 0))
_chart_cache.pop(oldest_key, None)
```

FastAPI with uvicorn uses async request handling. Multiple concurrent requests reading or writing
`_chart_cache` at the same time can corrupt the dict, causing:
- `RuntimeError: dictionary changed size during iteration`
- Stale data being returned to wrong requests
- Silent cache poisoning (wrong symbol's data returned)

The eviction code (`min()` over the entire dict) is also O(n) — with 300 entries it scans all 300
keys on every new chart load.

#### Fix

Replace the hand-rolled dict with `cachetools.TTLCache` which is designed for this:

```python
# server/core/cache.py (new file)
import threading
from cachetools import TTLCache

_chart_lock   = threading.Lock()
_filter_lock  = threading.Lock()

_chart_cache  = TTLCache(maxsize=300, ttl=300)   # 5 min TTL, 300 entries
_filter_cache = TTLCache(maxsize=500, ttl=120)   # 2 min TTL, 500 entries

def get_chart_cache(symbol: str, timeframe: str, ema_periods: list):
    key = (symbol.upper(), timeframe, tuple(sorted(ema_periods)), _CHART_CACHE_SCHEMA)
    with _chart_lock:
        return _chart_cache.get(key)

def set_chart_cache(symbol: str, timeframe: str, ema_periods: list, data: dict):
    key = (symbol.upper(), timeframe, tuple(sorted(ema_periods)), _CHART_CACHE_SCHEMA)
    with _chart_lock:
        _chart_cache[key] = data

def invalidate_chart_cache(symbol: str = None):
    with _chart_lock:
        if symbol is None:
            _chart_cache.clear()
        else:
            sym_u = symbol.upper()
            keys_to_delete = [k for k in _chart_cache if isinstance(k, tuple) and k[0] == sym_u]
            for k in keys_to_delete:
                _chart_cache.pop(k, None)
```

Add `cachetools` to `requirements_runtime.txt`.

The aggressive cache profile can simply pass larger `maxsize`/`ttl` values to the constructor.

---

### 1.3 `Path(__file__).parent.parent` — app-cache path leak guard

**Severity:** 🟠 High  
**Files:** Any new server module added by a developer  

#### Problem

In the encrypted distribution, `__file__` for any `.pyc.enc` module points to:
```
C:\Users\...\AppData\Local\CiM\app-cache\1.0.6\server\module.pyc
```
NOT the install root. This caused three separate bugs (documented in docs/handoff/PROJECT_HANDOFF.md §3.5–3.7).
The current fix is ad-hoc (per-module global path variables). A new developer writing:
```python
SCRAPE_PATH = Path(__file__).parent.parent / "scrape_daily.py"
```
will silently re-introduce the bug in production with no error in development.

#### Fix

Create `server/core/install_root.py`:

```python
# server/core/install_root.py
"""
Single source of truth for the install root path.

In development: resolves to CiM/ (the repo root).
In encrypted distribution: repointed by cim_bootstrap._repoint_server_install_paths()
to the real install directory (e.g. C:\FlowX) — NOT the app-cache.

RULE: All server modules that need to reference files outside server/ MUST import
get_install_root() from here. Never use Path(__file__).parent.parent directly.
"""
from pathlib import Path
import threading

_lock = threading.Lock()
_install_root: Path | None = None


def set_install_root(path: Path) -> None:
    """Called once by cim_bootstrap on encrypted startup."""
    global _install_root
    with _lock:
        _install_root = Path(path).resolve()


def get_install_root() -> Path:
    """Returns the install root. Falls back to dev-tree resolution if not set."""
    with _lock:
        if _install_root is not None:
            return _install_root
    # Dev fallback: server.py lives in CiM/server/, so parent.parent = CiM/
    return Path(__file__).resolve().parent.parent.parent


def get_data_dir() -> Path:
    return get_install_root() / "data"


def get_scripts_path(name: str) -> Path:
    return get_install_root() / name
```

Add a CI grep check to prevent regressions:

```bash
# In any pre-commit hook or CI script:
if grep -rn "Path(__file__).parent.parent" server/ --include="*.py" | grep -v "install_root.py"; then
  echo "ERROR: Direct Path(__file__).parent.parent usage found. Use get_install_root() instead."
  exit 1
fi
```

---

### 1.4 Startup runs schema migrations on every boot

**Severity:** 🟠 Medium  
**File:** `server/server.py` — `_on_startup()` function (~lines 218–378)  

#### Problem

Every time the server starts, `_on_startup()` runs 15+ DDL statements:
```python
market_sectors.ensure_screener_sector_columns(DB_PATH)
market_sectors.ensure_screener_isin_column(DB_PATH)
screener_quarters.ensure_screener_quarterly_table(DB_PATH)
market_cap_live.ensure_issued_shares_column(DB_PATH)
cur.execute("ALTER TABLE screener ADD COLUMN ...")  # guarded by try/except
cur.execute("CREATE INDEX IF NOT EXISTS ...")
```

Problems:
- Each `ensure_*` function opens its own connection, runs `PRAGMA table_info()`, compares columns
- This adds 200–800ms to startup time as DB grows
- Schema evolution is invisible — there's no record of what version the DB schema is at
- `ALTER TABLE` errors are silently swallowed by `try/except pass` blocks

#### Fix

Add a `schema_migrations` table and a lightweight migration runner:

```python
# server/core/migrations.py

MIGRATIONS = [
    # (migration_id, SQL statement)
    ("001_screener_base",
     """CREATE TABLE IF NOT EXISTS screener (
         symbol TEXT PRIMARY KEY, name TEXT, market_cap REAL, price REAL,
         change_pct REAL, pe REAL, nse_sector TEXT, updated_at TEXT
     )"""),
    ("002_screener_add_issued_shares",
     "ALTER TABLE screener ADD COLUMN issued_shares INTEGER DEFAULT 0"),
    ("003_screener_add_isin",
     "ALTER TABLE screener ADD COLUMN isin TEXT"),
    ("004_historical_data_index",
     "CREATE INDEX IF NOT EXISTS idx_hist_symbol_date ON historical_data(Symbol, Date)"),
    # ... add one entry per schema change from here on
]

def run_migrations(conn: sqlite3.Connection) -> int:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    applied = {r[0] for r in conn.execute("SELECT id FROM schema_migrations").fetchall()}
    count = 0
    for migration_id, sql in MIGRATIONS:
        if migration_id in applied:
            continue
        try:
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (id) VALUES (?)", (migration_id,))
            conn.commit()
            count += 1
            print(f"[migration] Applied: {migration_id}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                # Mark as applied if column/table already exists from manual migration
                conn.execute("INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)", (migration_id,))
                conn.commit()
            else:
                print(f"[migration] WARNING: {migration_id} failed: {e}")
    return count
```

Replace all `ensure_*` calls in `_on_startup()` with a single:
```python
from server.core.migrations import run_migrations
conn = get_db_connection()
run_migrations(conn)
conn.close()
```

---

### 1.5 SQLite connection opened and closed per-request

**Severity:** 🟡 Medium  
**File:** `server/server.py` line 389  

#### Problem

```python
def get_db_connection():
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found: {DB_PATH}")
    return _connect_sqlite(DB_PATH, row_factory=True)
```

Every API call creates a fresh connection. SQLite in WAL mode handles concurrent reads well, but
connection overhead (file open, PRAGMAs, row_factory setup) adds 2–10ms per request. On the
Dashboard screener with rapid filter changes, this is noticeable.

#### Fix

Use `threading.local()` to reuse connections per-thread:

```python
# server/core/db.py
import threading
import sqlite3
from pathlib import Path

_thread_local = threading.local()

def get_db_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found: {DB_PATH}")
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = _connect_sqlite(DB_PATH, row_factory=True)
        _thread_local.conn = conn
    # Test connection is still alive
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        conn = _connect_sqlite(DB_PATH, row_factory=True)
        _thread_local.conn = conn
    return conn
```

**Note:** With this pattern, callers must NOT call `conn.close()` after use — the connection is
reused. Audit all `finally: conn.close()` blocks and replace with `conn.rollback()` if needed.

---

## 2. Frontend Architecture

---

### 2.1 `App.js` has 40+ `useState` hooks — needs Context decomposition

**Severity:** 🔴 Critical  
**File:** `frontend/src/App.js` — 2,554 lines, 111 KB  

#### Problem

The root `App` component is managing state for every feature in the app simultaneously:

```jsx
// Lines 48–98: 21 useState hooks in the first 50 lines alone
const [view, setView]                       = useState('dashboard');
const [chartTabs, setChartTabs]             = useState([]);
const [activeTabIdx, setActiveTabIdx]       = useState(null);
const [indexTabs, setIndexTabs]             = useState([]);
const [activeIndexTab, setActiveIndexTab]   = useState(null);
const [constituentsTabs, ...]               = useState([]);
const [watchlists, setWatchlists]           = useState([]);
const [activeWatchlistName, ...]            = useState(...);
const [watchlistSelectedItem, ...]          = useState(...);
const [contextMenuState, ...]               = useState({...});
const [contextMenuPos, ...]                 = useState({...});
const [adminOpen, setAdminOpen]             = useState(false);
const [toastMessage, setToastMessage]       = useState(null);
const [settingsOpen, setSettingsOpen]       = useState(false);
const [aggressiveCacheRam, ...]             = useState(false);
const [cacheBusy, setCacheBusy]             = useState(false);
const [rebuildSnapshotsBusy, ...]           = useState(false);
const [rebuildSnapshotsPercent, ...]        = useState(0);
const [rebuildSnapshotsMessage, ...]        = useState('Preparing...');
const [desktopCanRestartBackend, ...]       = useState(false);
// ... 20 more below
```

Every state change at the top level triggers a re-render of the entire component tree unless
children are `React.memo`-wrapped. Changing a `toastMessage` re-renders `DashboardPage`.

#### Fix

Extract into React Contexts:

```
frontend/src/
  contexts/
    NavigationContext.jsx    ← view, chartTabs, indexTabs, constituentsTabs, all open/close/switch
    WatchlistContext.jsx     ← watchlists, activeWatchlistName, watchlistSelectedItem, loadWatchlists
    AdminJobContext.jsx      ← job state, all startXxx() functions, updateRunning, updatePercent
    UpdateContext.jsx        ← cimUpdateBusy, appVersion, runCiMUpdateApply(), background poll
    ToastContext.jsx         ← toastMessage, showToast() — one liner
    SettingsContext.jsx      ← aggressiveCacheRam, cacheBusy, handleToggleAggressiveCache
  hooks/
    useGlobalSearch.js       ← globalSearchOpen, query, results, activeIndex — extract from App.js
    useContextMenu.js        ← contextMenuState, contextMenuPos, layout effect — extract from App.js
    useDesktopCapabilities.js ← desktopCanRestartBackend, desktopCanReloadFrontend
```

Example for `ToastContext`:
```jsx
// frontend/src/contexts/ToastContext.jsx
import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(null), 4000);
    return () => clearTimeout(t);
  }, [message]);

  useEffect(() => {
    const handler = (e) => {
      const msg = typeof e?.detail === 'string' ? e.detail : String(e?.detail?.message || '');
      if (msg) setMessage(msg);
    };
    window.addEventListener('cim-toast', handler);
    return () => window.removeEventListener('cim-toast', handler);
  }, []);

  const showToast = useCallback((msg) => setMessage(msg), []);
  return (
    <ToastCtx.Provider value={{ message, showToast }}>
      {children}
      {message && <div className="toast">{message}</div>}
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
```

---

### 2.2 No React Router — navigation is not bookmarkable

**Severity:** 🟠 High  
**File:** `frontend/src/App.js` line 48  

#### Problem

```jsx
const [view, setView] = useState('dashboard');
```

All navigation is in-memory. Consequences:
- Refreshing the page always returns to Dashboard — users lose their place
- Browser back/forward buttons don't work
- No URL to share ("show me this stock's chart")
- Cannot deep-link from an external notification/email

#### Fix

Install `react-router-dom` and define routes:

```bash
cd frontend && npm install react-router-dom
```

```jsx
// frontend/src/index.js
import { HashRouter } from 'react-router-dom';
// Use HashRouter since the app is served locally — no server-side routing needed
root.render(<HashRouter><App /></HashRouter>);
```

```jsx
// frontend/src/App.js
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';

// Replace useState('dashboard') with useNavigate()
const navigate = useNavigate();

// Replace setView('market-map') with:
const goToMarketMap = useCallback(() => navigate('/market-map'), [navigate]);

// Route definitions:
<Routes>
  <Route path="/"              element={<DashboardPage ... />} />
  <Route path="/indices"       element={<IndicesPage ... />} />
  <Route path="/movers"        element={<MoversPage ... />} />
  <Route path="/market-map"    element={<MarketMapPage ... />} />
  <Route path="/earnings"      element={<EarningsBeatsPage ... />} />
  <Route path="/watchlist"     element={<WatchlistPage ... />} />
  <Route path="/swings"        element={<PotentialSwingsPage ... />} />
  <Route path="/chart/:symbol" element={<ChartTabsView ... />} />
  <Route path="*"              element={<Navigate to="/" replace />} />
</Routes>
```

---

### 2.3 Large page files need decomposition

**Severity:** 🟠 Medium  

| File | Size | Problem |
|------|------|---------|
| `DashboardPage.js` | 118 KB | Contains screener, chart panel, filter builders, movers section, snapshot status |
| `WatchlistPage.js` | 85 KB | Contains sidebar list, chart, earnings panel, filter bar, context menu handling |
| `MoversPage.js` | 41 KB | Live movers, day change list, chart panel all in one |
| `PotentialSwingsPage.js` | 49 KB | Scanner logic, results table, chart panel, filter state |
| `EarningsBeatsPage.js` | 51 KB | Table, chart, quarterly panel, filter state all combined |

#### Fix for `DashboardPage.js`

Break into:
```
frontend/src/pages/dashboard/
  DashboardPage.jsx          ← thin orchestrator, composes sub-components
  ScreenerTable.jsx          ← the paginated stock table
  ScreenerFilterBar.jsx      ← the filter chips row
  ScreenerFilterBuilders.jsx ← EMA, MACD, StochRSI, Price, MarketCap builders
  DashboardChartPanel.jsx    ← the right-side chart when a stock is selected
```

#### Fix for `WatchlistPage.js`

Break into:
```
frontend/src/pages/watchlist/
  WatchlistPage.jsx
  WatchlistSidebar.jsx       ← the left list of watchlists and their items
  WatchlistChart.jsx         ← the chart for the selected watchlist item
  WatchlistEarningsSection.jsx
```

---

### 2.4 No code splitting — all pages loaded upfront

**Severity:** 🟡 Medium  
**File:** `frontend/src/App.js` lines 3–14  

#### Problem

```jsx
import MarketMapPage       from './pages/MarketMapPage';
import PotentialSwingsPage from './pages/PotentialSwingsPage';
import EarningsBeatsPage   from './pages/EarningsBeatsPage';
```

All 14 pages + all components load in the initial JS bundle. The `d3-hierarchy` treemap library
(used only by MarketMapPage) and `lightweight-charts` (used only on chart pages) inflate the bundle
for every user who opens Dashboard first.

#### Fix

```jsx
import React, { lazy, Suspense } from 'react';

const MarketMapPage       = lazy(() => import('./pages/MarketMapPage'));
const PotentialSwingsPage = lazy(() => import('./pages/PotentialSwingsPage'));
const EarningsBeatsPage   = lazy(() => import('./pages/EarningsBeatsPage'));
const WatchlistPage       = lazy(() => import('./pages/WatchlistPage'));
// Keep DashboardPage and IndicesPage as eager imports (most visited)

// Wrap route rendering:
<Suspense fallback={<div className="page-loading">Loading...</div>}>
  {/* route rendering */}
</Suspense>
```

Expected bundle size reduction: ~30–40% for initial load.

---

### 2.5 ESLint warnings are building up — 10+ unresolved

**Severity:** 🟡 Medium  
**Files:** Multiple  

Current warnings at build time:
```
src/App.js
  Line 4:8     'ChartPage' is defined but never used
  Line 285:6   React Hook useCallback missing dependency: 'rebuildSnapshotsBusy'
  Line 384:9   'openIndex' is assigned a value but never used
  Line 2075:6  useLayoutEffect missing dependency: 'updateMenuRect'

src/pages/DashboardPage.js
  Line 228:10  'searchDropdownRect' assigned but never used
  Line 1023:18 'handleAddPickToPortfolio' defined but never used

src/pages/IndicesPage.js
  Line 47:10   'loading' assigned but never used

src/pages/MarketMapPage.js
  Line 278:6   useEffect missing dependency: 'selected?.name'

src/pages/SplitChartPage.js
  Line 66:6    useEffect missing dependency: 'onActiveSymbolChange'

src/support/supportQrPayload.generated.js
  Line 1:1     Unexpected Unicode BOM (Byte Order Mark)
```

#### Fix

Resolve each warning:
1. Remove unused `ChartPage` import from `App.js` (it was replaced by the tabbed chart system)
2. Remove unused `openIndex`, `searchDropdownRect`, `handleAddPickToPortfolio`, `loading` variables
3. Fix `useEffect` dependency arrays — either add the missing dep or use `useRef` for stable refs
4. Fix `supportQrPayload.generated.js` BOM by re-saving the file as UTF-8 without BOM
5. Add `"no-warning"` to build script: `"build": "REACT_APP_ENV=production react-scripts build && eslint src --max-warnings 0"`

---

## 3. Performance

---

### 3.1 Cache eviction is O(n) on every insert

**Severity:** 🟡 Medium  
**File:** `server/server.py` lines 1574–1576  

#### Problem

```python
if CHART_CACHE_MAX_ENTRIES > 0 and key not in _chart_cache and len(_chart_cache) >= CHART_CACHE_MAX_ENTRIES:
    oldest_key = min(_chart_cache, key=lambda k: _chart_cache[k].get("ts", 0))  # ← O(n)
    _chart_cache.pop(oldest_key, None)
```

With 300 cache entries, every new chart load triggers a linear scan of 300 items to find the oldest.
This is called on every cache miss for every chart tab opened.

#### Fix

As described in §1.2 — replace with `cachetools.TTLCache` which uses an O(1) LRU structure
internally. No manual eviction needed.

---

### 3.2 `_stock_df` screener DataFrame reloads on every filter cache miss

**Severity:** 🟡 Medium  
**File:** `server/server.py` around `_stock_df` global  

#### Problem

`_stock_df` is loaded from SQLite into a Pandas DataFrame once, but `invalidate_stock_df()` sets it
to `None` after every admin job, split adjustment, or snapshot rebuild. The next screener request
then re-reads all 2251 rows. While this is correct for data freshness, it means the dashboard
screener feels sluggish after any admin operation.

#### Fix

Add a `_stock_df_lock` and reload the DataFrame in a background thread (not blocking the API
request). Return stale data while the reload is in-progress:

```python
_stock_df_lock    = threading.Lock()
_stock_df_loading = threading.Event()

def get_stock_df_async():
    """Return current df immediately; trigger background reload if stale."""
    global _stock_df
    with _stock_df_lock:
        if _stock_df is not None:
            return _stock_df
        current = _stock_df  # may be None
    if not _stock_df_loading.is_set():
        _stock_df_loading.set()
        threading.Thread(target=_reload_stock_df, daemon=True).start()
    return current  # return None or stale; caller handles None gracefully
```

---

### 3.3 NSE index gap detection only runs at startup

**Severity:** 🟡 Medium  
**File:** `server/server.py` `_on_startup()` → `_ensure_equity_indices_background()`  

#### Problem

`sync_nse_index_history()` runs once when the server starts. If the server runs continuously for
days (common in production), new index data gaps from NSE API throttling will not be detected or
repaired until the next restart.

#### Fix

Add a scheduled daily run using the existing scheduler pattern from `earnings_plus_scheduler.py`:

```python
# server/index_history_scheduler.py

import threading
import time
from zoneinfo import ZoneInfo
from datetime import datetime

_thread: threading.Thread | None = None
_sync_fn = None

def configure(sync_fn):
    global _sync_fn
    _sync_fn = sync_fn

def _run():
    IST = ZoneInfo("Asia/Kolkata")
    TARGET_HOUR = 6   # 06:00 IST daily
    TARGET_MIN  = 0
    while True:
        now = datetime.now(IST)
        if now.hour == TARGET_HOUR and now.minute == TARGET_MIN:
            try:
                _sync_fn()
            except Exception as e:
                print(f"[index_history_scheduler] Error: {e}")
            time.sleep(60)  # avoid running twice in the same minute
        time.sleep(30)  # check every 30 seconds

def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, name="index-history-scheduler", daemon=True)
    _thread.start()
```

---

## 4. Developer Experience

---

### 4.1 No one-command dev setup — especially broken on Mac

**Severity:** 🔴 Critical  
**Affects:** All new developers  

#### Problem

A new Mac developer has to:
1. `python3 -m venv .venv` (know to use venv, not system pip)
2. `.venv/bin/pip install -r requirements_runtime.txt`
3. `cd frontend && npm install`
4. Realise there's no SQLite DB → `FileNotFoundError`
5. Manually create the DB → wrong schema → server crashes on startup
6. Debug the import path issue with `uvicorn --reload`

We went through all of these in the current session.

#### Fix: Add `Makefile` and `scripts/dev_setup.py`

```makefile
# Makefile (project root)

.PHONY: setup backend frontend dev clean

setup:
	@echo "→ Creating Python virtual environment..."
	python3 -m venv .venv
	@echo "→ Installing Python dependencies..."
	.venv/bin/pip install -r requirements_runtime.txt -q
	@echo "→ Installing frontend npm packages..."
	cd frontend && npm install --silent
	@echo "→ Seeding development database..."
	.venv/bin/python3 scripts/dev_setup.py
	@echo ""
	@echo "✅ Setup complete. Run 'make dev' to start."

backend:
	.venv/bin/python3 -m uvicorn server.server:app \
		--reload \
		--reload-dir server \
		--host 127.0.0.1 \
		--port 8000 \
		--app-dir .

frontend:
	cd frontend && BROWSER=none npm start

dev:
	@echo "Starting backend on :8000 and frontend on :3000..."
	@make -j2 backend frontend

clean:
	rm -rf .venv frontend/node_modules frontend/build data/nse_data.db __pycache__

test:
	.venv/bin/python3 -m pytest server/tests/ -v
	.venv/bin/python3 scripts/smoke_test.py
```

```python
# scripts/dev_setup.py
"""
One-shot development database seeder.
Run once after cloning: python3 scripts/dev_setup.py
"""
import sqlite3, random, math
from datetime import date, timedelta
from pathlib import Path

# ... (full implementation as in create_dev_db.py + seed_ohlcv.py combined)
# Creates all tables, seeds 20 NSE stocks, seeds indices,
# seeds 2 years of OHLCV, computes change_pct from last 2 candles
```

---

### 4.2 Python package versions are not pinned

**Severity:** 🟠 High  
**File:** `requirements_runtime.txt`  

#### Problem

```
fastapi
uvicorn
pandas
yfinance
tradingview-screener
requests
cryptography
```

No versions pinned. In 6 months:
- `yfinance` releases a breaking API change (it has done this multiple times historically)
- `pandas` 3.x drops deprecated APIs used in `server.py`
- `fastapi` 0.200+ changes how `startup` events work
- All three happen at once, and debugging which broke production is a nightmare

#### Fix

Create `requirements.txt` with pinned versions (generated from current working environment):

```
# requirements.txt — PINNED for reproducibility
# Regenerate: .venv/bin/pip freeze > requirements.txt
fastapi==0.136.3
uvicorn==0.49.0
pandas==2.3.3
yfinance==1.4.1
tradingview-screener==3.2.0
requests==2.34.2
cryptography==48.0.1
cachetools==5.3.3        # new — for thread-safe TTLCache
python-dotenv==1.0.1     # new — for .env support
```

Keep `requirements_runtime.txt` as the loose version spec for distribution builds.
Development uses pinned `requirements.txt`.

---

### 4.3 No `.env` support — config spread across `os.getenv()` calls

**Severity:** 🟠 Medium  
**File:** `server/server.py` lines 158–163  

#### Problem

```python
FEEDBACK_SMTP_HOST = os.getenv("NSE_PULSE_SMTP_HOST", "")
FEEDBACK_SMTP_PORT = int(os.getenv("NSE_PULSE_SMTP_PORT", "587"))
FEEDBACK_SMTP_USER = os.getenv("NSE_PULSE_SMTP_USER", "")
FEEDBACK_SMTP_PASS = os.getenv("NSE_PULSE_SMTP_PASS", "")
```

No `.env.example` exists. Developers have no way to know which env vars are available without
reading all 8,351 lines of `server.py`. Config is also scattered across `server.py`, `cim_bootstrap.py`,
`app_code_crypto.py`, and `github_updates.py`.

#### Fix

Add `python-dotenv` and create `.env.example`:

```bash
# .env.example — copy to .env and fill in for local development
# This file is safe to commit. .env is gitignored.

# ── Development mode ─────────────────────────────────────────────────────────
CIM_DEV=1                          # Set to 1 to skip license validation

# ── Database ──────────────────────────────────────────────────────────────────
# CIM_DB_PATH=./data/nse_data.db   # Override default DB location

# ── GitHub Updates ───────────────────────────────────────────────────────────
CIM_GITHUB_OWNER=unnwired
CIM_GITHUB_REPO=cim-updates
# GITHUB_TOKEN=                    # Optional: prevents rate limiting (60→5000 req/hr)

# ── Email / Feedback ─────────────────────────────────────────────────────────
# NSE_PULSE_SMTP_HOST=smtp.gmail.com
# NSE_PULSE_SMTP_PORT=587
# NSE_PULSE_SMTP_USER=
# NSE_PULSE_SMTP_PASS=
# NSE_PULSE_FROM_EMAIL=

# ── CORS ─────────────────────────────────────────────────────────────────────
# CIM_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Load in `server.py`:
```python
# At top of server.py, before any os.getenv() calls
from dotenv import load_dotenv
load_dotenv()  # reads .env if present, silently skips if not
```

---

### 4.4 `uvicorn --reload` is broken on Mac

**Severity:** 🟠 Medium  
**Cause:** Reloader spawns subprocess without CWD in `sys.path`  

#### Problem

Running `.venv/bin/uvicorn server.server:app --reload` fails with:
```
ERROR: Error loading ASGI app. Could not import module "server.server".
```

The `StatReload` reloader spawns a new Python subprocess that doesn't inherit the parent's
`sys.path`. So `import server.server` fails because `.` (the project root) is not in the path.

#### Fix

Use `--reload-dir` to limit watch scope AND pass `--app-dir` to ensure correct path:

```bash
# Correct dev startup command for Mac:
.venv/bin/python3 -m uvicorn server.server:app \
    --reload \
    --reload-dir server \
    --host 127.0.0.1 \
    --port 8000 \
    --app-dir .
```

Document this in `README.md` under "Running locally on Mac".

Alternatively, add a `dev_server.py` script in the project root:
```python
# dev_server.py — run with: python3 dev_server.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["server"],
    )
```

---

### 4.5 Frontend proxy is not configured — devs get 404 on `/api/*`

**Severity:** 🔴 (was a real issue in this session)  
**File:** `frontend/package.json`  

#### Problem

When running the React dev server (`npm start` on port 3000) without the `proxy` field,
all `axios.get('/api/stocks')` calls hit `localhost:3000/api/stocks` — the dev server itself —
and return 404. The FastAPI backend on port 8000 is never reached.

#### Fix (already applied in this session)

```json
// frontend/package.json
{
  "proxy": "http://127.0.0.1:8000"
}
```

This should have been present from the beginning. Commit it and never remove it.

---

## 5. Testing

---

### 5.1 Zero API integration tests

**Severity:** 🔴 Critical  
**Directory:** `server/tests/` (11 unit test files, but all are pure-function tests)  

#### Problem

There are no tests that actually call the FastAPI routes end-to-end. A schema change or import
error in `server.py` will not be caught until the server is started and a human tries to use it.

#### Fix

Use FastAPI's built-in `TestClient`:

```python
# server/tests/test_api_integration.py
import pytest
import sqlite3
from fastapi.testclient import TestClient
from pathlib import Path

# Create a minimal in-memory DB for tests
@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("data") / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE screener (
        symbol TEXT PRIMARY KEY, name TEXT, market_cap REAL,
        price REAL, change_pct REAL, pe REAL, nse_sector TEXT,
        issued_shares INTEGER, updated_at TEXT
    )""")
    conn.execute("""CREATE TABLE historical_data (
        Symbol TEXT, Date TEXT, Open REAL, High REAL, Low REAL,
        Close REAL, Volume INTEGER, PRIMARY KEY(Symbol, Date)
    )""")
    conn.execute("INSERT INTO screener VALUES ('TCS','Tata',14000000,3890,0.5,32,1,'IT',3653000000,'2026-01-01')")
    # insert 100+ daily OHLCV rows for TCS...
    conn.commit()
    conn.close()
    return db

@pytest.fixture(scope="module")
def client(test_db, monkeypatch):
    monkeypatch.setattr("server.server.DB_PATH", test_db)
    from server.server import app
    return TestClient(app)

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_stocks_list(client):
    r = client.get("/api/stocks?pageSize=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["data"][0]["Symbol"] == "TCS"

def test_chart_data_tcs(client):
    r = client.get("/api/chart-data/TCS?timeframe=1D&bars_limit=100")
    assert r.status_code == 200
    body = r.json()
    assert "bars" in body
    assert len(body["bars"]) > 0

def test_chart_data_unknown_symbol(client):
    r = client.get("/api/chart-data/FAKESYM999?timeframe=1D&bars_limit=100")
    assert r.status_code == 404

def test_indices(client):
    r = client.get("/api/indices")
    assert r.status_code == 200
```

---

### 5.2 No tests for `aggregate_ohlcv()` — the chart engine

**Severity:** 🔴 Critical  
**Location:** `server/server.py` — `aggregate_ohlcv()` function  

#### Problem

`aggregate_ohlcv()` converts raw daily OHLCV rows into 1W, 2W, 1M etc. candles. This is the heart
of the charting system — if it's wrong, every chart is wrong. There are currently zero tests for it.

#### Fix

```python
# server/tests/test_chart_aggregation.py
import pandas as pd
import pytest
from server.server import aggregate_ohlcv

def make_daily_df(rows):
    """rows: list of (date_str, open, high, low, close, volume)"""
    return pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])

def test_1d_passthrough():
    """1D timeframe should return one bar per trading day."""
    df = make_daily_df([
        ("2025-01-06", 100, 110, 95, 105, 1000000),
        ("2025-01-07", 105, 115, 100, 108, 900000),
    ])
    bars = aggregate_ohlcv(df, "1D")
    assert len(bars) == 2
    assert bars[0]["open"] == 100
    assert bars[0]["close"] == 105
    assert bars[1]["close"] == 108

def test_1w_aggregation():
    """1W should aggregate Mon-Fri into one bar with correct OHLC."""
    # Week: Jan 6–10 2025
    df = make_daily_df([
        ("2025-01-06", 100, 115, 98, 110, 500000),   # Mon
        ("2025-01-07", 110, 120, 105, 118, 600000),  # Tue
        ("2025-01-08", 118, 125, 112, 115, 550000),  # Wed
        ("2025-01-09", 115, 116, 108, 109, 480000),  # Thu
        ("2025-01-10", 109, 112, 100, 102, 520000),  # Fri
    ])
    bars = aggregate_ohlcv(df, "1W")
    assert len(bars) == 1
    assert bars[0]["open"] == 100        # first day open
    assert bars[0]["high"] == 125        # highest high of week
    assert bars[0]["low"] == 98          # lowest low of week
    assert bars[0]["close"] == 102       # last day close
    assert bars[0]["volume"] == 2650000  # sum of volumes

def test_2w_aggregation():
    """2W should produce one bar per two-week period."""
    # Build 10 trading days (2 weeks)
    dates = pd.bdate_range("2025-01-06", periods=10).strftime("%Y-%m-%d").tolist()
    rows = [(d, 100+i, 110+i, 90+i, 105+i, 1000000) for i, d in enumerate(dates)]
    df = make_daily_df(rows)
    bars = aggregate_ohlcv(df, "2W")
    assert len(bars) == 1

def test_empty_df_returns_empty():
    df = make_daily_df([])
    bars = aggregate_ohlcv(df, "1D")
    assert bars == []
```

---

### 5.3 No tests for EMA calculations

**Severity:** 🟠 High  

#### Problem

EMA9/21/50/100/200 are computed in `server.py` for chart overlays and indicator snapshots.
Wrong EMA calculations would produce incorrect trading signals for all users. No tests exist.

#### Fix

```python
# server/tests/test_ema.py
from server.server import compute_ema  # or wherever it's defined

def test_ema_9_basic():
    """EMA(9) of a constant series should equal the constant."""
    closes = [100.0] * 50
    emas = compute_ema(closes, period=9)
    assert abs(emas[-1] - 100.0) < 0.01

def test_ema_smoothing_factor():
    """EMA should react faster than SMA to recent price changes."""
    closes = [100.0] * 30 + [200.0] * 10  # sudden spike
    ema9  = compute_ema(closes, period=9)
    ema50 = compute_ema(closes, period=50)
    # EMA9 should be higher (reacted faster to the 200 spike)
    assert ema9[-1] > ema50[-1]

def test_ema_convergence():
    """EMA should converge to price level given enough bars."""
    closes = [50.0] * 200 + [150.0] * 200
    ema = compute_ema(closes, period=21)
    assert abs(ema[-1] - 150.0) < 1.0  # should be very close to 150
```

---

### 5.4 Mac-runnable smoke test (replacement for `Test-CiMPackagedSmoke.ps1`)

**Severity:** 🟠 Medium  

#### Problem

`scripts/Test-CiMPackagedSmoke.ps1` is Windows PowerShell only. Mac developers have no smoke test.

#### Fix

```python
# scripts/smoke_test.py
"""
Cross-platform smoke test. Requires backend running on :8000.
Usage: python3 scripts/smoke_test.py
"""
import sys
import requests

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0

def check(name, condition, got=""):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}  {got}")
        FAIL += 1

print("CiM Smoke Test")
print("=" * 40)

# 1. Health
r = requests.get(f"{BASE}/api/health", timeout=5)
check("GET /api/health → 200",        r.status_code == 200)
check("health.status == ok",          r.json().get("status") == "ok")
check("health.db_exists == true",     r.json().get("db_exists") == True)

# 2. Stocks
r = requests.get(f"{BASE}/api/stocks?pageSize=500", timeout=10)
check("GET /api/stocks → 200",        r.status_code == 200)
check("stocks.total >= 1",            r.json().get("total", 0) >= 1)

# 3. Chart data
syms = [s["Symbol"] for s in r.json().get("data", [])[:3]]
for sym in syms:
    r2 = requests.get(f"{BASE}/api/chart-data/{sym}?timeframe=1D&bars_limit=100", timeout=10)
    check(f"chart {sym} → 200 with bars",
          r2.status_code == 200 and len(r2.json().get("bars", [])) > 0)

# 4. Indices
r = requests.get(f"{BASE}/api/indices", timeout=5)
check("GET /api/indices → 200",       r.status_code == 200)
check("indices.data not empty",       len(r.json().get("data", [])) > 0)

# 5. Static (if frontend build present)
r = requests.get(f"{BASE}/", timeout=5)
if r.status_code == 200 and "root" in r.text:
    check("Frontend build served correctly", True)

print("=" * 40)
print(f"Results: {PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
```

---

## 6. Database & Data Pipeline

---

### 6.1 Dev database has no `Change %` — screener column is always null

**Severity:** 🟠 Medium  
**Cause:** `change_pct` in `screener` is computed by the daily scraper, which doesn't run in dev  

#### Problem

The `/api/stocks` response shows `"Change %": null` for every stock because:
1. The `change_pct` column in `screener` is populated by `scrape_daily.py` which pulls live prices
2. In dev, we only seed static prices — the column stays null/zero
3. The UI shows no colour coding, no gainers/losers filtering works, Market Pulse is empty

#### Fix

Add to `scripts/dev_setup.py` — compute `change_pct` from the last two seeded OHLCV candles:

```python
# After seeding OHLCV in dev_setup.py:
conn.execute("""
    UPDATE screener
    SET change_pct = (
        SELECT ROUND((t1.Close - t2.Close) / t2.Close * 100, 2)
        FROM historical_data t1
        JOIN historical_data t2 ON t1.Symbol = t2.Symbol
        WHERE t1.Symbol = screener.symbol
          AND t1.Date = (SELECT MAX(Date) FROM historical_data WHERE Symbol = screener.symbol)
          AND t2.Date = (SELECT MAX(Date) FROM historical_data
                         WHERE Symbol = screener.symbol
                           AND Date < (SELECT MAX(Date) FROM historical_data WHERE Symbol = screener.symbol))
    )
""")
```

---

### 6.2 No audit log for admin jobs

**Severity:** 🟡 Medium  

#### Problem

When `POST /api/admin/fetch-ohlcv` runs, there is no persistent record of:
- When the job ran
- How many symbols were updated
- Whether it succeeded or partially failed
- What errors occurred

Debugging "why is TCS data stale?" requires searching log files manually.

#### Fix

Add `admin_job_log` table in the migration (see §1.4) and write to it after every job:

```python
# server/routers/admin.py

def log_admin_job(conn, job_name, status, symbols_affected=0, error=None):
    conn.execute("""
        INSERT INTO admin_job_log (job, started_at, finished_at, status, symbols_affected, error_message)
        VALUES (?, ?, datetime('now'), ?, ?, ?)
    """, (job_name, job_state.get("started_at"), status, symbols_affected, error))
    conn.commit()
```

Add a `GET /api/admin/job-log?limit=50` endpoint so the admin panel can show history.

---

### 6.3 Market Pulse page shows nothing without NSE live API

**Severity:** 🟡 Medium  
**File:** `frontend/src/pages/MarketPulsePage.js`  

#### Problem

Market Pulse depends entirely on `movers_live.py` which calls `https://www.nseindia.com/api/...`.
Without internet or NSE access (common on Mac in development), the page is completely blank with
no fallback or explanation.

#### Fix

Add a fallback computed from `historical_data`:

```python
# server/routers/movers.py

@app.get("/api/market-pulse/summary")
def get_market_pulse_summary():
    try:
        # Try live NSE first
        return movers_live.get_market_pulse_summary()
    except Exception:
        pass

    # Fallback: compute advance/decline from last two DB candles
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT s.symbol,
                   (h1.Close - h2.Close) / h2.Close * 100 AS day_chg
            FROM screener s
            JOIN historical_data h1 ON h1.Symbol = s.symbol
                AND h1.Date = (SELECT MAX(Date) FROM historical_data WHERE Symbol = s.symbol)
            JOIN historical_data h2 ON h2.Symbol = s.symbol
                AND h2.Date = (SELECT MAX(Date) FROM historical_data
                               WHERE Symbol = s.symbol AND Date < h1.Date)
        """).fetchall()
        advances = sum(1 for r in rows if r[1] > 0)
        declines = sum(1 for r in rows if r[1] < 0)
        unchanged = len(rows) - advances - declines
        return {
            "source": "db_fallback",
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "total": len(rows),
        }
    finally:
        conn.close()
```

---

## 7. Security

---

### 7.1 CORS wildcard `allow_origins=["*"]`

**Severity:** 🟠 Medium  
**File:** `server/server.py` line 211  

#### Problem

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # ← any origin can call the API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

While CiM is local-only today, if a user ever runs the backend accessible on their LAN (e.g. for a
second PC), any webpage on the internet could make cross-origin requests to their CiM backend and
read their portfolio/watchlist data.

#### Fix

```python
import os

_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000"
_allowed = [o.strip() for o in os.getenv("CIM_ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
```

---

### 7.2 `window.confirm()` used for destructive admin actions

**Severity:** 🟡 Medium  
**File:** `frontend/src/App.js` lines 236–239, 799–800  

#### Problem

```jsx
if (!window.confirm(
  'Clear cached indicator snapshots and rebuild from historical data...'
)) return;
```

`window.confirm()` is a browser-native blocking dialog — it:
- Freezes the entire tab during display
- Cannot be styled
- Looks completely different from the rest of the CiM UI
- Is blocked by some browser policies when called programmatically

#### Fix

Replace with an in-app modal dialog component:

```jsx
// frontend/src/components/ConfirmModal.jsx
export function ConfirmModal({ title, message, confirmLabel="Confirm", onConfirm, onCancel }) {
  return (
    <div className="modal-overlay">
      <div className="confirm-modal">
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="confirm-modal-actions">
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn-danger"    onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
```

Usage:
```jsx
const [confirmState, setConfirmState] = useState(null);

// Instead of window.confirm(...):
setConfirmState({
  title: "Rebuild Indicator Snapshots",
  message: "This will clear and rebuild all snapshots. This can take several minutes.",
  onConfirm: () => { setConfirmState(null); doRebuild(); },
  onCancel:  () => setConfirmState(null),
});
```

---

## 8. Product & UX

---

### 8.1 Chart tab limit is hardcoded at 5

**Severity:** 🟡 Low  
**File:** `frontend/src/App.js` line 26  

```jsx
const MAX_CHART_TABS = 5;
```

#### Fix

Store in `data/layout.json` and expose in Settings:

```jsx
// In settings state:
const [maxChartTabs, setMaxChartTabs] = useState(5);

// On load:
const layout = await axios.get('/api/layout');
setMaxChartTabs(layout.data?.maxChartTabs ?? 5);

// In settings UI:
<label>Max chart tabs
  <select value={maxChartTabs} onChange={e => updateMaxChartTabs(Number(e.target.value))}>
    {[3, 5, 8, 10, 15].map(n => <option key={n} value={n}>{n}</option>)}
  </select>
</label>
```

---

### 8.2 No keyboard shortcut system

**Severity:** 🟡 Medium  

#### Problem

Navigation requires a mouse for everything. Power users analysing multiple stocks have no way to
switch views, open search, or navigate charts without clicking.

#### Fix

Add a global keyboard shortcut handler in `App.js`:

```jsx
useEffect(() => {
  let gPressed = false;
  let gTimer = null;

  function handleKey(e) {
    // Don't trigger inside input/textarea
    if (['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)) return;

    // '/' → open global search
    if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      setGlobalSearchOpen(true);
      return;
    }

    // Escape → close overlays
    if (e.key === 'Escape') {
      setGlobalSearchOpen(false);
      setSettingsOpen(false);
      return;
    }

    // 'G' prefix navigation (g d = go to Dashboard, etc.)
    if (e.key === 'g' && !e.ctrlKey) {
      gPressed = true;
      clearTimeout(gTimer);
      gTimer = setTimeout(() => { gPressed = false; }, 1000);
      return;
    }
    if (gPressed) {
      gPressed = false;
      clearTimeout(gTimer);
      const goMap = {
        'd': () => setView('dashboard'),
        'i': () => setView('indices'),
        'm': () => setView('market-map'),
        'w': () => setView('watchlist'),
        'p': () => setView('market-pulse'),
        'e': () => setView('earnings-beats'),
      };
      goMap[e.key]?.();
    }
  }

  window.addEventListener('keydown', handleKey);
  return () => window.removeEventListener('keydown', handleKey);
}, []);
```

Display shortcuts in a `?` help overlay or in the settings menu tooltip.

---

### 8.3 Feedback opens Google Form — no in-app structured feedback

**Severity:** 🟡 Low  
**File:** `frontend/src/App.js` lines 734–739  

#### Problem

```jsx
const target = `${baseUrl}?usp=pp_url&entry.${entryId}=${encodeURIComponent(message)}`;
window.open(target, '_blank', 'noopener,noreferrer');
```

The feedback flow opens an external Google Form in a new tab. The user has to:
1. Wait for the form to load
2. Re-describe their issue (context from `view` is URL-encoded but form fields aren't pre-populated
   reliably)
3. Submit and hope it went through

#### Fix

Add `POST /api/feedback` endpoint that stores to `data/feedback.json`:

```python
# server/routers/settings.py
@app.post("/api/feedback")
def submit_feedback(payload: dict = Body(...)):
    entry = {
        "id": str(uuid.uuid4()),
        "type": payload.get("type", "issue"),  # 'issue' | 'feature'
        "message": str(payload.get("message", ""))[:4000],
        "view": str(payload.get("view", "")),
        "version": open(BASE_DIR / "version.txt").read().strip(),
        "submitted_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
    }
    path = DATA_DIR / "feedback.json"
    existing = json.loads(path.read_text()) if path.exists() else []
    existing.append(entry)
    path.write_text(json.dumps(existing, indent=2))
    # Optionally also attempt SMTP if configured
    return {"status": "saved", "id": entry["id"]}
```

This works offline. If SMTP is configured, also send an email. No Google dependency.

---

### 8.4 `Potential Swings` is hidden from distribution clients

**Severity:** 🟡 Low (product decision)  
**File:** `frontend/src/App.js` line 615  

```jsx
const goToPotentialSwings = useCallback(() => {
  if (isDistributionProfile) return;   // ← hidden in packaged builds
  setView('potential-swings');
}, []);
```

The MACD/StochRSI swing scanner is fully built and working but gated out for all clients.

**Recommendation:** Either:
1. Enable it for all clients (it's a key differentiator)
2. Gate by license tier (same license file, different machine code tier)
3. Document the product decision in `docs/handoff/USER_REQUIREMENTS.md` to avoid confusion for future developers

---

## Prioritised Implementation Roadmap

### Sprint 1 — Stability & Dev Setup (1–2 weeks)
- [ ] 4.1 Add `Makefile` + `scripts/dev_setup.py`
- [ ] 4.2 Pin package versions in `requirements.txt`
- [ ] 4.3 Add `.env.example` + `python-dotenv`
- [ ] 4.4 Fix `uvicorn --reload` Mac command
- [ ] 4.5 Ensure `frontend/package.json` proxy is committed
- [ ] 1.2 Thread-safe cache with `cachetools`
- [ ] 5.4 Add `scripts/smoke_test.py`
- [ ] 2.5 Fix all ESLint warnings

### Sprint 2 — Architecture (2–4 weeks)
- [ ] 1.1 Split `server.py` into feature routers (largest task — do incrementally)
- [ ] 1.3 Add `server/core/install_root.py` guard + CI grep check
- [ ] 1.4 DB migrations system (`schema_migrations` table)
- [ ] 2.1 Extract 3 React Contexts (`Toast`, `Watchlist`, `AdminJob`)
- [ ] 2.4 Add `lazy()` code splitting for heavy pages

### Sprint 3 — Testing (1–2 weeks)
- [ ] 5.1 FastAPI `TestClient` integration tests
- [ ] 5.2 `aggregate_ohlcv()` unit tests
- [ ] 5.3 EMA calculation unit tests
- [ ] 6.1 Fix `change_pct` in dev DB after seeding

### Sprint 4 — Feature Polish (ongoing)
- [ ] 2.2 React Router (enables deep links and browser navigation)
- [ ] 2.3 Decompose `DashboardPage.js` and `WatchlistPage.js`
- [ ] 6.3 Market Pulse DB fallback
- [ ] 8.2 Keyboard shortcut system
- [ ] 8.3 In-app feedback submission
- [ ] 8.1 Configurable chart tab limit
- [ ] 7.2 Replace `window.confirm()` with modal dialogs

---

*Document maintained on branch `jay/dev-workspace`*  
*Last updated: June 2026*
