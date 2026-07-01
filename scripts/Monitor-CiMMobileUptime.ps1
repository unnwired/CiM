#Requires -Version 5.1
<#
.SYNOPSIS
  Long-interval health monitor for CiM live mobile (8011) + public URLs.

.DESCRIPTION
  Logs local + public reachability. Auto-heal delegates to Invoke-CiMLiveWebAndMobileHeal.ps1
  (same logic as Start-Live-WebAndMobile.bat).
#>
[CmdletBinding()]
param(
    [string]$PublicMobileUrl = "",
    [string]$LocalMobileUrl = "http://127.0.0.1:8011/mobile/",
    [string]$LocalWebHealthUrl = "http://127.0.0.1:8001/api/health",
    [string]$LocalMobileHealthUrl = "http://127.0.0.1:8011/mobile/api/health",
    [int]$DurationMinutes = 55,
    [int]$IntervalMinutes = 5,
    [string]$LogFile = "D:\CiM\Client\runtime\logs\uptime-monitor.log",
    [string]$WebRoot = "D:\CiM\Client",
    [switch]$AutoHeal
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$healScript = Join-Path $ScriptDir "Invoke-CiMLiveWebAndMobileHeal.ps1"

function Write-MonitorLine {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    $logDir = Split-Path -Parent $LogFile
    if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

$started = Get-Date
$deadline = $started.AddMinutes($DurationMinutes)
$checkNum = 0

if ([string]::IsNullOrWhiteSpace($PublicMobileUrl)) {
    . (Join-Path $ScriptDir "Get-CiMShowcasePublicUrl.ps1")
    $base = Get-CiMShowcaseTailscalePublicUrl
    if ($base) {
        $PublicMobileUrl = "$($base.Trim().TrimEnd('/'))/mobile/"
    } else {
        $PublicMobileUrl = "https://charts-in-motion.tail22251c.ts.net/mobile/"
    }
}

Write-MonitorLine "=== CiM live uptime monitor START ==="
Write-MonitorLine "Public mobile: $PublicMobileUrl"
Write-MonitorLine "Duration: ${DurationMinutes}m, interval: ${IntervalMinutes}m, autoHeal: $AutoHeal"

while ((Get-Date) -lt $deadline) {
    $checkNum++
    $elapsedMin = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)

    $result = if ($AutoHeal -and (Test-Path -LiteralPath $healScript)) {
        & $healScript -WebRoot $WebRoot -LogFn {
            param($Msg, $Lvl)
            Write-MonitorLine $Msg $Lvl
        }
    } else {
        & $healScript -WebRoot $WebRoot -CheckOnly
    }

    $summary = @(
        "check #$checkNum elapsed=${elapsedMin}m",
        "overall=$($result.OverallOk)",
        "webLocal=$($result.WebLocalOk)",
        "webPublic=$($result.WebPublicOk)",
        "mobileLocal=$($result.MobileLocalOk)",
        "mobilePublic=$($result.MobilePublicOk)",
        "heal=$($result.HealAction)"
    ) -join " | "

    $level = if ($result.OverallOk) { "OK" } else { "FAIL" }
    Write-MonitorLine $summary $level

    if ((Get-Date) -ge $deadline) { break }
    Start-Sleep -Seconds ([math]::Max(60, $IntervalMinutes * 60))
}

Write-MonitorLine "=== CiM live uptime monitor END (ran $checkNum checks) ==="
