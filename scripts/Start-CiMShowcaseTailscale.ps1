#Requires -Version 5.1
<#
.SYNOPSIS
  Start CiM showcase with a stable public URL via Tailscale Funnel (live) or local testbed only.

.DESCRIPTION
  Live install (D:\CiM\Client): public HTTPS via Tailscale Funnel on port 8001.
  Testbed (D:\CiM\Client_Test): local port 8002 only - does NOT enable public Funnel
  (that would replace the production URL for all users).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [int]$Port = 0,
    [int]$WaitForEnableMinutes = 8
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMShowcasePublicUrl.ps1")
. (Join-Path $ScriptDir "Get-CiMShowcaseInstallSettings.ps1")

if ($InstallRoot -match 'Client\\scripts$') {
    $InstallRoot = Split-Path -Parent $InstallRoot
}
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = "D:\CiM\Client"
}
$InstallRoot = $InstallRoot.Trim().Trim('"').TrimEnd('\')
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)

$repoRoot = Split-Path -Parent $ScriptDir
$settings = Get-CiMShowcaseInstallSettings -InstallRoot $InstallRoot -RepoRoot $repoRoot
if ($Port -le 0) { $Port = [int]$settings.port }

$logDir = Join-Path $InstallRoot "runtime\logs"
$urlFile = Join-Path $logDir "public-url.txt"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    if ($settings.role -eq 'testbed') {
        Write-Host "Tailscale not installed - starting testbed on http://127.0.0.1:$Port only." -ForegroundColor Yellow
    } else {
        throw "Tailscale CLI not found. Install Tailscale for Windows and sign in on this PC."
    }
}

$startShowcase = Join-Path $ScriptDir "Start-CiMShowcase.ps1"
if (-not (Test-Path -LiteralPath $startShowcase)) {
    $startShowcase = Join-Path $repoRoot "scripts\Start-CiMShowcase.ps1"
}

$funnelScript = Join-Path $ScriptDir "Enable-CiMShowcaseFunnel.ps1"
if (-not (Test-Path -LiteralPath $funnelScript)) {
    $funnelScript = Join-Path $repoRoot "scripts\Enable-CiMShowcaseFunnel.ps1"
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*cloudflared*tunnel*' } |
    ForEach-Object {
        Write-Host "Stopping cloudflared quick tunnel PID $($_.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "=== CiM showcase ($($settings.label)) ===" -ForegroundColor Cyan
Write-Host "  Install: $InstallRoot"
Write-Host "  Port: $Port"
& $startShowcase -InstallRoot $InstallRoot -Port $Port

if ($settings.role -eq 'testbed' -or $settings.publicAccess -eq 'local') {
    $localUrl = "http://127.0.0.1:$Port/"
    Write-Host ""
    Write-Host "TESTBED - public Tailscale Funnel is NOT enabled from this folder." -ForegroundColor Yellow
    Write-Host "  (Enabling Funnel here would redirect the production HTTPS URL away from live users.)"
    Write-Host ""
    Write-Host "Local test URLs:" -ForegroundColor Green
    Write-Host "  App:      $localUrl"
    Write-Host "  Operator: http://127.0.0.1:$Port/?operator=1"

    if (Get-Command tailscale -ErrorAction SilentlyContinue) {
        Write-Host ""
        Write-Host "Optional: Tailscale tailnet-only (no public internet) on port $Port..." -ForegroundColor DarkGray
        & $funnelScript -Port $Port -ServeOnly -UrlFile $urlFile 2>&1 | Out-Null
    }

    Save-CiMShowcaseClientLinkFiles -InstallRoot $InstallRoot -PublicUrl $localUrl -Role testbed

    Write-Host ""
    Write-Host "Production clients: use D:\CiM\Client\start_showcase_tailscale.bat"
    Write-Host "Stop testbed: stop_showcase_tailscale.bat (does not clear live Funnel)"
    exit 0
}

Write-Host "=== CiM live showcase (Tailscale public Funnel) ===" -ForegroundColor Cyan
& $funnelScript -Port $Port -WaitForEnableMinutes $WaitForEnableMinutes -OpenEnableLink -UrlFile $urlFile -InstallRoot $InstallRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Share this link with production clients:" -ForegroundColor Green
if (Test-Path -LiteralPath (Join-Path $InstallRoot "SHOWCASE_CLIENT_LINK.txt")) {
    Get-Content -LiteralPath (Join-Path $InstallRoot "SHOWCASE_CLIENT_LINK.txt")
} elseif (Test-Path -LiteralPath $urlFile) {
    Get-Content -LiteralPath $urlFile
} else {
    Get-CiMShowcaseTailscalePublicUrl
}
Write-Host ""
Write-Host "Stop: stop_showcase_tailscale.bat"
exit 0
