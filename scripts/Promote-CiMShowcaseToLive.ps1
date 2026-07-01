#Requires -Version 5.1
<#
.SYNOPSIS
  Promote a tested browser showcase build from the testbed install to the live host.

.DESCRIPTION
  Copies deployable code from showcaseInstallRoot (testbed) to showcaseLiveInstallRoot (live).
  Preserves live data\ (nse_data.db, user sessions, watchlists) and runtime\logs.
  Restarts the live showcase on showcaseLivePort and optionally runs operator deploy check.

.EXAMPLE
  .\Promote-CiMShowcaseToLive.ps1
  .\Promote-CiMShowcaseToLive.ps1 -SkipDeployCheck
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$TestInstallRoot = "",
    [string]$LiveInstallRoot = "",
    [int]$LivePort = 0,
    [switch]$RestartLive,
    [switch]$RunDeployCheck,
    [switch]$SkipDeployCheck
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }

. (Join-Path $ScriptDir "Get-CiMShowcaseDeployConfig.ps1")
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")

$cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
if ([string]::IsNullOrWhiteSpace($TestInstallRoot)) { $TestInstallRoot = $cfg.showcaseInstallRoot }
if ([string]::IsNullOrWhiteSpace($LiveInstallRoot)) { $LiveInstallRoot = $cfg.showcaseLiveInstallRoot }
if ($LivePort -le 0) { $LivePort = [int]$cfg.showcaseLivePort }
if (-not $RestartLive) { $RestartLive = [bool]$cfg.restartShowcaseAfterDeploy }
if (-not $RunDeployCheck -and -not $SkipDeployCheck) {
    $RunDeployCheck = [bool]$cfg.runDeployCheckAfterDeploy
}
if ($SkipDeployCheck) { $RunDeployCheck = $false }

$TestInstallRoot = Test-CiMShowcaseInstallRoot -InstallRoot $TestInstallRoot
Test-CiMShowcaseDistributionBuild -InstallRoot $TestInstallRoot

$liveParent = Split-Path -Parent $LiveInstallRoot
if (-not (Test-Path -LiteralPath $liveParent)) {
    New-Item -ItemType Directory -Force -Path $liveParent | Out-Null
}

$liveHasBootstrap = (Test-Path -LiteralPath (Join-Path $LiveInstallRoot "server\cim_bootstrap.py")) -or
    (Test-Path -LiteralPath (Join-Path $LiveInstallRoot "packages\server\cim_bootstrap.py"))
if (-not $liveHasBootstrap) {
    Write-Host "Live install missing - seeding structure from testbed (without data\)..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $LiveInstallRoot | Out-Null
    robocopy $TestInstallRoot $LiveInstallRoot /E /XD data runtime\logs UPDATE /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy seed failed ($LASTEXITCODE)" }
}

$LiveInstallRoot = [System.IO.Path]::GetFullPath($LiveInstallRoot)
$logFile = Join-Path $RepoRoot "runtime\logs\build-distribution.log"

function Write-PromoteLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    Write-Host $line
    $logDir = Split-Path -Parent $logFile
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Invoke-RobocopyMirror {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Promote source missing: $Source"
    }
    $parent = Split-Path -Parent $Destination
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    robocopy $Source $Destination /MIR /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed ($LASTEXITCODE): $Source -> $Destination"
    }
}

function Copy-TreeFresh {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Promote source missing: $Source"
    }
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    $parent = Split-Path -Parent $Destination
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

Write-PromoteLog "=== Promote showcase testbed -> live ==="
Write-PromoteLog "  Test: $TestInstallRoot"
Write-PromoteLog "  Live: $LiveInstallRoot (port $LivePort)"

$promoteRelPaths = @(
    "frontend\build",
    "server",
    "scripts",
    "runtime\run_uvicorn.py",
    "version.txt",
    "nse_index_history.py",
    "nse_bhavcopy.py",
    "scrape_daily.py",
    "scrape_4h.py",
    "requirements_runtime.txt",
    "Admin-Showcase.bat",
    "start_showcase_tailscale.bat",
    "stop_showcase_tailscale.bat",
    "start_cim.bat",
    "stop_cim.bat",
    "Apply-Update.bat",
    "Install-Client-Update.bat"
)

foreach ($rel in $promoteRelPaths) {
    $src = Join-Path $TestInstallRoot $rel
    $dst = Join-Path $LiveInstallRoot $rel
    if (-not (Test-Path -LiteralPath $src)) {
        Write-PromoteLog "  Skip missing: $rel"
        continue
    }
    if ((Get-Item -LiteralPath $src).PSIsContainer) {
        if ($rel -eq "frontend\build") {
            Invoke-RobocopyMirror -Source $src -Destination $dst
        } elseif ($rel -eq "server") {
            Invoke-RobocopyMirror -Source $src -Destination $dst
            Get-ChildItem -LiteralPath $dst -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
                ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
        } else {
            Invoke-RobocopyMirror -Source $src -Destination $dst
        }
    } else {
        $parent = Split-Path -Parent $dst
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }
    Write-PromoteLog "  Promoted $rel"
}

