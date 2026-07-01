#Requires -Version 5.1
<#
.SYNOPSIS
  Canonical port/root pairing for CiM web and mobile installs (live vs testbed).

.DESCRIPTION
  Live:     web 8001 (Client)     + mobile 8011 (Mobile_Main)     -> API 8001
  Testbed:  web 8002 (Client_Test) + mobile 8010 (Mobile_Testbed) -> API 8002

  Only the live pair may register Tailscale public Funnel paths (/ and /mobile).
  Testbed surfaces are local-only and must not hijack production routing.
#>

function Get-CiMWebMobilePairing {
    param(
        [Parameter(Mandatory)]
        [ValidateSet('live', 'testbed')]
        [string]$Tier
    )

    $table = @{
        live = [ordered]@{
            Tier           = 'live'
            WebPort        = 8001
            WebRoot        = 'D:\CiM\Client'
            MobilePort     = 8011
            MobileRoot     = 'D:\CiM\Mobile_Main'
            ApiUpstream    = 'http://127.0.0.1:8001'
            PublicFunnel   = $true
            MobileLocalUrl = 'http://127.0.0.1:8011/mobile/'
            WebLocalUrl    = 'http://127.0.0.1:8001/'
        }
        testbed = [ordered]@{
            Tier           = 'testbed'
            WebPort        = 8002
            WebRoot        = 'D:\CiM\Client_Test'
            MobilePort     = 8010
            MobileRoot     = 'D:\CiM\Mobile_Testbed'
            ApiUpstream    = 'http://127.0.0.1:8002'
            PublicFunnel   = $false
            MobileLocalUrl = 'http://127.0.0.1:8010/mobile/'
            WebLocalUrl    = 'http://127.0.0.1:8002/'
        }
    }

    return [pscustomobject]$table[$Tier]
}

function Get-CiMDeployTierForWebPort {
    param([Parameter(Mandatory)][int]$WebPort)
    switch ($WebPort) {
        8001 { return 'live' }
        8002 { return 'testbed' }
        default { return $null }
    }
}

function Get-CiMDeployTierForMobilePort {
    param([Parameter(Mandatory)][int]$MobilePort)
    switch ($MobilePort) {
        8011 { return 'live' }
        8010 { return 'testbed' }
        default { return $null }
    }
}

function Test-CiMDeployPortListening {
    param([int]$Port)
    if ($Port -le 0) { return $false }
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return [bool](netstat -ano | Select-String ":\s*$Port\s+.*LISTENING")
    }
}

function Resolve-CiMPairedMobilePort {
    param(
        [Parameter(Mandatory)][int]$WebPort,
        [int]$RequestedMobilePort = 0
    )

    $tier = Get-CiMDeployTierForWebPort -WebPort $WebPort
    if (-not $tier) {
        Write-Warning "Unknown web port $WebPort - mobile route skipped."
        return 0
    }

    $pair = Get-CiMWebMobilePairing -Tier $tier
    if (-not $pair.PublicFunnel) {
        return 0
    }

    $expected = [int]$pair.MobilePort
    if ($RequestedMobilePort -gt 0 -and $RequestedMobilePort -ne $expected) {
        Write-Warning (
            "Ignoring mobile port $RequestedMobilePort for web $WebPort; " +
            "live public /mobile must use port $expected ($($pair.MobileRoot))."
        )
    }

    if (Test-CiMDeployPortListening -Port $expected) {
        return $expected
    }

    Write-Host "Live mobile proxy not listening on port $expected ($($pair.MobileRoot)) - /mobile public route skipped." -ForegroundColor DarkYellow
    return 0
}

function Wait-CiMPairedMobilePort {
    param(
        [Parameter(Mandatory)][int]$WebPort,
        [int]$MaxWaitSeconds = 0
    )

    $tier = Get-CiMDeployTierForWebPort -WebPort $WebPort
    if (-not $tier) { return 0 }
    $pair = Get-CiMWebMobilePairing -Tier $tier
    if (-not $pair.PublicFunnel) { return 0 }

    $expected = [int]$pair.MobilePort
    if ($MaxWaitSeconds -le 0) {
        return (Resolve-CiMPairedMobilePort -WebPort $WebPort)
    }

    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    do {
        if (Test-CiMDeployPortListening -Port $expected) {
            return $expected
        }
        Write-Host "Waiting for live mobile on port $expected (up to ${MaxWaitSeconds}s)..." -ForegroundColor DarkYellow
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-Host "Timed out waiting for mobile on port $expected - /mobile will be registered when mobile starts." -ForegroundColor DarkYellow
    return 0
}

function Resolve-CiMPairedWebInstallRoot {
    param([Parameter(Mandatory)][int]$WebPort)
    $tier = Get-CiMDeployTierForWebPort -WebPort $WebPort
    if (-not $tier) { return $null }
    return (Get-CiMWebMobilePairing -Tier $tier).WebRoot
}

function Resolve-CiMPairedMobileInstallRoot {
    param(
        [Parameter(Mandatory)][int]$WebPort,
        [int]$MobilePort = 0
    )
    $tier = Get-CiMDeployTierForWebPort -WebPort $WebPort
    if (-not $tier) { return $null }
    $pair = Get-CiMWebMobilePairing -Tier $tier
    if ($MobilePort -gt 0 -and $MobilePort -ne $pair.MobilePort) { return $null }
    return $pair.MobileRoot
}
