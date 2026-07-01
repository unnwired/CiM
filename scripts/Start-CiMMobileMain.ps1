#Requires -Version 5.1
<#
.SYNOPSIS
  Start CiM Mobile live (8011) and register public /mobile without resetting web funnel.

.DESCRIPTION
  1. Ensures web live backend is running (8001) — required for API
  2. Starts mobile_proxy.py in background on 8011
  3. Registers Tailscale /mobile path (UpdateMobileOnly — web / stays intact)
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Mobile_Main",
    [switch]$SkipFunnel,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($InstallRoot)
Set-Location -LiteralPath $Root

$ScriptDir = Join-Path $Root "scripts"
$logDir = Join-Path $Root "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

. (Join-Path $ScriptDir "Get-CiMDeployPairing.ps1")
$pair = Get-CiMWebMobilePairing -Tier live

$configPath = Join-Path $Root "mobile-host.json"
$config = @{ mobilePort = $pair.MobilePort; apiUpstream = $pair.ApiUpstream }
if (Test-Path -LiteralPath $configPath) {
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
}
$mobilePort = [int]$config.mobilePort

function Test-PortListening {
    param([int]$Port)
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return [bool](netstat -ano | Select-String ":\s*$Port\s+.*LISTENING")
    }
}

function Ensure-WebLiveBackend {
    if (Test-PortListening -Port $pair.WebPort) {
        Write-Host "Web live backend already on port $($pair.WebPort)." -ForegroundColor DarkGray
        return
    }
    Write-Host "Web live backend not on port $($pair.WebPort)." -ForegroundColor Yellow
    Write-Host "  Start D:\CiM\Client\start_showcase_tailscale.bat first (mobile API needs web backend)." -ForegroundColor Yellow
    $startShowcase = Join-Path $pair.WebRoot "scripts\Start-CiMShowcase.ps1"
    if (-not (Test-Path -LiteralPath $startShowcase)) {
        throw "Web live not running and missing $startShowcase"
    }
    Write-Host "Starting web live backend on port $($pair.WebPort)..." -ForegroundColor Cyan
    & $startShowcase -InstallRoot $pair.WebRoot -Port $pair.WebPort
    if ($LASTEXITCODE -ne 0) { throw "Web live start failed (exit $LASTEXITCODE)" }
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $pair.WebPort) { return }
        Start-Sleep -Seconds 2
    }
    throw "Web live did not start on port $($pair.WebPort) within 90s"
}

function Start-MobileProxyBackground {
    if (Test-PortListening -Port $mobilePort) {
        Write-Host "Mobile proxy already listening on port $mobilePort." -ForegroundColor DarkGray
        return
    }
    $proxy = Join-Path $Root "mobile_proxy.py"
    if (-not (Test-Path -LiteralPath $proxy)) {
        throw "Missing mobile_proxy.py"
    }
    $dist = Join-Path $Root "dist\index.html"
    if (-not (Test-Path -LiteralPath $dist)) {
        throw "Missing dist/index.html. Promote from Mobile_Testbed first."
    }

    $outLog = Join-Path $logDir "mobile-proxy.log"
    $errLog = Join-Path $logDir "mobile-proxy.err.log"
    $pidFile = Join-Path $logDir "mobile-proxy.pid"

    Write-Host "Starting mobile MAIN proxy on port $mobilePort -> $($config.apiUpstream)..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath "python" `
        -ArgumentList @($proxy) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru
    Set-Content -LiteralPath $pidFile -Value $proc.Id -Encoding UTF8

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $mobilePort) {
            Write-Host "Mobile proxy started (PID $($proc.Id))." -ForegroundColor Green
            return
        }
        if ($proc.HasExited) {
            $err = ""
            if (Test-Path -LiteralPath $errLog) { $err = Get-Content -LiteralPath $errLog -Raw -ErrorAction SilentlyContinue }
            throw "Mobile proxy exited early. $err"
        }
        Start-Sleep -Seconds 1
    }
    throw "Mobile proxy did not bind port $mobilePort within 30s"
}

Write-Host "=== CiM Mobile MAIN (live) ===" -ForegroundColor Cyan
Write-Host "  Root: $Root"
Write-Host "  Mobile: port $mobilePort"
Write-Host "  API:    $($config.apiUpstream)"

Ensure-WebLiveBackend
Start-MobileProxyBackground

$localUrl = "http://127.0.0.1:$mobilePort/mobile/"
Set-Content -LiteralPath (Join-Path $Root "MOBILE_CLIENT_LINK.txt") -Value $localUrl -Encoding UTF8

if (-not $SkipFunnel -and (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    $funnelScript = Join-Path $ScriptDir "Enable-CiMMobileFunnel.ps1"
    if (Test-Path -LiteralPath $funnelScript) {
        Write-Host "Registering public /mobile (does not reset web /)..." -ForegroundColor Cyan
        & $funnelScript -InstallRoot $Root
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Funnel registration failed - local mobile still works at $localUrl" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Missing Enable-CiMMobileFunnel.ps1 - run from Client after web funnel is up." -ForegroundColor Yellow
    }
} elseif (-not $SkipFunnel) {
    Write-Host "Tailscale not installed - local only: $localUrl" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Local mobile:  $localUrl" -ForegroundColor Green
Write-Host "Local web:     $($pair.WebLocalUrl)" -ForegroundColor Green
Write-Host "Web and mobile run in parallel on ports $($pair.WebPort) + $mobilePort." -ForegroundColor Green

if ($OpenBrowser) {
    Start-Process $localUrl | Out-Null
}

exit 0
