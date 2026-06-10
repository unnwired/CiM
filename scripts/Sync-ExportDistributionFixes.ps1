#Requires -Version 5.1
<#
.SYNOPSIS
  Copy distribution-fix files from dev repo into installer\output\CiM (no export_cim.ps1 run).
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
$fx = Get-CiMPaths -RepoRoot $RepoRoot
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}
if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw "Export not found: $ExportRoot"
}

$copyMap = @(
    "start_cim.bat",
    "stop_cim.bat",
    "Apply-Update.bat",
    "scripts\_Apply-LocalUpdate.ps1",
    "scripts\Apply-LocalUpdate-Entry.ps1",
    "scripts\CiMUpdatePackage.ps1",
    "Install-Client-Update.bat",
    "scripts\Install-Client-Update.ps1",
    "scripts\CiMInstallLocator.ps1",
    "scripts\Diagnose-CiMInstall.ps1",
    "server\app_code_crypto.py",
    "server\cim_bootstrap.py",
    "server\product_config.py",
    "config\product.json",
    "config\github_updates.json",
    "scripts\CiMApplyUpdate.ps1",
    "scripts\CiMDownloadUpdate.ps1",
    "scripts\Repair-CiMLicense.ps1",
    "scripts\Verify-CiMLicenseChain.ps1",
    "scripts\Show-CiMInstallKey.ps1",
    "Repair-CiMLicense.bat",
    "Repair-CiMLicense-Auto.bat",
    "scripts\Apply-CiMLocalUpdate.ps1",
    "nse_index_history.py",
    "desktop\main.js",
    "desktop\preload.js",
    "desktop\loading.html",
    "requirements_runtime.txt"
)
$frontendBuildSrc = Join-Path $RepoRoot "frontend\build"
$frontendBuildDst = Join-Path $ExportRoot "frontend\build"
if (Test-Path -LiteralPath (Join-Path $frontendBuildSrc "index.html")) {
    if (-not (Test-Path -LiteralPath $frontendBuildDst)) {
        New-Item -ItemType Directory -Force -Path $frontendBuildDst | Out-Null
    }
    robocopy $frontendBuildSrc $frontendBuildDst /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    $manifestSrc = Join-Path $RepoRoot "frontend\public\manifest.json"
    if (Test-Path -LiteralPath $manifestSrc) {
        Copy-Item -LiteralPath $manifestSrc -Destination (Join-Path $frontendBuildDst "manifest.json") -Force
    }
    Write-Host "Synced frontend\build (production bundle)"
}
foreach ($rel in $copyMap) {
    $src = Join-Path $RepoRoot $rel
    $dst = Join-Path $ExportRoot $rel
    if (-not (Test-Path -LiteralPath $src)) {
        Write-Warning "Skip missing repo file: $rel"
        continue
    }
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host "Synced $rel"
}
$vendorFile = Get-CiMDistProfilePath -InstallRoot $ExportRoot -Paths $fx
if (Test-Path -LiteralPath $vendorFile) {
    $verify = Join-Path $ScriptDir "Verify-CiMLicenseChain.ps1"
    if (Test-Path -LiteralPath $verify) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $verify -ExportRoot $ExportRoot -RepoRoot $RepoRoot
    }
}
Write-Host "Export sync complete: $ExportRoot"
