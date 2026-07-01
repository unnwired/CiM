@echo off
setlocal EnableExtensions
REM Start CiM live web (8001) then mobile (8011) then background watchdog. Prints public HTTPS links.
echo === CiM LIVE: Web + Mobile + Watchdog ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CiM\Client\scripts\Start-CiMShowcaseTailscale.ps1" -InstallRoot "D:\CiM\Client"
if errorlevel 1 (
  echo Web live failed. See D:\CiM\Client\runtime\logs
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CiM\Mobile_Main\Start-MobileMain.ps1"
if errorlevel 1 (
  echo Mobile live failed. See D:\CiM\Mobile_Main\runtime\logs
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CiM\Client\scripts\Start-CiMLiveWatchdog.ps1" -WebRoot "D:\CiM\Client"
if errorlevel 1 (
  echo Watchdog failed to start. See D:\CiM\Client\runtime\logs\live-watchdog.log
  pause
  exit /b 1
)

echo.
echo === LIVE CLIENT LINKS (share with users) ===
echo Web:    https://charts-in-motion.tail22251c.ts.net/
echo Mobile: https://charts-in-motion.tail22251c.ts.net/mobile/
echo.
echo === LIVE ADMIN LINKS (host PC only - not public HTTPS) ===
echo Web operator: http://127.0.0.1:8001/?operator=1
echo Admin bat:    D:\CiM\Client\Admin-Showcase.bat
echo Mobile local: http://127.0.0.1:8011/mobile/
echo Watchdog log: D:\CiM\Client\runtime\logs\live-watchdog.log
echo.
pause
exit /b 0
