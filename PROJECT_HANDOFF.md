# Charts In Motion — Project Handoff

**Generated:** 12 April 26, 00:38:16 (local machine time)  
**Last updated:** 07 Jun 26 (1.0.6 release gate, blank-shell fix, post-update license repair, build script fix)  
**Workspace root:** `D:\Programs\NSE Pulse\Claude Ai`

**Document naming convention:** keep stable filenames without embedded timestamps; keep update timestamps inside the file using `DD Month YY` (month in words).

This is the detailed technical handoff for the next AI/developer. The short business-facing companion is `PROJECT_HANDOFF_EXEC_SUMMARY.md`. Product-owner expectations and release workflow are in **`USER_REQUIREMENTS.md`**. Keep all three: this file carries architecture, root causes, exact paths, and runbooks; the exec summary is for quick orientation; user requirements define what “done” means before publish.

---

## 0. Current State Snapshot

Charts In Motion is a Windows desktop distribution of a local FastAPI + React market-analysis app. The repo’s **`version.txt`** and **`installer\output\version.txt`** currently read **`1.0.6`** (last verified build with packaged smoke gate).

Current build artifacts (last verified build, version `1.0.6`):

- Installer: `installer\output\CiMSetup-1.0.6.exe`
- Export/payload tree: `installer\output\CiM`
- Client update package: `installer\output\CiM-Update-1.0.6\`
- GitHub upload ZIP: `installer\output\CiM-Update-1.0.6.zip`
- Build log: `runtime\logs\build-distribution.log`
- Distribution profile: `installer\output\CiM\config\.fx-dist.cfg`
- GitHub update config: `installer\output\CiM\config\github_updates.json`

The previous sibling export path `D:\Programs\NSE Pulse\!Export\FlowX` is no longer the default. New export/update work should stay under `installer\output\`.

---

## 1. Architecture

### 1.1 Runtime shape

Charts In Motion runs locally on each Windows PC:

- `start_cim.bat` starts the backend and Electron desktop shell.
- Backend: FastAPI/uvicorn on `http://127.0.0.1:8000`.
- Frontend: React production build served by FastAPI from `frontend\build`.
- Desktop shell: Electron in `desktop\main.js`, loading `http://127.0.0.1:8000`.
- Database: SQLite at `data\nse_data.db`.
- User state: JSON files under `data\` (watchlists, portfolio, layout, saved filters, Screener session/profile).

Main code paths:

- Backend app: `server\server.py`
- Encrypted distribution bootstrap: `server\cim_bootstrap.py`
- Crypto/license/decrypt helpers: `server\app_code_crypto.py`
- Update API: `server\update_apply.py`
- GitHub Releases provider: `server\github_updates.py`
- Daily OHLCV/update worker: `scrape_daily.py`
- Index data worker: `scrape_indices.py`
- NSE index OHLC fallback (Yahoo-missing indices): `nse_index_history.py`
- Frontend root: `frontend\src\App.js`
- Admin job status hook: `frontend\src\hooks\useAdminJobStatus.js`
- Electron launcher: `desktop\main.js`

### 1.2 Development startup

Typical dev flow:

```powershell
uvicorn server.server:app --reload --host 127.0.0.1 --port 8000
cd frontend
npm start
```

### 1.3 Packaged startup

Packaged/sold client flow:

```powershell
C:\FlowX\start_cim.bat
```

Normal startup opens a visible `CiM Backend` command window so users/support can see live uvicorn/admin-job output. Automation can set `CIM_NO_PAUSE=1` for hidden backend mode.

---

## 2. Installer, Export, Licensing, Encryption

### 2.1 Current build layout

All future distribution work should use `installer\output`:

- `installer\CiM.iss` — Inno Setup source script
- `installer\.gitignore` — ignores `output/`
- `installer\output\CiM` — export/payload tree used by installer/update package
- `installer\output\CiMSetup-{version}.exe` — compiled installer (version follows `version.txt`; currently **1.0.6**)
- `installer\output\CiM-Update-{version}\` — local client update package
- `installer\output\CiM-Update-{version}.zip` — same package, for GitHub Releases upload
- `installer\output\version.txt` — app version used by installer/update build
- `installer\output\generated_license_secret.pas` — generated Inno include with the distribution secret
- `installer\output\license_validate.pas` — Inno-side install key validation
- `installer\output\LICENSE_ISSUING.md` — internal support/license notes
- `installer\output\UPDATE_README.txt` — update readme bundled by installer

Central path helper:

- `scripts\Get-CiMPaths.ps1`

### 2.2 Build commands

Preferred full pipeline:

```powershell
.\Build-CiM.ps1
# equivalent:
.\scripts\build_distribution_full.ps1 -Version "1.0.4"
```

Manual phased pipeline:

```powershell
.\export_cim.ps1 -Mode distribution -HardenAll
.\scripts\Sync-ExportDistributionFixes.ps1
.\scripts\encrypt_app_code.ps1
.\scripts\build_installer.ps1
.\scripts\build_update_package.ps1
```

`export_cim.ps1` and `Sync-ExportDistributionFixes.ps1` now copy `config\github_updates.json` (and deprecated `config\update_manifest_url.json`) into the export tree.

**GitHub publish (vendor):** after build, upload `installer\output\CiM-Update-{version}.zip` to [unnwired/cim-updates Releases](https://github.com/unnwired/cim-updates/releases) with tag `v{version}`.

**Unit tests:** `python scripts\test_github_updates.py` (version parse, asset pick, ZIP extract layout).

**Build verification (07 Jun 26, v1.0.6):** full `Build-CiM.ps1` completed with exit code 0 — export smoke test, encryption (30 files), license chain, Inno Setup, update package + ZIP, and **`Test-CiMPackagedSmoke.ps1` (step 6/6 PASS)**. Log: `runtime\logs\build-distribution.log`.

The full pipeline must preserve the same license secret across export, encryption, installer, and update package. `build_distribution_full.ps1` now reads the existing generated installer secret if `CIM_LICENSE_SECRET` is not set, preventing accidental fallback to the default dev secret.

### 2.3 Licensing model

The installer shows a machine code. Support generates an install key for that machine code. The client enters the key in the installer wizard.

Important scripts:

- `scripts\Generate-CiMInstallKey.ps1`
- `scripts\Show-CiMInstallKey.ps1`
- `scripts\Repair-CiMLicense.ps1`
- `Repair-CiMLicense.bat`
- `Repair-CiMLicense-Auto.bat`
- `scripts\Verify-CiMLicenseChain.ps1`

Distribution profile:

- New/discreet name: `config\.fx-dist.cfg`
- Legacy fallback: `config\.flowx_vendor_secret`

The old filename was too revealing. `server\app_code_crypto.py` now uses `DIST_PROFILE_FILE = "config/.fx-dist.cfg"` and falls back to `LEGACY_DIST_PROFILE_FILE = "config/.flowx_vendor_secret"` for existing installs.

Known valid keys from the current production secret:

- Client machine code `F1927C3F4CCD33A733DD8AECEFDA6469` -> `5435-323D-981D-B6D1-C883-A7BE`
- Dev machine code `0CACE30AFA5EE57B3C8B47AB9F0A7BB9` -> `9FAD-D86E-6B9E-2610-B96A-C3E7`

### 2.4 Encryption model

Distribution builds encrypt:

- Backend bytecode: `server\*.pyc.enc`
- Frontend JS: `frontend\build\static\js\*.js.enc`

Runtime flow:

1. `uvicorn server.cim_bootstrap:app --host 127.0.0.1 --port 8000`
2. `server\cim_bootstrap.py` validates the local license.
3. `server\app_code_crypto.py` decrypts app code to `%LOCALAPPDATA%\CiM\app-cache\{version}`.
4. Server code loads from app-cache, but data/scripts/update files remain under the install root.

This is the most important invariant for future fixes:

> Code can execute from `%LOCALAPPDATA%\CiM\app-cache\1.0.3`, but install assets and writable data must be resolved from the real install root, e.g. `C:\FlowX`.

---

## 3. Bugs Encountered, Root Causes, and Fixes

### 3.1 License keys did not match between installer, Repair, and runtime

Symptoms:

- Support-generated keys were rejected on client PCs.
- Same PC produced different expected keys depending on script/runtime.
- Example drift: one path showed `F1927...`, another showed `12BCFC...`.

Root causes:

- `CIM_LICENSE_SECRET` environment variable could override the shipped file.
- Exported Python and Inno validation were not always using the same secret source.
- Earlier export had UTF-16/encoding drift in MD5 calculation assumptions.

Fixes:

- `distribution_secret(base_dir)` in `server\app_code_crypto.py` now prefers the shipped profile file when `base_dir` is provided.
- Repair/generate scripts clear stale env vars unless a secret is explicitly passed.
- `Verify-CiMLicenseChain.ps1` verifies profile file, Python formula, and Inno formula match.
- Distribution profile written as UTF-8 no BOM.

### 3.2 Silent install did not skip license pages

Symptom:

- Silent install still prompted or failed when `/INSTALLKEY=` was supplied.

Fix:

- `installer\CiM.iss` `ShouldSkipPage` logic skips license wizard pages when `StoredInstallKey` is set.

### 3.3 Blank Electron shell

Symptom:

- Charts In Motion opened as an empty dark/blue shell.
- Backend health returned 200, so earlier checks incorrectly treated it as working.

Evidence:

- Renderer diagnostics in `D:\CiM\runtime\logs\desktop-renderer.log` showed:

```text
Uncaught SyntaxError: Unexpected token '<'
rootChildren: 0
```

Root cause:

- Electron loaded `/static/js/main.1b6b62d1.js`, but FastAPI returned `index.html` instead of JavaScript.
- Static route was mounted after the catch-all SPA route, so `/static/js/...` hit the fallback.

Fixes:

- `server\cim_bootstrap.py` now inserts the decrypted static mount before `/{full_path:path}`.
- `app.router.routes` is updated with a `Mount("/static", ...)` placed before SPA fallback.
- `app_code_crypto.py` now copies plaintext CSS/assets into app-cache alongside decrypted JS.
- `desktop\main.js` now writes renderer diagnostics to `runtime\logs\desktop-renderer.log`.

Verification:

- Renderer log showed `rootChildren: 1`.
- Body text included `Market Pulse`, `Market Movers`, `Market Map`, `NSE`, filters, etc.
- `/api/stocks` returned 2251 rows.

### 3.4 Hidden/blank backend console

Symptom:

- User expected the old command prompt with scrolling stock/job output; packaged mode hid backend output.

Fix:

- Normal `start_cim.bat` opens a visible `CiM Backend` console.
- Automation still uses hidden mode via `CIM_NO_PAUSE=1`.
- Replaced `timeout /t` waits with `:FlowxSleep` because `timeout` fails under redirected stdin in `cmd /c`.

### 3.5 App-cache path leak: split adjustments

Client error:

```text
[Errno 2] No such file or directory:
'C:\Users\Sandeep\AppData\Local\FlowX\app-cache\1.0.3\scrape_daily.py'
```

Trigger:

- Frontend action: `Apply stock split adjustments`
- Endpoint: `POST http://127.0.0.1:8000/api/admin/apply-split-adjustments?days_back=365`
- Backend handler: `server\server.py` `admin_apply_split_adjustments()`
- Background job: `run_apply_split_adjustments()`