$authSrc = Join-Path $TestInstallRoot "frontend\auth"
$authDst = Join-Path $LiveInstallRoot "frontend\auth"
if (Test-Path -LiteralPath $authSrc) {
    Copy-TreeFresh -Source $authSrc -Destination $authDst
    Write-PromoteLog "  Promoted frontend\auth"
}

$configFiles = @("config\product.json", "config\github_updates.json")
foreach ($rel in $configFiles) {
    $src = Join-Path $TestInstallRoot $rel
    $dst = Join-Path $LiveInstallRoot $rel
    if (Test-Path -LiteralPath $src) {
        $parent = Split-Path -Parent $dst
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-PromoteLog "  Promoted $rel"
    }
}

# Ensure live host markers exist (never copy test session/license files from data\).
$webHostMarker = Join-Path $LiveInstallRoot "config\.cim-web-host"
$showcaseMarker = Join-Path $LiveInstallRoot "config\.cim-showcase-host"
New-Item -ItemType Directory -Force -Path (Join-Path $LiveInstallRoot "config") | Out-Null
if (-not (Test-Path -LiteralPath $webHostMarker)) {
    "" | Set-Content -LiteralPath $webHostMarker -Encoding UTF8
    Write-PromoteLog "  Created config\.cim-web-host on live"
}
if (-not (Test-Path -LiteralPath $showcaseMarker)) {
    "" | Set-Content -LiteralPath $showcaseMarker -Encoding UTF8
    Write-PromoteLog "  Created config\.cim-showcase-host on live"
}

Write-PromoteLog "Promote file copy complete (live data\ preserved)."

# 4H charts read bars_4h (separate from daily historical_data). Promote preserves live data\,
# so sync tested 4H session bars from testbed without touching other live DB tables.
$sync4hScript = Join-Path $RepoRoot "runtime\sync_bars_4h_to_live.py"
$testDb = Join-Path $TestInstallRoot "data\nse_data.db"
$liveDb = Join-Path $LiveInstallRoot "data\nse_data.db"
if ((Test-Path -LiteralPath $sync4hScript) -and (Test-Path -LiteralPath $testDb) -and (Test-Path -LiteralPath $liveDb)) {
    Write-PromoteLog "Syncing bars_4h from testbed -> live (4H chart data)..."
    & python $sync4hScript $testDb $liveDb
    if ($LASTEXITCODE -ne 0) { throw "bars_4h sync failed (exit $LASTEXITCODE)" }
} else {
    Write-PromoteLog "  Skip bars_4h sync (script or DB missing)"
}

. (Join-Path $ScriptDir "Get-CiMShowcaseInstallSettings.ps1")
$cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
Set-CiMShowcaseInstallSettings `
    -InstallRoot $LiveInstallRoot `
    -Port $LivePort `
    -Role live `
    -PublicAccess funnel | Out-Null
Write-PromoteLog "Wrote live config\showcase_host.json (port $LivePort, funnel, Yahoo-primary pipeline)"

if ($RestartLive) {
    Write-PromoteLog "Restarting live showcase on port $LivePort..."
    & (Join-Path $ScriptDir "Stop-CiMShowcase.ps1") -InstallRoot $LiveInstallRoot -Port $LivePort
    if ($LASTEXITCODE -ne 0) { throw "Stop-CiMShowcase failed (exit $LASTEXITCODE)" }
    & (Join-Path $ScriptDir "Start-CiMShowcase.ps1") -InstallRoot $LiveInstallRoot -Port $LivePort -KeepSession
    if ($LASTEXITCODE -ne 0) { throw "Start-CiMShowcase failed (exit $LASTEXITCODE)" }
}

if ($RunDeployCheck) {
    Write-PromoteLog "Running operator deploy check on live..."
    $baseUrl = "http://127.0.0.1:$LivePort"
    & (Join-Path $ScriptDir "Test-CiMShowcaseOperatorDeploy.ps1") `
        -InstallRoot $LiveInstallRoot `
        -BaseUrl $baseUrl `
        -RepoRoot $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "Test-CiMShowcaseOperatorDeploy failed on live (exit $LASTEXITCODE)" }
}

Write-PromoteLog "=== Promote to live complete ==="
Write-PromoteLog "  Live operator: http://127.0.0.1:$LivePort/?operator=1"
Write-PromoteLog "  Tailscale users: restart start_showcase_tailscale.bat if public URL is in use."
exit 0
