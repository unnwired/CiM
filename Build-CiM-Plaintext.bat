@echo off
setlocal
cd /d "%~dp0"
REM Plaintext distribution: readable server/*.py and frontend JS, with online sign-in gate.
REM Set license secret once in this window (same secret as encrypted Build-CiM.bat):
REM   set "CIM_LICENSE_SECRET=your-secret-here"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-CiM-Plaintext.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Plaintext build failed with exit code %EXITCODE%.
  pause
  exit /b %EXITCODE%
)
echo.
pause
exit /b 0
