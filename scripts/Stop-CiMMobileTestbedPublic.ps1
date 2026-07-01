#Requires -Version 5.1
<#
.SYNOPSIS
  Stop mobile testbed proxy only (does NOT touch production Tailscale funnel).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($Root -match '\\scripts$') {
    $Root = Split-Path -Parent $Root
}
$Root = [System.IO.Path]::GetFullPath($Root)

$configPath = Join-Path $Root "mobile-host.json"
$port = 8010
if (Test-Path -LiteralPath $configPath) {
    $cfg = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($cfg.mobilePort) { $port = [int]$cfg.mobilePort }
}

$logDir = Join-Path $Root "runtime\logs"
$pidFile = Join-Path $logDir "mobile-proxy.pid"

if (Test-Path -LiteralPath $pidFile) {
    $procId = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($procId -gt 0) {
        Write-Host "Stopping mobile testbed proxy PID $procId..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

try {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $listeners) {
        $procId = $conn.OwningProcess
        if ($procId -gt 0) {
            Write-Host "Stopping listener on port $port (PID $procId)..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    $lines = netstat -ano | Select-String ":\s*$port\s+.*LISTENING"
    foreach ($line in $lines) {
        $parts = ($line -replace '\s+', ' ').ToString().Trim().Split(' ')
        $procId = [int]$parts[-1]
        if ($procId -gt 0) {
            taskkill /PID $procId /F 2>$null | Out-Null
        }
    }
}

Write-Host "Mobile testbed stopped (port $port)." -ForegroundColor Green
Write-Host 'Production Tailscale routes unchanged - web / and live mobile /mobile stay as-is.' -ForegroundColor DarkGray
