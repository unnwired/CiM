#Requires -Version 5.1
<#
.SYNOPSIS
  One health check + selective heal for CiM live web (8001) and mobile (8011).

.DESCRIPTION
  Mirrors Start-Live-WebAndMobile.bat:
    1. Start-CiMShowcaseTailscale.ps1 when local web is down
    2. Enable-CiMTailscalePublicRoutes.ps1 when public web is down but local OK
    3. Start-MobileMain.ps1 when local mobile is down (web must be up)
    4. UpdateMobileOnly when public mobile is down but local OK

  Never touches testbed ports. Cooldown prevents heal thrash.
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [int]$CooldownMinutes = 10,
    [int]$ConsecutiveFailures = 0,
    [switch]$ResetFunnelFirst,
    [string]$WebRoot = "",
    [string]$MobileRoot = "",
    [string]$StateFile = "",
    [scriptblock]$LogFn
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMDeployPairing.ps1")
. (Join-Path $ScriptDir "Get-CiMShowcasePublicUrl.ps1")

$pair = Get-CiMWebMobilePairing -Tier live
if ([string]::IsNullOrWhiteSpace($WebRoot)) { $WebRoot = $pair.WebRoot }
if ([string]::IsNullOrWhiteSpace($MobileRoot)) { $MobileRoot = $pair.MobileRoot }
$WebRoot = [System.IO.Path]::GetFullPath($WebRoot.Trim().TrimEnd('\'))
$MobileRoot = [System.IO.Path]::GetFullPath($MobileRoot.Trim().TrimEnd('\'))

if ([string]::IsNullOrWhiteSpace($StateFile)) {
    $StateFile = Join-Path $WebRoot "runtime\logs\live-watchdog-heal-state.json"
}

function Write-HealLog {
    param([string]$Message, [string]$Level = "INFO")
    if ($LogFn) {
        & $LogFn $Message $Level
    }
}

function Test-CiMHealPortListening {
    param([int]$Port)
    Test-CiMDeployPortListening -Port $Port
}

function Restart-CiMTailscaleForHeal {
    param([hashtable]$State)
    if (Test-CiMHealCooldown -ActionKey "tailscaleRestart" -State $State) {
        Write-HealLog "HEAL skipped (cooldown): tailscaleRestart" "WARN"
        return $false
    }
    Write-HealLog "HEAL: restart Tailscale service (stale funnel after sleep/network change)" "HEAL"
    try {
        Restart-Service -Name Tailscale -Force -ErrorAction Stop
    } catch {
        tailscale down 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        tailscale up 2>&1 | Out-Null
    }
    Start-Sleep -Seconds 8
    Set-CiMHealCooldown -ActionKey "tailscaleRestart" -State $State
    return $true
}

function Test-CiMHealHttp {
    param([string]$Url, [int]$TimeoutSec = 20)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        $ok = ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400)
        return [ordered]@{
            Ok = $ok
            Status = [int]$resp.StatusCode
            Ms = [int]$sw.ElapsedMilliseconds
            Error = $null
        }
    } catch {
        $status = 0
        if ($_.Exception.Response) {
            try { $status = [int]$_.Exception.Response.StatusCode } catch { }
        }
        return [ordered]@{
            Ok = $false
            Status = $status
            Ms = [int]$sw.ElapsedMilliseconds
            Error = $_.Exception.Message
        }
    } finally {
        $sw.Stop()
    }
}

function Get-CiMHealFunnelStatusText {
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) { return "tailscale:missing" }
    try {
        return (tailscale funnel status 2>&1 | Out-String).Trim()
    } catch {
        return "tailscale:error $($_.Exception.Message)"
    }
}

function Test-CiMSnapshotRebuildHoldActive {
    param([string]$Root)
    foreach ($name in @('snapshot-rebuild-hold.json', 'live-watchdog-pause.json')) {
        $path = Join-Path $Root "runtime\logs\$name"
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try {
            $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($name -eq 'snapshot-rebuild-hold.json' -and -not $raw.active) { continue }
            $untilRaw = [string]$raw.until
            if ([string]::IsNullOrWhiteSpace($untilRaw)) {
                return @{ Active = $true; Reason = [string]$raw.reason; Path = $name }
            }
            $until = [datetime]::Parse($untilRaw)
            if ((Get-Date) -lt $until) {
                return @{ Active = $true; Reason = [string]$raw.reason; Path = $name; Until = $untilRaw }
            }
        } catch {
            return @{ Active = $true; Reason = 'hold_file_parse_error'; Path = $name }
        }
    }
    return @{ Active = $false }
}

function Read-CiMHealState {
    if (-not (Test-Path -LiteralPath $StateFile)) { return @{} }
    try {
        $raw = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $h = @{}
        if ($raw.PSObject.Properties) {
            foreach ($p in $raw.PSObject.Properties) {
                $h[$p.Name] = [string]$p.Value
            }
        }
        return $h
    } catch {
        return @{}
    }
}

function Write-CiMHealState {
    param([hashtable]$State)
    $dir = Split-Path -Parent $StateFile
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $obj = [ordered]@{}
    foreach ($k in ($State.Keys | Sort-Object)) {
        $obj[$k] = $State[$k]
    }
    ($obj | ConvertTo-Json -Compress) | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Test-CiMHealCooldown {
    param(
        [string]$ActionKey,
        [hashtable]$State,
        [switch]$Force
    )
    if ($Force) { return $false }
    if ($CooldownMinutes -le 0) { return $false }
    if ($ConsecutiveFailures -ge 2 -and ($ActionKey -like '*Funnel*')) {
        # Public funnel often goes stale after sleep — retry sooner than the default 10m cooldown.
        return $false
    }
    $key = "lastHeal_$ActionKey"
    if (-not $State.ContainsKey($key)) { return $false }
    try {
        $last = [datetime]::Parse($State[$key])
        return ((Get-Date) - $last).TotalMinutes -lt $CooldownMinutes
    } catch {
        return $false
    }
}

function Set-CiMHealCooldown {
    param(
        [string]$ActionKey,
        [hashtable]$State
    )
    $State["lastHeal_$ActionKey"] = (Get-Date).ToString("o")
    Write-CiMHealState -State $State
}

function Invoke-CiMHealStepWebFull {
    param([hashtable]$State)
    $script = Join-Path $WebRoot "scripts\Start-CiMShowcaseTailscale.ps1"
    if (-not (Test-Path -LiteralPath $script)) {
        $script = Join-Path $ScriptDir "Start-CiMShowcaseTailscale.ps1"
    }
    if (-not (Test-Path -LiteralPath $script)) {
        throw "Missing Start-CiMShowcaseTailscale.ps1"
    }
    if (Test-CiMHealCooldown -ActionKey "webFull" -State $State) {
        Write-HealLog "HEAL skipped (cooldown): webFull" "WARN"
        return "skipped_cooldown:webFull"
    }
    Write-HealLog "HEAL: Start-CiMShowcaseTailscale.ps1" "HEAL"
    & $script -InstallRoot $WebRoot
    if ($LASTEXITCODE -ne 0) { throw "Start-CiMShowcaseTailscale failed (exit $LASTEXITCODE)" }
    Set-CiMHealCooldown -ActionKey "webFull" -State $State
    return "webFull"
}

function Invoke-CiMHealStepWebFunnel {
    param([hashtable]$State)
    $routesScript = Join-Path $ScriptDir "Enable-CiMTailscalePublicRoutes.ps1"
    if (-not (Test-Path -LiteralPath $routesScript)) {
        throw "Missing Enable-CiMTailscalePublicRoutes.ps1"
    }
    if (Test-CiMHealCooldown -ActionKey "webFunnel" -State $State) {
        Write-HealLog "HEAL skipped (cooldown): webFunnel" "WARN"
        return "skipped_cooldown:webFunnel"
    }
    $doReset = $ResetFunnelFirst.IsPresent -or $ConsecutiveFailures -ge 2
    if ($doReset) {
        [void](Restart-CiMTailscaleForHeal -State $State)
    }
    if ($doReset) {
        Write-HealLog "HEAL: reset + refresh public web funnel /" "HEAL"
    } else {
        Write-HealLog "HEAL: refresh public web funnel /" "HEAL"
    }
    $routeArgs = @{
        WebPort               = $pair.WebPort
        SkipMobileRoute       = $true
        WaitForEnableMinutes  = 0
        WebInstallRoot        = $WebRoot
    }
    if ($doReset) { $routeArgs.ResetFirst = $true }
    & $routesScript @routeArgs
    if ($LASTEXITCODE -ne 0) { throw "Enable-CiMTailscalePublicRoutes (web) failed (exit $LASTEXITCODE)" }
    Set-CiMHealCooldown -ActionKey "webFunnel" -State $State
    return "webFunnel"
}

function Invoke-CiMHealStepMobileFull {
    param([hashtable]$State)
    $starter = Join-Path $MobileRoot "Start-MobileMain.ps1"
    if (-not (Test-Path -LiteralPath $starter)) {
        $starter = Join-Path $MobileRoot "scripts\Start-CiMMobileMain.ps1"
    }
    if (-not (Test-Path -LiteralPath $starter)) {
        throw "Missing Start-MobileMain.ps1 / Start-CiMMobileMain.ps1"
    }
    if (Test-CiMHealCooldown -ActionKey "mobileFull" -State $State) {
        Write-HealLog "HEAL skipped (cooldown): mobileFull" "WARN"
        return "skipped_cooldown:mobileFull"
    }
    Write-HealLog "HEAL: Start-MobileMain.ps1 (with funnel)" "HEAL"
    & $starter
    if ($LASTEXITCODE -ne 0) { throw "Start-MobileMain failed (exit $LASTEXITCODE)" }
    Set-CiMHealCooldown -ActionKey "mobileFull" -State $State
    return "mobileFull"
}

function Invoke-CiMHealStepMobileFunnel {
    param([hashtable]$State)
    $routesScript = Join-Path $ScriptDir "Enable-CiMTailscalePublicRoutes.ps1"
    if (-not (Test-Path -LiteralPath $routesScript)) {
        throw "Missing Enable-CiMTailscalePublicRoutes.ps1"
    }
    if (Test-CiMHealCooldown -ActionKey "mobileFunnel" -State $State) {
        Write-HealLog "HEAL skipped (cooldown): mobileFunnel" "WARN"
        return "skipped_cooldown:mobileFunnel"
    }
    if ($ResetFunnelFirst.IsPresent -or $ConsecutiveFailures -ge 2) {
        Write-HealLog "HEAL: reset + refresh full funnel (web + /mobile)" "HEAL"
        $routeArgs = @{
            WebPort              = $pair.WebPort
            MobilePort           = $pair.MobilePort
            WaitForEnableMinutes = 0
            WebInstallRoot       = $WebRoot
            MobileInstallRoot    = $MobileRoot
            ResetFirst           = $true
        }
        & $routesScript @routeArgs
    } else {
        Write-HealLog "HEAL: UpdateMobileOnly /mobile funnel" "HEAL"
        & $routesScript `
            -WebPort $pair.WebPort `
            -MobilePort $pair.MobilePort `
            -UpdateMobileOnly `
            -WebInstallRoot $WebRoot `
            -MobileInstallRoot $MobileRoot
    }
    if ($LASTEXITCODE -ne 0) { throw "Enable-CiMTailscalePublicRoutes (mobile) failed (exit $LASTEXITCODE)" }
    Set-CiMHealCooldown -ActionKey "mobileFunnel" -State $State
    return "mobileFunnel"
}

$publicBase = Get-CiMShowcaseTailscalePublicUrl
$publicWebHealth = $null
$publicMobile = $null
if ($publicBase) {
    $base = $publicBase.Trim().TrimEnd('/')
    $publicWebHealth = "$base/api/health"
    $publicMobile = "$base/mobile/"
}

$portWeb = Test-CiMHealPortListening -Port $pair.WebPort
$portMobile = Test-CiMHealPortListening -Port $pair.MobilePort
$webLocal = Test-CiMHealHttp -Url "http://127.0.0.1:$($pair.WebPort)/api/health"
$mobileLocal = Test-CiMHealHttp -Url $pair.MobileLocalUrl
$webPublic = if ($publicWebHealth) { Test-CiMHealHttp -Url $publicWebHealth -TimeoutSec 60 } else { @{ Ok = $false; Status = 0; Error = "no_tailscale_dns" } }
$mobilePublic = if ($publicMobile) { Test-CiMHealHttp -Url $publicMobile -TimeoutSec 60 } else { @{ Ok = $false; Status = 0; Error = "no_tailscale_dns" } }
$funnelStatus = Get-CiMHealFunnelStatusText

$webLocalOk = $portWeb -and $webLocal.Ok
$webPublicOk = $webPublic.Ok
$mobileLocalOk = $portMobile -and $mobileLocal.Ok
$mobilePublicOk = $mobilePublic.Ok
$overallOk = $webLocalOk -and $webPublicOk -and $mobileLocalOk -and $mobilePublicOk

$healAction = $null
$healError = $null
$state = Read-CiMHealState
$snapshotHold = Test-CiMSnapshotRebuildHoldActive -Root $WebRoot

if (-not $CheckOnly -and -not $overallOk) {
    if ($snapshotHold.Active) {
        $holdReason = if ($snapshotHold.Reason) { $snapshotHold.Reason } else { 'snapshot_rebuild_hold' }
        Write-HealLog "HEAL skipped (snapshot rebuild hold): $holdReason" "INFO"
    } else {
    try {
        if (-not $webLocalOk) {
            $healAction = Invoke-CiMHealStepWebFull -State $state
        } elseif (-not $webPublicOk) {
            $healAction = Invoke-CiMHealStepWebFunnel -State $state
        } elseif (-not $mobileLocalOk) {
            $healAction = Invoke-CiMHealStepMobileFull -State $state
        } elseif (-not $mobilePublicOk) {
            $healAction = Invoke-CiMHealStepMobileFunnel -State $state
        }

        if ($healAction -and $healAction -notlike "skipped_*") {
            Start-Sleep -Seconds 5
            $portWeb = Test-CiMHealPortListening -Port $pair.WebPort
            $portMobile = Test-CiMHealPortListening -Port $pair.MobilePort
            $webLocal = Test-CiMHealHttp -Url "http://127.0.0.1:$($pair.WebPort)/api/health"
            $mobileLocal = Test-CiMHealHttp -Url $pair.MobileLocalUrl
            if ($publicWebHealth) { $webPublic = Test-CiMHealHttp -Url $publicWebHealth -TimeoutSec 60 }
            if ($publicMobile) { $mobilePublic = Test-CiMHealHttp -Url $publicMobile -TimeoutSec 60 }
            $webLocalOk = $portWeb -and $webLocal.Ok
            $webPublicOk = $webPublic.Ok
            $mobileLocalOk = $portMobile -and $mobileLocal.Ok
            $mobilePublicOk = $mobilePublic.Ok
            $overallOk = $webLocalOk -and $webPublicOk -and $mobileLocalOk -and $mobilePublicOk
        }
    } catch {
        $healError = $_.Exception.Message
        Write-HealLog "HEAL error: $healError" "FAIL"
    }
    }
}

$result = [pscustomobject][ordered]@{
    CheckedAt          = (Get-Date).ToString("o")
    OverallOk          = $overallOk
    WebLocalOk         = $webLocalOk
    WebPublicOk        = $webPublicOk
    MobileLocalOk      = $mobileLocalOk
    MobilePublicOk     = $mobilePublicOk
    PortWeb            = $portWeb
    PortMobile         = $portMobile
    WebLocalStatus     = $webLocal.Status
    WebPublicStatus    = $webPublic.Status
    MobileLocalStatus  = $mobileLocal.Status
    MobilePublicStatus = $mobilePublic.Status
    PublicWebUrl       = $publicWebHealth
    PublicMobileUrl    = $publicMobile
    FunnelStatus       = $funnelStatus
    HealAction         = $healAction
    HealError          = $healError
    CheckOnly          = [bool]$CheckOnly
}

return $result
