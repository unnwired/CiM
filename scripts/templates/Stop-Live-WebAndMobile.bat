@echo off
setlocal EnableExtensions
REM Stop CiM live watchdog, mobile (8011), then web (8001). Clears public Tailscale Funnel.
echo === CiM LIVE STOP: Watchdog + Mobile + Web ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CiM\Client\scripts\Stop-CiMLiveWatchdog.ps1" -WebRoot "D:\CiM\Client"
if errorlevel 1 (
  echo Watchdog stop reported an error.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CiM\Mobile_Main\Stop-MobileMain.ps1" -Root "D:\CiM\Mobile_Main"
if errorlevel 1 (
  echo Mobile live stop reported an error.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CiM\Client\scripts\Stop-CiMShowcaseTailscale.ps1" -InstallRoot "D:\CiM\Client"
if errorlevel 1 (
  echo Web live stop reported an error.
  pause
  exit /b 1
)

echo.
echo === LIVE STOPPED ===
echo Watchdog, mobile port 8011, and web port 8001 are down.
echo Public Tailscale Funnel cleared — client HTTPS links are offline until you run Start-Live-WebAndMobile.bat again.
echo.
pause
exit /b 0
