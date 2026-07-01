@echo off
setlocal DisableDelayedExpansion

REM ========================================================================
REM Primary way to run Charts In Motion: double-click this file or run from CMD here.
REM It prepares Python, rebuilds packages\browser\build when sources are newer,
REM starts the API at http://127.0.0.1:8000 , then opens Charts In Motion Desktop.
REM
REM Optional environment variables (set before running, or in System):
REM   CIM_SKIP_FRONTEND_BUILD=1  — never run npm run build (uses existing build)
REM   CIM_FORCE_FRONTEND_BUILD=1   — always run npm run build before start
REM   CIM_REQUIRE_ONLINE_AUTH=1  — show sign-in / sign-up (dev auth test; or use start_cim_auth_test.bat)
REM
REM Manual start without this file ^(developers^):
REM   cd /d "<project folder>"
REM   cd packages\browser ^&^& npm install ^&^& npm run build ^&^& cd ..
REM   runtime\python\python.exe -s runtime\run_uvicorn.py server.server:app --host 127.0.0.1 --port 8000
REM   Open http://127.0.0.1:8000  ^(or let Charts In Motion Desktop load it^)
REM ========================================================================

REM Resolve project root from this script location
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

call "%ROOT%\scripts\Resolve-CiMPaths.bat" "%ROOT%" 2>nul
if not defined CIM_FRONTEND_DIR (
  set "CIM_FRONTEND_DIR=%ROOT%\frontend"
  if not exist "%CIM_FRONTEND_DIR%\package.json" if exist "%ROOT%\packages\browser\package.json" set "CIM_FRONTEND_DIR=%ROOT%\packages\browser"
)
if not defined CIM_UVICORN_LAUNCHER set "CIM_UVICORN_LAUNCHER=%ROOT%\runtime\run_uvicorn.py"
if not exist "%ROOT%\scripts\Resolve-CiMPaths.bat" if not exist "%CIM_UVICORN_LAUNCHER%" (
  echo [ERROR] Missing runtime\run_uvicorn.py — re-run export/sync from the dev repo.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
set "FRONTEND_DIR=%CIM_FRONTEND_DIR%"
set "UVICORN_LAUNCHER=%CIM_UVICORN_LAUNCHER%"

REM Set log paths here (not inside parenthesized blocks — avoids empty vars with DisableDelayedExpansion).
set "BACKEND_LOG=%ROOT%\runtime\logs\backend-startup.log"
set "BACKEND_ERR=%ROOT%\runtime\logs\backend-startup.err.log"

echo ==========================================
echo Charts In Motion Bootstrap + Start
echo ==========================================
echo Project root: "%ROOT%"
echo.

set "BOOTSTRAP_PYTHON="
set "VENV_PY=%ROOT%\runtime\venv\Scripts\python.exe"
set "EMBEDDED_PY=%ROOT%\runtime\python\python.exe"

set "SERVER_LAYOUT_OK=0"
if exist "%ROOT%\server\server.py" set "SERVER_LAYOUT_OK=1"
if exist "%ROOT%\packages\server\server.py" set "SERVER_LAYOUT_OK=1"
if exist "%ROOT%\server\server.pyc" set "SERVER_LAYOUT_OK=1"
if exist "%ROOT%\server\server.pyc.enc" set "SERVER_LAYOUT_OK=1"
if exist "%ROOT%\server\cim_bootstrap.py" if exist "%ROOT%\server\app_code_crypto.py" (
  if exist "%ROOT%\server\server.pyc.enc" set "SERVER_LAYOUT_OK=1"
)
if exist "%ROOT%\packages\server\cim_bootstrap.py" if exist "%ROOT%\packages\server\app_code_crypto.py" (
  if exist "%ROOT%\packages\server\server.pyc.enc" set "SERVER_LAYOUT_OK=1"
)
if "%SERVER_LAYOUT_OK%"=="0" (
  echo [ERROR] Charts In Motion server files are missing.
  echo Expected dev build: packages\server\server.py or server\server.py
  echo Expected distribution: server\cim_bootstrap.py + server\server.pyc.enc
  echo Ensure this .bat is inside a complete Charts In Motion install folder.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

if not exist "%ROOT%\data\nse_data.db" (
  echo [ERROR] Required database file is missing: data\nse_data.db
  echo Please restore the distribution package or contact support.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

if not exist "%ROOT%\db_sqlite.py" (
  echo [ERROR] Required module is missing: db_sqlite.py
  echo This export folder is incomplete. Re-run export_cim.ps1 from the dev project,
  echo or copy a complete Charts In Motion package — do not run from a partial Charts In Motion.staging folder.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

if not exist "%ROOT%\runtime\python\python.exe" (
  echo [ERROR] Bundled Python runtime is missing: runtime\python\python.exe
  echo Re-export Charts In Motion or restore runtime\python from a complete package.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

REM -----------------------------------------------------------
REM 1) Prefer embedded runtime (no install required)
REM -----------------------------------------------------------
if exist "%EMBEDDED_PY%" (
  echo Using bundled embedded Python runtime.
  "%EMBEDDED_PY%" -c "import fastapi, uvicorn, pandas, yfinance, tradingview_screener, cryptography" >nul 2>&1
  if errorlevel 1 (
    echo Embedded runtime dependencies missing. Repairing...
    if exist "%ROOT%\runtime\wheelhouse" (
      "%EMBEDDED_PY%" -m pip install --upgrade --no-index --find-links "%ROOT%\runtime\wheelhouse" pip
      if exist "%ROOT%\requirements_runtime.txt" (
        "%EMBEDDED_PY%" -m pip install --upgrade --no-index --find-links "%ROOT%\runtime\wheelhouse" -r "%ROOT%\requirements_runtime.txt"
      ) else (
        "%EMBEDDED_PY%" -m pip install --upgrade --no-index --find-links "%ROOT%\runtime\wheelhouse" fastapi uvicorn pandas yfinance
      )
      if errorlevel 1 (
        echo Offline wheelhouse install incomplete. Retrying from online index...
        if exist "%ROOT%\requirements_runtime.txt" (
          "%EMBEDDED_PY%" -m pip install -r "%ROOT%\requirements_runtime.txt"
        ) else (
          "%EMBEDDED_PY%" -m pip install fastapi uvicorn pandas yfinance
        )
      )
    ) else (
      if exist "%ROOT%\requirements_runtime.txt" (
        "%EMBEDDED_PY%" -m pip install -r "%ROOT%\requirements_runtime.txt"
      ) else (
        "%EMBEDDED_PY%" -m pip install fastapi uvicorn pandas yfinance
      )
    )
    if errorlevel 1 (
      echo [ERROR] Failed to repair embedded runtime dependencies.
      echo Re-export package and ensure runtime\wheelhouse is included.
      if not defined CIM_NO_PAUSE pause
      exit /b 1
    )
    "%EMBEDDED_PY%" -c "import fastapi, uvicorn, pandas, yfinance, tradingview_screener, cryptography" >nul 2>&1
    if errorlevel 1 (
      echo [ERROR] Embedded runtime still invalid after repair.
      if not defined CIM_NO_PAUSE pause
      exit /b 1
    )
  )
  set "PYTHON_EXE=%EMBEDDED_PY%"
  goto :python_ready
)

REM -----------------------------------------------------------
REM 2) Resolve bootstrap Python (py/python/winget) for venv fallback
REM -----------------------------------------------------------
py -3 --version >nul 2>&1
if not errorlevel 1 (
  set "BOOTSTRAP_PYTHON=py -3"
  goto :python_found
)

python --version >nul 2>&1
if not errorlevel 1 (
  set "BOOTSTRAP_PYTHON=python"
  goto :python_found
)

where winget >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is unavailable and winget is not installed.
  echo Install App Installer from Microsoft Store and re-run this file.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
echo Python runtime missing. Attempting automatic install via winget...
set "WINGET_LOG=%TEMP%\cim_winget_python_install.log"
del /q "%WINGET_LOG%" >nul 2>&1

REM First try user-scope install (works without admin in most cases).
winget install --id Python.Python.3 --source winget --scope user --accept-package-agreements --accept-source-agreements --silent >"%WINGET_LOG%" 2>&1
if errorlevel 1 (
  echo User-scope install failed. Retrying default scope...
  winget install --id Python.Python.3 --source winget --accept-package-agreements --accept-source-agreements --silent >>"%WINGET_LOG%" 2>&1
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
  set "BOOTSTRAP_PYTHON=py -3"
  goto :python_found
)
python --version >nul 2>&1
if not errorlevel 1 (
  set "BOOTSTRAP_PYTHON=python"
  goto :python_found
)
python3 --version >nul 2>&1
if not errorlevel 1 (
  set "BOOTSTRAP_PYTHON=python3"
  goto :python_found
)
echo [ERROR] Python installation failed.
echo Winget log: "%WINGET_LOG%"
echo Run this manually for details:
echo winget install --id Python.Python.3 --source winget --scope user --accept-package-agreements --accept-source-agreements --silent
if not defined CIM_NO_PAUSE pause
exit /b 1

:python_found
echo.
echo Preparing app-local Python runtime...
if not exist "%VENV_PY%" (
  echo Creating virtual environment in runtime\venv ...
  %BOOTSTRAP_PYTHON% -m venv "%ROOT%\runtime\venv"
  if errorlevel 1 (
    echo [ERROR] Failed to create local virtual environment.
    if not defined CIM_NO_PAUSE pause
    exit /b 1
  )
)
set "PYTHON_EXE=%VENV_PY%"

echo Installing/validating backend Python packages...
if exist "%ROOT%\runtime\wheelhouse" (
  echo Using packaged offline wheelhouse...
  "%PYTHON_EXE%" -s -m pip install --upgrade --no-index --find-links "%ROOT%\runtime\wheelhouse" pip
  if exist "%ROOT%\requirements_runtime.txt" (
    "%PYTHON_EXE%" -s -m pip install --upgrade --no-index --find-links "%ROOT%\runtime\wheelhouse" -r "%ROOT%\requirements_runtime.txt"
  ) else (
    "%PYTHON_EXE%" -s -m pip install --upgrade --no-index --find-links "%ROOT%\runtime\wheelhouse" fastapi uvicorn pandas yfinance
  )
  if errorlevel 1 (
    echo Offline wheelhouse install incomplete. Retrying from online index...
    if exist "%ROOT%\requirements_runtime.txt" (
      "%PYTHON_EXE%" -s -m pip install -r "%ROOT%\requirements_runtime.txt"
    ) else (
      "%PYTHON_EXE%" -s -m pip install fastapi uvicorn pandas yfinance
    )
  )
) else (
  "%PYTHON_EXE%" -s -m pip install --upgrade pip
  if exist "%ROOT%\requirements_runtime.txt" (
    "%PYTHON_EXE%" -s -m pip install -r "%ROOT%\requirements_runtime.txt"
  ) else (
    "%PYTHON_EXE%" -s -m pip install fastapi uvicorn pandas yfinance
  )
)
if errorlevel 1 (
  echo [ERROR] Failed to install backend Python packages in runtime\venv.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
"%PYTHON_EXE%" -s -c "import fastapi, uvicorn, pandas, yfinance, tradingview_screener" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Backend dependency validation failed in runtime\venv.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

:python_ready

echo.
REM -----------------------------------------------------------
REM 2a) Distribution: license + skip dev-only frontend rebuild
REM     Dev tree = server\server.py present (repo) or CIM_DEV=1
REM -----------------------------------------------------------
set "CIM_DISTRIBUTION=0"
if exist "%ROOT%\config\.cim-plaintext-dist" (
  set "CIM_DISTRIBUTION=1"
)
if exist "%ROOT%\server\server.pyc.enc" if not exist "%ROOT%\server\server.py" (
  set "CIM_DISTRIBUTION=1"
)
if /I "%CIM_DEV%"=="1" set "CIM_DISTRIBUTION=0"
if /I "%CIM_DEV%"=="true" set "CIM_DISTRIBUTION=0"
if /I "%CIM_DEV%"=="yes" set "CIM_DISTRIBUTION=0"

if "%CIM_DISTRIBUTION%"=="1" (
  if exist "%ROOT%\config\.cim-plaintext-dist" (
    echo Distribution build detected ^(plaintext — readable source, online auth^).
  ) else (
    echo Distribution build detected ^(encrypted app code^).
  )
  if exist "%ROOT%\runtime\python\python.exe" (
    set "CIM_LICENSE_SECRET="
    "%ROOT%\runtime\python\python.exe" -s -c "import sys; sys.path.insert(0, r'%ROOT%'); sys.path.insert(0, r'%ROOT%\packages'); from pathlib import Path; from server.app_code_crypto import access_granted; raise SystemExit(0 if access_granted(Path(r'%ROOT%')) else 1)" >nul 2>&1
    if errorlevel 1 (
      echo No offline license or online session — sign-in screen will open first.
    ) else (
      echo License OK ^(offline key or online session^).
    )
  )
  goto :after_frontend_build_check
)

if /I "%CIM_REQUIRE_ONLINE_AUTH%"=="1" (
  echo Online auth required ^(CIM_REQUIRE_ONLINE_AUTH=1^) — sign-in before full app.
  echo.
)

if exist "%ROOT%\server\server.py" if exist "%ROOT%\server\server.pyc.enc" (
  echo Development tree ^(server\server.py^) — license not required; using plaintext backend.
  echo.
)

REM -----------------------------------------------------------
REM 2b) Keep frontend\build in sync with frontend\src (needs Node/npm)
REM -----------------------------------------------------------
call :EnsureFrontendBuild
if errorlevel 1 (
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
:after_frontend_build_check

echo.
REM -----------------------------------------------------------
REM 3) Prefer built frontend (no npm/node needed for users)
REM -----------------------------------------------------------
if exist "%FRONTEND_DIR%\build\index.html" (
  call :StartPackagedApp
  exit /b %ERRORLEVEL%
)

REM -----------------------------------------------------------
REM 4) Dev mode fallback: install node/npm and run frontend
REM -----------------------------------------------------------
if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] browser package.json not found and no frontend build exists.
  echo This package appears incomplete.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

