@echo off
REM Shared path resolution for Charts In Motion .bat launchers (dev packages\ layout + export layout).
REM Usage: call "%ROOT%\scripts\Resolve-CiMPaths.bat" "%ROOT%"
REM Sets: CIM_ROOT, CIM_FRONTEND_DIR, CIM_DESKTOP_DIR, CIM_UVICORN_LAUNCHER,
REM       CIM_INSTALL_ROOT, CIM_SERVER_RELOAD_DIR, CIM_DEV_PACKAGES_LAYOUT

set "CIM_ROOT=%~1"
if "%CIM_ROOT:~-1%"=="\" set "CIM_ROOT=%CIM_ROOT:~0,-1%"

set "CIM_FRONTEND_DIR=%CIM_ROOT%\frontend"
if not exist "%CIM_FRONTEND_DIR%\package.json" if exist "%CIM_ROOT%\packages\browser\package.json" set "CIM_FRONTEND_DIR=%CIM_ROOT%\packages\browser"

set "CIM_DESKTOP_DIR=%CIM_ROOT%\desktop"
if not exist "%CIM_DESKTOP_DIR%\package.json" if exist "%CIM_ROOT%\packages\desktop\package.json" set "CIM_DESKTOP_DIR=%CIM_ROOT%\packages\desktop"
if exist "%CIM_DESKTOP_DIR%\desktop\package.json" if not exist "%CIM_DESKTOP_DIR%\package.json" set "CIM_DESKTOP_DIR=%CIM_DESKTOP_DIR%\desktop"

set "CIM_UVICORN_LAUNCHER=%CIM_ROOT%\runtime\run_uvicorn.py"

set "CIM_DEV_PACKAGES_LAYOUT=0"
if exist "%CIM_ROOT%\packages\server\server.py" if not exist "%CIM_ROOT%\server\server.py" set "CIM_DEV_PACKAGES_LAYOUT=1"

set "CIM_SERVER_RELOAD_DIR=%CIM_ROOT%\server"
if "%CIM_DEV_PACKAGES_LAYOUT%"=="1" set "CIM_SERVER_RELOAD_DIR=%CIM_ROOT%\packages\server"

set "CIM_INSTALL_ROOT="
if exist "%CIM_ROOT%\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=%CIM_ROOT%"
if not defined CIM_INSTALL_ROOT if exist "%CIM_ROOT%\start_cim.bat" if exist "%CIM_ROOT%\data\nse_data.db" (
  if exist "%CIM_ROOT%\packages\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=%CIM_ROOT%"
)
if not defined CIM_INSTALL_ROOT if exist "D:\CiM\Client_Test\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=D:\CiM\Client_Test"
if not defined CIM_INSTALL_ROOT if exist "D:\CiM\Client\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=D:\CiM\Client"

exit /b 0
