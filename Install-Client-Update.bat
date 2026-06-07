@echo off
setlocal
REM Run this from the extracted FlowX-Update-* folder on the CLIENT PC (double-click).
for %%I in ("%~dp0.") do set "PKG=%%~fI"
echo.
echo FlowX client update - extract into FlowX\UPDATE\FlowX-Update-* then run this bat.
echo.
if exist "%PKG%\Install-Client-Update.ps1" (
  set "PS1=%PKG%\Install-Client-Update.ps1"
) else (
  set "PS1=%PKG%\scripts\Install-Client-Update.ps1"
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [FAILED] Exit code %EC%
)
echo.
pause
exit /b %EC%
