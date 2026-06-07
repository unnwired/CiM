#Requires -Version 5.1
<#
.SYNOPSIS
  Copy distribution-fix files from dev repo into installer\output\FlowX (no export_flowx.ps1 run).
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
$fx = Get-FlowXPaths -RepoRoot $RepoRoot
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}
if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw "Export not found: $ExportRoot"
}

$copyMap = @(
    "start_flowx.bat",
    "stop_flowx.bat",
    "Apply-Update.bat",
    "scripts\_Apply-LocalUpdate.ps1",
    "scripts\Apply-LocalUpdate-Entry.ps1",
    "scripts\FlowXUpdatePackage.ps1",
    "Install-Client-Update.bat",
    "scripts\Install-Client-Update.ps1",
    "scripts\FlowXInstallLocator.ps1",
    "scripts\Diagnose-FlowXInstall.ps1",
    "server\app_code_crypto.py",
    "server\flowx_bootstrap.py",
    "config\github_updates.json",
    "scripts\FlowXApplyUpdate.ps1",
    "scripts\FlowXDownloadUpdate.ps1",
    "scripts\Repair-FlowXLicense.ps1",
    "scripts\Verify-FlowXLicenseChain.ps1",
    "scripts\Show-FlowXInstallKey.ps1",
    "Repair-FlowXLicense.bat",
    "Repair-FlowXLicense-Auto.bat",
    "scripts\Apply-FlowXLocalUpdate.ps1",
    "desktop\main.js",
    "desktop\preload.js",
    "requirements_runtime.txt"
)
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
$vendorFile = Get-FlowXDistProfilePath -InstallRoot $ExportRoot -Paths $fx
if (Test-Path -LiteralPath $vendorFile) {
    $verify = Join-Path $ScriptDir "Verify-FlowXLicenseChain.ps1"
    if (Test-Path -LiteralPath $verify) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $verify -ExportRoot $ExportRoot -RepoRoot $RepoRoot
    }
}
Write-Host "Export sync complete: $ExportRoot"
