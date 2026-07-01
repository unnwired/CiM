#Requires -Version 5.1
<#
.SYNOPSIS
  Configure Tailscale Funnel path routing for CiM web + mobile on one public hostname.

.DESCRIPTION
  Web browser client:  https://YOUR-MACHINE.tailXXXX.ts.net/
  Mobile dashboard:    https://YOUR-MACHINE.tailXXXX.ts.net/mobile/

  Live only (web 8001 + mobile 8011). Testbed never registers public routes.
#>
[CmdletBinding()]
param(
    [int]$WebPort = 8001,
    [int]$MobilePort = 0,
    [string]$MobilePublicPath = "/mobile",
    [switch]$SkipMobileRoute,
    [switch]$ResetFirst,
    [switch]$UpdateMobileOnly,
    [int]$WaitForMobileSeconds = 0,
    [int]$WaitForEnableMinutes = 0,
    [switch]$OpenEnableLink,
    [string]$WebInstallRoot = "",
    [string]$MobileInstallRoot = ""
)

$ErrorActionPreference = "Continue"
$RoutesScriptDir = $PSScriptRoot
. (Join-Path $RoutesScriptDir "Get-CiMDeployPairing.ps1")

function Test-PortListening {
    param([int]$Port)
    if ($Port -le 0) { return $false }
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return [bool](netstat -ano | Select-String ":\s*$Port\s+.*LISTENING")
    }
}

function Get-TailscaleMachineUrl {
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) { return $null }
    try {
        $json = tailscale status --json 2>&1 | ConvertFrom-Json
        $dns = [string]$json.Self.DNSName
        if ([string]::IsNullOrWhiteSpace($dns)) { return $null }
        return ("https://{0}/" -f $dns.Trim().TrimEnd('.'))
    } catch {
        return $null
    }
}

function Test-TailscaleFunnelPublic {
    $status = tailscale funnel status 2>&1 | Out-String
    if ($status -match 'tailnet only') { return $false }
    if ($status -match '\(Funnel on\)|available on the internet|Funnel on') { return $true }

    $url = Get-TailscaleMachineUrl
    if (-not $url) { return $false }
    $hostName = ([Uri]$url).Host
    $ns = nslookup $hostName 8.8.8.8 2>&1 | Out-String
    return ($ns -notmatch 'Non-existent domain|NXDOMAIN|can''t find')
}

function Invoke-TailscaleFunnelArgs {
    param([string[]]$FunnelArgs)
    $job = Start-Job -ScriptBlock {
        param($argsList)
        & tailscale @argsList 2>&1 | Out-String
    } -ArgumentList (,$FunnelArgs)
    $completed = Wait-Job -Job $job -Timeout 25
    $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
    if (-not $completed) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        $output = ($output | Out-String) + "`n(timed out waiting for tailscale funnel)"
    }
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    return [string]$output
}

function Set-CiMTailscalePublicRoutes {
    param(
        [int]$WebPort,
        [int]$MobilePort,
        [string]$MobilePath,
        [bool]$IncludeMobile,
        [bool]$DoReset
    )

    if ($DoReset) {
        tailscale serve reset 2>&1 | Out-Null
        tailscale funnel reset 2>&1 | Out-Null
    }

    $webOut = Invoke-TailscaleFunnelArgs -FunnelArgs @('funnel', '--bg', '--yes', '--set-path=/', "$WebPort")
    Write-Host $webOut

    if ($IncludeMobile) {
        $target = "http://127.0.0.1:$MobilePort$MobilePath"
        $mobileOut = Invoke-TailscaleFunnelArgs -FunnelArgs @('funnel', '--bg', '--yes', "--set-path=$MobilePath", $target)
        Write-Host $mobileOut
    }

    tailscale funnel status 2>&1
}

