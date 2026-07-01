#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy Plaintext distribution build to the browser showcase host folder (never Encrypted).

.DESCRIPTION
  Fast path: npm build (distribution) + Sync-ExportDistributionFixes.
  Optional full path: build_distribution_full.ps1 -PlaintextExport to showcase path.
  Browser showcase always uses readable frontend/build + frontend/auth — no encrypt step.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$InstallRoot = "",
    [switch]$RestartShowcase,
    [switch]$RunDeployCheck,
    [switch]$FullPlaintextExportRefresh,
    [switch]$SkipSmoke,
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }

. (Join-Path $ScriptDir "Get-CiMShowcaseDeployConfig.ps1")
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")

$cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = $cfg.showcaseInstallRoot
}
$InstallRoot = Test-CiMShowcaseInstallRoot -InstallRoot $InstallRoot
if ($Port -le 0) { $Port = [int]$cfg.showcasePort }

$logFile = Join-Path $RepoRoot "runtime\logs\build-distribution.log"
$script:DeployStep = 0
$script:DeployStepTotal = 1
if ($FullPlaintextExportRefresh) { $script:DeployStepTotal++ }
else { $script:DeployStepTotal += 3 }
$script:DeployStepTotal++
if ($RestartShowcase) { $script:DeployStepTotal++ }
if ($RunDeployCheck) { $script:DeployStepTotal++ }

