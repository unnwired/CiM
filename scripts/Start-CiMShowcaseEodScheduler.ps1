#Requires -Version 5.1
<#
.SYNOPSIS
  Host-only EOD scheduler for CiM web showcase — runs bhavcopy reconcile ~16:00 IST on session days.

.DESCRIPTION
  Requires config\.cim-showcase-host on the install root (set by Start-CiMShowcase.ps1).
  Retries reconcile until NSE bhavcopy is available (same logic as eod_reconcile module).
  Schedule via Windows Task Scheduler or run in a persistent PowerShell session alongside showcase.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [int]$TargetHourIst = 16,
    [int]$TargetMinuteIst = 0,
    [int]$PollMinutes = 5,
    [int]$MaxAttemptsPerDay = 36
)

$ErrorActionPreference = "Stop"

function Resolve-CiMInstallRoot {
    param([string]$Path)
    $normalized = $Path.Trim().Trim('"').TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($normalized)) { throw "InstallRoot is empty" }
    return [System.IO.Path]::GetFullPath($normalized)
}

$InstallRoot = Resolve-CiMInstallRoot $InstallRoot
$py = Join-Path $InstallRoot "runtime\python\python.exe"
$hostMarker = Join-Path $InstallRoot "config\.cim-showcase-host"

if (-not (Test-Path -LiteralPath $py)) {
    throw "Missing embedded Python: $py"
}
if (-not (Test-Path -LiteralPath $hostMarker)) {
    throw "Missing showcase host marker: $hostMarker (run Start-CiMShowcase.ps1 on the host PC only)"
}

$runner = @"
import sys
from pathlib import Path
root = Path(r'$InstallRoot')
sys.path.insert(0, str(root))
from server import eod_reconcile, market_data_version
db = root / 'data' / 'nse_data.db'
bars = eod_reconcile.run_eod_bhavcopy_reconcile(db, log_fn=print)
st = eod_reconcile.last_reconcile_status()
ver = market_data_version.get_version(db)
print({'bars': bars, 'reconcile': st, 'market_data_version': ver})
"@

function Get-IstNow {
    $utc = [DateTime]::UtcNow
    return $utc.AddHours(5.5)
}

function Invoke-EodReconcile {
    & $py -s -c $runner
    if ($LASTEXITCODE -ne 0) { throw "EOD reconcile script failed ($LASTEXITCODE)" }
}

Write-Host "CiM showcase EOD scheduler (root: $InstallRoot)" -ForegroundColor Cyan
Write-Host "Target: ${TargetHourIst}:$('{0:D2}' -f $TargetMinuteIst) IST, poll every $PollMinutes min" -ForegroundColor Cyan

$lastRunDate = ""

while ($true) {
    $ist = Get-IstNow
    $today = $ist.ToString('yyyy-MM-dd')
    $target = Get-Date -Year $ist.Year -Month $ist.Month -Day $ist.Day -Hour $TargetHourIst -Minute $TargetMinuteIst -Second 0

    if ($ist -ge $target -and $lastRunDate -ne $today) {
        Write-Host "[$(Get-Date -Format o)] Starting EOD reconcile for $today" -ForegroundColor Yellow
        $attempt = 0
        $done = $false
        while ($attempt -lt $MaxAttemptsPerDay -and -not $done) {
            $attempt++
            try {
                Invoke-EodReconcile
                $done = $true
                $lastRunDate = $today
                Write-Host "[OK] EOD reconcile finished for $today (attempt $attempt)" -ForegroundColor Green
            } catch {
                Write-Host "[WARN] attempt $attempt failed: $($_.Exception.Message)" -ForegroundColor DarkYellow
                Start-Sleep -Seconds ([Math]::Max(60, $PollMinutes * 60))
            }
        }
        if (-not $done) {
            Write-Host "[FAIL] EOD reconcile did not succeed for $today after $MaxAttemptsPerDay attempts" -ForegroundColor Red
            $lastRunDate = $today
        }
    }

    Start-Sleep -Seconds ([Math]::Max(60, $PollMinutes * 60))
}
