@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
echo.
echo FlowX license repair - this PC only
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\Repair-FlowXLicense.ps1" %*
echo.
pause
