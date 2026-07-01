#Requires -Version 5.1
<#
.SYNOPSIS
  Gate tests for Invoke-CiMLiveWebAndMobileHeal.ps1 (check-only + script presence).
#>
[CmdletBinding()]
param(
    [string]$WebRoot = "D:\CiM\Client"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$failed = 0

function Assert-True {
    param([bool]$Cond, [string]$Name)
    if ($Cond) {
        Write-Host "  OK $Name" -ForegroundColor Green
    } else {
        Write-Host "  FAIL $Name" -ForegroundColor Red
        $script:failed++
    }
}

Write-Host "=== Test-CiMLiveWatchdogHeal ===" -ForegroundColor Cyan

$required = @(
    "Invoke-CiMLiveWebAndMobileHeal.ps1",
    "Start-CiMLiveWatchdogLoop.ps1",
    "Start-CiMLiveWatchdog.ps1",
    "Stop-CiMLiveWatchdog.ps1",
    "Get-CiMDeployPairing.ps1",
    "Get-CiMShowcasePublicUrl.ps1"
)
foreach ($f in $required) {
    Assert-True (Test-Path -LiteralPath (Join-Path $ScriptDir $f)) "repo script $f"
}

$clientScripts = Join-Path $WebRoot "scripts"
foreach ($f in @(
    "Invoke-CiMLiveWebAndMobileHeal.ps1",
    "Start-CiMLiveWatchdog.ps1",
    "Stop-CiMLiveWatchdog.ps1"
)) {
    Assert-True (Test-Path -LiteralPath (Join-Path $clientScripts $f)) "synced $f"
}

$heal = Join-Path $ScriptDir "Invoke-CiMLiveWebAndMobileHeal.ps1"
$result = & $heal -WebRoot $WebRoot -CheckOnly
Assert-True ($null -ne $result) "heal returns result"
Assert-True ($result.PSObject.Properties.Name -contains "OverallOk") "result has OverallOk"
Assert-True ($result.PSObject.Properties.Name -contains "WebLocalOk") "result has WebLocalOk"
Assert-True ($result.PSObject.Properties.Name -contains "WebPublicOk") "result has WebPublicOk"
Assert-True ($result.PSObject.Properties.Name -contains "MobileLocalOk") "result has MobileLocalOk"
Assert-True ($result.PSObject.Properties.Name -contains "MobilePublicOk") "result has MobilePublicOk"

Write-Host ""
Write-Host "Probe snapshot: overall=$($result.OverallOk) webLocal=$($result.WebLocalOk) webPublic=$($result.WebPublicOk) mobileLocal=$($result.MobileLocalOk) mobilePublic=$($result.MobilePublicOk)" -ForegroundColor DarkGray

# Idempotent watchdog spawn test (does not require services up)
$spawn = Join-Path $ScriptDir "Start-CiMLiveWatchdog.ps1"
if (Test-Path -LiteralPath $spawn) {
    & $spawn -WebRoot $WebRoot | Out-Host
    Start-Sleep -Seconds 6
    $pidFile = Join-Path $WebRoot "runtime\logs\live-watchdog.pid"
    Assert-True (Test-Path -LiteralPath $pidFile) "watchdog pid file after spawn"
    & (Join-Path $ScriptDir "Stop-CiMLiveWatchdog.ps1") -WebRoot $WebRoot | Out-Host
    Assert-True (-not (Test-Path -LiteralPath $pidFile)) "watchdog pid removed after stop"
}

Write-Host ""
if ($failed -gt 0) {
    Write-Host "FAILED ($failed)" -ForegroundColor Red
    exit 1
}
Write-Host "All watchdog heal gate checks passed." -ForegroundColor Green
exit 0
