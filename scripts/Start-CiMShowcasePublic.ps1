#Requires -Version 5.1
<#
.SYNOPSIS
  Start CiM showcase + public HTTPS URL via Cloudflare Quick Tunnel (no Tailscale policy, no domain).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [int]$Port = 8001,
    [string]$Cloudflared = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($InstallRoot -match 'Client\\scripts$') {
    $InstallRoot = Split-Path -Parent $InstallRoot
}
$InstallRoot = $InstallRoot.Trim().Trim('"').TrimEnd('\')
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)

if (-not $Cloudflared) {
    foreach ($c in @(
            "$env:ProgramFiles\cloudflared\cloudflared.exe",
            "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
        )) {
        if (Test-Path -LiteralPath $c) { $Cloudflared = $c; break }
    }
}
if (-not $Cloudflared) {
    $Cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
}
if (-not $Cloudflared) {
    throw "cloudflared not found. Install: winget install Cloudflare.cloudflared"
}

$logDir = Join-Path $InstallRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$tunnelLog = Join-Path $logDir "cloudflared-quick.log"
$urlFile = Join-Path $logDir "public-url.txt"
$pidFile = Join-Path $logDir "cloudflared-quick.pid"

function Stop-QuickTunnel {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*cloudflared*tunnel*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $pidFile) {
        $old = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($old -match '^\d+$') { Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
}

$startScript = Join-Path $ScriptDir "Start-CiMShowcase.ps1"
if (-not (Test-Path -LiteralPath $startScript)) {
    $startScript = Join-Path (Split-Path -Parent $ScriptDir) "scripts\Start-CiMShowcase.ps1"
    if (-not (Test-Path -LiteralPath $startScript)) {
        $startScript = "D:\Programs\NSE Pulse\Claude Ai\scripts\Start-CiMShowcase.ps1"
    }
}

Write-Host "=== CiM public showcase (Cloudflare Quick Tunnel) ===" -ForegroundColor Cyan
& $startScript -InstallRoot $InstallRoot -Port $Port

Stop-QuickTunnel
"" | Set-Content -LiteralPath $tunnelLog -Encoding UTF8

$p = Start-Process -FilePath $Cloudflared -ArgumentList @(
    'tunnel', '--url', "http://127.0.0.1:$Port",
    '--logfile', $tunnelLog,
    '--loglevel', 'info'
) -PassThru -WindowStyle Hidden

$p.Id | Set-Content -LiteralPath $pidFile -Encoding ASCII
Write-Host "cloudflared PID: $($p.Id)"

$publicUrl = $null
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $tunnelLog) {
        $text = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
        if ($text -match '(https://[a-z0-9-]+\.trycloudflare\.com)/?') {
            $publicUrl = $Matches[1].TrimEnd('/')
            break
        }
    }
    Start-Sleep -Seconds 2
}

if (-not $publicUrl) {
    Write-Host "cloudflared log tail:" -ForegroundColor Red
    Get-Content -LiteralPath $tunnelLog -Tail 20 -ErrorAction SilentlyContinue
    throw "Could not read public URL from cloudflared (see $tunnelLog)"
}

Set-Content -LiteralPath $urlFile -Value $publicUrl -Encoding UTF8

Write-Host ""
Write-Host "Waiting for public URL to become reachable (DNS can take 15-45 seconds)..." -ForegroundColor Cyan
$publicOk = $false
$verifyDeadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $verifyDeadline) {
    try {
        $h = Invoke-RestMethod -Uri "$publicUrl/api/health" -TimeoutSec 15
        if ($h.status -eq 'ok') {
            $publicOk = $true
            Write-Host "Public health OK: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}

Write-Host ""
Write-Host "PUBLIC URL (share with clients):" -ForegroundColor Green
Write-Host "  $publicUrl"
Write-Host ""
Write-Host "Local test: http://127.0.0.1:$Port"
Write-Host "URL saved: $urlFile"
Write-Host "Stop everything: stop_showcase_public.bat"
if (-not $publicOk) {
    Write-Host ""
    Write-Host "Tunnel URL was created but is not reachable yet from this PC." -ForegroundColor Yellow
    Write-Host "Wait 30-60 seconds, then open the URL in your browser. Backend on 127.0.0.1:$Port is running." -ForegroundColor Yellow
    Write-Host "If it still fails, check antivirus/firewall blocking cloudflared." -ForegroundColor Yellow
}
