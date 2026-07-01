#Requires -Version 5.1
<#
.SYNOPSIS
  Verify web live/testbed and mobile live/testbed run on independent ports without cross-wiring.
#>
[CmdletBinding()]
param(
    [switch]$RequireAllListening
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMDeployPairing.ps1")

function Test-CiMDeployPortListening {
    param([int]$Port)
    if ($Port -le 0) { return $false }
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return [bool](netstat -ano | Select-String ":\s*$Port\s+.*LISTENING")
    }
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 12
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Read-MobileHostJson {
    param([string]$Root)
    $path = Join-Path $Root "mobile-host.json"
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

$failures = @()
$live = Get-CiMWebMobilePairing -Tier live
$test = Get-CiMWebMobilePairing -Tier testbed

$checks = @(
    @{ Name = 'live web port'; Port = $live.WebPort; Url = "$($live.WebLocalUrl)"; Tier = 'live' }
    @{ Name = 'live mobile port'; Port = $live.MobilePort; Url = $live.MobileLocalUrl; Tier = 'live' }
    @{ Name = 'testbed web port'; Port = $test.WebPort; Url = "$($test.WebLocalUrl)"; Tier = 'testbed' }
    @{ Name = 'testbed mobile port'; Port = $test.MobilePort; Url = $test.MobileLocalUrl; Tier = 'testbed' }
)

Write-Host '=== CiM deploy independence check ===' -ForegroundColor Cyan

foreach ($c in $checks) {
    $listening = Test-CiMDeployPortListening -Port $c.Port
    $httpOk = $false
    if ($listening) {
        $httpOk = Test-HttpOk -Url $c.Url
    }

    $status = if ($listening -and $httpOk) { 'OK' } elseif ($listening) { 'LISTEN (HTTP check failed)' } else { 'DOWN' }
    $color = if ($status -eq 'OK') { 'Green' } elseif ($status -like 'LISTEN*') { 'Yellow' } else { 'DarkGray' }
    Write-Host ("  {0,-22} port {1} -> {2}" -f $c.Name, $c.Port, $status) -ForegroundColor $color

    if ($RequireAllListening -and -not $listening) {
        $failures += "$($c.Name) not listening on port $($c.Port)"
    }
}

foreach ($tierName in @('live', 'testbed')) {
    $pair = Get-CiMWebMobilePairing -Tier $tierName
    $hostJson = Read-MobileHostJson -Root $pair.MobileRoot
    if (-not $hostJson) {
        $failures += "Missing mobile-host.json under $($pair.MobileRoot)"
        continue
    }
    $upstream = [string]$hostJson.apiUpstream
    $mobilePort = [int]$hostJson.mobilePort
    if ($mobilePort -ne $pair.MobilePort) {
        $failures += "$tierName mobile-host.json mobilePort=$mobilePort expected $($pair.MobilePort)"
    }
    if ($upstream -ne $pair.ApiUpstream) {
        $failures += "$tierName mobile-host.json apiUpstream=$upstream expected $($pair.ApiUpstream)"
    } else {
        Write-Host "  $tierName API pairing OK: mobile $mobilePort -> $upstream" -ForegroundColor Green
    }
}

$pairedLiveMobile = Resolve-CiMPairedMobilePort -WebPort $live.WebPort
if ($pairedLiveMobile -ne 0 -and $pairedLiveMobile -ne $live.MobilePort) {
    $failures += "Resolve-CiMPairedMobilePort returned $pairedLiveMobile instead of $($live.MobilePort)"
}

$pairedTestbed = Resolve-CiMPairedMobilePort -WebPort $test.WebPort
if ($pairedTestbed -ne 0) {
    $failures += "Testbed web must not register public mobile route (got port $pairedTestbed)"
} else {
    Write-Host '  testbed public funnel blocked OK' -ForegroundColor Green
}

$requiredScripts = @(
    "D:\CiM\Client\scripts\Enable-CiMTailscalePublicRoutes.ps1",
    "D:\CiM\Client\scripts\Get-CiMDeployPairing.ps1"
)
foreach ($path in $requiredScripts) {
    if (-not (Test-Path -LiteralPath $path)) {
        $failures += "Missing synced script: $path"
    }
}

if ($failures.Count -gt 0) {
    Write-Host ''
    Write-Host '[FAIL] Deploy independence check failed:' -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" -ForegroundColor Red }
    exit 1
}

Write-Host ''
Write-Host '[OK] Deploy independence check passed.' -ForegroundColor Green
exit 0
