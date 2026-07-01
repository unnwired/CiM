#Requires -Version 5.1
<#
.SYNOPSIS
  Register a Windows scheduled task to keep live web + mobile + funnel healthy.

.DESCRIPTION
  OPTIONAL / DEPRECATED for most hosts: Task Scheduler did not fire reliably on some PCs.
  Preferred path: Start-Live-WebAndMobile.bat spawns Start-CiMLiveWatchdog.ps1 (background loop).

  When used, runs Watch-CiMLiveServices.ps1 every N minutes (one-shot heal per run).
  Requires Administrator once at install time.
#>
[CmdletBinding()]
param(
    [string]$TaskName = "CiM-LiveServices-Watchdog",
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
$watch = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "Watch-CiMLiveServices.ps1"
if (-not (Test-Path -LiteralPath $watch)) {
    throw "Missing $watch"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$watch`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Registered scheduled task '$TaskName' (every ${IntervalMinutes}m)." -ForegroundColor Green
Write-Host "Runs: $watch" -ForegroundColor DarkGray