Root cause:

- `_load_scrape_daily_module()` used:

```python
Path(__file__).resolve().parent.parent / "scrape_daily.py"
```

- In encrypted runtime, `server.pyc.__file__` points to app-cache, not install root.
- `scrape_daily.py` stays at `C:\FlowX\scrape_daily.py`.

Fix:

- `_load_scrape_daily_module()` now uses `SCRAPE_DAILY_PATH`.
- `cim_bootstrap._repoint_server_install_paths()` already repoints `SCRAPE_DAILY_PATH` to install root; this fix makes the job use it.

### 3.6 Adjacent app-cache path leaks

Additional affected areas:

- `server\update_apply.py` used `Path(__file__).resolve().parent.parent`, so in-app updates could look for scripts/logs under app-cache.
- `server\movers_data.py` used `Path(__file__).resolve().parent.parent / "data" / "nse_calendar.json"`.
- `server\movers_live.py` loaded its own `movers_data` copy and could miss the configured install-root calendar path.
- `server._load_module_from_path()` did not register dynamically loaded modules in `sys.modules`, so bootstrap could not repoint actual instances.

Fixes:

- `server\update_apply.py`: added `configure_install_root(base_dir)`.
- `server\movers_data.py`: added `configure_paths(data_dir=...)`.
- `server\movers_live.py`: added `configure_paths(data_dir=...)` and passes it to its loaded movers data module.
- `server\server.py`: registers path-loaded modules in `sys.modules`.
- `server\cim_bootstrap.py`: calls install-root repoint hooks for `update_apply`, `nse_pulse_movers_data`, and `nse_pulse_movers_live`.

