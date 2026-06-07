@echo off
setlocal

REM Resolve paths
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "TARGET=%ROOT%\start_flowx.bat"
set "ICON=%SystemRoot%\System32\SHELL32.dll,220"

if not exist "%TARGET%" (
  echo [ERROR] start_flowx.bat was not found in:
  echo         "%ROOT%"
  pause
  exit /b 1
)

set "PS_SCRIPT=%TEMP%\nse_pulse_shortcut_%RANDOM%.ps1"

(
  echo $desktop = [Environment]::GetFolderPath('Desktop'^)
  echo $shortcutPath = Join-Path $desktop 'FlowX.lnk'
  echo $targetPath = '%TARGET:\=\\%'
  echo $workingDir = '%ROOT:\=\\%'
  echo $iconLoc = '%ICON%'
  echo $shell = New-Object -ComObject WScript.Shell
  echo $shortcut = $shell.CreateShortcut($shortcutPath^)
  echo $shortcut.TargetPath = $targetPath
  echo $shortcut.WorkingDirectory = $workingDir
  echo $shortcut.IconLocation = $iconLoc
  echo $shortcut.WindowStyle = 1
  echo $shortcut.Description = 'Launch FlowX (bootstrap + start^)'
  echo $shortcut.Save(^)
) > "%PS_SCRIPT%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set "ERR=%ERRORLEVEL%"
del "%PS_SCRIPT%" >nul 2>&1

if not "%ERR%"=="0" (
  echo [ERROR] Could not create desktop shortcut.
  echo Try running this file as Administrator.
  pause
  exit /b 1
)

echo Desktop shortcut created: "FlowX"
echo Double-click it to launch the app.
exit /b 0

