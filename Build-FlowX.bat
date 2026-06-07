@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-FlowX.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Build failed with exit code %EXITCODE%.
  pause
  exit /b %EXITCODE%
)
echo.
pause
exit /b 0
