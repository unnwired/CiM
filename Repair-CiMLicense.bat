@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
echo.
echo Charts In Motion license repair - this PC only
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\Repair-CiMLicense.ps1" %*
echo.
pause
