#Requires -Version 5.1
<#
.SYNOPSIS
  Pre-promote gate: unit tests + API E2E + optional showcase PnL import E2E.
#>
[CmdletBinding()]
param(
    [switch]$SkipShowcaseE2E,
    [string]$SourceRoot = "D:\CiM\Client_Test",
    [int]$Port = 8002,
    [switch]$UseRunningShowcase
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

Write-Host "=== PnL Import Gate ===" -ForegroundColor Cyan

Push-Location $RepoRoot
try {
    python -m unittest discover -s packages/server/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Unit tests failed ($LASTEXITCODE)" }

    python -m unittest discover -s packages/server/tests -p "test_pnl_import_e2e.py" -v
    if ($LASTEXITCODE -ne 0) { throw "API E2E failed ($LASTEXITCODE)" }

    if (-not $SkipShowcaseE2E) {
        & (Join-Path $ScriptDir "Test-CiMPnlImportE2E.ps1") -SourceRoot $SourceRoot -Port $Port -UseRunningShowcase:$UseRunningShowcase
        if ($LASTEXITCODE -ne 0) { throw "Showcase PnL E2E failed ($LASTEXITCODE)" }
    }
}
finally {
    Pop-Location
}

Write-Host "PNL IMPORT GATE PASS" -ForegroundColor Green
exit 0
