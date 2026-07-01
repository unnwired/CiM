#Requires -Version 5.1
<#
.SYNOPSIS
  True idle test: no HTTP traffic until after WaitMinutes, then probe once.
#>
[CmdletBinding()]
param(
    [int]$WaitMinutes = 42,
    [string]$PublicMobileUrl = "https://charts-in-motion.tail22251c.ts.net/mobile/",
    [string]$LogFile = "D:\CiM\Mobile_Main\runtime\logs\idle-test.log"
)

$ErrorActionPreference = "Continue"
$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

function Log([string]$Msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Msg
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

Log "IDLE TEST START: no probes for ${WaitMinutes}m"
Log "Sleeping until $((Get-Date).AddMinutes($WaitMinutes).ToString('HH:mm:ss')) ..."
Start-Sleep -Seconds ($WaitMinutes * 60)

Log "=== POST-IDLE PROBE ==="
foreach ($label in @(
    @{ Name = "local8011"; Url = "http://127.0.0.1:8011/mobile/" },
    @{ Name = "localApi"; Url = "http://127.0.0.1:8011/mobile/api/health" },
    @{ Name = "web8001"; Url = "http://127.0.0.1:8001/api/health" },
    @{ Name = "publicMobile"; Url = $PublicMobileUrl }
)) {
    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $r = Invoke-WebRequest -Uri $label.Url -UseBasicParsing -TimeoutSec 35
        Log ("{0}: HTTP {1} in {2}ms" -f $label.Name, $r.StatusCode, [int]$sw.ElapsedMilliseconds)
    } catch {
        Log ("{0}: FAIL - {1}" -f $label.Name, $_.Exception.Message)
    }
}

if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    Log ("funnel:`n" + (tailscale funnel status 2>&1 | Out-String).Trim())
}

Log "IDLE TEST END"
