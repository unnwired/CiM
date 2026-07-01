#Requires -Version 5.1
<#
.SYNOPSIS
  Read/write browser showcase deploy settings for Build Launcher and Deploy-CiMShowcaseFromRepo.ps1.

.DESCRIPTION
  showcaseInstallRoot / showcasePort = testbed (default deploy target).
  showcaseLiveInstallRoot / showcaseLivePort = production web host (promote target).
#>
function Get-CiMShowcaseDeployConfig {
    param(
        [string]$RepoRoot = ""
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $defaults = [ordered]@{
        showcaseInstallRoot         = "D:\CiM\Client_Test"
        showcasePort                = 8002
        showcaseLiveInstallRoot     = "D:\CiM\Client"
        showcaseLivePort            = 8001
        restartShowcaseAfterDeploy  = $true
        runDeployCheckAfterDeploy   = $true
        fullPlaintextExportRefresh  = $false
    }
    $path = Join-Path $RepoRoot "config\showcase_deploy.json"
    if (-not (Test-Path -LiteralPath $path)) {
        return [pscustomobject]$defaults
    }
    try {
        $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Warning "Could not parse config\showcase_deploy.json - using defaults."
        return [pscustomobject]$defaults
    }
    $root = [string]$raw.showcaseInstallRoot
    if ([string]::IsNullOrWhiteSpace($root)) { $root = $defaults.showcaseInstallRoot }
    $root = [System.IO.Path]::GetFullPath((Remove-CiMShowcasePathQuotes $root))

    $liveRoot = [string]$raw.showcaseLiveInstallRoot
    if ([string]::IsNullOrWhiteSpace($liveRoot)) { $liveRoot = $defaults.showcaseLiveInstallRoot }
    $liveRoot = [System.IO.Path]::GetFullPath((Remove-CiMShowcasePathQuotes $liveRoot))

    $port = $defaults.showcasePort
    if ($null -ne $raw.showcasePort) {
        $parsed = 0
        if ([int]::TryParse([string]$raw.showcasePort, [ref]$parsed) -and $parsed -gt 0) {
            $port = $parsed
        }
    }
    $livePort = $defaults.showcaseLivePort
    if ($null -ne $raw.showcaseLivePort) {
        $parsedLive = 0
        if ([int]::TryParse([string]$raw.showcaseLivePort, [ref]$parsedLive) -and $parsedLive -gt 0) {
            $livePort = $parsedLive
        }
    }
    return [pscustomobject]@{
        ConfigPath                  = $path
        showcaseInstallRoot         = $root
        showcasePort                = $port
        showcaseLiveInstallRoot     = $liveRoot
        showcaseLivePort            = $livePort
        restartShowcaseAfterDeploy  = if ($null -eq $raw.restartShowcaseAfterDeploy) { $true } else { [bool]$raw.restartShowcaseAfterDeploy }
        runDeployCheckAfterDeploy   = if ($null -eq $raw.runDeployCheckAfterDeploy) { $true } else { [bool]$raw.runDeployCheckAfterDeploy }
        fullPlaintextExportRefresh  = if ($null -eq $raw.fullPlaintextExportRefresh) { $false } else { [bool]$raw.fullPlaintextExportRefresh }
    }
}

function Set-CiMShowcaseDeployConfig {
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [string]$ShowcaseInstallRoot,
        [int]$ShowcasePort = 8002,
        [string]$ShowcaseLiveInstallRoot,
        [int]$ShowcaseLivePort = 8001,
        [bool]$RestartShowcaseAfterDeploy,
        [bool]$RunDeployCheckAfterDeploy,
        [bool]$FullPlaintextExportRefresh
    )
    $existing = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
    $dir = Join-Path $RepoRoot "config"
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $path = Join-Path $dir "showcase_deploy.json"
    $testRoot = if ($ShowcaseInstallRoot) {
        [System.IO.Path]::GetFullPath((Remove-CiMShowcasePathQuotes $ShowcaseInstallRoot))
    } else {
        $existing.showcaseInstallRoot
    }
    $liveRoot = if ($ShowcaseLiveInstallRoot) {
        [System.IO.Path]::GetFullPath((Remove-CiMShowcasePathQuotes $ShowcaseLiveInstallRoot))
    } else {
        $existing.showcaseLiveInstallRoot
    }
    $payload = [ordered]@{
        showcaseInstallRoot         = $testRoot
        showcasePort                = $ShowcasePort
        showcaseLiveInstallRoot     = $liveRoot
        showcaseLivePort            = $ShowcaseLivePort
        restartShowcaseAfterDeploy  = $RestartShowcaseAfterDeploy
        runDeployCheckAfterDeploy   = $RunDeployCheckAfterDeploy
        fullPlaintextExportRefresh  = $FullPlaintextExportRefresh
    }
    $json = ($payload | ConvertTo-Json -Depth 3)
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($path, $json + [Environment]::NewLine, $utf8NoBom)
    return $path
}

function Remove-CiMShowcasePathQuotes {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return $Path.Trim().Trim([char]34).Trim([char]39)
}

function Test-CiMShowcaseInstallRoot {
    param([Parameter(Mandatory)][string]$InstallRoot)
    $full = [System.IO.Path]::GetFullPath((Remove-CiMShowcasePathQuotes $InstallRoot))
    . (Join-Path $PSScriptRoot "Get-CiMPaths.ps1")
    if (-not (Test-CiMInstallHasServerBootstrap -Root $full)) {
        throw "Not a CiM install tree (missing server\cim_bootstrap.py or packages\server\cim_bootstrap.py): $full"
    }
    return $full
}

function Test-CiMShowcaseDistributionBuild {
    param([Parameter(Mandatory)][string]$InstallRoot)
    $marker = Join-Path $InstallRoot "frontend\build\.cim-distribution-build"
    if (-not (Test-Path -LiteralPath $marker)) {
        throw "Missing distribution build marker at $marker - deploy to the testbed first."
    }
}