function Write-DeployLog {
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

function Write-DeployStep {
    param([string]$Name)
    $script:DeployStep++
    Write-DeployLog ("Step {0}/{1}: {2}" -f $script:DeployStep, $script:DeployStepTotal, $Name)
}

Write-DeployLog "=== Showcase deploy (Plaintext browser host) ==="
Write-DeployLog "  Target: $InstallRoot"
Write-DeployLog "  Full Plaintext export: $FullPlaintextExportRefresh"
Write-DeployLog "  Restart showcase: $RestartShowcase"
Write-DeployLog "  Run deploy check: $RunDeployCheck"

if ($FullPlaintextExportRefresh) {
    Write-DeployStep "build_distribution_full.ps1 (Plaintext, no encrypt/installer)"
    $fullBuild = Join-Path $ScriptDir "build_distribution_full.ps1"
    & $fullBuild `
        -RepoRoot $RepoRoot `
        -ExportRoot $InstallRoot `
        -PlaintextExport `
        -SkipEncrypt `
        -SkipInstaller `
        -SkipUpdatePackage `
        -SkipSmoke:$SkipSmoke
    if ($LASTEXITCODE -ne 0) { throw "Full Plaintext export to showcase failed (exit $LASTEXITCODE)" }
} else {
    $qrAssets = Join-Path $pkg.BrowserSrc "assets"
    $qrSource = Join-Path $qrAssets "support-upi-qr.png"
    if (-not (Test-Path -LiteralPath $qrSource)) { $qrSource = Join-Path $qrAssets "support-upi-qr.jpg" }
    if (-not (Test-Path -LiteralPath $qrSource)) { $qrSource = Join-Path $qrAssets "support-upi-qr.jpeg" }
    if (Test-Path -LiteralPath $qrSource) {
        Write-DeployStep "Generate-SupportQrPayload.ps1 (sync encrypted payload with source image)"
        $qrOut = Join-Path $pkg.BrowserSrc "support\supportQrPayload.generated.js"
        & (Join-Path $ScriptDir "Generate-SupportQrPayload.ps1") -ImagePath $qrSource -OutPath $qrOut
        if ($LASTEXITCODE -ne 0) { throw "Generate-SupportQrPayload failed (exit $LASTEXITCODE)" }
    }

    Write-DeployStep "npm run build (REACT_APP_EXPORT_MODE=distribution)"
    if (-not (Test-Path -LiteralPath (Join-Path $pkg.BrowserRoot "package.json"))) {
        throw "Missing packages\browser\package.json"
    }
    Invoke-CiMBrowserProductionBuild -BrowserRoot $pkg.BrowserRoot -DistributionMode

    Write-DeployStep "Sync-ExportDistributionFixes.ps1"
    & (Join-Path $ScriptDir "Sync-ExportDistributionFixes.ps1") -RepoRoot $RepoRoot -ExportRoot $InstallRoot
    if ($LASTEXITCODE -ne 0) { throw "Sync-ExportDistributionFixes failed (exit $LASTEXITCODE)" }
}

Write-DeployStep "Test-CiMShowcaseLauncherFiles.ps1"
& (Join-Path $ScriptDir "Test-CiMShowcaseLauncherFiles.ps1") -InstallRoot $InstallRoot
if ($LASTEXITCODE -ne 0) { throw "Showcase launcher file check failed (exit $LASTEXITCODE)" }

$appVersion = Sync-CiMRepoVersionToInstallRoot -RepoRoot $RepoRoot -InstallRoot $InstallRoot
Write-DeployLog "Synced version.txt = $appVersion (repo canonical -> showcase host)"

. (Join-Path $ScriptDir "Get-CiMShowcaseInstallSettings.ps1")
if ($InstallRoot -ieq $cfg.showcaseInstallRoot) {
    Set-CiMShowcaseInstallSettings -InstallRoot $InstallRoot -Port $Port -Role testbed -PublicAccess local | Out-Null
    Write-DeployLog "Wrote config\showcase_host.json (testbed, port $Port, local only)"
    Write-DeployStep "Prune-CiMTestbedLaunchers.ps1"
    & (Join-Path $ScriptDir "Prune-CiMTestbedLaunchers.ps1") -InstallRoot $InstallRoot
    if ($LASTEXITCODE -ne 0) { throw "Prune-CiMTestbedLaunchers failed (exit $LASTEXITCODE)" }
} elseif ($InstallRoot -ieq $cfg.showcaseLiveInstallRoot) {
    Set-CiMShowcaseInstallSettings -InstallRoot $InstallRoot -Port $Port -Role live -PublicAccess funnel | Out-Null
    Write-DeployLog "Wrote config\showcase_host.json (live, port $Port, funnel)"
}

$manifestPath = Join-Path $InstallRoot "frontend\build\asset-manifest.json"
$mainBundle = "unknown"
if (Test-Path -LiteralPath $manifestPath) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $mainBundle = [string]$manifest.files.'main.js'
}
Write-DeployLog "Deployed bundle: $mainBundle"

if ($RestartShowcase) {
    Write-DeployStep "Restart showcase on port $Port"
    & (Join-Path $ScriptDir "Stop-CiMShowcase.ps1") -InstallRoot $InstallRoot -Port $Port
    if ($LASTEXITCODE -ne 0) { throw "Stop-CiMShowcase failed (exit $LASTEXITCODE)" }
    & (Join-Path $ScriptDir "Start-CiMShowcase.ps1") -InstallRoot $InstallRoot -Port $Port
    if ($LASTEXITCODE -ne 0) { throw "Start-CiMShowcase failed (exit $LASTEXITCODE)" }
}

if ($RunDeployCheck) {
    Write-DeployStep "Test-CiMShowcaseOperatorDeploy.ps1"
    $baseUrl = "http://127.0.0.1:$Port"
    & (Join-Path $ScriptDir "Test-CiMShowcaseOperatorDeploy.ps1") -InstallRoot $InstallRoot -BaseUrl $baseUrl -RepoRoot $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "Test-CiMShowcaseOperatorDeploy failed (exit $LASTEXITCODE)" }
}

Write-DeployLog "=== Showcase deploy complete ==="
Write-DeployLog "  Admin entry: Admin-Showcase.bat or http://127.0.0.1:$Port/?operator=1"
Write-DeployLog "  Clients: hard refresh (Ctrl+Shift+R) after deploy to load $mainBundle"
exit 0
