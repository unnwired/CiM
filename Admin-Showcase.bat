@echo off
setlocal EnableExtensions
REM One-click host operator entry: start showcase (if needed) and open operator sign-in.
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "RESOLVER=%HERE%\scripts\Resolve-CiMPaths.bat"
if exist "%RESOLVER%" (
  call "%RESOLVER%" "%HERE%"
) else (
  if exist "%HERE%\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=%HERE%"
  if not defined CIM_INSTALL_ROOT if exist "%HERE%\data\nse_data.db" if exist "%HERE%\packages\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=%HERE%"
  if not defined CIM_INSTALL_ROOT if exist "D:\CiM\Client_Test\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=D:\CiM\Client_Test"
  if not defined CIM_INSTALL_ROOT if exist "D:\CiM\Client\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=D:\CiM\Client"
)
if not defined CIM_INSTALL_ROOT (
  echo Could not find CiM install. Run from the repo root, D:\CiM\Client_Test, D:\CiM\Client, or deploy showcase first.
  echo Missing scripts\Resolve-CiMPaths.bat - re-run showcase deploy from Build Launcher.
  pause
  exit /b 1
)
set "INSTALL=%CIM_INSTALL_ROOT%"

set "PS1=%HERE%\scripts\Open-CiMShowcaseOperator.ps1"
if not exist "%PS1%" set "PS1=%INSTALL%\scripts\Open-CiMShowcaseOperator.ps1"
if not exist "%PS1%" (
  echo Missing scripts\Open-CiMShowcaseOperator.ps1 under %INSTALL%
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -InstallRoot "%INSTALL%"
if errorlevel 1 (
  echo Showcase failed to start. See runtime\logs under %INSTALL%
  pause
  exit /b 1
)
exit /b 0
