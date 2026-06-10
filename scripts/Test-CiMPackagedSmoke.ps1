#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke-test a packaged Charts In Motion tree: backend starts, JS bundle is real JS, API returns data.

  Catches the blank-Electron defect: /static/js/main.*.js must not return index.html.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InstallRoot,
    [int]$StartupTimeoutSec = 120,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")

function Stop-SmokeBackend {
    param([string]$Root, [int]$ListenPort)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*$ListenPort*" -and
            $_.CommandLine -like "*cim_bootstrap*"
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    $pidFile = Join-Path $Root "runtime\logs\backend.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($oldPid -match '^\d+$') {
            Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
}

function Ensure-TestLicense {
    param([string]$Root)
    $licensePath = Join-Path $Root "data\.cim-license"
    if (Test-Path -LiteralPath $licensePath) { return }
    $py = Join-Path $Root "runtime\python\python.exe"
    if (-not (Test-Path -LiteralPath $py)) { throw "Missing embedded Python: $py" }
    $repoRoot = Split-Path -Parent $ScriptDir
    $secret = Get-CiMVendorSecret -RepoRoot $repoRoot
    if (-not $secret) { throw "Missing config\.build_license_secret for smoke test license" }
    $repoEsc = $repoRoot.Replace("'", "''")
    $rootEsc = $Root.Replace("'", "''")
    $secretEsc = $secret.Replace("'", "''")
    & $py -s -c @"
import sys
sys.path.insert(0, r'$repoEsc')
from pathlib import Path
from server.app_code_crypto import current_machine_code, install_key_for_machine, validate_install_key
root = Path(r'$rootEsc')
mc = current_machine_code()
key = install_key_for_machine(mc, secret=r'$secretEsc'.encode('utf-8'))
assert validate_install_key(mc, key, base_dir=root)
(root / 'data').mkdir(parents=True, exist_ok=True)
(root / 'data' / '.cim-license').write_text(
    '# smoke test license\nMachineCode=' + mc + '\nInstallKey=' + key + '\n',
    encoding='utf-8',
)
"@ | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $licensePath)) {
        throw "Could not write test license under $Root"
    }
}

