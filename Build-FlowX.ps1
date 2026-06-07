#Requires -Version 5.1
<#
.SYNOPSIS
  One command: export → encrypt → installer (+ update package).

.DESCRIPTION
  Replaces the manual four-step paste into cmd:

    $env:FLOWX_LICENSE_SECRET = '...'
    .\export_flowx.ps1 -Mode distribution -HardenAll
    .\scripts\encrypt_app_code.ps1
    .\scripts\build_installer.ps1

  License secret (pick one — set once, reuse every build):
    1. Save one line in config\.build_license_secret (gitignored; copy from build_license_secret.example)
    2. $env:FLOWX_LICENSE_SECRET = '...' in this PowerShell window
    3. -LicenseSecret '...' on this script (avoid if shell logs commands)

.EXAMPLE
  .\Build-FlowX.ps1

.EXAMPLE
  .\Build-FlowX.ps1 -SkipExport
#>
[CmdletBinding()]
param(
    [string]$LicenseSecret = "",
    [string]$ExportRoot = "",
    [string]$Version = "",
    [switch]$SkipExport,
    [switch]$SkipEncrypt,
    [switch]$SkipUpdatePackage,
    [switch]$InstallerOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$fullBuild = Join-Path $RepoRoot "scripts\build_distribution_full.ps1"

if (-not (Test-Path -LiteralPath $fullBuild)) {
    throw "Missing $fullBuild"
}

if ($InstallerOnly) {
    $SkipExport = $true
    $SkipUpdatePackage = $true
}

$params = @{
    LicenseSecret = $LicenseSecret
    SkipExport    = $SkipExport
    SkipEncrypt   = $SkipEncrypt
}
if ($ExportRoot) { $params.ExportRoot = $ExportRoot }
if ($Version) { $params.Version = $Version }
if ($SkipUpdatePackage) { $params.SkipUpdatePackage = $true }

Write-Host ""
Write-Host "=== FlowX distribution build (single command) ===" -ForegroundColor Cyan
Write-Host "  export -> sync -> encrypt -> installer$(if (-not $SkipUpdatePackage) { ' -> update package' } else { '' })"
Write-Host ""

& $fullBuild @params
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. See runtime\logs\build-distribution.log" -ForegroundColor Green
