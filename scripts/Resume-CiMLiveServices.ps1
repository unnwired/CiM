#Requires -Version 5.1
<#
.SYNOPSIS
  Heal live web + mobile public links after sleep, unlock, or logon.

.DESCRIPTION
  Tailscale Funnel often goes stale when the PC sleeps or sits idle. Local ports
  (8001/8011) keep working but public HTTPS times out. This script:
    1. Ensures the background watchdog loop is running
    2. Runs a full heal with funnel reset (-ResetFunnelFirst)

  Registered by Install-CiMLiveResumeHeal.ps1 on logon, startup, and resume-from-sleep.
#>
[CmdletBinding()]
param(
    [string]$WebRoot = "D:\CiM\Client"
)

$ErrorActionPreference = "Stop"
$WebRoot = [System.IO.Path]::GetFullPath($WebRoot.Trim().TrimEnd('\'))
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $WebRoot "runtime\logs"
$logFile = Join-Path $logDir "live-resume-heal.log"

if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

function Write-ResumeLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

Write-ResumeLog "=== Resume heal START ==="

try {
    Write-ResumeLog "Restarting Tailscale service..."
    Restart-Service -Name Tailscale -Force -ErrorAction Stop
} catch {
    try {
        tailscale down 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        tailscale up 2>&1 | Out-Null
    } catch {
        Write-ResumeLog "Tailscale restart failed: $($_.Exception.Message)"
    }
}
Start-Sleep -Seconds 8

$watchdogStarter = Join-Path $ScriptDir "Start-CiMLiveWatchdog.ps1"
if (Test-Path -LiteralPath $watchdogStarter) {
    try {
        & $watchdogStarter -WebRoot $WebRoot
        Write-ResumeLog "Watchdog ensure: exit $LASTEXITCODE"
    } catch {
        Write-ResumeLog "Watchdog ensure failed: $($_.Exception.Message)"
    }
} else {
    Write-ResumeLog "Missing Start-CiMLiveWatchdog.ps1"
}

$healScript = Join-Path $ScriptDir "Invoke-CiMLiveWebAndMobileHeal.ps1"
if (-not (Test-Path -LiteralPath $healScript)) {
    Write-ResumeLog "Missing Invoke-CiMLiveWebAndMobileHeal.ps1"
    exit 1
}

try {
    $result = & $healScript -WebRoot $WebRoot -ResetFunnelFirst -LogFn {
        param($Msg, $Lvl)
        Write-ResumeLog "[$Lvl] $Msg"
    }
    Write-ResumeLog ("overallOk={0} webPublic={1} mobilePublic={2} heal={3}" -f `
        $result.OverallOk, $result.WebPublicOk, $result.MobilePublicOk, $result.HealAction)
    if ($result.HealError) { Write-ResumeLog "healError=$($result.HealError)" }
    exit $(if ($result.OverallOk) { 0 } else { 1 })
} catch {
    Write-ResumeLog "Heal exception: $($_.Exception.Message)"
    exit 1
} finally {
    Write-ResumeLog "=== Resume heal END ==="
}
