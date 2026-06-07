# FlowX — Executive Handoff Summary

**Generated:** 13 April 26  
**Last updated:** 05 Jun 26 (GitHub updates + UPDATE folder fixes)  
**Project root:** `D:\Programs\NSE Pulse\Claude Ai`

---

## Why This File Exists

There are two handoffs:

- `PROJECT_HANDOFF.md` is the detailed technical handoff for the next engineer/AI.
- `PROJECT_HANDOFF_EXEC_SUMMARY.md` is this shorter status/risk summary.

Keep both for now. If you only want one later, keep `PROJECT_HANDOFF.md` because it contains the full architecture, error trail, root causes, and runbooks.

---

## Current Project Status

- **Product surface:** Market Pulse, NSE Dashboard, Market Movers, Market Map, Earnings, Indices, Watchlist, Portfolio, chart tabs, and admin refresh workflows are implemented.
- **Distribution model:** Windows installer distribution is implemented.
- **Activation model:** Offline machine-code/install-key licensing is implemented.
- **Runtime model:** Local Electron desktop + local FastAPI backend + local SQLite DB.
- **Current version:** `1.0.2` in `installer\output\version.txt` (last verified build). Production clients may still be on **`1.0.3`** from an earlier ship — **bump `version.txt` to the next release (e.g. `1.0.4`) before publishing** the GitHub-enabled update so cogwheel/background checks see a newer version.
- **Current release artifacts (last verified build):**
  - Installer: `installer\output\FlowXSetup-1.0.2.exe`
  - Update package: `installer\output\FlowX-Update-1.0.2\`
  - GitHub upload ZIP: `installer\output\FlowX-Update-1.0.2.zip`
  - Export tree: `installer\output\FlowX`

---

## What Changed Recently

### Installer, licensing, and export layout

- Added Inno Setup installer with machine-code and install-key wizard.
- Added silent install key support (`/INSTALLKEY=`).
- Added support scripts for key generation, license repair, and chain verification.
- Moved export/update output from `!Export\FlowX` to `installer\output\FlowX`.
- Renamed the client-visible distribution secret file from `config\.flowx_vendor_secret` to the more discreet `config\.fx-dist.cfg`.
- Kept legacy fallback for existing installs that still have the old filename.

### Encrypted runtime

- Distribution builds encrypt server bytecode and frontend JS.
- Runtime decrypts into `%LOCALAPPDATA%\FlowX\app-cache\{version}` after license validation.
- Important invariant: code may execute from app-cache, but data/scripts/update files must resolve from the install root (`C:\FlowX`, `D:\FlowX`, etc.).

### Major bugs fixed

- **Blank Electron shell:** caused by `/static/js/main.*.js` returning `index.html`; fixed by mounting decrypted `/static` before the SPA catch-all route.
- **Hidden backend console:** normal `start_flowx.bat` now opens a visible `FlowX Backend` console again.
- **Split-adjustments client failure:** fixed app-cache path leak where the app looked for `%LOCALAPPDATA%\FlowX\app-cache\1.0.3\scrape_daily.py` instead of `C:\FlowX\scrape_daily.py`.
- **Update path leaks:** update apply scripts/logs now resolve from install root, not app-cache.
- **Movers/calendar path leaks:** movers data now uses configured install-root `data\nse_calendar.json`.
- **License drift:** installer, Repair, and runtime now use the same profile/secret source and are verified by `Verify-FlowXLicenseChain.ps1`.

### GitHub Release updates (Jun 26)

- **Remote update source:** FlowX now pulls updates from GitHub Releases only — repo [unnwired/flowx-updates](https://github.com/unnwired/flowx-updates), asset `FlowX-Update-{version}.zip`. Legacy `config\update_manifest_url.json` / HTTPS manifest multi-file remote is **deprecated** (not used).
- **Update priority:** `{install}\UPDATE\FlowX-Update-*` (local) first; GitHub `releases/latest` second. Same version → local wins.
- **In-app flow:** Settings cogwheel **Apply update** → check → confirm → download (GitHub ZIP to staging → extract to `UPDATE\`) → apply via existing `FlowXApplyUpdate.ps1` → quit.
- **Background prompt:** While the app is open, polls `GET /api/update/check?background=true` every **90 minutes** (configurable). Popup offers update; **No** dismisses until a newer version appears (`sessionStorage` key `flowx.dismissedUpdateVersion`).
- **Config:** `config\github_updates.json` (owner, repo, `checkIntervalMinutes`, `backgroundCheckEnabled`). Shipped in export, installer, and update payload. Env overrides: `FLOWX_GITHUB_OWNER`, `FLOWX_GITHUB_REPO`.
- **Backend:** `server\github_updates.py` (Releases API, asset pick, ZIP download/extract); wired in `server\update_apply.py` (`/api/update/settings`, `/check`, `/download`, `/apply`).
- **Build:** `build_update_package.ps1` emits `FlowX-Update-{version}.zip` beside the folder for GitHub upload. Full build verified via `Build-FlowX.ps1` (see build log).

### UPDATE folder detection (Jun 26)

- Client updates must live under **`{install}\UPDATE\FlowX-Update-{version}\`**, not the FlowX root.
- Fixed install-path detection when the user runs `Install-Client-Update.bat` from inside `UPDATE\` (no manual path typing).
- Scripts updated: `FlowXInstallLocator.ps1`, `Install-Client-Update.ps1`, `FlowXUpdatePackage.ps1`, `Apply-LocalUpdate-Entry.ps1`, `update_apply.py` (`_local_update_package_roots`).

---

## Important Errors Seen and Their Meanings

### Empty desktop shell

Observed error:

```text
Uncaught SyntaxError: Unexpected token '<'
```

Meaning: Electron requested a JS bundle, but FastAPI returned HTML. Fixed in `server\flowx_bootstrap.py`.

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

---

## Current Build/Release Commands

Full build:

```powershell
.\Build-FlowX.ps1
# or: .\scripts\build_distribution_full.ps1 -Version "1.0.4"
```

Expected outputs:

- `installer\output\FlowXSetup-{version}.exe`
- `installer\output\FlowX-Update-{version}\` and `FlowX-Update-{version}.zip`
- `installer\output\FlowX\config\.fx-dist.cfg` and `config\github_updates.json`

**Publish to GitHub:** upload `FlowX-Update-{version}.zip` to [unnwired/flowx-updates Releases](https://github.com/unnwired/flowx-updates/releases) with tag `v{version}`.

**First rollout of GitHub support:** existing clients still need **one** manual/bat update (folder in `UPDATE\` or `Install-Client-Update.bat`) to receive the GitHub update code; after that, cogwheel + 90-minute background checks work without support sending ZIPs every time.

Client remediation for an already-installed machine (manual path):

1. Send `installer\output\FlowX-Update-{version}` or have client use GitHub ZIP → `UPDATE\FlowX-Update-{version}\`.
2. Client runs `Install-Client-Update.bat` (install path auto-detected from `UPDATE\` ancestry).
3. Client restarts FlowX.
4. Re-test **Apply update** (cogwheel) and admin jobs (e.g. split adjustments).

## Current Risks

- Third-party data sources remain fragile. Yahoo can be blocked by client networks; NSE can rate-limit/block.
- Installer is unsigned, so Windows warnings are expected.
- Encrypted runtime path issues are the main class of future bugs. Any use of `Path(__file__)` in modules loaded from app-cache should be reviewed carefully.
- Client support depends on clear instructions for install key generation, update package application, and network diagnostics.
- **GitHub Releases repo must exist** with a matching `FlowX-Update-{version}.zip` asset before remote in-app updates work end-to-end; unauthenticated API limit is 60 req/hr/IP (background poll ≈ 16/day — safe).
- **Version bump required** before shipping GitHub-enabled build to clients already on 1.0.3; do not republish 1.0.2 as a “new” update for those machines.

---

## Suggested Next Milestones

1. Bump `installer\output\version.txt` (e.g. to `1.0.4`), run `Build-FlowX.ps1`, publish ZIP to GitHub Releases (`v{version}` tag).
2. Ship one bat/manual update to clients on 1.0.3 so they receive GitHub update code.
3. Verify cogwheel **Apply update** and 90-minute background prompt against live GitHub release.
4. Test the latest update package on the unhappy client install at `C:\FlowX` (UPDATE folder layout).
5. Run a clean install test from `FlowXSetup-{version}.exe`.
6. Add regression tests for encrypted runtime install-root paths (extend `scripts\test_github_updates.py` as needed).
7. Decide whether to code-sign the installer before wider rollout.
8. Improve client-facing network diagnostics for Yahoo/NSE failures.

---

## One-Line Executive Summary

FlowX now has a working Windows installer, offline license activation, encrypted runtime, GitHub Release updates (with local `UPDATE\` priority), UPDATE-folder auto-detection, and install-root path fixes; the next priority is version bump, first GitHub release publish, and client validation on `C:\FlowX` / `D:\FlowX` installs.

