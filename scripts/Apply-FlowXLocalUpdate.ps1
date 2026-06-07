#Requires -Version 5.1
<#
.SYNOPSIS
  Apply a FlowX-Update-* folder to an install directory (no running app required).

.EXAMPLE
  # CLIENT PC only — use that PC's install path and its UPDATE folder:
  .\Apply-FlowXLocalUpdate.ps1 -InstallRoot "C:\FlowX" -UpdateDir "C:\FlowX\UPDATE"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$UpdateDir
)

$ErrorActionPreference = "Stop"
$UpdateDir = (Resolve-Path -LiteralPath $UpdateDir).Path
$InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path

$manifestPath = Join-Path $UpdateDir "update.manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Missing update.manifest.json in $UpdateDir"
}

$payloadRoot = Join-Path $UpdateDir "payload"
if (-not (Test-Path -LiteralPath $payloadRoot)) {
    $payloadRoot = $UpdateDir
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$applyScript = Join-Path $InstallRoot "scripts\FlowXApplyUpdate.ps1"
if (-not (Test-Path -LiteralPath $applyScript)) {
    $applyScript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "FlowXApplyUpdate.ps1"
}

$pendingPath = Join-Path $InstallRoot "runtime\logs\update-pending-local.json"
$pending = [ordered]@{
    version   = [string]$manifest.version
    source    = "local"
    sourceDir = $UpdateDir
    manifest  = $manifest
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pendingPath) | Out-Null
$pending | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $pendingPath -Encoding UTF8

Write-Host "Applying update $($manifest.version) to $InstallRoot ..."
& powershell -NoProfile -ExecutionPolicy Bypass -File $applyScript -InstallRoot $InstallRoot -ManifestPath $pendingPath
if ($LASTEXITCODE -ne 0) { throw "FlowXApplyUpdate failed (exit $LASTEXITCODE)" }
Write-Host "Update applied."
