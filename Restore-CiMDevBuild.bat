@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\Restore-CiMDevBuild.ps1" %*
if errorlevel 1 (
  echo.
  echo Restore failed.
  if not defined CIM_NO_PAUSE pause
  exit /b 1
)
if not defined CIM_NO_PAUSE pause
exit /b 0
