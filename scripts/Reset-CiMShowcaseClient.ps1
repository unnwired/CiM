#Requires -Version 5.1
<#
.SYNOPSIS
  Reset D:\CiM\Client showcase to a fresh Sign in page (no E2E / stale sessions).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [int]$Port = 8001,
    [switch]$SkipRestart
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = $InstallRoot.Trim().Trim('"').TrimEnd('\')
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)

function Stop-ShowcaseProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                ($_.CommandLine -like "*:$Port*" -and $_.CommandLine -like "*cim_bootstrap*") -or
                ($_.CommandLine -like '*cloudflared*tunnel*')
            )
        } |
        ForEach-Object {
            Write-Host "Stopping PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    if (Get-Command tailscale -ErrorAction SilentlyContinue) {
        tailscale funnel off 2>&1 | Out-Null
        tailscale serve reset 2>&1 | Out-Null
    }
    Start-Sleep -Seconds 2
}

Write-Host "=== Reset CiM showcase client ($InstallRoot) ===" -ForegroundColor Cyan
Stop-ShowcaseProcesses

$dataDir = Join-Path $InstallRoot "data"
$configDir = Join-Path $InstallRoot "config"
foreach ($rel in @(
        "data\.cim-session.json",
        "data\.cim-license.json",
        "data\.cim-license",
        "config\.cim-web-host"
    )) {
    $path = Join-Path $InstallRoot ($rel -replace '/', '\')
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        Write-Host "Removed $rel"
    }
}

$sessionsDir = Join-Path $dataDir "sessions"
if (Test-Path -LiteralPath $sessionsDir) {
    Remove-Item -LiteralPath $sessionsDir -Recurse -Force
    Write-Host "Removed data/sessions/"
}

$usersDir = Join-Path $dataDir "users"
if (Test-Path -LiteralPath $usersDir) {
    Get-ChildItem -LiteralPath $usersDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like '*cim-e2e*' -or $_.Name -like '*_at_example.com' } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
            Write-Host "Removed E2E user dir $($_.Name)"
        }
}

$defaults = @{
    "watchlists.json"   = "[]"
    "portfolio.json"    = '{"items":[]}'
    "layout.json"       = "{}"
    "saved_filters.json" = "[]"
}
foreach ($name in $defaults.Keys) {
    $path = Join-Path $dataDir $name
    Set-Content -LiteralPath $path -Value $defaults[$name] -Encoding UTF8
}

if (-not $SkipRestart) {
    $start = Join-Path $ScriptDir "Start-CiMShowcaseTailscale.ps1"
    if (-not (Test-Path -LiteralPath $start)) {
        $start = Join-Path $ScriptDir "Start-CiMShowcase.ps1"
    }
    & $start -InstallRoot $InstallRoot -Port $Port
}

try {
    $signIn = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 20
    if ($signIn.Content -notmatch 'Sign in') {
        throw "Expected Sign in page at /"
    }
    Write-Host "OK: fresh Sign in page at http://127.0.0.1:$Port/" -ForegroundColor Green
} catch {
    Write-Host "WARN: could not verify Sign in page (backend may still be starting): $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host "Showcase client reset complete."