call :ResolveNpmCmd
if errorlevel 1 (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Node.js is missing and winget is unavailable.
    echo Install Node.js LTS manually from https://nodejs.org and retry.
    if not defined CIM_NO_PAUSE pause
    exit /b 1
  )
  echo Node.js not found. Installing Node.js LTS...
  call :TryInstallNodeWithWinget
  call :FlowxSleep 3
  call :ResolveNpmCmd
  if errorlevel 1 (
    echo [ERROR] Node.js installation failed or PATH not updated. Re-run this script as Administrator,
    echo or install Node.js LTS manually from https://nodejs.org  ^(ensure "Add to PATH" is checked^).
    if not defined CIM_NO_PAUSE pause
    exit /b 1
  )
)

echo Installing/validating frontend npm packages...
cd /d "%FRONTEND_DIR%"
"%NPM_CMD%" install
if errorlevel 1 (
  echo [ERROR] npm install failed in browser package.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
cd /d "%ROOT%"

echo Starting Charts In Motion services (backend + frontend dev server)...
start "CiM Backend" /D "%ROOT%" "%PYTHON_EXE%" -s "%UVICORN_LAUNCHER%" server.server:app --reload --reload-dir "%CIM_SERVER_RELOAD_DIR%" --host 127.0.0.1 --port 8000
start "Charts In Motion Frontend" /D "%FRONTEND_DIR%" cmd /k call "%NPM_CMD%" start
call :FlowxSleep 5
start "" "http://localhost:3000"

echo.
echo Done. Backend and frontend terminals are running.
echo If startup fails, check both opened terminal windows for details.
exit /b 0

:StartPackagedApp
echo Found prebuilt frontend. Starting backend service...
if not exist "%ROOT%\runtime\logs" mkdir "%ROOT%\runtime\logs"
del /q "%BACKEND_LOG%" "%BACKEND_ERR%" >nul 2>&1
set "CIM_UVICORN_APP=server.cim_bootstrap:app"
if exist "%ROOT%\config\.cim-plaintext-dist" (
  echo Plaintext distribution backend ^(cim_bootstrap — online auth gate^).
) else if exist "%ROOT%\server\server.py" (
  if /I "%CIM_REQUIRE_ONLINE_AUTH%"=="1" (
    echo Development backend with online auth gate ^(cim_bootstrap — sign-in required^).
  ) else (
    set "CIM_UVICORN_APP=server.server:app"
    echo Development backend ^(server.server:app — no license required^).
  )
) else if exist "%ROOT%\packages\server\server.py" (
  if /I "%CIM_REQUIRE_ONLINE_AUTH%"=="1" (
    echo Development backend with online auth gate ^(cim_bootstrap — sign-in required^).
  ) else (
    set "CIM_UVICORN_APP=server.server:app"
    echo Development backend ^(server.server:app — no license required^).
  )
) else (
  echo Distribution backend ^(encrypted app code^).
)
if defined CIM_NO_PAUSE goto :StartPackagedApp_Hidden
echo Opening CiM Backend console ^(live scan / fetch logs appear here^)...
start "CiM Backend" /D "%ROOT%" cmd /k ""%PYTHON_EXE%" -s "%UVICORN_LAUNCHER%" %CIM_UVICORN_APP% --host 127.0.0.1 --port 8000"
goto :StartPackagedApp_AfterLaunch
:StartPackagedApp_Hidden
powershell -NoProfile -WindowStyle Hidden -Command ^
  "$root = '%ROOT%'; $py = '%PYTHON_EXE%'; $launcher = Join-Path $root 'runtime\run_uvicorn.py'; $app = '%CIM_UVICORN_APP%'; $log = Join-Path $root 'runtime\logs\backend-startup.log'; $err = Join-Path $root 'runtime\logs\backend-startup.err.log'; $pidf = Join-Path $root 'runtime\logs\backend.pid'; New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null; $p = Start-Process -FilePath $py -ArgumentList @('-s',$launcher,$app,'--host','127.0.0.1','--port','8000') -WorkingDirectory $root -PassThru -RedirectStandardOutput $log -RedirectStandardError $err; if ($p) { $p.Id | Out-File -FilePath $pidf -Encoding ascii }"
:StartPackagedApp_AfterLaunch
if errorlevel 1 (
  echo [ERROR] Failed to launch backend process.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
call :WaitForBackendReady
if errorlevel 1 (
  echo [ERROR] Backend did not start. See:
  echo   "%BACKEND_LOG%"
  echo   "%BACKEND_ERR%"
  call :ShowBackendErrTail
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
call :LaunchDesktop
if errorlevel 1 (
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
echo.
echo Done. Charts In Motion is starting.
exit /b 0

:ShowBackendErrTail
if exist "%BACKEND_ERR%" (
  echo.
  echo --- Last lines of backend-startup.err.log ---
  powershell -NoProfile -Command "Get-Content -LiteralPath '%BACKEND_ERR%' -Tail 25 -ErrorAction SilentlyContinue"
  echo ---
)
exit /b 0

:WaitForBackendReady
set "WAIT_SEC=0"
:WaitForBackendReady_Loop
powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { exit 0 } else { exit 1 } } catch { exit 1 }"
if not errorlevel 1 exit /b 0
set /a WAIT_SEC+=2
if %WAIT_SEC% GEQ 90 (
  echo [ERROR] Timed out waiting for backend on http://127.0.0.1:8000
  exit /b 1
)
call :FlowxSleep 2
goto :WaitForBackendReady_Loop

:LaunchDesktop
set "DESKTOP_DIR=%CIM_DESKTOP_DIR%"
set "ELECTRON_EXE=%DESKTOP_DIR%\node_modules\electron\dist\electron.exe"

if not exist "%DESKTOP_DIR%\package.json" (
  echo [ERROR] Desktop launcher files missing: "%DESKTOP_DIR%\package.json"
  echo Re-export Charts In Motion and retry.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)

if exist "%ELECTRON_EXE%" (
  echo Starting Charts In Motion Desktop window...
  start "Charts In Motion Desktop" /D "%DESKTOP_DIR%" "%ELECTRON_EXE%" --disable-gpu --disable-http-cache .
  cd /d "%ROOT%"
  exit /b 0
)

call :ResolveNpmCmd
if errorlevel 1 (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Desktop shell ^(Electron^) needs Node.js/npm; winget is unavailable on this machine.
    call :PromptBrowserFallback
    exit /b %ERRORLEVEL%
  )
  echo Node.js not found. Installing Node.js LTS for Charts In Motion Desktop...
  call :TryInstallNodeWithWinget
  call :FlowxSleep 3
  call :ResolveNpmCmd
  if errorlevel 1 (
    echo [ERROR] Automatic Node.js install did not expose npm in this session ^(common after winget^).
    call :PromptBrowserFallback
    exit /b %ERRORLEVEL%
  )
  echo Node.js located successfully.
)

echo Starting Charts In Motion Desktop window...
cd /d "%DESKTOP_DIR%"
if not exist "%ELECTRON_EXE%" (
  echo Installing desktop runtime...
  "%NPM_CMD%" install
  if errorlevel 1 (
    echo [ERROR] Desktop runtime install failed. Desktop window cannot start.
    cd /d "%ROOT%"
    call :PromptBrowserFallback
    exit /b %ERRORLEVEL%
  )
)
if not exist "%DESKTOP_DIR%\node_modules\electron\dist\electron.exe" (
  echo [ERROR] Electron executable not found: "%DESKTOP_DIR%\node_modules\electron\dist\electron.exe"
  echo Try deleting desktop\node_modules and re-run start_cim.bat.
  cd /d "%ROOT%"
  call :PromptBrowserFallback
  exit /b %ERRORLEVEL%
)
set "ELECTRON_EXE=%DESKTOP_DIR%\node_modules\electron\dist\electron.exe"
start "Charts In Motion Desktop" /D "%DESKTOP_DIR%" "%ELECTRON_EXE%" --disable-gpu --disable-http-cache .
cd /d "%ROOT%"
exit /b 0

REM Prefer the standalone Node.js npm.cmd. Do NOT use bare "npm" first: PATH often has
REM frontend\node_modules\.bin ahead of global Node, which invokes a broken nested
REM frontend\node_modules\npm package (missing npm-prefix.js / npm-cli.js).
:ResolveNpmCmd
set "NPM_CMD="
if exist "%ProgramFiles%\nodejs\npm.cmd" (
  set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
  exit /b 0
)
if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" (
  set "NPM_CMD=%ProgramFiles(x86)%\nodejs\npm.cmd"
  exit /b 0
)
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\nodejs\npm.cmd" (
  set "NPM_CMD=%LOCALAPPDATA%\Programs\nodejs\npm.cmd"
  exit /b 0
)
for /f "delims=" %%P in ('where npm 2^>nul') do (
  echo %%P | findstr /I "node_modules" >nul 2>&1
  if errorlevel 1 (
    set "NPM_CMD=%%~P"
    exit /b 0
  )
)
where npm >nul 2>&1
if not errorlevel 1 (
  set "NPM_CMD=npm"
  exit /b 0
)
exit /b 1

