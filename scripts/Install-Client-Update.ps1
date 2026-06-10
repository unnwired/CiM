#Requires -Version 5.1
<#
.SYNOPSIS
  Run from the extracted CiM-Update-* folder on the CLIENT PC.
  Primary layout: <Charts In Motion install>\UPDATE\CiM-Update-*\Install-Client-Update.bat
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
$PackageRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path

function Resolve-InstallGuessFromPackage([string]$Path) {
    if (-not $Path) { return $null }
    $d = $Path.TrimEnd('\')
    for ($i = 0; $i -lt 12; $i++) {
        if ((Split-Path -Leaf $d) -ieq 'UPDATE') {
            return (Split-Path -Parent $d)
        }
        $p = Split-Path -Parent $d
        if (-not $p -or $p -eq $d) { break }
        $d = $p
    }
    return $null
}

$installGuess = Resolve-InstallGuessFromPackage -Path $PackageRoot
$Locator = $null
if ($installGuess) {
    foreach ($try in @(
            (Join-Path $installGuess "scripts\CiMInstallLocator.ps1")
        )) {
        if (Test-Path -LiteralPath $try) { $Locator = $try; break }
    }
}
if (-not $Locator) {
    foreach ($try in @(
            (Join-Path $PSScriptRoot "scripts\CiMInstallLocator.ps1"),
            (Join-Path $PSScriptRoot "CiMInstallLocator.ps1")
        )) {
        if (Test-Path -LiteralPath $try) { $Locator = $try; break }
    }
}
if (-not $Locator -and $installGuess) {
    throw "Missing CiMInstallLocator.ps1 under $installGuess\scripts\ (run a newer update or copy scripts from support)."
}
if (-not $Locator) {
    throw "Missing CiMInstallLocator.ps1 (expected in scripts\ next to this file or install\scripts\)."
}
. $Locator

$pkgHelper = $null
if ($installGuess) {
    $try = Join-Path $installGuess "scripts\CiMUpdatePackage.ps1"
    if (Test-Path -LiteralPath $try) { $pkgHelper = $try }
}
if (-not $pkgHelper) {
    $pkgHelper = Join-Path $PSScriptRoot "CiMUpdatePackage.ps1"
}
if (-not (Test-Path -LiteralPath $pkgHelper) -and $installGuess) {
    $pkgHelper = Join-Path $installGuess "scripts\CiMUpdatePackage.ps1"
}
if (Test-Path -LiteralPath $pkgHelper) { . $pkgHelper }

Write-Host ""
Write-Host "=========================================="
Write-Host " Charts In Motion client update installer"
Write-Host "=========================================="
Write-Host "Update package: $PackageRoot"
Write-Host ""

$manifestSrc = Join-Path $PackageRoot "update.manifest.json"
if (-not (Test-Path -LiteralPath $manifestSrc)) {
    throw @"
This folder is not a valid update package (missing update.manifest.json).

Extract the CiM-Update ZIP into your Charts In Motion UPDATE folder, e.g.:
  D:\CiM\UPDATE\CiM-Update-1.0.2

Then double-click Install-Client-Update.bat inside that folder.
"@
}

if ($InstallRoot) {
    $install = Select-FlowXInstallRoot -FromPath $PackageRoot -PreferPath $InstallRoot
} elseif ($installGuess) {
    $install = $installGuess.TrimEnd('\')
} else {
    $install = $null
    if (Get-Command Get-CiMInstallRootFromPath -ErrorAction SilentlyContinue) {
        $install = Get-CiMInstallRootFromPath -FromPath $PackageRoot
    }
    if (-not $install) {
        $install = Select-FlowXInstallRoot -FromPath $PackageRoot
    }
}

if (-not $install) {
    throw @"
Could not find Charts In Motion on this PC.

Put the extracted CiM-Update folder inside your Charts In Motion UPDATE folder, e.g.:
  D:\CiM\UPDATE\CiM-Update-1.0.2

Then run Install-Client-Update.bat from inside that folder.

Manual override: powershell -File Install-Client-Update.ps1 -InstallRoot "D:\CiM"
"@
}

Write-Host "Found Charts In Motion install: $install"
Write-Host ""

if (Get-Command Copy-UpdatePackageToInstall -ErrorAction SilentlyContinue) {
    $updateDir = Copy-UpdatePackageToInstall -PackageRoot $PackageRoot -InstallRoot $install
} else {
    $updateDir = $PackageRoot
}

$payload = Join-Path $updateDir "payload"
if (-not (Test-Path -LiteralPath $payload)) {
    throw "UPDATE package payload\ missing. Re-run from the CiM-Update ZIP or contact support."
}

Write-Host "Bootstrapping launchers into install root ..."
$bootstrap = @(
    "Apply-Update.bat",
    "start_cim.bat",
    "stop_cim.bat",
    "scripts\CiMApplyUpdate.ps1",
    "scripts\CiMDownloadUpdate.ps1",
    "scripts\Repair-CiMLicense.ps1",
    "scripts\_Apply-LocalUpdate.ps1",
    "scripts\CiMInstallLocator.ps1",
    "scripts\Install-Client-Update.ps1",
    "scripts\Diagnose-CiMInstall.ps1",
    "scripts\Apply-LocalUpdate-Entry.ps1",
    "scripts\CiMUpdatePackage.ps1",
    "Repair-CiMLicense.bat"
)
foreach ($rel in $bootstrap) {
    $src = Join-Path $payload ($rel -replace '/', '\')
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dst = Join-Path $install ($rel -replace '/', '\')
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host "  $rel"
}

$manifest = Get-Content -LiteralPath (Join-Path $updateDir "update.manifest.json") -Raw | ConvertFrom-Json
$logDir = Join-Path $install "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$pendingPath = Join-Path $logDir "update-pending-local.json"
[ordered]@{
    version   = [string]$manifest.version
    source    = "local"
    sourceDir = $updateDir
    manifest  = $manifest
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $pendingPath -Encoding UTF8

$applyScript = Join-Path $install "scripts\CiMApplyUpdate.ps1"
if (-not (Test-Path -LiteralPath $applyScript)) {
    throw "Missing $applyScript after bootstrap"
}

Write-Host ""
Write-Host "Applying update $($manifest.version) ..."
& powershell -NoProfile -ExecutionPolicy Bypass -File $applyScript -InstallRoot $install -ManifestPath $pendingPath
if ($LASTEXITCODE -ne 0) {
    throw "CiMApplyUpdate failed. See $logDir\update-apply.log"
}

$licensePath = Join-Path $install "data\.cim-license"
if (-not (Test-Path -LiteralPath $licensePath)) {
    Write-Host ""
    Write-Host "WARNING: data\.cim-license is still missing. Run Repair-CiMLicense.bat with a support install key."
} else {
    Write-Host ""
    Write-Host "Update complete. Start Charts In Motion: $install\start_cim.bat"
}

$resultFile = Join-Path $install "update-result.txt"
if (Test-Path -LiteralPath $resultFile) {
    Write-Host ""
    Get-Content -LiteralPath $resultFile
}

$diag = Join-Path $install "scripts\Diagnose-CiMInstall.ps1"
if (Test-Path -LiteralPath $diag) {
    Write-Host ""
    Write-Host "Running install diagnostic ..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $diag -InstallRoot $install
}
