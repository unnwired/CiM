@echo off
REM Launch Charts In Motion with the online sign-in / sign-up screen (dev repo testing).
setlocal
set "CIM_REQUIRE_ONLINE_AUTH=1"
call "%~dp0start_cim.bat" %*