:TryInstallNodeWithWinget
winget install --id OpenJS.NodeJS.LTS --source winget --scope user --accept-package-agreements --accept-source-agreements --silent
if errorlevel 1 (
  echo Retrying winget without --scope user...
  winget install --id OpenJS.NodeJS.LTS --source winget --accept-package-agreements --accept-source-agreements --silent
)
exit /b 0

:PromptBrowserFallback
set "FLOWX_FALLBACK_CHOICE="
where powershell >nul 2>&1
if not errorlevel 1 (
  for /f "usebackq delims=" %%R in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Windows.Forms; $msg='Electron failed to start. Open browser mode instead?'; $title='Charts In Motion Startup'; $btn=[System.Windows.Forms.MessageBoxButtons]::YesNo; $icon=[System.Windows.Forms.MessageBoxIcon]::Warning; $res=[System.Windows.Forms.MessageBox]::Show($msg,$title,$btn,$icon); if($res -eq [System.Windows.Forms.DialogResult]::Yes){'YES'} else {'NO'}" 2^>nul`) do set "FLOWX_FALLBACK_CHOICE=%%R"
)
if /I "%FLOWX_FALLBACK_CHOICE%"=="YES" goto :FallbackYes
if /I "%FLOWX_FALLBACK_CHOICE%"=="NO" goto :FallbackNo

