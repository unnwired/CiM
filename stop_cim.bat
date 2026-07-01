@echo off
setlocal

echo Stopping Charts In Motion processes...

REM Kill backend (uvicorn / run_uvicorn launcher) by matching command line
wmic process where "CommandLine like '%%run_uvicorn.py%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%uvicorn server.server:app%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%uvicorn server.cim_bootstrap:app%%'" call terminate >nul 2>&1

REM Kill React dev server started by react-scripts
wmic process where "CommandLine like '%%react-scripts start%%'" call terminate >nul 2>&1

REM Kill Electron desktop wrapper (legacy desktop\ and packages\desktop\ layouts)
wmic process where "CommandLine like '%%desktop\\main.js%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%desktop/main.js%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%packages\\desktop%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%packages/desktop%%'" call terminate >nul 2>&1

REM Fallback: if any node process still holds port 3000, terminate it
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>&1
)

REM Fallback: backend ports 8000 (app) and 8001 (showcase)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8001 ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>&1
)

echo Stop command completed.
exit /b 0
