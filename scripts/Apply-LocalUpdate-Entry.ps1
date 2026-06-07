#Requires -Version 5.1
<#
.SYNOPSIS
  Called from Apply-Update.bat only. Avoids passing paths with trailing backslashes through cmd.exe.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$LauncherDir
)

$ErrorActionPreference = "Stop"

function Normalize-InstallPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return [System.IO.Path]::GetFullPath($Path.Trim()).TrimEnd([char]'\')
}

$LauncherDir = Normalize-InstallPath $LauncherDir

$loc = Join-Path $LauncherDir "scripts\FlowXInstallLocator.ps1"
if (-not (Test-Path -LiteralPath $loc)) {
    throw "Missing $loc"
}
. $loc

$pkgHelper = Join-Path $LauncherDir "scripts\FlowXUpdatePackage.ps1"
if (-not (Test-Path -LiteralPath $pkgHelper)) {
    $pkgHelper = Join-Path (Split-Path -Parent $LauncherDir) "scripts\FlowXUpdatePackage.ps1"
}
if (Test-Path -LiteralPath $pkgHelper) { . $pkgHelper }

$install = Get-FlowXInstallRootFromPath -FromPath $LauncherDir
if (-not $install) {
    $install = Select-FlowXInstallRoot -FromPath $LauncherDir
}
if (-not $install -and (Test-FlowXInstall $LauncherDir)) {
    $install = $LauncherDir
}
if (-not $install) {
    throw "Could not find FlowX install root from: $LauncherDir"
}
$install = Normalize-InstallPath $install
$updateDir = Normalize-InstallPath (Join-Path $install "UPDATE")

Write-Host "=========================================="
Write-Host " FlowX - Apply local update"
Write-Host "=========================================="
Write-Host "Install folder: $install"
Write-Host ""

$packageRoot = $null
$flatManifest = Join-Path $updateDir "update.manifest.json"
if (Test-Path -LiteralPath $flatManifest) {
    $packageRoot = $updateDir
}
if (-not $packageRoot -and (Get-Command Find-FlowXUpdatePackageRoot -ErrorAction SilentlyContinue)) {
    $packageRoot = Find-FlowXUpdatePackageRoot -InstallRoot $install
}

if (-not $packageRoot) {
    $diag = if (Get-Command Get-UpdateFolderDiagnosis -ErrorAction SilentlyContinue) {
        Get-UpdateFolderDiagnosis -UpdateDir $updateDir
    } else { "" }
    $hint = @(
        "No update package found under $updateDir"
        ""
        "Extract the FlowX-Update ZIP into your FlowX UPDATE folder, e.g.:"
        "  D:\FlowX\UPDATE\FlowX-Update-1.0.2"
        ""
        "Then double-click Install-Client-Update.bat inside that folder."
        ""
        if ($diag) { "Current state: $diag" }
    ) -join "`n"
    throw $hint
}

Write-Host "Update package: $packageRoot"
Write-Host ""

$helper = Join-Path $LauncherDir "scripts\_Apply-LocalUpdate.ps1"
if (-not (Test-Path -LiteralPath $helper)) {
    $helper = Join-Path $install "scripts\_Apply-LocalUpdate.ps1"
}
if (-not (Test-Path -LiteralPath $helper)) {
    throw "Missing _Apply-LocalUpdate.ps1"
}

Write-Host "Close FlowX if it is running. Applying in 3 seconds ..."
Start-Sleep -Seconds 3

& powershell -NoProfile -ExecutionPolicy Bypass -File $helper -InstallRoot $install -UpdateDir $packageRoot
exit $LASTEXITCODE
