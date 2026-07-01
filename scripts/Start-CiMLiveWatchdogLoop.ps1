#Requires -Version 5.1
<#
.SYNOPSIS
  Background loop: periodic live web+mobile health check and selective heal.

.DESCRIPTION
  Single-instance via live-watchdog.pid. Spawned from Start-Live-WebAndMobile.bat.
#>
[CmdletBinding()]
param(
    [int]$IntervalMinutes = 5,
    [string]$WebRoot = "D:\CiM\Client",
    [int]$ToastAfterFailures = 3,
    [int]$ToastCooldownMinutes = 60,
    [switch]$Foreground
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WebRoot = [System.IO.Path]::GetFullPath($WebRoot.Trim().TrimEnd('\'))
$logDir = Join-Path $WebRoot "runtime\logs"
$logFile = Join-Path $logDir "live-watchdog.log"
$statusFile = Join-Path $logDir "live-watchdog-status.json"
$pidFile = Join-Path $logDir "live-watchdog.pid"
$toastStateFile = Join-Path $logDir "live-watchdog-toast-state.json"

$healScript = Join-Path $ScriptDir "Invoke-CiMLiveWebAndMobileHeal.ps1"
if (-not (Test-Path -LiteralPath $healScript)) {
    throw "Missing $healScript"
}

function Write-WatchdogLine {
    param([string]$Message, [string]$Level = "INFO")
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
    if ($Foreground) { Write-Host $line }
}

function Test-WatchdogAlreadyRunning {
    if (-not (Test-Path -LiteralPath $pidFile)) { return $false }
    $raw = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($raw -notmatch '^\d+$') { return $false }
    $procId = [int]$raw
    try {
        $p = Get-Process -Id $procId -ErrorAction Stop
        if ($p.ProcessName -match 'powershell|pwsh') { return $true }
    } catch { }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    return $false
}

function Write-WatchdogStatus {
    param(
        $Result,
        [int]$ConsecutiveFailures,
        [string]$LastToastAt
    )
    $payload = [ordered]@{
        lastCheckAt         = $Result.CheckedAt
        overallOk           = $Result.OverallOk
        webLocalOk          = $Result.WebLocalOk
        webPublicOk         = $Result.WebPublicOk
        mobileLocalOk       = $Result.MobileLocalOk
        mobilePublicOk      = $Result.MobilePublicOk
        consecutiveFailures = $ConsecutiveFailures
        lastHealAction      = $Result.HealAction
        lastHealAt          = if ($Result.HealAction) { $Result.CheckedAt } else { $null }
        lastError           = $Result.HealError
        publicWebUrl        = $Result.PublicWebUrl
        publicMobileUrl     = $Result.PublicMobileUrl
        portWeb             = $Result.PortWeb
        portMobile          = $Result.PortMobile
        funnelStatusSnippet = ($Result.FunnelStatus -split "`n" | Select-Object -First 3) -join " | "
        lastToastAt         = $LastToastAt
        loopPid             = $PID
        intervalMinutes     = $IntervalMinutes
    }
    ($payload | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Send-CiMWatchdogToast {
    param([string]$Message)
    try {
        if (-not ([System.Management.Automation.PSTypeName]'Windows.UI.Notifications.ToastNotificationManager').Type) {
            Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        }
        $appId = "ChartsInMotion.LiveWatchdog"
        $xml = @"
<toast>
  <visual>
    <binding template="ToastText02">
      <text id="1">CiM live services</text>
      <text id="2">$([System.Security.SecurityElement]::Escape($Message))</text>
    </binding>
  </visual>
</toast>
"@
        $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
        $doc.LoadXml($xml)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId)
        $notifier.Show($toast)
        return $true
    } catch {
        Write-WatchdogLine "Toast failed: $($_.Exception.Message)" "WARN"
        try {
            [void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
            [System.Windows.Forms.MessageBox]::Show($Message, "CiM Live Watchdog", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
            return $true
        } catch {
            return $false
        }
    }
}

function Test-ShouldSendToast {
    param(
        [int]$ConsecutiveFailures,
        [string]$LastToastAt
    )
    if ($ConsecutiveFailures -lt $ToastAfterFailures) { return $false }
    if ([string]::IsNullOrWhiteSpace($LastToastAt)) { return $true }
    try {
        $last = [datetime]::Parse($LastToastAt)
        return ((Get-Date) - $last).TotalMinutes -ge $ToastCooldownMinutes
    } catch {
        return $true
    }
}

if (Test-WatchdogAlreadyRunning) {
    if ($Foreground) {
        Write-Host "CiM live watchdog already running (see $pidFile)."
    }
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$PID | Set-Content -LiteralPath $pidFile -Encoding ASCII

Write-WatchdogLine "=== CiM live watchdog loop START pid=$PID interval=${IntervalMinutes}m ==="
$consecutiveFailures = 0
$lastToastAt = $null
if (Test-Path -LiteralPath $toastStateFile) {
    try {
        $ts = Get-Content -LiteralPath $toastStateFile -Raw | ConvertFrom-Json
        $lastToastAt = [string]$ts.lastToastAt
        $consecutiveFailures = [int]$ts.consecutiveFailures
    } catch { }
}

try {
    while ($true) {
        $logBlock = {
            param($Msg, $Lvl)
            Write-WatchdogLine $Msg $Lvl
        }
        $result = & $healScript -WebRoot $WebRoot -LogFn $logBlock

        if ($result.OverallOk) {
            $consecutiveFailures = 0
            $level = "OK"
        } else {
            $consecutiveFailures++
            $level = "FAIL"
        }

        $summary = @(
            "overall=$($result.OverallOk)",
            "webLocal=$($result.WebLocalOk)",
            "webPublic=$($result.WebPublicOk)",
            "mobileLocal=$($result.MobileLocalOk)",
            "mobilePublic=$($result.MobilePublicOk)",
            "heal=$($result.HealAction)",
            "failStreak=$consecutiveFailures"
        ) -join " | "
        Write-WatchdogLine $summary $level

        if (Test-ShouldSendToast -ConsecutiveFailures $consecutiveFailures -LastToastAt $lastToastAt) {
            $sent = Send-CiMWatchdogToast -Message "Live client link unhealthy - see live-watchdog.log"
            if ($sent) {
                $lastToastAt = (Get-Date).ToString("o")
                Write-WatchdogLine "Toast sent (failStreak=$consecutiveFailures)" "WARN"
            }
        }

        Write-WatchdogStatus -Result $result -ConsecutiveFailures $consecutiveFailures -LastToastAt $lastToastAt
        @{
            lastToastAt = $lastToastAt
            consecutiveFailures = $consecutiveFailures
        } | ConvertTo-Json | Set-Content -LiteralPath $toastStateFile -Encoding UTF8

        Start-Sleep -Seconds ([math]::Max(60, $IntervalMinutes * 60))
    }
} finally {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-WatchdogLine "=== CiM live watchdog loop END ==="
}
