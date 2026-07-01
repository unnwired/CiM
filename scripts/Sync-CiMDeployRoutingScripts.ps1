#Requires -Version 5.1
<#
.SYNOPSIS
  Copy deploy routing scripts to web and mobile install roots so they stay in sync.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string[]]$ExtraTargets = @()
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }

$routingFiles = @(
    "Get-CiMDeployPairing.ps1",
    "Enable-CiMTailscalePublicRoutes.ps1",
    "Enable-CiMShowcaseFunnel.ps1",
    "Enable-CiMMobileFunnel.ps1",
    "Start-CiMMobileMain.ps1",
    "Stop-CiMMobileTestbedPublic.ps1",
    "Get-CiMShowcasePublicUrl.ps1",
    "Invoke-CiMLiveWebAndMobileHeal.ps1",
    "Start-CiMLiveWatchdogLoop.ps1",
    "Start-CiMLiveWatchdog.ps1",
    "Stop-CiMLiveWatchdog.ps1"
)

$defaultTargets = @(
    "D:\CiM\Client\scripts",
    "D:\CiM\Client_Test\scripts",
    "D:\CiM\Mobile_Testbed\scripts",
    "D:\CiM\Mobile_Main\scripts"
)

$targets = @($defaultTargets + $ExtraTargets | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)

foreach ($destDir in $targets) {
    if (-not (Test-Path -LiteralPath $destDir)) {
        Write-Warning "Skip missing target: $destDir"
        continue
    }
    foreach ($file in $routingFiles) {
        $src = Join-Path $ScriptDir $file
        if (-not (Test-Path -LiteralPath $src)) {
            throw "Missing repo script: $src"
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $destDir $file) -Force
        Write-Host "Synced $file -> $destDir"
    }
}

Write-Host "Deploy routing script sync complete." -ForegroundColor Green
