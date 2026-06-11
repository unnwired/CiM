#Requires -Version 5.1
<#
.SYNOPSIS
  End-to-end: online-only installer (no install key) -> auth shell -> signup -> full app.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [string]$Version = "",
    [int]$Port = 8011,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind Plaintext

if (-not $Version) {
    $Version = if (Test-Path -LiteralPath $fx.VersionFile) {
        (Get-Content -LiteralPath $fx.VersionFile -Raw).Trim()
    } else { "1.0.3" }
}
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "CiM-OnlineE2E"
}

function Stop-E2EBackend {
    param([string]$Root, [int]$ListenPort)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and $_.CommandLine -like "*$ListenPort*" -and $_.CommandLine -like "*cim_bootstrap*"
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Wait-Health {
    param([int]$ListenPort, [string]$ExpectedMode, [int]$TimeoutSec = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$ListenPort/api/health" -TimeoutSec 5
            if ($r.status -eq "ok") {
                if (-not $ExpectedMode -or $r.mode -eq $ExpectedMode) { return $r }
            }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $null
}

function Start-E2EBackend {
    param([string]$Root, [int]$ListenPort)
    $py = Join-Path $Root "runtime\python\python.exe"
    $logDir = Join-Path $Root "runtime\logs"
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    $outLog = Join-Path $logDir "online-e2e.out.log"
    $errLog = Join-Path $logDir "online-e2e.err.log"
    Remove-Item Env:CIM_DEV -ErrorAction SilentlyContinue
    return Start-Process -FilePath $py `
        -ArgumentList @("-s", "-m", "uvicorn", "server.cim_bootstrap:app", "--host", "127.0.0.1", "--port", "$ListenPort") `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru `
        -WindowStyle Hidden
}

Write-Host "=== CiM online activation E2E ==="
Write-Host "Version: $Version"
Write-Host "Install: $InstallDir"
Write-Host ""

if (-not $SkipBuild) {
    Write-Host "[1/8] Full plaintext distribution build..."
    & (Join-Path $ScriptDir "build_distribution_full.ps1") -PlaintextExport -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "build_distribution_full.ps1 failed" }
} else {
    Write-Host "[1/8] SkipBuild - using existing export"
}

$setupExe = Join-Path $fx.SetupOutputDir "CiMSetup-$Version.exe"
if (-not (Test-Path -LiteralPath $setupExe)) {
    throw "Installer not found: $setupExe (run a full build first)"
}
Write-Host "      Installer present: $setupExe"

$onlineMarker = Join-Path $fx.ExportRoot "config\.cim-online-only"
if (-not (Test-Path -LiteralPath $onlineMarker)) {
    throw "Export missing config\.cim-online-only - run a distribution build first"
}

Write-Host "[2/8] Deploy license API..."
$apiDir = Join-Path $RepoRoot "license-api"
Push-Location $apiDir
try {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & npx wrangler deploy 2>&1 | ForEach-Object { Write-Host $_ }
    $deployExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($deployExit -ne 0) { throw "wrangler deploy failed (exit $deployExit)" }
} finally {
    Pop-Location
}

Write-Host "[3/8] Verify Worker API..."
& (Join-Path $ScriptDir "Verify-CiMOnlineLicense.ps1")
if ($LASTEXITCODE -ne 0) { throw "Verify-CiMOnlineLicense failed" }

if (Test-Path -LiteralPath $InstallDir) {
    Write-Host "[4/8] Removing prior install: $InstallDir"
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

Write-Host "[5/8] Deploy install tree (export mirror, same files as CiMSetup)..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
robocopy $fx.ExportRoot $InstallDir /MIR /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy export -> install failed (exit $LASTEXITCODE)" }

$licensePath = Join-Path $InstallDir "data\.cim-license"
if (Test-Path -LiteralPath $licensePath) {
    throw "Online-only install must not write data\.cim-license"
}
Write-Host "      OK: no offline license file"

Write-Host "[6/8] Auth shell on first launch..."
Stop-E2EBackend -Root $InstallDir -ListenPort $Port
$proc = Start-E2EBackend -Root $InstallDir -ListenPort $Port
try {
    $health = Wait-Health -ListenPort $Port -ExpectedMode "auth_only" -TimeoutSec 90
    if (-not $health) { throw "Expected auth_only health; backend did not start" }

    $index = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 15
    if ($index.Content -notmatch 'form-signin') {
        throw "GET / should show sign-in shell (missing form-signin)"
    }
    if ($index.Content -match 'id="root"') {
        throw "GET / should not show main React app before sign-in"
    }

    $status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/license/status" -TimeoutSec 15
    if ($status.valid) {
        throw "License status should be invalid before sign-in (mode=$($status.mode))"
    }

    $testEmail = "cim-e2e-{0}@example.com" -f ([Guid]::NewGuid().ToString("N").Substring(0, 10))
    $testPassword = "CiM-E2E-Test-Password-123!"
    Write-Host "      Signup: $testEmail"
    $signup = Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:$Port/api/auth/signup" `
        -ContentType "application/json" `
        -Body (@{ email = $testEmail; password = $testPassword } | ConvertTo-Json)
    if (-not $signup.recovery_codes) { throw "Signup missing recovery_codes" }

    $status2 = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/license/status" -TimeoutSec 15
    if ($status2.valid) {
        throw "Session must not be valid after signup (mode=$($status2.mode))"
    }

    Write-Host "      Login: $testEmail"
    Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:$Port/api/auth/login" `
        -ContentType "application/json" `
        -Body (@{ email = $testEmail; password = $testPassword } | ConvertTo-Json) | Out-Null

    $status3 = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/license/status" -TimeoutSec 15
    if (-not $status3.valid) {
        throw "Session should be valid after login (mode=$($status3.mode))"
    }

    Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:$Port/api/auth/complete" -TimeoutSec 15 | Out-Null
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-E2EBackend -Root $InstallDir -ListenPort $Port
}

Write-Host "[7/8] Full app after activation..."
$proc2 = Start-E2EBackend -Root $InstallDir -ListenPort $Port
try {
    $health2 = Wait-Health -ListenPort $Port -ExpectedMode $null -TimeoutSec 90
    if (-not $health2) { throw "Full app backend did not start" }
    if ($health2.mode -eq "auth_only") {
        throw "Backend still in auth_only after session saved"
    }

    $index2 = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 15
    if ($index2.Content -notmatch 'id="root"') {
        throw "Full app index missing React root"
    }

    $license = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/license/status" -TimeoutSec 15
    if (-not $license.valid -or $license.mode -ne "online") {
        throw "Expected valid online license (got mode=$($license.mode))"
    }

    $stocks = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/stocks?pageSize=10" -TimeoutSec 60
    if ([int]$stocks.total -lt 50) {
        throw "/api/stocks total too low: $($stocks.total)"
    }
}
finally {
    if ($proc2 -and -not $proc2.HasExited) {
        Stop-Process -Id $proc2.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-E2EBackend -Root $InstallDir -ListenPort $Port
}

Write-Host "[8/8] Device binding rejects second machine..."
$wrongDevice = "FFFF" + ("0" * 28)
try {
    Invoke-RestMethod -Method POST -Uri "https://chartsinmotion.chartsinmotion.workers.dev/auth/login" `
        -ContentType "application/json" `
        -Body (@{
            email       = $testEmail
            password    = $testPassword
            device_id   = $wrongDevice
            device_name = "WrongPC"
        } | ConvertTo-Json) | Out-Null
    throw "Login from wrong device_id should have failed"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 403) {
        throw "Expected 403 for wrong device, got: $_"
    }
    Write-Host "      OK: wrong device rejected (403)"
}

Write-Host ""
Write-Host "ONLINE ACTIVATION E2E PASS"
Write-Host "  Installer: no install key"
Write-Host "  First launch: auth shell"
Write-Host "  Signup: recovery only (no session)"
Write-Host "  Login: device bound + session"
Write-Host "  Second launch: full app + API"
Write-Host "  Anti-sharing: wrong device_id blocked"
exit 0