function Save-CiMPublicLinkFiles {
    param(
        [string]$BaseUrl,
        [string]$WebRoot,
        [string]$MobileRoot,
        [string]$MobilePath,
        [bool]$MobileActive
    )
    if ([string]::IsNullOrWhiteSpace($BaseUrl)) { return }
    $base = $BaseUrl.Trim().TrimEnd('/')
    $webUrl = "$base/"
    $mobileUrl = "$base$MobilePath/"

    if ($WebRoot -and (Test-Path -LiteralPath $WebRoot)) {
        $linkBody = @(
            'Charts In Motion - browser client sign-in (HTTPS)'
            ''
            'Web client (desktop/tablet browser UI):'
            $webUrl
            ''
            'Mobile client (phone-optimized UI):'
            $mobileUrl
            if ($MobileActive) { '  (live mobile proxy on port 8011)' } else { '  (start Mobile_Main on 8011 to enable /mobile)' }
            ''
            'Same hostname, different paths - web and mobile do not replace each other.'
            ''
            'Testbed (local only): web http://127.0.0.1:8002/  mobile http://127.0.0.1:8010/mobile/'
            ''
            'After the host deploys an update, clients should hard refresh (Ctrl+Shift+R).'
            'Host operator only: Admin-Showcase.bat on the host PC (not this HTTPS link).'
        ) -join [Environment]::NewLine
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText((Join-Path $WebRoot 'SHOWCASE_CLIENT_LINK.txt'), $linkBody + [Environment]::NewLine, $utf8NoBom)
        $logDir = Join-Path $WebRoot 'runtime\logs'
        if (-not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }
        [System.IO.File]::WriteAllText((Join-Path $logDir 'public-url.txt'), $webUrl, $utf8NoBom)
    }

    if ($MobileRoot -and (Test-Path -LiteralPath $MobileRoot)) {
        $mobileHelper = Join-Path $RoutesScriptDir 'Get-CiMMobilePublicUrl.ps1'
        if (-not (Test-Path -LiteralPath $mobileHelper)) {
            $mobileHelper = Join-Path $MobileRoot 'scripts\Get-CiMMobilePublicUrl.ps1'
        }
        if (Test-Path -LiteralPath $mobileHelper) {
            . $mobileHelper
            Save-CiMMobileClientLinkFiles -InstallRoot $MobileRoot -PublicUrl $mobileUrl -WebUrl $webUrl
        }
    }
}

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    throw 'Tailscale CLI not found. Install Tailscale for Windows and sign in on this PC.'
}

$tier = Get-CiMDeployTierForWebPort -WebPort $WebPort
if ($tier -eq 'testbed') {
    Write-Host "Refusing public Tailscale routes for testbed web port $WebPort (local only)." -ForegroundColor Yellow
    Write-Host "  Web:    http://127.0.0.1:8002/"
    Write-Host "  Mobile: http://127.0.0.1:8010/mobile/"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($WebInstallRoot)) {
    $WebInstallRoot = Resolve-CiMPairedWebInstallRoot -WebPort $WebPort
}

$publicUrl = Get-TailscaleMachineUrl
if (-not $publicUrl) {
    throw 'Tailscale is not running or MagicDNS name is unavailable.'
}

$mobilePath = $MobilePublicPath.Trim()
if (-not $mobilePath.StartsWith('/')) { $mobilePath = "/$mobilePath" }

$activeMobilePort = 0
if (-not $SkipMobileRoute) {
    if ($WaitForMobileSeconds -gt 0) {
        $activeMobilePort = Wait-CiMPairedMobilePort -WebPort $WebPort -MaxWaitSeconds $WaitForMobileSeconds
    } else {
        $activeMobilePort = Resolve-CiMPairedMobilePort -WebPort $WebPort -RequestedMobilePort $MobilePort
    }
}

