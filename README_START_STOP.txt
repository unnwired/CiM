FlowX - Start and Stop Guide

This project includes one-click scripts to bootstrap, start, and stop the app.
Keep both documentation files together for distribution:

- README_START_STOP.md
- README_START_STOP.txt

Files to use (root folder)

- start_flowx.bat - Bootstraps automatically and starts the app with the best available mode
- stop_flowx.bat - Stops backend/frontend processes
- requirements_runtime.txt - Backend Python runtime dependency list
- create_desktop_shortcut.bat - Creates a Desktop shortcut named FlowX
- export_flowx.ps1 - Builds frontend + runtime package for distribution

One-click start (recommended)

1. Double-click start_flowx.bat
2. Script will automatically:
   - Verify required files exist (for safer unzip/use anywhere)
   - Use bundled embedded Python from runtime\python (no user install needed)
   - If embedded dependencies are missing: auto-repair from runtime\wheelhouse (offline) or online pip fallback
   - If embedded runtime is missing: create/use app-local Python env at runtime\venv
   - Install backend dependencies in background for venv fallback (uses offline wheelhouse when available)
   - If frontend/build exists: start backend only and open http://127.0.0.1:8000
   - If no build exists: install Node.js + npm (if missing), run npm install, start backend + frontend dev servers, open http://localhost:3000

Build distribution package

Run this from project root in PowerShell:

powershell -ExecutionPolicy Bypass -File ".\export_flowx.ps1"

Export modes:

- standard (default): full export including saved layout/presets/watchlists and frontend source.
- distribution: clean export for sharing; strips user state (presets/watchlists/session), forces baseline layout files, omits frontend/src, and builds frontend with distribution defaults:
  - single-chart layout
  - indicators disabled
  - EMA 100 and 200 enabled (EMA 21 and 50 disabled)

Examples:

- powershell -ExecutionPolicy Bypass -File ".\export_flowx.ps1" -Mode standard
- powershell -ExecutionPolicy Bypass -File ".\export_flowx.ps1" -Mode distribution

Note: if you pass -SkipFrontendBuild in distribution mode, existing frontend/build is reused as-is and may not reflect the distribution default indicator/EMA profile.

Optional: Create desktop shortcut

1. Double-click create_desktop_shortcut.bat
2. A Desktop shortcut named FlowX will be created
3. Use the shortcut for one-click launch in future

Stop the app

Preferred method (desktop app):

1. Click the window close button (X) on the FlowX desktop window.
2. Confirm shutdown when prompted.
3. FlowX will stop backend services and close the desktop app.

Fallback method:

1. Double-click stop_flowx.bat
2. This attempts to stop backend/frontend processes and related port listeners.

Notes

- First run can take several minutes because dependencies are installed.
- winget is only used as a last-resort fallback when no embedded runtime and no system Python are available.
- For best user experience, distribute with:
  - runtime\python\python.exe
  - runtime\wheelhouse\ (offline Python dependency packages)
  - frontend\build\index.html
- export_flowx.ps1 prepares these by default unless skip flags are used.
- If winget is needed and missing:
  - Install App Installer from Microsoft Store.
- Some machines may still require Run as Administrator on first setup.
- If browser does not open automatically:
  - Build mode: open http://127.0.0.1:8000
  - Dev mode: open http://localhost:3000
- If startup fails, check the opened backend/frontend terminals for exact errors.

