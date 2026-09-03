# Charts In Motion — Lovable Design Handoff

**Purpose:** Give Lovable (or any external UI designer) enough structure to extend the **browser showcase** UI without breaking product conventions.  
**Audience:** Design + front-end implementation on `packages/browser/`  
**Last updated:** 03 Sep 26  
**Companion docs:** `CiMLovableDesign/CIM_UI_STANDARD.md` (mandatory tokens/buttons), `CiMLovableDesign/INR_DISPLAY.md` (M/B/T formatting)

> **GitHub:** All Lovable design files live in the repo root folder **[CiMLovableDesign/](../CiMLovableDesign/)** — start with `CiMLovableDesign/README.md`.

---

## 1. What CiM Is

**Charts In Motion (CiM)** is a dark-themed, information-dense **NSE equities & indices** workstation:

- Local FastAPI backend + React SPA (no React Router — `view` state in `App.js`)
- SQLite market DB + per-user JSON for portfolio, watchlists, P&L ledger, layout
- Primary UI code: **`packages/browser/src/`**
- Production CSS tokens: **`packages/browser/src/styles/global.css`** (snapshot: `CiMLovableDesign/reference/global.css`)

### Product surfaces (do not mix scopes)

| Surface | Code | Port | Notes |
|---------|------|------|--------|
| **Web showcase (default for Lovable)** | `packages/browser/` + `packages/server/web_host.py` | Testbed **8002**, live **8001** | Browser-only; online auth; Tailscale Funnel for public HTTPS |
| **Desktop Electron** | `packages/desktop/` + same browser bundle | **8000** | Offline license; separate agent scope |
| **Mobile dashboard** | `D:\CiM\Mobile_Testbed\` (separate tree) | **8010** / **8011** | Read `packages/browser/` for API patterns only |

**Lovable should target `packages/browser/`** and follow `CiMLovableDesign/CIM_UI_STANDARD.md`. Deploy testbed via `scripts/Deploy-CiMShowcaseFromRepo.ps1` → `D:\CiM\Client_Test`.

---

## 2. App Shell Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Top tab bar (Market Pulse, NSE, Movers, …) + Refresh/Update     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Active page (DashboardPage, PnLPage, ChartPage, …)             │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Chart tab strip (FIFO max 5 opened full charts)                 │
├─────────────────────────────────────────────────────────────────┤
│ Server status bar (optional) │ Knowledge Base chrome rail (?)    │
└─────────────────────────────────────────────────────────────────┘
```

**Navigation:** `packages/browser/src/App.js` — single `view` string (e.g. `dashboard`, `pnl`, `chart`, `index_^NSEI`, `constituents_^NSEBANK`).

**No React Router.** Deep links use view prefixes + symbol suffixes. Back navigation uses an internal stack (`chartTabStack.js`, `chartTabFifo.js`).

**Global providers (wrap app):**

| Provider | File | Role |
|----------|------|------|
| `ToastProvider` | `context/ToastContext.js` | Toasts |
| `BasketProvider` | `components/Basket.js` | Multi-symbol basket DnD |
| `IntradayPatchProvider` | `intraday/useIntradayPatch.js` | Live bar patches |
| `PageLiveProvider` | `intraday/pageLiveContext.js` | Per-page live symbol sets |
| `ChartPrefsProvider` | `chartPrefs/useChartPrefs.js` | Chart UI prefs |

---

## 3. Design System (tokens)

**Single source:** `packages/browser/src/styles/global.css` `:root` variables.

| Token | Hex (reference) | Use |
|--------|-----------------|-----|
| `--bg-primary` | `#0d1117` | App background |
| `--bg-secondary` | `#161b22` | Panels, sidebars |
| `--bg-tertiary` | `#1c2128` | Inputs, chips |
| `--bg-hover` / `--bg-active` | — | Row hover, pressed |
| `--border` / `--border-light` | — | Dividers |
| `--text-primary` | `#e6edf3` | Body |
| `--text-secondary` | `#8b949e` | Labels |
| `--text-muted` | `#484f58` | Hints |
| `--accent-blue` | `#388bfd` | **Primary actions** |
| `--accent-green` / `--accent-red` | — | P&L, success, error |
| `--font-mono` | Consolas stack | Prices, symbols, tables |
| `--font-sans` | System UI | Labels, dialogs |

**Layout constants:** `--header-height: 52px`, `--tabbar-height: 36px`, `--chart-toolbar-height: 48px`, `--row-height: 36px`.

**Rule:** Do **not** invent new hex colors in components. Use CSS variables only.

**INR / counts:** Display **M / B / T** only (never Cr/L/Lakh in UI). See `CiMLovableDesign/INR_DISPLAY.md` and `reference/formatMarketCap.js`.

