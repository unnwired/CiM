#Requires -Version 5.1
<#
.SYNOPSIS
  Register live CiM Mobile on the shared public /mobile path (paired with web live on 8001).

.DESCRIPTION
  Updates only the /mobile funnel path — does NOT reset web routing at /.
  Run after Mobile_Main proxy is listening on 8011.
#>
[CmdletBinding()]
param(
    [switch]$OpenEnableLink,
    [int]$WaitForEnableMinutes = 0,
    [string]$InstallRoot = "D:\CiM\Mobile_Main"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMDeployPairing.ps1")

$pair = Get-CiMWebMobilePairing -Tier live
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)

if ($InstallRoot -ne $pair.MobileRoot) {
    Write-Warning "InstallRoot $InstallRoot is not the live mobile root ($($pair.MobileRoot))."
}

$routesScript = Join-Path $ScriptDir "Enable-CiMTailscalePublicRoutes.ps1"
if (-not (Test-Path -LiteralPath $routesScript)) {
    throw "Missing $routesScript"
}

Write-Host "=== CiM Mobile live - register public /mobile (port $($pair.MobilePort)) ===" -ForegroundColor Cyan
& $routesScript `
    -WebPort $pair.WebPort `
    -MobilePort $pair.MobilePort `
    -UpdateMobileOnly `
    -WaitForMobileSeconds 30 `
    -WaitForEnableMinutes $WaitForEnableMinutes `
    -OpenEnableLink:$OpenEnableLink `
    -WebInstallRoot $pair.WebRoot `
    -MobileInstallRoot $pair.MobileRoot
exit $LASTEXITCODE
