#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot live web+mobile health check and heal (for manual debug).

.DESCRIPTION
  Prefer Start-CiMLiveWatchdog.ps1 for continuous monitoring.
  Windows Task Scheduler install (Install-CiMLiveWatchdogTask.ps1) is optional/deprecated;
  use the background loop spawned from Start-Live-WebAndMobile.bat instead.
#>
[CmdletBinding()]
param(
    [string]$WebRoot = "D:\CiM\Client"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$healScript = Join-Path $ScriptDir "Invoke-CiMLiveWebAndMobileHeal.ps1"
if (-not (Test-Path -LiteralPath $healScript)) {
    throw "Missing $healScript"
}

$result = & $healScript -WebRoot $WebRoot -LogFn {
    param($Msg, $Lvl)
    Write-Host "[$Lvl] $Msg"
}

Write-Host ""
Write-Host "overallOk=$($result.OverallOk) webLocal=$($result.WebLocalOk) webPublic=$($result.WebPublicOk) mobileLocal=$($result.MobileLocalOk) mobilePublic=$($result.MobilePublicOk)" -ForegroundColor $(if ($result.OverallOk) { 'Green' } else { 'Yellow' })
if ($result.HealAction) { Write-Host "healAction=$($result.HealAction)" -ForegroundColor Cyan }
if ($result.HealError) { Write-Host "healError=$($result.HealError)" -ForegroundColor Red }
exit $(if ($result.OverallOk) { 0 } else { 1 })