echo.
echo Electron failed. Open browser mode? ^(Y/N^)
choice /C YN /N /M "Press Y for browser mode, N to stop Charts In Motion: "
if errorlevel 2 goto :FallbackNo
if errorlevel 1 goto :FallbackYes

:FallbackNo
if exist "%ROOT%\stop_cim.bat" (
  call "%ROOT%\stop_cim.bat" >nul 2>&1
)
exit /b 1

:FallbackYes
start "" "http://127.0.0.1:8000/"
exit /b 0

REM ------------------------------------------------------------------
REM Rebuild production bundle when sources/config are newer than build,
REM or when CIM_FORCE_FRONTEND_BUILD=1 . Requires npm on PATH.
REM ------------------------------------------------------------------
:EnsureFrontendBuild
if "%CIM_SKIP_FRONTEND_BUILD%"=="1" (
  echo CIM_SKIP_FRONTEND_BUILD=1 — skipping frontend rebuild check.
  exit /b 0
)

if "%CIM_FORCE_FRONTEND_BUILD%"=="1" (
  echo CIM_FORCE_FRONTEND_BUILD=1 — rebuilding frontend...
  goto :EnsureFrontendBuild_RunNpm
)

if not exist "%ROOT%\scripts\frontend_needs_build.ps1" (
  echo [WARN] scripts\frontend_needs_build.ps1 missing — cannot check stale frontend. Continuing.
  exit /b 0
)

