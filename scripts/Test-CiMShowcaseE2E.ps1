#Requires -Version 5.1
<#
.SYNOPSIS
  End-to-end showcase test using an isolated temp tree (never pollutes D:\CiM\Client).
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\CiM\Client",
    [string]$InstallRoot = "",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$SourceRoot = $SourceRoot.Trim().Trim('"').TrimEnd('\')
$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)

$tempRoot = $InstallRoot
$createdTemp = $false
$touchedProduction = $false
if ([string]::IsNullOrWhiteSpace($tempRoot)) {
    $tempRoot = Join-Path $env:TEMP ("CiM-Showcase-E2E-{0}" -f [Guid]::NewGuid().ToString("N"))
    $createdTemp = $true
} else {
    $tempRoot = [System.IO.Path]::GetFullPath($tempRoot.Trim().Trim('"').TrimEnd('\'))
    if ($tempRoot -ieq $SourceRoot) {
        throw "Do not run E2E against production Client folder. Omit -InstallRoot to use a temp tree."
    }
}

$base = "http://127.0.0.1:$Port"

function Wait-Health {
    param([int]$TimeoutSec = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 5
            if ($r.status -eq 'ok') { return $r }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw "Backend not healthy on $base within ${TimeoutSec}s"
}

function Cleanup {
    & (Join-Path $ScriptDir "Stop-CiMShowcase.ps1") -InstallRoot $tempRoot -Port $Port -ErrorAction SilentlyContinue
    if ($createdTemp -and (Test-Path -LiteralPath $tempRoot)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($touchedProduction) {
        & (Join-Path $ScriptDir "Reset-CiMShowcaseClient.ps1") -InstallRoot $SourceRoot -Port $Port -SkipRestart
    }
}

try {
    if ($createdTemp) {
        if (-not (Test-Path -LiteralPath $SourceRoot)) {
            throw "SourceRoot not found: $SourceRoot (export client first)"
        }
        Write-Host "Copying showcase tree to $tempRoot"
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
        robocopy $SourceRoot $tempRoot /MIR /NFL /NDL /NJH /NJS /nc /ns /np /XD runtime\logs | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
    }

    Write-Host "=== CiM Showcase E2E ($tempRoot :$Port) ===" -ForegroundColor Cyan

    & (Join-Path $ScriptDir "Start-CiMShowcase.ps1") -InstallRoot $tempRoot -Port $Port
    if ($LASTEXITCODE -ne 0) { throw "Start-CiMShowcase.ps1 failed" }

    $h = Wait-Health
    Write-Host "[OK] health: $($h | ConvertTo-Json -Compress)"

    $signIn = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 15 -SessionVariable web
    if ($signIn.Content -notmatch 'Sign in') {
        throw "Expected auth sign-in page at /"
    }
    Write-Host "[OK] auth sign-in page at /"

    $testEmail = "cim-e2e-{0}@example.com" -f ([Guid]::NewGuid().ToString("N").Substring(0, 10))
    $testPassword = "CiM-E2E-Password-123!"
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/signup" -ContentType "application/json" `
        -Body (@{ email = $testEmail; password = $testPassword } | ConvertTo-Json) -WebSession $web | Out-Null
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/login" -ContentType "application/json" `
        -Body (@{ email = $testEmail; password = $testPassword } | ConvertTo-Json) -WebSession $web | Out-Null
    $st = Invoke-RestMethod -Uri "$base/api/license/status" -TimeoutSec 15 -WebSession $web
    if (-not $st.valid) { throw "Login failed: license not valid (mode=$($st.mode))" }
    if ($st.host_mode -ne 'web') { throw "Expected host_mode=web, got $($st.host_mode)" }
    Write-Host "[OK] cookie login -> license valid (email=$testEmail)"

    Invoke-RestMethod -Method POST -Uri "$base/api/auth/complete" -TimeoutSec 15 -WebSession $web | Out-Null
    $idx = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 15 -WebSession $web
    if ($idx.Content -notmatch 'id="root"') {
        throw "Full React app did not load after auth complete"
    }
    Write-Host "[OK] full React app shell (id=root) at /"

    $stocks = Invoke-RestMethod -Uri "$base/api/stocks?pageSize=100" -TimeoutSec 60 -WebSession $web
    if ([int]$stocks.total -lt 100) { throw "/api/stocks total too low: $($stocks.total)" }
    Write-Host "[OK] /api/stocks total=$($stocks.total)"

    if ($st.is_showcase_host -ne $true) {
        throw "Expected is_showcase_host=true on host install, got $($st.is_showcase_host)"
    }
    Write-Host "[OK] license status is_showcase_host=true"

    $mdv = Invoke-RestMethod -Uri "$base/api/market-data-version" -TimeoutSec 15 -WebSession $web
    if ($null -eq $mdv.status) { throw "market-data-version missing status" }
    Write-Host "[OK] /api/market-data-version status=$($mdv.status)"

    try {
        Invoke-RestMethod -Method POST -Uri "$base/api/admin/fetch-ohlcv" -TimeoutSec 15 -WebSession $web | Out-Null
        Write-Host "[OK] host POST /api/admin/fetch-ohlcv allowed"
    } catch {
        throw "Host admin fetch-ohlcv should succeed: $($_.Exception.Message)"
    }

    $hostMarker = Join-Path $tempRoot "config\.cim-showcase-host"
    if (Test-Path -LiteralPath $hostMarker) {
        Remove-Item -LiteralPath $hostMarker -Force
        try {
            Invoke-RestMethod -Method POST -Uri "$base/api/admin/fetch-ohlcv" -TimeoutSec 15 -WebSession $web | Out-Null
            throw "Expected 403 on admin when showcase host marker removed"
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -ne 403) {
                throw "Expected HTTP 403 for non-host admin, got: $($_.Exception.Message)"
            }
            Write-Host "[OK] non-host POST /api/admin/fetch-ohlcv -> 403"
        }
        "" | Set-Content -LiteralPath $hostMarker -Encoding UTF8
    }

    Invoke-RestMethod -Method POST -Uri "$base/api/auth/logout" -WebSession $web | Out-Null
    $signInAgain = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 15 -WebSession $web
    if ($signInAgain.Content -notmatch 'Sign in') {
        throw "Expected Sign in page after logout"
    }
    Write-Host "[OK] logout returns Sign in page"

    Write-Host ""
    Write-Host "SHOWCASE E2E PASS" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "SHOWCASE E2E FAIL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Cleanup
}