### 3.7 Yahoo/yfinance client network failures

Client log:

```text
Failed to get ticker 'AFFLE.NS' reason:
curl: (7) Failed to connect to fc.yahoo.com port 443
$AFFLE.NS: possibly delisted; no timezone found
50 Failed downloads: [...]
[!] 15 consecutive failures. Pausing 60s...
```

Interpretation:

- This is a network/proxy/firewall problem reaching Yahoo Finance, not actual delistings.
- `yfinance` reports "possibly delisted" for many transport errors.
- Charts In Motion's daily OHLCV job backs off after consecutive failures.

Quick client diagnostic:

```powershell
curl.exe -v https://fc.yahoo.com
curl.exe -I https://query1.finance.yahoo.com
```

### 3.8 Build/update packaging issues fixed

Issues encountered:

- `build_distribution_full.ps1` lost the production secret and fell back to `flowx-distribution-change-me`, failing license-chain validation.
- `Diagnose-CiMInstall.ps1` had PowerShell parser errors due to embedded Python here-strings/quoting.
- Windows PowerShell 5.1 does not support `&&` as a statement separator.

Fixes:

- `build_distribution_full.ps1` now accepts `-LicenseSecret`, respects `CIM_LICENSE_SECRET`, or reads the existing `generated_license_secret.pas`.
- `Diagnose-CiMInstall.ps1` was simplified to robust file/process/log checks.
- Commands and scripts avoid PowerShell 7-only syntax.

