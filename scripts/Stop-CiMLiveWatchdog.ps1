#Requires -Version 5.1
<#
.SYNOPSIS
  Stop the CiM live watchdog background loop.
#>
[CmdletBinding()]
param(
    [string]$WebRoot = "D:\CiM\Client"
)

$ErrorActionPreference = "Continue"
$WebRoot = [System.IO.Path]::GetFullPath($WebRoot.Trim().TrimEnd('\'))
$pidFile = Join-Path $WebRoot "runtime\logs\live-watchdog.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "Live watchdog not running (no pid file)." -ForegroundColor DarkGray
    exit 0
}

$raw = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
if ($raw -notmatch '^\d+$') {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Removed stale watchdog pid file." -ForegroundColor Yellow
    exit 0
}

$procId = [int]$raw
try {
    $p = Get-Process -Id $procId -ErrorAction Stop
    Stop-Process -Id $procId -Force -ErrorAction Stop
    Write-Host "Stopped CiM live watchdog (PID $procId)." -ForegroundColor Green
} catch {
    Write-Host "Watchdog PID $procId not found - already stopped." -ForegroundColor DarkGray
}

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
exit 0