set "FB_EXIT=0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\frontend_needs_build.ps1" "%ROOT%"
set "FB_EXIT=%ERRORLEVEL%"
if "%FB_EXIT%"=="0" exit /b 0

:EnsureFrontendBuild_RunNpm
call :ResolveNpmCmd
if errorlevel 1 (
  echo.
  echo [WARN] Frontend must be rebuilt but npm was not found.
  echo Install Node.js LTS from https://nodejs.org ^(check "Add to PATH"^) and re-run,
  echo or run manually: cd packages\browser ^&^& npm install ^&^& npm run build
  echo Continuing with existing browser build — UI may be outdated.
  exit /b 0
)

REM Ensure global Node wins over frontend\node_modules\.bin for child processes.
if exist "%ProgramFiles%\nodejs\" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%ProgramFiles(x86)%\nodejs\" set "PATH=%ProgramFiles(x86)%\nodejs;%PATH%"
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\nodejs\" set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [cim] Installing browser npm dependencies ^(first run may take a few minutes^)...
  pushd "%FRONTEND_DIR%"
  call "%NPM_CMD%" install
  if errorlevel 1 (
    popd
    echo [ERROR] npm install failed in browser package.
    exit /b 1
  )
  popd
)

echo [cim] Running npm run build in browser package...
pushd "%FRONTEND_DIR%"
call "%NPM_CMD%" run build
if errorlevel 1 (
  popd
  echo [ERROR] npm run build failed.
  exit /b 1
)
popd
echo [cim] Frontend production build OK.
exit /b 0

:FlowxSleep
REM Non-interactive sleep (timeout /t fails when stdin is redirected under cmd /c).
set "FXS_SEC=%~1"
if not defined FXS_SEC set "FXS_SEC=1"
powershell -NoProfile -Command "Start-Sleep -Seconds %FXS_SEC%"
exit /b 0
