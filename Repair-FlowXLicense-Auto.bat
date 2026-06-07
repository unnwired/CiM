@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
echo.
echo FlowX license auto-repair (uses distribution profile on this PC)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\Repair-FlowXLicense.ps1" -AutoFix
echo.
pause
