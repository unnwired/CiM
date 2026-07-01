#Requires -Version 5.1
<#
.SYNOPSIS
  Plaintext distribution build: readable server/JS + online auth gate (no encryption).

.DESCRIPTION
  Same pipeline as Build-CiM.ps1 except:
  - Export without -HardenAll (no bytecode obfuscation, no JS obfuscation)
  - Skips encrypt_app_code.ps1
  - Writes config\.cim-plaintext-dist so start_cim.bat uses cim_bootstrap + sign-in shell

  Build machine may use config\.build_license_secret for plaintext export embed (online sign-in at runtime).

.EXAMPLE
  $env:CIM_LICENSE_SECRET = 'your-secret'
  .\Build-CiM-Plaintext.ps1

.EXAMPLE
  .\Build-CiM-Plaintext.ps1 -SkipExport
#>
[CmdletBinding()]
param(
    [string]$LicenseSecret = "",
    [string]$ExportRoot = "",
    [string]$Version = "",
    [switch]$SkipExport,
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
    LicenseSecret    = $LicenseSecret
    SkipExport       = $SkipExport
    SkipEncrypt      = $true
    PlaintextExport  = $true
}
if ($ExportRoot) { $params.ExportRoot = $ExportRoot }
if ($Version) { $params.Version = $Version }
if ($SkipUpdatePackage) { $params.SkipUpdatePackage = $true }

Write-Host ""
Write-Host "=== Charts In Motion PLAINTEXT build (readable source + online auth) ===" -ForegroundColor Cyan
Write-Host "  export (no harden) -> sync -> prepare plaintext -> installer -> update package -> smoke"
Write-Host ""

& $fullBuild @params
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Plaintext build output: installer\Plaintext\ (CiM, CiMSetup-*.exe, CiM-Update-*). Log: runtime\logs\build-distribution.log" -ForegroundColor Green
