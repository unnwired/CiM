#Requires -Version 5.1
<#
.SYNOPSIS
  Fast refresh of an existing export tree from repo source (no installer, no update ZIP).

.DESCRIPTION
  Use after a full build when you changed app code and want a new update package without
  rebuilding embedded Python or the Inno installer.

  Steps: version sync -> fast export -> sync fixes -> prepare/encrypt -> smoke test.

  Then run *-UpdatePackage.bat to create CiM-Update-{version}.zip.

  Version comes from repo root version.txt. Bump it before refresh if you want clients
  to see an in-app update (e.g. 1.0.3 -> 1.0.4).

.EXAMPLE
  .\scripts\Build-CiM-RefreshExport.ps1 -DistributionKind Plaintext
#>
[CmdletBinding()]
param(
    [ValidateSet('Plaintext', 'Encrypted')]
    [string]$DistributionKind = 'Encrypted',
    [string]$LicenseSecret = ''
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
. (Join-Path $ScriptDir 'Get-CiMPaths.ps1')

$fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind $DistributionKind
$ExportRoot = $fx.ExportRoot

if (-not (Test-Path -LiteralPath (Join-Path $ExportRoot 'start_cim.bat'))) {
    throw @"
No export tree at:
  $ExportRoot

Run the full build batch first (*-Full-Build.bat).
"@
}

$py = Join-Path $ExportRoot 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    throw @"
Missing embedded Python in export tree:
  $py

Run the full build batch once (embedded Python is not rebuilt on refresh).
"@
}

$version = Get-CiMRepoVersion -RepoRoot $RepoRoot
Write-Host ''
Write-Host "=== CiM refresh export ($DistributionKind) version $version ===" -ForegroundColor Cyan
Write-Host "  Export: $ExportRoot"
Write-Host "  Skips: embedded Python rebuild, wheelhouse, installer, update ZIP"
Write-Host ''

$params = @{
    ExportRoot         = $ExportRoot
    Version            = $version
    LicenseSecret      = $LicenseSecret
    SkipInstaller      = $true
    SkipUpdatePackage  = $true
    FastExport         = $true
}
if ($DistributionKind -eq 'Plaintext') {
    $params.PlaintextExport = $true
    $params.SkipEncrypt = $true
}

& (Join-Path $ScriptDir 'build_distribution_full.ps1') @params
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Export tree refreshed.' -ForegroundColor Green
Write-Host "  Version: $version (from repo version.txt)"
Write-Host "  Next: run Batch Files\$DistributionKind-UpdatePackage.bat"
Write-Host ''
