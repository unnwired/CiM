#Requires -Version 5.1
<#
.SYNOPSIS
  Expose CiM showcase (port 8001) via Tailscale Serve + Funnel — stable public HTTPS URL.

.DESCRIPTION
  Tailnet (Tailscale app required):  tailscale serve
  Public browser (no client app):    tailscale funnel  -> https://YOUR-MACHINE.tailXXXX.ts.net

  Funnel requires a one-time approval in your browser (Tailscale admin). Do not share passwords;
  open the printed login.tailscale.com/f/funnel link while signed in as tailnet owner/admin.
#>
[CmdletBinding()]
param(
    [int]$Port = 8001,
    [switch]$ServeOnly,
    [switch]$OpenEnableLink,
    [int]$WaitForEnableMinutes = 0,
    [string]$UrlFile = "",
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMShowcasePublicUrl.ps1")

function Get-TailscaleMachineUrl {
    try {
        $json = tailscale status --json 2>&1 | ConvertFrom-Json
        $dns = [string]$json.Self.DNSName
        if ([string]::IsNullOrWhiteSpace($dns)) { return $null }
        return ("https://{0}/" -f $dns.TrimEnd('.'))
    } catch {
        return $null
    }
}

function Test-TailscaleFunnelPublic {
    $status = tailscale funnel status 2>&1 | Out-String
    if ($status -match 'tailnet only') { return $false }
    if ($status -match '\(Funnel on\)|available on the internet') { return $true }

    $url = Get-TailscaleMachineUrl
    if (-not $url) { return $false }
    $hostName = ([Uri]$url).Host
    $ns = nslookup $hostName 8.8.8.8 2>&1 | Out-String
    return ($ns -notmatch 'Non-existent domain|NXDOMAIN|can''t find')
}

function Invoke-TailscaleFunnelCommand {
    param([int]$ListenPort)
    $job = Start-Job -ScriptBlock {
        param($p)
        & tailscale funnel --bg --yes $p 2>&1 | Out-String
    } -ArgumentList $ListenPort
    $completed = Wait-Job -Job $job -Timeout 25
    $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
    if (-not $completed) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        $output = ($output | Out-String) + "`n(timed out waiting for tailscale funnel; may still need browser approval)"
    }
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    return [string]$output
}

function Save-PublicUrl {
    param([string]$Path, [string]$Url, [string]$Root)
    if ([string]::IsNullOrWhiteSpace($Url)) { return }
    if (-not [string]::IsNullOrWhiteSpace($Root)) {
        Save-CiMShowcaseClientLinkFiles -InstallRoot $Root -PublicUrl $Url
        return
    }
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    Set-Content -LiteralPath $Path -Value $Url.TrimEnd('/') -Encoding UTF8
}

$publicUrl = Get-TailscaleMachineUrl
if (-not $publicUrl) {
    throw "Tailscale is not running or MagicDNS name is unavailable. Open the Tailscale app and ensure this PC is connected."
}

if ($ServeOnly) {
    Write-Host "=== Tailscale Serve (tailnet HTTPS) ===" -ForegroundColor Cyan
    tailscale serve reset 2>&1 | Out-Null
    tailscale serve --bg --yes $Port 2>&1
    tailscale serve status 2>&1
    Write-Host ""
    Write-Host "Tailnet URL (clients need Tailscale app): $publicUrl" -ForegroundColor Yellow
    Save-PublicUrl -Path $UrlFile -Url $publicUrl -Root $InstallRoot
    exit 0
}

. (Join-Path $ScriptDir "Get-CiMDeployPairing.ps1")

$tier = Get-CiMDeployTierForWebPort -WebPort $Port
if ($tier -eq 'testbed') {
    Write-Host "Testbed web port $Port - public Funnel is not enabled (local only)." -ForegroundColor Yellow
    exit 0
}

$pair = Get-CiMWebMobilePairing -Tier live
$routesScript = Join-Path $ScriptDir "Enable-CiMTailscalePublicRoutes.ps1"
if (-not (Test-Path -LiteralPath $routesScript)) {
    $routesScript = Join-Path (Split-Path -Parent $ScriptDir) "scripts\Enable-CiMTailscalePublicRoutes.ps1"
}
if (-not (Test-Path -LiteralPath $routesScript)) {
    throw "Missing Enable-CiMTailscalePublicRoutes.ps1"
}

Write-Host "=== Tailscale Funnel (live web / + live mobile /mobile) ===" -ForegroundColor Cyan
& $routesScript `
    -WebPort $pair.WebPort `
    -MobilePort $pair.MobilePort `
    -ResetFirst `
    -WaitForMobileSeconds 45 `
    -WaitForEnableMinutes $WaitForEnableMinutes `
    -OpenEnableLink:$OpenEnableLink `
    -WebInstallRoot $InstallRoot `
    -MobileInstallRoot $pair.MobileRoot
exit $LASTEXITCODE

