@echo off
setlocal EnableExtensions
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

call "%HERE%\scripts\Resolve-CiMPaths.bat" "%HERE%"
if not defined CIM_INSTALL_ROOT (
  if exist "D:\CiM\Client_Test\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=D:\CiM\Client_Test"
)
if not defined CIM_INSTALL_ROOT (
  if exist "D:\CiM\Client\server\cim_bootstrap.py" set "CIM_INSTALL_ROOT=D:\CiM\Client"
)
set "INSTALL=%CIM_INSTALL_ROOT%"

set "PS1=%HERE%\scripts\Stop-CiMShowcaseTailscale.ps1"
if not exist "%PS1%" set "PS1=%INSTALL%\scripts\Stop-CiMShowcaseTailscale.ps1"
if not exist "%PS1%" (
  echo Missing scripts\Stop-CiMShowcaseTailscale.ps1
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -InstallRoot "%INSTALL%"
pause
exit /b 0