---

## 4. Mandatory Chrome Modules (reuse, don’t duplicate)

| Surface | Module | Exports |
|---------|--------|---------|
| Admin / confirm dialogs | `components/cimDialogChrome.js` | `CimFormDialog`, `CimDialogButton`, `cimChipButtonStyle` |
| P&L dialogs / toolbar | `components/pnlFormDialogChrome.js` | `PnlFormDialog`, `PnlDialogButton`, `PnlToolbarButton`, `PnlGridActionButton` |
| Stock / P&L tables | `components/stockTableChrome.js` | `STOCK_LIST_ROW_HEIGHT`, `StockListGridCell`, column resize hooks |
| P&L symbol column | `components/PnlSymbolCell.js` | Fixed drag + chevron + label slots |
| Confirm prompts | `components/ConfirmDialog.js` | `askConfirm()` |
| Date selects (P&L) | `components/PnLDateSelect.js` | Period UI |

**Button spec:** 28px height, 11px font, `nowrap`, primary = `--accent-blue` weight 600. Footer buttons go in dialog **`footer` prop**, never inside `children`.

Full rules: **`CiMLovableDesign/CIM_UI_STANDARD.md`** (chrome snapshots in `CiMLovableDesign/reference/chrome/`).

---

## 5. UI/UX Principles (owner mandate)

1. **One job per region** — one primary action per toolbar/dialog footer.
2. **Gestalt proximity** — related controls adjacent with fixed gap (`8px`); avoid `space-between` that pulls pairs to opposite edges.
3. **Stable chrome** — toolbars/fields do not wrap or jump on resize; `flexWrap: nowrap`, fixed widths on controls; only content areas grow.
4. **Progressive disclosure** — long help behind `?` / Knowledge Base; keep always-on copy short.
5. **Purposeful color** — ~60/30/10; WCAG contrast on `--text-secondary` vs backgrounds.

---

## 6. Page Inventory

| Tab label | `view` key | Main component |
|-----------|------------|----------------|
| Market Pulse | `market-pulse` | `pages/MarketPulsePage.js` |
| NSE (dashboard) | `dashboard` | `pages/DashboardPage.js` |
| Market Movers | `market-movers` | `pages/MoversPage.js` |
| Market Map | `market-map` | `pages/MarketMapPage.js` (lazy) |
| Earnings+ | `earnings-beats` | `pages/EarningsBeatsPage.js` (lazy) |
| Indices | `indices` | `pages/IndicesPage.js` |
| Index chart | `index_{symbol}` | `pages/IndexChartPage.js` |
| Constituents | `constituents_{symbol}` | `pages/ConstituentsPage.js` |
| Funds | `funds` | `pages/FundsPage.js` |
| Watchlist | `watchlist` | `pages/WatchlistPage.js` |
| Portfolio | `portfolio` | (in App / portfolio views) |
| Profit/Loss | `pnl` | `pages/PnLPage.js` (lazy) |
| Potential Swings | `potential-swings` | `pages/PotentialSwingsPage.js` (lazy) |
| Full chart | `chart` | `pages/ChartPage.js` / `SplitChartPage.js` |

**Settings cog (⚙):** Account, Knowledge Base editor (dev), scheduler, admin jobs, layout save, update apply.

---

## 7. Chart System

| Piece | Path | Notes |
|-------|------|-------|
| Stock chart container | `components/chart/ChartContainer.js` | Multi-pane (price, volume, indicators); crosshair sync via `utils/chartPanelSync.js` |
| Index chart | `components/chart/IndexChartContainer.js` | Index OHLC; corp-action markers (`utils/corpChartMarkers.js`) |
| Chart header / toolbar | `components/chart/ChartHeaderBar.js`, `ChartTopBar.js` | Symbol, timeframe, indicators |
| Tab FIFO | `utils/chartTabFifo.js` | Max 5 opened chart tabs; 6th replaces oldest |
| Tab stack | `utils/chartTabStack.js` | Back/forward between chart faces |
| Intraday live patch | `intraday/useIntradayPatch.js`, `mergeLiveBars.js` | Merges live bars into cached OHLC |
| 1D % alignment | `utils/chartPanelSync.js` | List vs chart day-change must share same session anchor |

**Library:** Lightweight Charts (wrapped in chart components). Do not replace without coordinating indicator pane layout.

---

## 8. Tables & Data Grids

- **Stock list pattern:** `StockListColumnHeader.js` + `StockListGridCell.js` + `useStockListColumnWidths.js` (persisted widths in `hooks/stockListColumnStorage.js`).
- **Row height:** 32px body, 36px header (`stockTableChrome.js`).
- **Column resize:** drag on header; min widths enforced per column id.

