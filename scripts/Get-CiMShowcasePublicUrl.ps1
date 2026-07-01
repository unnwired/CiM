#Requires -Version 5.1
<#
.SYNOPSIS
  Resolve the Tailscale HTTPS client URL for browser showcase (from live MagicDNS, not stale files).
#>
function Get-CiMShowcaseTailscalePublicUrl {
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
        return $null
    }
    try {
        $json = tailscale status --json 2>&1 | ConvertFrom-Json
        $dns = [string]$json.Self.DNSName
        if ([string]::IsNullOrWhiteSpace($dns)) { return $null }
        return ("https://{0}/" -f $dns.Trim().TrimEnd('.'))
    } catch {
        return $null
    }
}

function Save-CiMShowcaseClientLinkFiles {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [Parameter(Mandatory)][string]$PublicUrl,
        [ValidateSet('live', 'testbed')]
        [string]$Role = 'live'
    )
    $url = $PublicUrl.Trim().TrimEnd('/')
    if ([string]::IsNullOrWhiteSpace($url)) { return }

    $logDir = Join-Path $InstallRoot 'runtime\logs'
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText((Join-Path $logDir 'public-url.txt'), $url, $utf8NoBom)

    if ($Role -eq 'testbed') {
        $linkBody = @(
            'Charts In Motion - TESTBED (not for production clients)'
            ''
            'Local test URLs on this PC only:'
            $url
            ''
            'This install does NOT enable the public Tailscale Funnel.'
            'Production clients must use the live install (D:\CiM\Client) and its SHOWCASE_CLIENT_LINK.txt.'
            ''
            'Operator entry: append ?operator=1 to the URL above.'
        ) -join [Environment]::NewLine
    } else {
        $linkBody = @(
            'Charts In Motion - browser client sign-in (HTTPS)'
            ''
            'Web client (desktop/tablet browser UI):'
            $url
            ''
            'Mobile client (phone-optimized UI):'
            ("{0}mobile/" -f $url.TrimEnd('/'))
            ''
            'Same hostname, different paths - web at / and mobile at /mobile/.'
            ''
            'This URL follows your Tailscale machine name (MagicDNS). After renaming the host PC,'
            'run start_showcase_tailscale.bat once so Funnel and this file refresh.'
            ''
            'After the host deploys an update, clients should hard refresh (Ctrl+Shift+R).'
            'Host operator only: Admin-Showcase.bat on the host PC (not this HTTPS link).'
        ) -join [Environment]::NewLine
    }
    [System.IO.File]::WriteAllText((Join-Path $InstallRoot 'SHOWCASE_CLIENT_LINK.txt'), $linkBody + [Environment]::NewLine, $utf8NoBom)
}

function Update-CiMShowcaseClientLinkFromTailscale {
    param(
        [string]$InstallRoot = 'D:\CiM\Client'
    )
    $InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))
    $url = Get-CiMShowcaseTailscalePublicUrl
    if (-not $url) {
        throw 'Tailscale is not running or MagicDNS name is unavailable.'
    }
    Save-CiMShowcaseClientLinkFiles -InstallRoot $InstallRoot -PublicUrl $url
    return $url
}
