#Requires -Version 5.1
<#
.SYNOPSIS
  Register or remove the Windows Scheduled Task for daily showcase EOD bhavcopy reconcile.

.DESCRIPTION
  Creates task "Charts In Motion Showcase EOD" — daily trigger aligned to 16:00 IST.
  Runs scripts\Run-CiMShowcaseEodOnce.ps1 (retries until 16:30 IST or success).

.EXAMPLE
  .\Register-CiMShowcaseEodTask.ps1
  .\Register-CiMShowcaseEodTask.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$InstallRoot = "",
    [string]$TaskName = "Charts In Motion Showcase EOD",
    [int]$StartHourIst = 16,
    [int]$StartMinuteIst = 0,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }

. (Join-Path $ScriptDir "Get-CiMShowcaseDeployConfig.ps1")

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "Task not registered: $TaskName" -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName" -ForegroundColor Green
    exit 0
}

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
    $InstallRoot = $cfg.showcaseLiveInstallRoot
}
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))

$runner = Join-Path $ScriptDir "Run-CiMShowcaseEodOnce.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing $runner"
}

try {
    $InstallRoot = Test-CiMShowcaseInstallRoot -InstallRoot $InstallRoot
} catch {
    Write-Warning "Install root validation: $_"
    Write-Warning "Task will still be registered; ensure showcase is deployed to $InstallRoot before EOD runs."
}

function Get-LocalTimeForIstToday {
    param([int]$HourIst, [int]$MinuteIst)
    $utc = [DateTime]::UtcNow
    $istNow = $utc.AddHours(5.5)
    $istTarget = Get-Date -Year $istNow.Year -Month $istNow.Month -Day $istNow.Day -Hour $HourIst -Minute $MinuteIst -Second 0
    $utcTarget = $istTarget.AddHours(-5.5)
    return [DateTime]::SpecifyKind($utcTarget, [DateTimeKind]::Utc).ToLocalTime()
}

$localStart = Get-LocalTimeForIstToday -HourIst $StartHourIst -MinuteIst $StartMinuteIst
$atString = $localStart.ToString("HH:mm")

$tz = [TimeZoneInfo]::Local
$istZone = [TimeZoneInfo]::FindSystemTimeZoneById("India Standard Time")
$isIst = ($tz.Id -eq $istZone.Id)
if (-not $isIst) {
    Write-Host "Note: PC timezone is '$($tz.Id)' — task trigger $atString local = $StartHourIst`:$('{0:D2}' -f $StartMinuteIst) IST today." -ForegroundColor Cyan
    Write-Host "      Run-CiMShowcaseEodOnce.ps1 still enforces the 16:00–16:30 IST retry window." -ForegroundColor Cyan
} else {
    Write-Host "Registering daily EOD at $StartHourIst`:$('{0:D2}' -f $StartMinuteIst) IST ($atString local)" -ForegroundColor Cyan
}

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`" -InstallRoot `"$InstallRoot`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $ScriptDir

$trigger = New-ScheduledTaskTrigger -Daily -At $atString
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily NSE bhavcopy EOD reconcile for Charts In Motion browser showcase host ($InstallRoot). Window 16:00-16:30 IST." | Out-Null

Write-Host "Registered scheduled task: $TaskName" -ForegroundColor Green
Write-Host "  Install root: $InstallRoot"
Write-Host "  Script: $runner"
Write-Host "  Log: $InstallRoot\runtime\logs\showcase-eod-scheduled.log"
Write-Host ""
Write-Host "Test now: powershell -ExecutionPolicy Bypass -File `"$runner`" -InstallRoot `"$InstallRoot`""
Write-Host 'Remove:   .\Register-CiMShowcaseEodTask.ps1 -Unregister'