**P&L grids:** grouped open/closed rows; `PnlSymbolCell` for parent/child alignment; Book action via `PnlGridActionButton`.

---

## 9. Filters & Screener

Filter builders live under `components/*FilterBuilder.js` (EMA, MACD, Price, Screener, etc.). Shared patterns:

- Chip toggles: `cimChipButtonStyle(active)` from `cimDialogChrome.js`
- Saved filters: `data/saved_filters.json` (server-backed layout API)
- Combined filter E2E: server tests `verify_*_filters_e2e.py`

---

## 10. Scheduler & Admin UI

| Component | Path |
|-----------|------|
| Showcase scheduler modal | `components/ShowcaseSchedulerModal.js` / `components/scheduler/SchedulerModal.js` |
| Task editor | `components/scheduler/SchedulerTaskEditor.js` |
| IST time input | `components/scheduler/IstTimeInput.js` |
| Live watchdog banner | Reads `/api/admin/live-watchdog-status` — **public Tailscale health**, not local port |

**Field styles:** `components/scheduler/schedulerFieldStyles.js` — keep toolbar nowrap.

---

## 11. Auth & Account (showcase)

- Online sign-in: `packages/browser/src/api/auth.js`, `frontend/auth/` in export trees
- **Account modal:** `components/AccountSettingsModal.js` — shows “Signed in as {email}” when `/api/license/status` returns session (web showcase must not short-circuit to `mode: dev` when cookie session exists — see `packages/server/license_client.py`)
- **Operator mode:** `?operator=1` on loopback for admin tools without exposing on public funnel

---

## 12. API Client

- **HTTP setup:** `api/http.js` (axios defaults, credentials)
- **Data fetching:** `api/client.js` — stocks, chart data, layout, admin jobs
- **Base URL:** empty string `''` (same origin as FastAPI host)

---

## 13. Folder Map (`packages/browser/src/`)

```
src/
├── App.js                 # Shell, navigation, cog menu, global search
├── api/                   # axios client + auth
├── chartPrefs/            # Chart preference context
├── components/            # Shared UI (dialogs, tables, chart, scheduler, filters)
├── content/               # Knowledge base page ids
├── context/               # Toast
├── hooks/                 # Admin jobs, column widths, server status, scroll
├── intraday/              # Live feed patch pipeline
├── pages/                 # Top-level views (one file per major tab)
├── styles/global.css      # Design tokens — ONLY source for colors
└── utils/                 # Formatting, chart sync, tab stack, DnD
```

---

## 14. Recent Implementation Notes (03 Sep 26)

Work already in repo / testbed — **preserve behavior when redesigning:**

| Area | What changed |
|------|----------------|
| **Account** | Web showcase shows signed-in email; license status refresh when Account modal opens (`App.js` + `license_client.py`) |
| **Charts** | 1D % list/chart alignment; crosshair sync across panes (`chartPanelSync.js`, `ChartContainer.js`) |
| **Index history** | Interior gap backfill for sector indices (`scrape_indices.py`, `index_history_integrity.py`) |
| **P&L corp actions** | Idempotent `corp_actions_applied` — no double bonus/split on reload (`pnl_ledger.py`, `corp_actions.py`) |
| **Live public links** | Watchdog escalates: Tailscale restart + funnel reset after sleep; 60s public health timeout (`Invoke-CiMLiveWebAndMobileHeal.ps1`, `Resume-CiMLiveServices.ps1`) |
| **Column widths** | Stock list column resize persisted per view (`stockListColumnStorage.js`) |

---

## 15. What Lovable Should Not Do

- Add React Router or replace `view` navigation without a migration plan
- Introduce Cr/L/Lakh in labels or table cells
- Use raw `<button style={{...}}>` in dialogs — use `CimDialogButton` / `PnlDialogButton`
- Edit `packages/desktop/` or mobile install trees for showcase-only design tasks
- Deploy to live `D:\CiM\Client` (8001) — testbed **8002** only unless owner explicitly requests live
- Commit `data/nse_data.db`, license secrets, or `data/users/` snapshots

---

## 16. Verification After UI Changes

```powershell
cd packages\browser
npm test -- --watchAll=false
.\scripts\Deploy-CiMShowcaseFromRepo.ps1 -RestartShowcase
# Hard refresh browser: Ctrl+Shift+R at http://127.0.0.1:8002
```

Check: dialog footers, table alignment, chart crosshair, Account email, scheduler banner semantics.

---

*Implementation code: `packages/browser/`. Design package: `CiMLovableDesign/` on GitHub.*
