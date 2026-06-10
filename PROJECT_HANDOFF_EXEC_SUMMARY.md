# Charts In Motion — Executive Handoff Summary

**Generated:** 13 April 26  
**Last updated:** 07 Jun 26 (1.0.6 release gate, blank-shell fix, post-update license repair, build script fix)  
**Project root:** `D:\Programs\NSE Pulse\Claude Ai`

**Product-owner workflow:** see also `USER_REQUIREMENTS.md` (dev → tested build → release-ready artifacts).

---

## Why This File Exists

There are three handoff docs:

- `PROJECT_HANDOFF.md` is the detailed technical handoff for the next engineer/AI.
- `PROJECT_HANDOFF_EXEC_SUMMARY.md` is this shorter status/risk summary.
- `USER_REQUIREMENTS.md` is the product-owner workflow (dev → tested build → release-ready artifacts).

Keep all three. If you only want one technical file later, keep `PROJECT_HANDOFF.md` because it contains the full architecture, error trail, root causes, and runbooks.

---

## Current Project Status

- **Product surface:** Market Pulse, NSE Dashboard, Market Movers, Market Map, Earnings, Indices, Watchlist, Portfolio, chart tabs, and admin refresh workflows are implemented.
- **Distribution model:** Windows installer distribution is implemented.
- **Activation model:** Offline machine-code/install-key licensing is implemented.
- **Runtime model:** Local Electron desktop + local FastAPI backend + local SQLite DB.
- **Current version:** **`1.0.6`** in `version.txt` and `installer\output\version.txt` (last verified build with release gate).
- **Current release artifacts (last verified build):**
  - Installer: `installer\output\CiMSetup-1.0.6.exe`
  - Update package: `installer\output\CiM-Update-1.0.6\`
  - GitHub upload ZIP: `installer\output\CiM-Update-1.0.6.zip`
  - Export tree: `installer\output\CiM`

---

## What Changed Recently

### Installer, licensing, and export layout

- Added Inno Setup installer with machine-code and install-key wizard.
- Added silent install key support (`/INSTALLKEY=`).
- Added support scripts for key generation, license repair, and chain verification.
- Moved export/update output from `!Export\FlowX` to `installer\output\CiM`.
- Renamed the client-visible distribution secret file from `config\.flowx_vendor_secret` to the more discreet `config\.fx-dist.cfg`.
- Kept legacy fallback for existing installs that still have the old filename.

### Encrypted runtime

- Distribution builds encrypt server bytecode and frontend JS.
- Runtime decrypts into `%LOCALAPPDATA%\CiM\app-cache\{version}` after license validation.
- Important invariant: code may execute from app-cache, but data/scripts/update files must resolve from the install root (`C:\FlowX`, `D:\CiM`, etc.).

### Major bugs fixed

- **Blank Electron shell:** caused by `/static/js/main.*.js` returning `index.html`; fixed by mounting decrypted `/static` before the SPA catch-all route.
- **Hidden backend console:** normal `start_cim.bat` now opens a visible `CiM Backend` console again.
- **Split-adjustments client failure:** fixed app-cache path leak where the app looked for `%LOCALAPPDATA%\CiM\app-cache\1.0.3\scrape_daily.py` instead of `C:\FlowX\scrape_daily.py`.
- **Update path leaks:** update apply scripts/logs now resolve from install root, not app-cache.
- **Movers/calendar path leaks:** movers data now uses configured install-root `data\nse_calendar.json`.
- **License drift:** installer, Repair, and runtime now use the same profile/secret source and are verified by `Verify-CiMLicenseChain.ps1`.

### GitHub Release updates (Jun 26)

- **Remote update source:** Charts In Motion now pulls updates from GitHub Releases only — repo [unnwired/cim-updates](https://github.com/unnwired/cim-updates), asset `CiM-Update-{version}.zip`. Legacy `config\update_manifest_url.json` / HTTPS manifest multi-file remote is **deprecated** (not used).
- **Update priority:** `{install}\UPDATE\CiM-Update-*` (local) first; GitHub `releases/latest` second. Same version → local wins.
- **In-app flow:** Settings cogwheel **Apply update** → check → confirm → download (GitHub ZIP to staging → extract to `UPDATE\`) → apply via existing `CiMApplyUpdate.ps1` → quit.
- **Background prompt:** While the app is open, polls `GET /api/update/check?background=true` every **90 minutes** (configurable). Popup offers update; **No** dismisses until a newer version appears (`sessionStorage` key `flowx.dismissedUpdateVersion`).
- **Config:** `config\github_updates.json` (owner, repo, `checkIntervalMinutes`, `backgroundCheckEnabled`). Shipped in export, installer, and update payload. Env overrides: `CIM_GITHUB_OWNER`, `CIM_GITHUB_REPO`.
- **Backend:** `server\github_updates.py` (Releases API, asset pick, ZIP download/extract); wired in `server\update_apply.py` (`/api/update/settings`, `/check`, `/download`, `/apply`).
- **Build:** `build_update_package.ps1` emits `CiM-Update-{version}.zip` beside the folder for GitHub upload. Full build verified via `Build-CiM.ps1` (see build log).

### UPDATE folder detection (Jun 26)

- Client updates must live under **`{install}\UPDATE\CiM-Update-{version}\`**, not the Charts In Motion root.
- Fixed install-path detection when the user runs `Install-Client-Update.bat` from inside `UPDATE\` (no manual path typing).
- Scripts updated: `CiMInstallLocator.ps1`, `Install-Client-Update.ps1`, `CiMUpdatePackage.ps1`, `Apply-LocalUpdate-Entry.ps1`, `update_apply.py` (`_local_update_package_roots`).

### Nifty India Defence index chart history (Jun 26)

- **Symptom:** `^CNXINDDEF` chart showed a vertical spike between Feb and Oct 2025; history appeared to “start” only on **11 Nov 2024**; console noise from Yahoo 404s.
- **11 Nov 2024 start is correct:** NIFTY INDIA DEFENCE launched on NSE that day — not pre-existing data “vanishing.”
- **Feb–Oct 2025 gap was a bug:** NSE `indicesHistory` returns only **~60–70 trading days per request** regardless of requested span. Old code used 360-day windows and incremental forward-only updates, leaving unrepaired middle gaps.
- **Fix:** `nse_index_history.py` — 85-day sliding windows, `find_index_history_gaps()`, full-series repair when gaps exist; `scrape_indices.py` — `NSE_ONLY_INDEX_SYMBOLS`, `NSE_INDEX_HISTORY_START`, gap-aware `sync_nse_index_history()` on startup and Update.
- **Verified on dev DB:** 220 rows with 1 gap → **387 continuous rows** (2024-11-11 → 2026-06-05), 0 gaps after repair.
- **Tests:** `python -m unittest server.tests.test_nse_index_history -v`

### Git repository hygiene (Jun 26)

- **Problem:** Push to GitHub failed — old commits contained `data/nse_data.db` (~1.35 GB) and `electron.exe` (~195 MB). Cursor showed tens of thousands of “active changes.”
- **Fix:** Updated `.gitignore` (DB, `runtime/`, `node_modules/`, `installer/output/`, negated `!OLD/` rule); orphan-branch clean history; force-pushed to [unnwired/FlowX_GitHubRepo](https://github.com/unnwired/FlowX_GitHubRepo.git).
- **Invariant:** Never commit `data/nse_data.db`, embedded Python, or build output — they stay local per install.

### 1.0.6 — blank Electron shell regression + release gate (Jun 26)

- **Symptom:** Client update opened blank Electron shell; `/api/health` still 200. Console: `Uncaught SyntaxError: Unexpected token '<'`.
- **Root cause:** `encrypt_app_code.ps1` left plaintext `server.py` beside `server.pyc.enc`. Client treated install as dev tree, skipped JS decrypt; `/static/js/main.*.js` returned `index.html`.
- **Fix:** Strip plaintext server `*.py` after encrypt; `is_development_tree()` honors `config\.fx-dist.cfg` + encrypted code; `cim_bootstrap` calls `ensure_app_cache()` when only `*.js.enc` exists.
- **Release gate:** `scripts\Test-CiMPackagedSmoke.ps1` — mandatory step 6/6 in `build_distribution_full.ps1`. Verifies JS bundle is JavaScript and `/api/stocks` returns 2251+ symbols. **Do not publish without PASS.**

### 1.0.6 — post-update license invalid (Jun 26)

- **Symptom:** After update, `start_cim.bat` reports: *License file exists but is NOT valid on this PC.*
- **Root cause:** Updates refresh `config\.fx-dist.cfg` to match new encrypted code; old `data\.cim-license` install key no longer matches.
- **Fix:** `CiMApplyUpdate.ps1` and `Install-Client-Update.ps1` auto-run `Repair-CiMLicense.ps1 -AutoFix` after apply. `data\.cim-license` is protected and never shipped in update ZIPs.
- **Client remediation (already updated):** Run `Repair-CiMLicense-Auto.bat` in install folder, then restart.
- **Vendor rule:** Use one stable production secret in `config\.build_license_secret` — changing it breaks all clients until repair.

### Build script fix (Jun 26)

- Unicode em-dash in `build_distribution_full.ps1` Log line broke PowerShell 5.1 (`Unexpected token ')'`). Replaced with ASCII hyphen only in script strings.

---

## Important Errors Seen and Their Meanings

### Empty desktop shell

Observed error:

```text
Uncaught SyntaxError: Unexpected token '<'
```

Meaning: Electron requested a JS bundle, but FastAPI returned HTML. Fixed in 1.0.6 encrypt + bootstrap path. Run `Test-CiMPackagedSmoke.ps1` before every publish.

### License invalid after update

Observed error:

```text
[ERROR] License file exists but is NOT valid on this PC.
Usually: install key does not match config\.fx-dist.cfg (common after an update).
```

Meaning: update refreshed vendor profile; install key must be regenerated. Run `Repair-CiMLicense-Auto.bat`. New updates auto-repair during apply (1.0.6+).

### Split-adjustments failure

Observed error:

```text
[Errno 2] No such file or directory:
'C:\Users\Sandeep\AppData\Local\FlowX\app-cache\1.0.3\scrape_daily.py'
```

Meaning: encrypted runtime loaded `server.pyc` from app-cache and a helper recomputed script paths from `__file__`. Fixed by using install-root globals/config hooks.

### Yahoo/yfinance failures

Observed error:

```text
curl: (7) Failed to connect to fc.yahoo.com port 443
possibly delisted; no timezone found
```

Meaning: client network/proxy/firewall cannot reach Yahoo; not a real delisting signal.

### Nifty India Defence chart gap / 404

Observed symptoms:

- Chart line jumps vertically between two dates months apart.
- `/api/index-chart/^CNXINDDEF` returned 404 when `index_history` was empty.
- Yahoo 404 spam for `^CNXINDDEF` (no Yahoo series exists).

Meaning: NSE-only index — use `nse_index_history.py`, not Yahoo. Gaps in `index_history` mean chunked NSE fetch missed middle dates; run Update or restart backend so `sync_nse_index_history()` repairs gaps.

---

## Current Build/Release Commands

Full build:

```powershell
.\Build-CiM.ps1
# or: .\scripts\build_distribution_full.ps1 -Version "1.0.7"
```

Release gate (runs automatically as build step 6/6; can run alone):

```powershell
.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"
```

Expected outputs:

- `installer\output\CiMSetup-{version}.exe`
- `installer\output\CiM-Update-{version}\` and `CiM-Update-{version}.zip`
- `installer\output\CiM\config\.fx-dist.cfg` and `config\github_updates.json`

**Publish to GitHub:** upload `CiM-Update-{version}.zip` to [unnwired/cim-updates Releases](https://github.com/unnwired/cim-updates/releases) with tag `v{version}`.

**First rollout of GitHub support:** existing clients still need **one** manual/bat update (folder in `UPDATE\` or `Install-Client-Update.bat`) to receive the GitHub update code; after that, cogwheel + 90-minute background checks work without support sending ZIPs every time.

Client remediation for an already-installed machine (manual path):

1. Send `installer\output\CiM-Update-{version}` or have client use GitHub ZIP → `UPDATE\CiM-Update-{version}\`.
2. Client runs `Install-Client-Update.bat` (install path auto-detected; license auto-repaired on 1.0.6+).
3. If start fails with license error: run `Repair-CiMLicense-Auto.bat`.
4. Client restarts Charts In Motion.
5. Re-test UI loads (not blank shell) and admin jobs.

## Current Risks

- Third-party data sources remain fragile. Yahoo can be blocked by client networks; NSE can rate-limit/block. NSE `indicesHistory` caps ~70 bars per request — any new NSE-only index must use chunked fetch + gap repair (see `nse_index_history.py`).
- Installer is unsigned, so Windows warnings are expected.
- Encrypted runtime path issues are the main class of future bugs. Any use of `Path(__file__)` in modules loaded from app-cache should be reviewed carefully.
- Client support depends on clear instructions for install key generation, update package application, and network diagnostics.
- **GitHub Releases repo must exist** with a matching `CiM-Update-{version}.zip` asset before remote in-app updates work end-to-end; unauthenticated API limit is 60 req/hr/IP (background poll ≈ 16/day — safe).
- **Version bump required** before each GitHub publish; run release gate before uploading ZIP.
- **Never publish** if `Test-CiMPackagedSmoke.ps1` fails (blank shell / empty data).
- **One production license secret** — do not rotate without planning client-wide repair.

---

## Suggested Next Milestones

1. Publish **`CiM-Update-1.0.6.zip`** to GitHub if not already live; verify client `C:\FlowX` after update + auto license repair.
2. For each future release: bump version → `Build-CiM.ps1` → confirm smoke PASS → publish ZIP.
3. Verify cogwheel **Apply update** and 90-minute background prompt against live GitHub release.
4. Run clean install test from `CiMSetup-{version}.exe`.
5. Decide whether to code-sign the installer before wider rollout.
6. Implement per-machine feature entitlements in update (see owner notes in `USER_REQUIREMENTS.md`).

---

## One-Line Executive Summary

Charts In Motion **1.0.6** adds a mandatory packaged smoke gate, fixes the blank-Electron encrypt regression and post-update license repair, and ships NSE Defence index history repair; use **`Build-CiM.ps1` + smoke PASS** before every GitHub release, and **`Repair-CiMLicense-Auto.bat`** if a client is stuck after an older update.

