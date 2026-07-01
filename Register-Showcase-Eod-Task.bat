@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\Register-CiMShowcaseEodTask.ps1" %*
if errorlevel 1 (
  echo Registration failed.
  pause
  exit /b 1
)
echo.
echo Done. Task runs daily ~4:00 PM IST (retries until ~4:30 PM).
pause
exit /b 0
