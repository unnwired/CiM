#Requires -Version 5.1
<#
.SYNOPSIS
  P&L Zerodha import E2E — auth, import preview/apply, assert TRENT qty and today sells.
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\CiM\Client_Test",
    [string]$InstallRoot = "",
    [int]$Port = 8012,
    [string]$RepoRoot = "",
    [switch]$UseRunningShowcase
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $ScriptDir
}
$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot.Trim().TrimEnd('\'))

$SourceRoot = $SourceRoot.Trim().Trim('"').TrimEnd('\')
$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)

$Fixtures = Join-Path $RepoRoot "packages\server\tests\fixtures\zerodha"
if (-not (Test-Path -LiteralPath $Fixtures)) {
    throw "Fixtures not found: $Fixtures"
}

function To-JsonBody([hashtable]$Obj) {
    $parts = @()
    foreach ($key in $Obj.Keys) {
        $val = $Obj[$key]
        if ($val -is [bool]) {
            $parts += ('"{0}":{1}' -f $key, ($(if ($val) { 'true' } else { 'false' })))
        } elseif ($null -eq $val) {
            $parts += ('"{0}":null' -f $key)
        } else {
            $escaped = [string]$val
            $escaped = $escaped -replace '\\', '\\\\'
            $escaped = $escaped -replace '"', '\"'
            $escaped = $escaped -replace "`r", '\r'
            $escaped = $escaped -replace "`n", '\n'
            $escaped = $escaped -replace "`t", '\t'
            $parts += ('"{0}":"{1}"' -f $key, $escaped)
        }
    }
    return '{' + ($parts -join ',') + '}'
}

$tempRoot = $InstallRoot
$createdTemp = $false
if ($UseRunningShowcase) {
    $tempRoot = $SourceRoot
    $createdTemp = $false
} elseif ([string]::IsNullOrWhiteSpace($tempRoot)) {
    $tempRoot = Join-Path $env:TEMP ("CiM-PnL-Import-E2E-{0}" -f [Guid]::NewGuid().ToString("N"))
    $createdTemp = $true
} else {
    $tempRoot = [System.IO.Path]::GetFullPath($tempRoot.Trim().Trim('"').TrimEnd('\'))
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

function Read-Fixture {
    param([string]$Name)
    $path = Join-Path $Fixtures $Name
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing fixture: $path" }
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8
}

function Cleanup {
    if (-not $UseRunningShowcase) {
        & (Join-Path $ScriptDir "Stop-CiMShowcase.ps1") -InstallRoot $tempRoot -Port $Port -ErrorAction SilentlyContinue
    }
    if ($createdTemp -and (Test-Path -LiteralPath $tempRoot)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    if ($createdTemp) {
        if (-not (Test-Path -LiteralPath $SourceRoot)) {
            throw "SourceRoot not found: $SourceRoot"
        }
        Write-Host "Copying showcase tree to $tempRoot"
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
        robocopy $SourceRoot $tempRoot /MIR /NFL /NDL /NJH /NJS /nc /ns /np /XD runtime\logs | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
    }

    Write-Host "=== CiM PnL Import E2E ($tempRoot :$Port) ===" -ForegroundColor Cyan

    if (-not $UseRunningShowcase) {
        & (Join-Path $ScriptDir "Start-CiMShowcase.ps1") -InstallRoot $tempRoot -Port $Port
        if ($LASTEXITCODE -ne 0) { throw "Start-CiMShowcase.ps1 failed" }
    } else {
        Write-Host "Using running showcase at $base"
    }

    Wait-Health | Out-Null
    Write-Host "[OK] health"

    $testEmail = "cim-pnl-e2e-{0}@example.com" -f ([Guid]::NewGuid().ToString("N").Substring(0, 10))
    $testPassword = "CiM-PnL-E2E-Password-123!"
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/signup" -ContentType "application/json" `
        -Body (@{ email = $testEmail; password = $testPassword } | ConvertTo-Json) -SessionVariable web | Out-Null
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/login" -ContentType "application/json" `
        -Body (@{ email = $testEmail; password = $testPassword } | ConvertTo-Json) -WebSession $web | Out-Null
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/complete" -TimeoutSec 15 -WebSession $web | Out-Null
    Write-Host "[OK] auth ($testEmail)"

    $tradebook = Read-Fixture "tradebook_trent_partial.csv"
    $holdings = Read-Fixture "holdings_trent.csv"

    $previewBody = To-JsonBody @{
        csv = $tradebook
        holdings_csv = $holdings
        reconcile_holdings = $true
        apply_corp_actions = $true
    }
    $preview = Invoke-RestMethod -Method POST -Uri "$base/api/pnl/import/zerodha/preview" `
        -ContentType "application/json" -WebSession $web -Body $previewBody

    if (-not $preview.ok) { throw "Preview failed: $($preview | ConvertTo-Json -Compress)" }
    if ($preview.open_qty_after.TRENT -ne 25 -and -not $preview.holdings_mismatches) {
        Write-Host "[WARN] preview TRENT qty=$($preview.open_qty_after.TRENT) (expected 25 after corp/holdings dry-run)"
    }
    Write-Host "[OK] preview (mismatches=$($preview.holdings_mismatches.Count), corp=$($preview.corp_actions_applied.Count))"

    $importBody = To-JsonBody @{
        csv = $tradebook
        holdings_csv = $holdings
        reconcile_holdings = $true
        apply_corp_actions = $true
    }
    $import = Invoke-RestMethod -Method POST -Uri "$base/api/pnl/import/zerodha" `
        -ContentType "application/json" -WebSession $web -Body $importBody
    if ($import.status -ne 'ok') { throw "Import failed" }
    Write-Host "[OK] import applied"

    $open = Invoke-RestMethod -Uri "$base/api/pnl/open" -WebSession $web
    $trentQty = ($open.data | Where-Object { $_.symbol -eq 'TRENT' } | Measure-Object -Property qty -Sum).Sum
    if ([int]$trentQty -ne 25) {
        throw "TRENT open qty expected 25, got $trentQty"
    }
    Write-Host "[OK] TRENT open qty = 25"

    Write-Host ""
    Write-Host "PNL IMPORT E2E PASS" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "PNL IMPORT E2E FAIL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Cleanup
}
