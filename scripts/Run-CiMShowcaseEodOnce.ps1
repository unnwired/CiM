#Requires -Version 5.1
<#
.SYNOPSIS
  Run one showcase EOD bhavcopy reconcile (retries until success or IST deadline).

.DESCRIPTION
  Intended for Windows Task Scheduler (daily ~16:00 IST). Waits until the IST window opens,
  then retries every PollMinutes until NSE bhavcopy reconcile succeeds or DeadlineIst passes.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [int]$WindowStartHourIst = 16,
    [int]$WindowStartMinuteIst = 0,
    [int]$WindowEndHourIst = 16,
    [int]$WindowEndMinuteIst = 30,
    [int]$PollMinutes = 5
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMShowcaseDeployConfig.ps1")

function Resolve-CiMInstallRoot {
    param([string]$Path)
    $normalized = $Path.Trim().Trim('"').TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($normalized)) { throw "InstallRoot is empty" }
    return [System.IO.Path]::GetFullPath($normalized)
}

function Get-IstNow {
    return [DateTime]::UtcNow.AddHours(5.5)
}

function Write-EodLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    Write-Host $line
    if ($script:LogFile) {
        Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8
    }
}

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $cfg = Get-CiMShowcaseDeployConfig -RepoRoot (Split-Path -Parent $ScriptDir)
    $InstallRoot = $cfg.showcaseLiveInstallRoot
}
$InstallRoot = Resolve-CiMInstallRoot $InstallRoot

$logDir = Join-Path $InstallRoot "runtime\logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
$script:LogFile = Join-Path $logDir "showcase-eod-scheduled.log"

$py = Join-Path $InstallRoot "runtime\python\python.exe"
$hostMarker = Join-Path $InstallRoot "config\.cim-showcase-host"

if (-not (Test-Path -LiteralPath $py)) {
    Write-EodLog "FAIL missing embedded Python: $py"
    exit 1
}
if (-not (Test-Path -LiteralPath $hostMarker)) {
    Write-EodLog "FAIL missing showcase host marker: $hostMarker (run Start-CiMShowcase.ps1 on host first)"
    exit 1
}

$runner = @"
import sys
from pathlib import Path
root = Path(r'$($InstallRoot.Replace("'", "''"))')
sys.path.insert(0, str(root))
from server import eod_reconcile, market_data_version
db = root / 'data' / 'nse_data.db'
bars = eod_reconcile.run_eod_bhavcopy_reconcile(db, log_fn=print)
st = eod_reconcile.last_reconcile_status()
ver = market_data_version.get_version(db)
print({'bars': bars, 'reconcile': st, 'market_data_version': ver})
if not st.get('ok'):
    sys.exit(1)
sys.exit(0)
"@

function Invoke-EodReconcile {
    & $py -s -c $runner
    if ($LASTEXITCODE -ne 0) {
        throw "EOD reconcile failed (exit $LASTEXITCODE)"
    }
}

$ist = Get-IstNow
$today = $ist.ToString('yyyy-MM-dd')
$windowStart = Get-Date -Year $ist.Year -Month $ist.Month -Day $ist.Day -Hour $WindowStartHourIst -Minute $WindowStartMinuteIst -Second 0
$windowEnd = Get-Date -Year $ist.Year -Month $ist.Month -Day $ist.Day -Hour $WindowEndHourIst -Minute $WindowEndMinuteIst -Second 59

Write-EodLog "=== Showcase EOD run ($today) root=$InstallRoot window=$WindowStartHourIst`:$('{0:D2}' -f $WindowStartMinuteIst)-$WindowEndHourIst`:$('{0:D2}' -f $WindowEndMinuteIst) IST ==="

while ((Get-IstNow) -lt $windowStart) {
    $waitSec = [Math]::Min(300, [Math]::Max(15, ($windowStart - (Get-IstNow)).TotalSeconds))
    Write-EodLog "Waiting for EOD window (IST now $(Get-IstNow -Format 'HH:mm'))..."
    Start-Sleep -Seconds $waitSec
}

$attempt = 0
while ($true) {
    $nowIst = Get-IstNow
    if ($nowIst -gt $windowEnd) {
        Write-EodLog "FAIL deadline passed ($WindowEndHourIst`:$('{0:D2}' -f $WindowEndMinuteIst) IST) after $attempt attempt(s)"
        exit 1
    }
    $attempt++
    try {
        Write-EodLog "Attempt $attempt at $(Get-IstNow -Format 'HH:mm') IST"
        Invoke-EodReconcile
        Write-EodLog "OK EOD reconcile finished for $today (attempt $attempt)"
        exit 0
    } catch {
        Write-EodLog "WARN attempt $attempt: $($_.Exception.Message)"
        if ((Get-IstNow).AddMinutes($PollMinutes) -gt $windowEnd) {
            Write-EodLog "FAIL no time left for another retry before deadline"
            exit 1
        }
        Start-Sleep -Seconds ([Math]::Max(60, $PollMinutes * 60))
    }
}
