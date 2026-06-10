#Requires -Version 5.1
<#
.SYNOPSIS
  Dev-only: simulate client install path with spaces and verify update staging + apply entry.
#>
[CmdletBinding()]
param(
    [string]$SourceInstall = "",
    [string]$UpdatePackage = "",
    [switch]$RunApply
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-CiMPaths -RepoRoot $RepoRoot
if (-not $SourceInstall) {
    $SourceInstall = $fx.ExportRoot
}
if (-not (Test-Path -LiteralPath $SourceInstall)) {
    throw "Source install not found: $SourceInstall. Run export_cim.ps1 first."
}

$testRoot = Join-Path $env:TEMP ("CiM-UpdateTest-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
$install = Join-Path $testRoot "zTo Delete\Charts In Motion"
$zipSibling = Join-Path $testRoot "zTo Delete\CiM-Update-test"

if (Test-Path -LiteralPath $testRoot) {
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $install | Out-Null

Write-Host "Copying minimal install from $SourceInstall ..."
$keep = @(
    "start_cim.bat", "stop_cim.bat", "Apply-Update.bat",
    "scripts", "server", "config", "data", "runtime"
)
foreach ($name in $keep) {
    $src = Join-Path $SourceInstall $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    Copy-Item -LiteralPath $src -Destination (Join-Path $install $name) -Recurse -Force
}

# Repo scripts override export (latest fixes)
foreach ($rel in @(
        "scripts\Apply-LocalUpdate-Entry.ps1",
        "scripts\_Apply-LocalUpdate.ps1",
        "scripts\CiMInstallLocator.ps1",
        "scripts\CiMUpdatePackage.ps1",
        "Apply-Update.bat"
    )) {
    $src = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dst = Join-Path $install $rel
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}

if (-not $UpdatePackage) {
    $candidates = Get-ChildItem -LiteralPath $fx.InstallerOutputDir -Directory -Filter "CiM-Update*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($candidates) { $UpdatePackage = $candidates[0].FullName }
}
if (-not $UpdatePackage -or -not (Test-Path -LiteralPath $UpdatePackage)) {
    throw "No CiM-Update package. Run: scripts\build_update_package.ps1 -Version 1.0.2"
}

Copy-Item -LiteralPath $UpdatePackage -Destination $zipSibling -Recurse -Force
Write-Host "Test install: $install"
Write-Host "Update ZIP sibling: $zipSibling"
Write-Host ""

# Scenario A: Apply without UPDATE (should auto-stage from sibling)
$updateDir = Join-Path $install "UPDATE"
if (Test-Path -LiteralPath $updateDir) {
    Remove-Item -LiteralPath $updateDir -Recurse -Force
}

$entry = Join-Path $install "scripts\Apply-LocalUpdate-Entry.ps1"
Write-Host "=== Scenario A: Apply-LocalUpdate-Entry auto-stages sibling package ==="
if ($RunApply) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $entry -LauncherDir $install
    if ($LASTEXITCODE -ne 0) { throw "Apply failed with exit $LASTEXITCODE" }
} else {
    . (Join-Path $RepoRoot "scripts\CiMUpdatePackage.ps1")
    $found = Find-CiMUpdatePackageRoot -InstallRoot $install
    if (-not $found) { throw "Find-CiMUpdatePackageRoot did not find sibling package" }
    Copy-UpdatePackageToInstall -PackageRoot $found -InstallRoot $install | Out-Null
}
$manifest = Join-Path $updateDir "update.manifest.json"
if (-not (Test-Path -LiteralPath $manifest)) {
    throw "After staging, manifest still missing: $manifest"
}
Write-Host "OK: $manifest exists"
Write-Host ""
Write-Host "All update-flow checks passed."
