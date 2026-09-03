#Requires -Version 5.1
<#
.SYNOPSIS
  Register scheduled tasks to heal Tailscale Funnel after sleep, logon, or startup.

.DESCRIPTION
  Prevents public CiM links from staying broken when the host PC wakes from sleep or
  sits idle. Requires Administrator once at install time.

  Triggers:
    - At logon (any user session)
    - At system startup
    - System resumed from sleep (Power-Troubleshooter event 1)
#>
[CmdletBinding()]
param(
    [string]$TaskName = "CiM-Live-ResumeHeal",
    [string]$WebRoot = "D:\CiM\Client",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$WebRoot = [System.IO.Path]::GetFullPath($WebRoot.Trim().TrimEnd('\'))
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resumeScript = Join-Path $ScriptDir "Resume-CiMLiveServices.ps1"
if (-not (Test-Path -LiteralPath $resumeScript)) {
    throw "Missing $resumeScript"
}

$argLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$resumeScript`" -WebRoot `"$WebRoot`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine

$triggers = @(
    New-ScheduledTaskTrigger -AtLogOn
    New-ScheduledTaskTrigger -AtStartup
)

$eventTriggerXml = @"
<Triggers>
  <EventTrigger>
    <Enabled>true</Enabled>
    <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Microsoft-Windows-Power-Troubleshooter/Operational"&gt;&lt;Select Path="Microsoft-Windows-Power-Troubleshooter/Operational"&gt;*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    <Delay>PT30S</Delay>
  </EventTrigger>
</Triggers>
"@

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $triggers `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null

    # Add event trigger via schtasks XML merge (Register-ScheduledTask event triggers are awkward in PS 5.1)
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $taskXml = [xml](Export-ScheduledTask -TaskName $TaskName)
    $ns = New-Object System.Xml.XmlNamespaceManager($taskXml.NameTable)
    $ns.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")

    $triggersNode = $taskXml.SelectSingleNode("//t:Triggers", $ns)
    if ($triggersNode) {
        $eventFragment = [xml]$eventTriggerXml
        $imported = $taskXml.ImportNode($eventFragment.DocumentElement.ChildNodes[0], $true)
        $triggersNode.AppendChild($imported) | Out-Null
        $taskXml.OuterXml | Out-File -FilePath "$env:TEMP\cim-resume-heal-task.xml" -Encoding Unicode
        Register-ScheduledTask -TaskName $TaskName -Xml (Get-Content "$env:TEMP\cim-resume-heal-task.xml" -Raw) -Force | Out-Null
        Remove-Item "$env:TEMP\cim-resume-heal-task.xml" -Force -ErrorAction SilentlyContinue
    }

    if (-not $Quiet) {
        Write-Host "Registered '$TaskName' (logon + startup + resume-from-sleep)." -ForegroundColor Green
        Write-Host "Runs: $resumeScript" -ForegroundColor DarkGray
        Write-Host "Log:  $WebRoot\runtime\logs\live-resume-heal.log" -ForegroundColor DarkGray
    }
} catch {
    if (-not $Quiet) {
        Write-Host "Could not register scheduled task (run this script as Administrator):" -ForegroundColor Yellow
        Write-Host $_.Exception.Message -ForegroundColor Red
        Write-Host "You can still run manually after sleep: $resumeScript" -ForegroundColor DarkGray
    }
    exit 1
}

exit 0
