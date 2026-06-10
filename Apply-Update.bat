@echo off
setlocal EnableExtensions
REM Run from Charts In Motion install root. Paths with spaces are handled inside Apply-LocalUpdate-Entry.ps1.
for %%I in ("%~dp0.") do set "LAUNCHER=%%~fI"
powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%\scripts\Apply-LocalUpdate-Entry.ps1" -LauncherDir "%LAUNCHER%"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] Update failed. Exit code %EC%
  if exist "%LAUNCHER%\runtime\logs\update-apply.log" (
    echo See: %LAUNCHER%\runtime\logs\update-apply.log
    type "%LAUNCHER%\runtime\logs\update-apply.log"
  )
)
echo.
pause
exit /b %EC%