if ($UpdateMobileOnly) {
    if ($activeMobilePort -le 0) {
        Write-Host "Cannot update /mobile - live mobile proxy is not listening on port 8011." -ForegroundColor Red
        Write-Host "Start Mobile_Main first, then re-run Enable-CiMMobileFunnel.ps1" -ForegroundColor Yellow
        exit 1
    }
    if ([string]::IsNullOrWhiteSpace($MobileInstallRoot)) {
        $MobileInstallRoot = Resolve-CiMPairedMobileInstallRoot -WebPort $WebPort -MobilePort $activeMobilePort
    }
    Write-Host '=== CiM mobile /mobile path update (no funnel reset) ===' -ForegroundColor Cyan
    $target = "http://127.0.0.1:$activeMobilePort$mobilePath"
    $mobileOut = Invoke-TailscaleFunnelArgs -FunnelArgs @('funnel', '--bg', '--yes', "--set-path=$mobilePath", $target)
    Write-Host $mobileOut
    tailscale funnel status 2>&1
    Save-CiMPublicLinkFiles `
        -BaseUrl $publicUrl `
        -WebRoot $WebInstallRoot `
        -MobileRoot $MobileInstallRoot `
        -MobilePath $mobilePath `
        -MobileActive:$true
    Write-Host ''
    Write-Host "Mobile public URL: $($publicUrl.TrimEnd('/'))$mobilePath/" -ForegroundColor Green
    exit 0
}

if ($activeMobilePort -gt 0 -and [string]::IsNullOrWhiteSpace($MobileInstallRoot)) {
    $MobileInstallRoot = Resolve-CiMPairedMobileInstallRoot -WebPort $WebPort -MobilePort $activeMobilePort
}

Write-Host '=== CiM public path routing (Tailscale Funnel) ===' -ForegroundColor Cyan
Write-Host "  Tier:   live (web $WebPort + mobile 8011 only)"
Write-Host "  Web:    $publicUrl (port $WebPort)"
if ($activeMobilePort -gt 0) {
    Write-Host "  Mobile: $($publicUrl.TrimEnd('/'))$mobilePath/ (port $activeMobilePort)" -ForegroundColor Cyan
} else {
    Write-Host '  Mobile: not running on 8011 - only web path will be registered' -ForegroundColor DarkGray
}

$deadline = if ($WaitForEnableMinutes -gt 0) {
    (Get-Date).AddMinutes($WaitForEnableMinutes)
} else {
    (Get-Date).AddSeconds(1)
}

$attempt = 0
do {
    $attempt++
    Set-CiMTailscalePublicRoutes `
        -WebPort $WebPort `
        -MobilePort $activeMobilePort `
        -MobilePath $mobilePath `
        -IncludeMobile:($activeMobilePort -gt 0) `
        -DoReset:($ResetFirst.IsPresent -and $attempt -eq 1)

    if (Test-TailscaleFunnelPublic) {
        Write-Host ''
        Write-Host 'Public URLs:' -ForegroundColor Green
        Write-Host "  Web:    $($publicUrl.TrimEnd('/'))/" -ForegroundColor Green
        if ($activeMobilePort -gt 0) {
            Write-Host "  Mobile: $($publicUrl.TrimEnd('/'))$mobilePath/" -ForegroundColor Green
        }
        Save-CiMPublicLinkFiles `
            -BaseUrl $publicUrl `
            -WebRoot $WebInstallRoot `
            -MobileRoot $MobileInstallRoot `
            -MobilePath $mobilePath `
            -MobileActive:($activeMobilePort -gt 0)
        exit 0
    }

    $probe = Invoke-TailscaleFunnelArgs -FunnelArgs @('funnel', '--bg', '--yes', '--set-path=/', "$WebPort")
    if ($probe -match 'Managed via external system|managed by an external system|update your policy file in git') {
        Write-Host 'FUNNEL BLOCKED: tailnet ACL is Git-managed. Add funnel node attribute.' -ForegroundColor Yellow
        exit 1
    }

    if ($probe -match '(https://login\.tailscale\.com/f/funnel\?node=[^\s]+)') {
        $enableUrl = $Matches[1]
        Write-Host ''
        Write-Host 'ONE-TIME SETUP: Enable Funnel in your browser (tailnet admin):' -ForegroundColor Yellow
        Write-Host "  $enableUrl"
        if ($OpenEnableLink -or $WaitForEnableMinutes -gt 0) {
            Start-Process $enableUrl | Out-Null
        }
        if ($WaitForEnableMinutes -le 0) { exit 1 }
        Write-Host "Waiting for approval (up to $WaitForEnableMinutes min)..." -ForegroundColor Cyan
        Start-Sleep -Seconds 10
        continue
    }

    if ($WaitForEnableMinutes -le 0) { exit 1 }
    Start-Sleep -Seconds 10
} while ((Get-Date) -lt $deadline)

Write-Host 'Timed out waiting for Funnel approval.' -ForegroundColor Red
exit 1
