#Requires -Version 5.1
<#
.SYNOPSIS
  Spawn CiM live watchdog loop in background (idempotent).
#>
[CmdletBinding()]
param(
    [int]$IntervalMinutes = 5,
    [string]$WebRoot = "D:\CiM\Client"
)

$ErrorActionPreference = "Stop"
$WebRoot = [System.IO.Path]::GetFullPath($WebRoot.Trim().TrimEnd('\'))

$loopScript = Join-Path $WebRoot "scripts\Start-CiMLiveWatchdogLoop.ps1"
if (-not (Test-Path -LiteralPath $loopScript)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $loopScript = Join-Path $ScriptDir "Start-CiMLiveWatchdogLoop.ps1"
}
if (-not (Test-Path -LiteralPath $loopScript)) {
    throw "Missing Start-CiMLiveWatchdogLoop.ps1 under $WebRoot\scripts"
}

$pidFile = Join-Path $WebRoot "runtime\logs\live-watchdog.pid"

if (Test-Path -LiteralPath $pidFile) {
    $raw = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($raw -match '^\d+$') {
        try {
            $null = Get-Process -Id ([int]$raw) -ErrorAction Stop
            Write-Host "CiM live watchdog already running (PID $raw)." -ForegroundColor DarkGray
            exit 0
        } catch { }
    }
}

$workDir = Split-Path -Parent $loopScript
$argList = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $loopScript,
    '-IntervalMinutes', "$IntervalMinutes",
    '-WebRoot', $WebRoot
)

Start-Process -FilePath "powershell.exe" `
    -ArgumentList $argList `
    -WindowStyle Hidden `
    -WorkingDirectory $workDir | Out-Null

Start-Sleep -Seconds 5
if (Test-Path -LiteralPath $pidFile) {
    $newPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    Write-Host "CiM live watchdog started (PID $newPid)." -ForegroundColor Green
} else {
    Write-Host "CiM live watchdog spawn requested (check live-watchdog.log)." -ForegroundColor Yellow
}
exit 0
