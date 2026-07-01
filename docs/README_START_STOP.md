# Charts In Motion - Start and Stop Guide

This project includes one-click scripts to bootstrap, start, and stop the app.
Keep both documentation files together for distribution:

- `README_START_STOP.md`
- `docs/README_START_STOP.md` (plain-text copy may exist under `zDelete/legacy-root/`)

## Files to use (root folder)

- `start_cim.bat` - **Bootstraps automatically** and starts the app with the best available mode
- `stop_cim.bat` - Stops backend/frontend processes
- `requirements_runtime.txt` - Backend Python runtime dependency list
- `create_desktop_shortcut.bat` - Creates a Desktop shortcut named **Charts In Motion**
- `export_cim.ps1` - Builds frontend + runtime package for distribution

## One-click start (recommended)

1. Double-click `start_cim.bat`
2. Script will automatically:
   - Verify required files exist (for safer unzip/use anywhere)
   - Use bundled embedded Python from `runtime\python` (no user install needed)
   - If embedded dependencies are missing: auto-repair from `runtime\wheelhouse` (offline) or online pip fallback
   - If embedded runtime is missing: create/use app-local Python env at `runtime\venv`
   - Install backend dependencies in background for venv fallback (uses offline wheelhouse when available)
   - If `packages/browser/build` exists: start backend only and open `http://127.0.0.1:8000`
   - If no build exists: install Node.js + npm (if missing), run `npm install` in `packages/browser`, start backend + frontend dev servers, open `http://localhost:3000`

## Build distribution package

Run this from project root in PowerShell:

`powershell -ExecutionPolicy Bypass -File ".\export_cim.ps1"`

Export modes:

- `standard` (default): full export including saved layout/presets/watchlists and frontend source.
- `distribution`: clean export for sharing; strips user state (presets/watchlists/session), forces baseline layout files, omits `packages/browser/src`, and builds browser with distribution defaults:
  - single-chart layout
  - indicators disabled
  - EMA 100 and 200 enabled (EMA 21 and 50 disabled)

Examples:

- `powershell -ExecutionPolicy Bypass -File ".\export_cim.ps1" -Mode standard`
- `powershell -ExecutionPolicy Bypass -File ".\export_cim.ps1" -Mode distribution`

Note: if you pass `-SkipFrontendBuild` in distribution mode, existing `packages/browser/build` is reused as-is and may not reflect the distribution default indicator/EMA profile.

## Optional: Create desktop shortcut

1. Double-click `create_desktop_shortcut.bat`
2. A Desktop shortcut named **Charts In Motion** will be created
3. Use the shortcut for one-click launch in future

## Stop the app

Preferred method (desktop app):

1. Click the window close button (`X`) on the Charts In Motion desktop window.
2. Confirm shutdown when prompted.
3. Charts In Motion will stop backend services and close the desktop app.

Fallback method:

1. Double-click `stop_cim.bat`
2. This attempts to stop backend/frontend processes and related port listeners.

## Notes

- First run can take several minutes because dependencies are installed.
- `winget` is only used as a last-resort fallback when no embedded runtime and no system Python are available.
- For best user experience, distribute with:
  - `runtime\python\python.exe`
  - `runtime\wheelhouse\` (offline Python dependency packages)
  - `frontend\build\index.html`
- `export_cim.ps1` prepares these by default unless skip flags are used.
- If `winget` is needed and missing:
  - Install **App Installer** from Microsoft Store.
- Some machines may still require **Run as Administrator** on first setup.
- If browser does not open automatically:
  - Build mode: open `http://127.0.0.1:8000`
  - Dev mode: open `http://localhost:3000`
- If startup fails, check the opened backend/frontend terminals for exact errors.

## Web showcase (Tailscale / browser clients)

Host PC install (e.g. `D:\CiM\Client`) serves the app to browsers. **Only the host** mutates shared market data (`data\nse_data.db`).

### Host setup

1. Export/sync the client tree to the host folder.
2. Start showcase: `powershell -ExecutionPolicy Bypass -File ".\scripts\Start-CiMShowcase.ps1" -InstallRoot "D:\CiM\Client"`
   - Creates `config\.cim-web-host` (per-browser cookie sessions) and `config\.cim-showcase-host` (admin/EOD allowed).
   - **Do not** ship `.cim-showcase-host` to remote client copies.
3. **Public client URL (Tailscale Funnel):** double-click `start_showcase_tailscale.bat` on the host PC.
   - Writes `SHOWCASE_CLIENT_LINK.txt` and `runtime\logs\public-url.txt` from live Tailscale MagicDNS (e.g. `https://charts-in-motion.tailXXXX.ts.net/`).
   - After renaming the PC in Tailscale, run this once so clients get the new link (old `asus-laptop.*` URLs stop working).
4. **Daily EOD (16:00–16:30 IST, NSE bhavcopy):** double-click `Register-Showcase-Eod-Task.bat` once on the host PC to install the Windows scheduled task. Logs: `{install}\runtime\logs\showcase-eod-scheduled.log`. Manual run: `scripts\Run-CiMShowcaseEodOnce.ps1` or **Account → Run EOD reconcile now** on the host operator session. Remove task: `Unregister-Showcase-Eod-Task.bat`.

### Browser clients

- Sign in at the HTTPS URL in `SHOWCASE_CLIENT_LINK.txt` on the host PC; watchlists/portfolio/layout are per user.
- Use **Refresh live prices** (not Update) for intraday overlay — stored in each browser only.
- After host EOD publish, clients poll `GET /api/market-data-version` and drop local patches automatically.

### Verify

`powershell -ExecutionPolicy Bypass -File ".\scripts\Test-CiMShowcaseE2E.ps1"`

### Future: Postgres EOD (out of v1)

When EOD moves from host SQLite to managed Postgres, keep the same client contracts:

- `GET /api/market-data-version` — `{ eod_trade_date, published_at, status, session_intraday_allowed }`
- `GET|POST /api/intraday-patch` — stateless NSE overlay, no DB writes

Point API reads at Postgres; run bhavcopy worker on cloud cron; auth stays on Cloudflare Worker.