function Wait-Health {
    param([int]$ListenPort, [int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ListenPort/api/health" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Clear-AppCacheForInstall {
    param([string]$Root)
    $verFile = Join-Path $Root "version.txt"
    $ver = "0.0.0"
    if (Test-Path -LiteralPath $verFile) {
        $ver = (Get-Content -LiteralPath $verFile -Raw -ErrorAction Stop).Trim()
    }
    if (-not $ver) { $ver = "0.0.0" }
    $safeVer = ($ver -replace '[^\w\.\-_]', '_')
    $cacheBase = Join-Path $env:LOCALAPPDATA "CiM\app-cache"
    foreach ($name in @($safeVer, "0.0.0")) {
        $cacheRoot = Join-Path $cacheBase $name
        if (Test-Path -LiteralPath $cacheRoot) {
            Remove-Item -LiteralPath $cacheRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$root = (Resolve-Path -LiteralPath $InstallRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $root "server\cim_bootstrap.py"))) {
    throw "Not a Charts In Motion install/export root: $root"
}
if (-not (Test-Path -LiteralPath (Join-Path $root "data\nse_data.db"))) {
    throw "Missing data\nse_data.db under $root"
}

$licensePath = Join-Path $root "data\.cim-license"
$hadLicenseBefore = Test-Path -LiteralPath $licensePath
Ensure-TestLicense -Root $root
Clear-AppCacheForInstall -Root $root
Stop-SmokeBackend -Root $root -ListenPort $Port

$py = Join-Path $root "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { throw "Missing embedded Python: $py" }

$logDir = Join-Path $root "runtime\logs"
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$outLog = Join-Path $logDir "release-gate-smoke.log"
$errLog = Join-Path $logDir "release-gate-smoke.err.log"
Remove-Item -LiteralPath $outLog, $errLog -ErrorAction SilentlyContinue

# Packaged smoke must exercise the distribution decrypt path even when CIM_DEV=1
# is set in the user profile (common after Restore-CiMDevBuild.ps1).
$savedFlowxDev = $env:CIM_DEV
Remove-Item Env:CIM_DEV -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath $py `
    -ArgumentList @("-s", "-m", "uvicorn", "server.cim_bootstrap:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $root `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru `
    -WindowStyle Hidden

try {
    if (-not (Wait-Health -ListenPort $Port -TimeoutSec $StartupTimeoutSec)) {
        if (Test-Path -LiteralPath $errLog) {
            Write-Host "--- release-gate-smoke.err.log (tail) ---"
            Get-Content -LiteralPath $errLog -Tail 40 | ForEach-Object { Write-Host $_ }
        }
        throw "Backend did not become healthy within ${StartupTimeoutSec}s"
    }

    $index = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 15
    if ($index.Content -notmatch 'id="root"') {
        throw "GET / missing React root (got $($index.Content.Length) bytes)"
    }
    if ($index.Content -match '<title>FlowX</title>') {
        throw "index.html still branded FlowX; rebuild frontend and re-encrypt export"
    }
    if ($index.Content -notmatch 'Charts In Motion') {
        throw "index.html missing Charts In Motion title"
    }

    $html = $index.Content
    if ($html -match 'src="(/static/js/[^"]+\.js)"') {
        $jsPath = $Matches[1]
    } else {
        throw "Could not find main JS script path in index.html"
    }

    $js = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$jsPath" -UseBasicParsing -TimeoutSec 30
    $jsBody = $js.Content
    if ($jsBody -match '^\s*<!DOCTYPE' -or $jsBody -match '^\s*<html') {
        throw "BLANK SHELL BUG: $jsPath returned HTML instead of JavaScript (length $($jsBody.Length))"
    }
    if ($jsBody.Length -lt 5000) {
        throw "JS bundle suspiciously small ($($jsBody.Length) bytes) at $jsPath"
    }

    $stocks = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/stocks?pageSize=500" -UseBasicParsing -TimeoutSec 60
    $stockJson = $stocks.Content | ConvertFrom-Json
    $total = [int]$stockJson.total
    $pageRows = @($stockJson.data).Count
    if ($total -lt 100) {
        throw "/api/stocks total=$total (expected hundreds+; DB may be empty or broken)"
    }
    if ($pageRows -lt 50) {
        throw "/api/stocks page returned only $pageRows rows (expected pageSize batch)"
    }

    $chart = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/chart-data/RELIANCE?timeframe=1D" -UseBasicParsing -TimeoutSec 60
    if ($chart.StatusCode -lt 200 -or $chart.StatusCode -ge 300) {
        throw "/api/chart-data/RELIANCE returned $($chart.StatusCode)"
    }
    if ($chart.Content.Length -lt 1000) {
        throw "/api/chart-data/RELIANCE body too small ($($chart.Content.Length) bytes)"
    }

    Write-Host "PACKAGED SMOKE PASS"
    Write-Host "  health     : OK"
    Write-Host "  index.html : OK (root div present)"
    Write-Host "  $jsPath : OK ($($jsBody.Length) bytes, JavaScript)"
    Write-Host "  /api/stocks: OK (total=$total, page=$pageRows)"
    Write-Host "  /api/chart-data/RELIANCE: OK ($($chart.Content.Length) bytes)"
    exit 0
}
finally {
    if ($null -ne $savedFlowxDev) {
        $env:CIM_DEV = $savedFlowxDev
    } else {
        Remove-Item Env:CIM_DEV -ErrorAction SilentlyContinue
    }
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-SmokeBackend -Root $root -ListenPort $Port
    if (-not $hadLicenseBefore -and (Test-Path -LiteralPath $licensePath)) {
        Remove-Item -LiteralPath $licensePath -Force -ErrorAction SilentlyContinue
    }
}