### 3.9 UPDATE folder layout and install-path detection

Symptoms:

- Client placed `CiM-Update-*` under `{install}\UPDATE\` but `Install-Client-Update.bat` prompted for install path or looked in the wrong folder.
- Updates were sometimes applied from Charts In Motion root instead of `UPDATE\`.

Root cause:

- Install locator and update scripts assumed the package lived at install root or required manual path entry.

Fixes:

- **`scripts\CiMInstallLocator.ps1`:** resolves install root from `UPDATE\CiM-Update-*` ancestry; structural paths use `SkipValidation` where appropriate.
- **`scripts\Install-Client-Update.ps1`:** fast path when run from inside `UPDATE\`; prefers install `scripts\` when package is under `UPDATE\`.
- **`scripts\CiMUpdatePackage.ps1`**, **`scripts\Apply-LocalUpdate-Entry.ps1`:** scan `UPDATE\` for nested `CiM-Update-*` packages.
- **`server\update_apply.py`:** `_local_update_package_roots()` scans `{install}\UPDATE\CiM-Update-*`.

Invariant for all update flows:

> Client update packages belong under **`{install}\UPDATE\CiM-Update-{version}\`**, not directly under the Charts In Motion install root.

### 3.10 GitHub Release updates (remote source)

**Scope:** GitHub Releases only. `config\update_manifest_url.json` is deprecated (empty); no MEGA / multi-file HTTPS manifest remote.

Architecture:

1. **`GET /api/update/check`** — compare `version.txt` to local `UPDATE\CiM-Update-*` packages, then GitHub `releases/latest` for asset `CiM-Update-{version}.zip`. Local wins on tie or higher version.
2. **`POST /api/update/download`** — if source is `github`, download to `%LOCALAPPDATA%\CiM\update-staging\{version}\package.zip`, extract to `{install}\UPDATE\CiM-Update-{version}\`, validate manifest + `payload\`.
3. **`POST /api/update/apply`** — requires local package ready (GitHub must download first); writes pending JSON and spawns `scripts\CiMApplyUpdate.ps1`.

Key files:

| File | Role |
|------|------|
| `config\github_updates.json` | Owner `unnwired`, repo `cim-updates`, 90 min poll, background enabled |
| `server\github_updates.py` | Releases API, asset pick, ZIP download/extract, log to `runtime\logs\update-download.log` |
| `server\update_apply.py` | Check/download/apply endpoints; `configure_install_root()` also calls `github_updates.configure_paths()` |
| `frontend\src\App.js` | `runCiMUpdateApply()` shared by cogwheel and background prompt |
| `scripts\build_update_package.ps1` | Ships GitHub module/config in payload; emits `CiM-Update-{version}.zip` |
| `docs\UPDATE.md`, `docs\CLIENT_UPDATE.md` | Client/vendor runbooks |

Frontend behavior:

- **Settings → Apply update:** confirm → download if GitHub → apply → quit via `flowxDesktop.quitForUpdate`.
- **Background:** first check ~30s after load, then every `checkIntervalMinutes` (default 90) via `GET /api/update/check?background=true`. Dismissed version stored in `sessionStorage` (`flowx.dismissedUpdateVersion`).

Rollout note:

- Clients on builds **without** GitHub code need **one** manual/bat update before cogwheel/background GitHub pull works.

### 3.11 Nifty India Defence (`^CNXINDDEF`) index chart gaps and 404

Symptoms:

- Index chart for Nifty India Defence showed a **vertical line** (price spike) between **Feb 2025** and **Oct 2025**.
- Chart history appeared to begin only on **11 Nov 2024** (user thought earlier data “vanished”).
- `/api/index-chart/^CNXINDDEF` returned **404** when `index_history` had no rows.
- Console/log noise from Yahoo Finance 404s for `^CNXINDDEF`.

Interpretation:

- **11 Nov 2024 is the NSE index launch date** for NIFTY INDIA DEFENCE. There is no official NSE history before that date. Comparisons to TradingView or other continuous symbols are not apples-to-apples.
- **Feb–Oct 2025 gap was a data-ingestion bug**, not user data loss.

Root causes:

1. Yahoo Finance has **no OHLC series** for `^CNXINDDEF`. Charts In Motion must use NSE `GET /api/historicalOR/indicesHistory`.
2. NSE returns only **~60–70 trading days per request**, even when the URL requests a 360-day span. A single large-window request does **not** return the full range — it typically returns the most recent portion of that window.
3. Original `nse_index_history.py` used `MAX_RANGE_DAYS = 360` and treated each response as complete.
4. Incremental `scrape_history_from_nse` only extended forward from `last_date - 7` days. **Middle gaps were never repaired** once stale data existed.
5. `sync_nse_index_history()` only refreshed when latest bar was stale or row count `< 2` — it did **not** detect interior gaps.

Fixes:

| File | Change |
|------|--------|
| `nse_index_history.py` | New module: NSE session bootstrap, row normalize, **85-day sliding windows** (`NSE_CHUNK_CALENDAR_DAYS`), `find_index_history_gaps()`, gap-aware `scrape_history_from_nse()` with optional `force_full` |
| `scrape_indices.py` | `NSE_ONLY_INDEX_SYMBOLS = {"^CNXINDDEF"}` — skip Yahoo; `NSE_INDEX_HISTORY_START = {"^CNXINDDEF": "2024-11-11"}`; gap detection in `_nse_history_symbols_to_refresh()`; `sync_nse_index_history()` passes inception date and repairs gaps on startup/Update |
| `server\server.py` | Calls `sync_nse_index_history()` on boot and after index update jobs |
| `server\tests\test_nse_index_history.py` | Parse/chunk/gap tests + stale-target refresh test |

Verification (dev DB `data\nse_data.db`):

```text
BEFORE: 220 rows, min 2024-11-11, max 2026-06-05, 1 gap (2025-02-19 → 2025-10-26)
AFTER:  387 rows, min 2024-11-11, max 2026-06-05, 0 gaps
```

Run tests:

```powershell
python -m unittest server.tests.test_nse_index_history -v
```

Trigger repair on a client install:

- Restart backend (startup sync), or run **Update** from admin/cogwheel (index scrape path calls `sync_nse_index_history()`).

Future NSE-only indices:

- Add symbol to `NSE_ONLY_INDEX_SYMBOLS`, `NSE_NAME_MAP`, and `NSE_INDEX_HISTORY_START` (inception date if known).
- Never assume one NSE `indicesHistory` call returns a full date range.

### 3.12 Git repository hygiene (source repo push failures)

Symptoms:

- `git push` failed due to oversized blobs in history (`data/nse_data.db` ~1.35 GB, `electron.exe` ~195 MB).
- Cursor reported tens of thousands of active changes.
- `.gitignore` appeared ignored for some paths.

Root causes:

- Large files were committed in early history; later `.gitignore` entries do not remove blobs from past commits.
- Windows duplicate `.gitignore.txt` could confuse tooling.
- `.gitignore` rule `!OLD/` was a **negation** (un-ignored `OLD/` instead of ignoring it).

Fixes:

- Expanded `.gitignore`: `data/nse_data.db`, `runtime/`, `node_modules/`, `installer/output/`, build artifacts, etc.
- Rewrote history on orphan branch and force-pushed clean tree to [unnwired/FlowX_GitHubRepo](https://github.com/unnwired/FlowX_GitHubRepo.git).

Invariant:

> **Never commit** `data/nse_data.db`, embedded `runtime/python`, or `installer/output/` — they are per-machine / per-build artifacts.

Note: GitHub **update** repo (`unnwired/cim-updates`) is separate from the **source** repo (`unnwired/FlowX_GitHubRepo`).

### 3.13 Blank Electron shell regression (1.0.6 encrypt pipeline)

Symptoms:

- After applying a distribution update, Electron opened a **blank shell**; backend `/api/health` returned 200.
- Renderer: `Uncaught SyntaxError: Unexpected token '<'`.

Root cause:

1. `encrypt_app_code.ps1` copied plaintext `server.py` into export, encrypted `server.pyc`, but **did not remove** plaintext `server.py`.
2. `is_development_tree()` saw `server/server.py` and treated client install as dev tree.
3. Encrypted JS bootstrap skipped; `/static` served from install tree where only `main.*.js.enc` exists.
4. Request for `/static/js/main.*.js` fell through to SPA fallback → **HTML instead of JavaScript**.

Fixes:

| File | Change |
|------|--------|
| `scripts\encrypt_app_code.ps1` | After encrypt, delete plaintext server `*.py` except `__init__.py`, `app_code_crypto.py`, `cim_bootstrap.py` |
| `server\app_code_crypto.py` | `is_development_tree()`: if `config/.fx-dist.cfg` + encrypted code present → **not** dev tree |
| `server\cim_bootstrap.py` | `_patch_static_mount_for_cache()` calls `ensure_app_cache()` when only `*.js.enc` on disk |
| `server\tests\test_distribution_bootstrap.py` | Regression tests for distribution vs dev detection |

### 3.14 Post-update license invalid (1.0.6)

Symptoms:

```text
[ERROR] License file exists but is NOT valid on this PC.
Usually: install key does not match config\.fx-dist.cfg (common after an update).
```

Root cause:

- `CiMApplyUpdate.ps1` **always copies** `config\.fx-dist.cfg` from the update payload so decrypted server/JS match the build secret.
- Existing `data\.cim-license` install key was generated from the **previous** profile → `validate_install_key()` fails.

Fixes:

| File | Change |
|------|--------|
| `scripts\CiMApplyUpdate.ps1` | After copying vendor profile, run `Repair-CiMLicense.ps1 -AutoFix`; skip overwriting `data\.cim-license` in manifest loop |
| `scripts\Install-Client-Update.ps1` | Verify/repair license after apply |
| `scripts\build_update_package.ps1` | Never include `data/.cim-license` in update payload; strip from export before manifest |
| `server\update_apply.py` | `PROTECTED_REL` includes `data/.cim-license` |
| `start_cim.bat` | Clearer error text pointing to `Repair-CiMLicense-Auto.bat` |

Client remediation (any stuck install):

```bat
Repair-CiMLicense-Auto.bat
start_cim.bat
```

Vendor invariant: **one stable production secret** in `config\.build_license_secret`. Rotating the secret invalidates all client keys until repair.

### 3.15 Release gate — mandatory before publish (1.0.6)

**Problem:** Prior gates checked `/api/health` and `/` status only — blank Electron shell still shipped.

**Gate script:** `scripts\Test-CiMPackagedSmoke.ps1`

Checks:

1. `cim_bootstrap` starts uvicorn on install/export tree
2. `GET /` contains React `id="root"`
3. `GET /static/js/main.*.js` is JavaScript (not HTML) — catches blank shell
4. `GET /api/stocks?pageSize=500` → `total` ≥ 100 (expect ~2251)

Wired into:

- `scripts\build_distribution_full.ps1` — **step 6/6** (build fails if gate fails)
- `scripts\Run-CiMFullGate.ps1` — after silent install

Run manually:

```powershell
.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"
```

**Build script fix (Jun 26):** Unicode em-dash in `build_distribution_full.ps1` Log strings broke PowerShell 5.1 parsing — use ASCII hyphens only in executable script strings.

---

## 4. Current API Surface (Key Routes)

Core:

- `GET /api/health`
- `GET /api/stocks`
- `GET /api/stocks/search`
- `GET /api/stock/{symbol}`
- `GET /api/chart-data/{symbol}`
- `GET /api/layout`
- `POST /api/layout`

Admin jobs:

- `GET /api/admin/status`
- `POST /api/admin/fetch-ohlcv`
- `POST /api/admin/rebuild-indicator-snapshots`
- `POST /api/admin/rebuild-indicator-snapshots-incremental`
- `POST /api/admin/apply-split-adjustments?days_back=365`
- `POST /api/admin/refresh-earnings-plus-cache`

Market data/features:

- `GET /api/indices`
- `GET /api/index-chart/{symbol:path}`
- `GET /api/index-constituents/{symbol:path}`
- `GET /api/market-map/catalog`
- `GET /api/market-map/summary`
- `GET /api/market-map/index/{symbol}`
- `GET /api/movers/day-change`
- `GET /api/movers/live/day-change`
- `GET /api/earnings-beats`

Update:

- `GET /api/update/settings` — GitHub poll interval / background flag for frontend
- `GET /api/update/check` — optional `?background=true` (lighter local validation on idle polls)
- `POST /api/update/download`
- `POST /api/update/apply`

---

## 5. Frontend/UI Flow

No React Router. `frontend\src\App.js` controls navigation with `view` state and top-level tabs.

Major pages/components:

- `MarketPulsePage`
- `DashboardPage`
- `MoversPage`
- `MarketMapPage`
- `EarningsBeatsPage`
- `IndicesPage`
- `WatchlistPage`
- `PortfolioPage`
- `SplitChartPage`
- `IndexChartPage`
- `ConstituentsPage`

Admin/update interactions:

- Admin menu and settings gear live mainly in `frontend\src\App.js`.
- Job polling is in `frontend\src\hooks\useAdminJobStatus.js`.
- The split adjustment button calls `startSplitAdjustments(365)`, which POSTs to `/api/admin/apply-split-adjustments`.
- **Apply update** (cogwheel) and **90-minute background update prompt** use shared `runCiMUpdateApply()`; GitHub source label shown in confirm dialog.

---

## 6. Data and User-State Files

Preserve these on install/update (never overwrite from update payload):

- `data\nse_data.db`
- `data\watchlists.json`
- `data\portfolio.json`
- `data\layout.json`
- `data\saved_filters.json`
- `data\screener_session.json`
- `data\screener_profile\*`
- `data\.cim-license` (protected; **regenerated** after update when vendor profile refreshes — see §3.14)

Installer exclusions/preserve behavior is in `installer\CiM.iss`.

Update package protected paths are in `scripts\build_update_package.ps1` and `server\update_apply.py`.

---

## 7. Verification Commands

Syntax:

```powershell
python -m py_compile server\server.py server\cim_bootstrap.py server\update_apply.py server\github_updates.py server\movers_data.py server\movers_live.py nse_index_history.py
python scripts\test_github_updates.py
python -m unittest server.tests.test_distribution_bootstrap server.tests.test_nse_index_history server.tests.test_indices_alignment -v
.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"
```

Distribution smoke:

```powershell
.\scripts\verify_distribution.ps1 -SkipInstaller
```

License chain:

```powershell
.\scripts\Verify-CiMLicenseChain.ps1
```

Full build:

```powershell
.\Build-CiM.ps1
```

Expected final artifacts:

- `installer\output\CiMSetup-{version}.exe`
- `installer\output\CiM-Update-{version}\` and `CiM-Update-{version}.zip`
- `installer\output\CiM\config\.fx-dist.cfg` and `config\github_updates.json`

Client update for currently installed machines:

1. **First GitHub-capable build:** send update folder/ZIP → client extracts to `{install}\UPDATE\CiM-Update-{version}\` and runs `Install-Client-Update.bat` (path auto-detected).
2. **Later updates:** client can use **Settings → Apply update** or wait for the 90-minute background prompt (once a release is on GitHub).
3. Restart Charts In Motion after apply (license auto-repaired on 1.0.6+ during apply).
4. If license error on start: `Repair-CiMLicense-Auto.bat`.
5. Re-test UI loads (not blank shell), admin jobs, and cogwheel update flow.

For encrypted-runtime path bugs on very old installs, prefer the external update package over in-app apply until the client is on a build with install-root repoint fixes.

---

## 8. Known Constraints and Risks

- Yahoo/yfinance can fail due to client firewall/proxy/DNS. `curl (7) Failed to connect to fc.yahoo.com port 443` means network, not delisting.
- Installer is unsigned, so Windows SmartScreen/unknown publisher warnings are expected unless signing is added.
- Electron reports CSP security warnings in dev/unpackaged mode; not the same as the blank-shell bug.
- Current runtime uses local backend only (`127.0.0.1:8000`); this is not a cloud/multi-user architecture.
- `CIM_LICENSE_SECRET` is still an internal build/support env var. Avoid exposing it in client-facing instructions.
- The build tree includes large runtime/vendor files under `installer\output\CiM`; do not commit generated output unless intentionally archiving a release.
- GitHub remote updates require a published Release with matching `CiM-Update-{version}.zip`; repo defaults to `unnwired/cim-updates`.
- Bump `version.txt` before each GitHub publish; **`Test-CiMPackagedSmoke.ps1` must PASS** before uploading ZIP.
- Post-update license failures are expected if vendor profile changes; 1.0.6+ auto-repairs on apply (see §3.14).
- NSE `indicesHistory` is capped at ~70 bars per request. NSE-only indices (`^CNXINDDEF` today) require chunked fetch and gap repair — see §3.11.
- Source code repo: `unnwired/FlowX_GitHubRepo`. Do not commit local DB or build output.

---

## 9. Recommendations for the Next AI

1. **Never assume a 200 health check means the UI works.** For Electron blank shells, inspect `runtime\logs\desktop-renderer.log` and verify `rootChildren > 0`.
2. **For encrypted runtime bugs, distrust `__file__`.** If code may be loaded from app-cache, use configured install-root globals or explicit `configure_*` hooks.
3. **When changing packaged server code, re-export.** Editing repo `server.py` is not enough; distribution uses encrypted `server.pyc.enc`.
4. **Run the full pipeline before shipping.** `Build-CiM.ps1` runs export, encrypt, installer, update ZIP, and **`Test-CiMPackagedSmoke.ps1` (step 6/6)**. Do not publish if gate fails.
5. **Keep generated/build files under `installer\output`.** Do not reintroduce sibling `!Export` defaults.
6. **Preserve client data.** Update must not overwrite watchlists, layout, or license files; vendor profile refresh triggers license auto-repair (§3.14).
7. **Updates live in `UPDATE\`.** Never instruct clients to unpack `CiM-Update-*` into the install root; use `{install}\UPDATE\CiM-Update-{version}\`.
8. **Publish GitHub ZIP after build.** Tag `v{version}`, asset name must match `CiM-Update-{version}.zip` (see `config\github_updates.json` prefixes).
9. **NSE-only index history:** For symbols in `NSE_ONLY_INDEX_SYMBOLS`, never call Yahoo; use `nse_index_history.py` with 85-day chunks. If a chart shows a vertical jump, check `find_index_history_gaps()` on `index_history` for that symbol.
10. **Git hygiene:** Keep `data\nse_data.db`, `runtime\`, and `installer\output\` out of commits. Source repo is `unnwired/FlowX_GitHubRepo`; update releases go to `unnwired/cim-updates`.
11. **Read `USER_REQUIREMENTS.md`** before marking a build release-ready for the product owner.

---

## 10. Why There Are Two Handoff Files

- `PROJECT_HANDOFF.md` (this file): detailed technical handoff for an engineer/AI that will debug or continue implementation.
- `PROJECT_HANDOFF_EXEC_SUMMARY.md`: short status/risk/milestone summary for quick orientation.
- `USER_REQUIREMENTS.md`: product-owner workflow — instruction → tested build → release-ready artifacts.

They should not be identical. If maintaining only one technical file, keep this detailed handoff; keep `USER_REQUIREMENTS.md` for release expectations.

---

*End of handoff.*
