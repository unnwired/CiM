#Requires -Version 5.1
<#
.SYNOPSIS
  Copy distribution-fix files from dev repo into the export tree (installer\Plaintext\CiM or installer\Encrypted\CiM).
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
$fx = Get-CiMPaths -RepoRoot $RepoRoot
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}
if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw "Export not found: $ExportRoot"
}

$copyMap = @(
    "Admin-Showcase.bat",
    "start_showcase_tailscale.bat",
    "stop_showcase_tailscale.bat",
    "start_cim.bat",
    "stop_cim.bat",
    "Apply-Update.bat",
    "scripts\_Apply-LocalUpdate.ps1",
    "scripts\Apply-LocalUpdate-Entry.ps1",
    "scripts\CiMUpdatePackage.ps1",
    "Install-Client-Update.bat",
    "scripts\Install-Client-Update.ps1",
    "scripts\CiMInstallLocator.ps1",
    "scripts\Diagnose-CiMInstall.ps1",
    "server\app_code_crypto.py",
    "server\cim_bootstrap.py",
    "server\product_config.py",
    "server\license_client.py",
    "server\license_routes.py",
    "server\http_ssl.py",
    "config\product.json",
    "config\github_updates.json",
    "config\nse_index_chart_tokens.json",
    "scripts\CiMApplyUpdate.ps1",
    "scripts\CiMDownloadUpdate.ps1",
    "scripts\Get-CiMPaths.ps1",
    "scripts\Resolve-CiMPaths.bat",
    "scripts\Start-CiMShowcase.ps1",
    "scripts\Stop-CiMShowcase.ps1",
    "scripts\Start-CiMShowcaseTailscale.ps1",
    "scripts\Stop-CiMShowcaseTailscale.ps1",
    "scripts\Get-CiMShowcasePublicUrl.ps1",
    "scripts\Get-CiMShowcaseInstallSettings.ps1",
    "scripts\Open-CiMShowcaseOperator.ps1",
    "scripts\Enable-CiMShowcaseFunnel.ps1",
    "scripts\Enable-CiMTailscalePublicRoutes.ps1",
    "scripts\Get-CiMDeployPairing.ps1",
    "scripts\Apply-CiMLocalUpdate.ps1",
    "nse_index_history.py",
    "nse_bhavcopy.py",
    "scrape_daily.py",
    "scrape_4h.py",
    "server\nse_bhavcopy.py",
    "server\eod_reconcile.py",
    "server\nse_constituents.py",
    "server\market_map.py",
    "desktop\main.js",
    "desktop\preload.js",
    "desktop\loading.html",
    "requirements_runtime.txt"
)
$frontendBuildSrc = $pkg.BrowserBuild
$frontendBuildDst = Join-Path $ExportRoot "frontend\build"
if (-not (Test-Path -LiteralPath (Join-Path $frontendBuildSrc "index.html"))) {
    if (-not (Test-Path -LiteralPath (Join-Path $pkg.BrowserRoot "package.json"))) {
        throw "Missing packages\browser\build and package.json - run npm run build first."
    }
    Write-Host "Building browser package (distribution profile)..."
    Invoke-CiMBrowserProductionBuild -BrowserRoot $pkg.BrowserRoot -DistributionMode
}
if (Test-Path -LiteralPath (Join-Path $frontendBuildSrc "index.html")) {
    if (-not (Test-Path -LiteralPath $frontendBuildDst)) {
        New-Item -ItemType Directory -Force -Path $frontendBuildDst | Out-Null
    }
    # /MIR removes stale main.*.js bundles left from past deploys (showcase static/js was ~50MB).
    robocopy $frontendBuildSrc $frontendBuildDst /MIR /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    $distMarker = Join-Path $frontendBuildDst ".cim-distribution-build"
    if (-not (Test-Path -LiteralPath $distMarker)) {
        throw "frontend\build is not a distribution build (missing .cim-distribution-build). Run Invoke-CiMBrowserProductionBuild -DistributionMode."
    }
    $manifestSrc = Join-Path $pkg.BrowserPublic "manifest.json"
    if (Test-Path -LiteralPath $manifestSrc) {
        Copy-Item -LiteralPath $manifestSrc -Destination (Join-Path $frontendBuildDst "manifest.json") -Force
    }
    Write-Host "Synced frontend\build (production bundle)"
}
$authSrc = $pkg.BrowserAuth
$authDst = Join-Path $ExportRoot "frontend\auth"
if (Test-Path -LiteralPath $authSrc) {
    $authParent = Split-Path -Parent $authDst
    if ($authParent -and -not (Test-Path -LiteralPath $authParent)) {
        New-Item -ItemType Directory -Force -Path $authParent | Out-Null
    }
    # Replace entire tree - Copy-Item into an existing folder creates nested auth\auth\ (broken deploy).
    if (Test-Path -LiteralPath $authDst) {
        Remove-Item -LiteralPath $authDst -Recurse -Force
    }
    Copy-Item -LiteralPath $authSrc -Destination $authDst -Recurse -Force
    Write-Host "Synced frontend\auth"
}
foreach ($rel in $copyMap) {
    if ($rel -like "desktop\*") {
        $src = Join-Path $pkg.DesktopRoot ($rel -replace '^desktop\\', '')
    } elseif ($rel -like "server\*") {
        $src = Join-Path $pkg.ServerRoot ($rel -replace '^server\\', '')
    } else {
        $src = Join-Path $RepoRoot $rel
    }
    $dst = Join-Path $ExportRoot $rel
    if (-not (Test-Path -LiteralPath $src)) {
        Write-Warning "Skip missing repo file: $rel"
        continue
    }
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host "Synced $rel"
}

$runUvicornSrc = Join-Path $RepoRoot "runtime\run_uvicorn.py"
$runUvicornDst = Join-Path $ExportRoot "runtime\run_uvicorn.py"
if (Test-Path -LiteralPath $runUvicornSrc) {
    $runtimeDir = Join-Path $ExportRoot "runtime"
    if (-not (Test-Path -LiteralPath $runtimeDir)) {
        New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
    }
    Copy-Item -LiteralPath $runUvicornSrc -Destination $runUvicornDst -Force
    Write-Host "Synced runtime\run_uvicorn.py"
} else {
    Write-Warning "Skip missing repo file: runtime\run_uvicorn.py"
}

$serverSrc = $pkg.ServerRoot
$serverDst = Join-Path $ExportRoot "server"
if (Test-Path -LiteralPath $serverSrc) {
    if (-not (Test-Path -LiteralPath $serverDst)) {
        New-Item -ItemType Directory -Force -Path $serverDst | Out-Null
    }
    Get-ChildItem -LiteralPath $serverSrc -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $serverDst $_.Name) -Recurse -Force
    }
    Get-ChildItem -LiteralPath $serverDst -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Host "Synced full server package from repo"
    $plaintextMarker = Join-Path $ExportRoot "config\.cim-plaintext-dist"
    if (Test-Path -LiteralPath $plaintextMarker) {
        Get-ChildItem -LiteralPath $serverDst -Recurse -File -Filter "*.pyc.enc" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        $jsEnc = Join-Path $ExportRoot "frontend\build\static\js"
        if (Test-Path -LiteralPath $jsEnc) {
            Get-ChildItem -LiteralPath $jsEnc -File -Filter "*.js.enc" -ErrorAction SilentlyContinue |
                ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        }
        Write-Host "Removed stale encrypted artifacts (plaintext showcase/host sync)"
    }
}

$dbSrc = Join-Path $RepoRoot "data\nse_data.db"
$dbDst = Join-Path $ExportRoot "data\nse_data.db"
$dataDirDst = Join-Path $ExportRoot "data"
if (-not (Test-Path -LiteralPath $dataDirDst)) {
    New-Item -ItemType Directory -Force -Path $dataDirDst | Out-Null
}
foreach ($dataJson in @("sector_mapping.json", "screener_market_sets.json")) {
    $jsonSrc = Join-Path $RepoRoot "data\$dataJson"
    $jsonDst = Join-Path $dataDirDst $dataJson
    if (Test-Path -LiteralPath $jsonSrc) {
        Copy-Item -LiteralPath $jsonSrc -Destination $jsonDst -Force
        Write-Host "Synced data\$dataJson"
    }
}
$snapPy = Join-Path $RepoRoot "scripts\copy_db_snapshot.py"
$integrityPy = Join-Path $ScriptDir "check_db_integrity.py"
if ((Test-Path -LiteralPath $dbSrc) -and (Test-Path -LiteralPath $snapPy) -and (Test-Path -LiteralPath $dbDst)) {
    $py = Join-Path $ExportRoot "runtime\python\python.exe"
    if (-not (Test-Path -LiteralPath $py)) {
        $py = Join-Path $RepoRoot "runtime\python\python.exe"
    }
    $needsCopy = $true
    if ((Test-Path -LiteralPath $integrityPy) -and (Test-Path -LiteralPath $py)) {
        & $py -s $integrityPy $dbDst 2>$null
        if ($LASTEXITCODE -eq 0) { $needsCopy = $false }
    }
    if ($needsCopy -and (Test-Path -LiteralPath $py)) {
        try {
            & $py -s $snapPy $dbSrc $dbDst
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "copy_db_snapshot skipped (exit $LASTEXITCODE) - stop CiM if export DB must refresh"
            } else {
                Write-Host "Refreshed data\nse_data.db via SQLite backup"
            }
        } catch {
            Write-Warning "copy_db_snapshot failed: $_"
        }
    }
}

$syncedVersion = Sync-CiMRepoVersionToInstallRoot -RepoRoot $RepoRoot -InstallRoot $ExportRoot
Write-Host "Synced version.txt = $syncedVersion (repo canonical -> install root)"

$isTestbedExport = $false
$hostSettingsPath = Join-Path $ExportRoot "config\showcase_host.json"
if (Test-Path -LiteralPath $hostSettingsPath) {
    try {
        $hostRaw = Get-Content -LiteralPath $hostSettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$hostRaw.role -eq 'testbed') { $isTestbedExport = $true }
    } catch { }
}
if (-not $isTestbedExport) {
    $deployCfgScript = Join-Path $ScriptDir "Get-CiMShowcaseDeployConfig.ps1"
    if (Test-Path -LiteralPath $deployCfgScript) {
        . $deployCfgScript
        $deployCfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
        if ($ExportRoot -ieq $deployCfg.showcaseInstallRoot) { $isTestbedExport = $true }
    }
}
if ($isTestbedExport) {
    $pruneScript = Join-Path $ScriptDir "Prune-CiMTestbedLaunchers.ps1"
    if (Test-Path -LiteralPath $pruneScript) {
        & $pruneScript -InstallRoot $ExportRoot
        if ($LASTEXITCODE -ne 0) { throw "Prune-CiMTestbedLaunchers failed (exit $LASTEXITCODE)" }
    }
}

$launcherTest = Join-Path $ScriptDir "Test-CiMShowcaseLauncherFiles.ps1"
if (Test-Path -LiteralPath $launcherTest) {
    & $launcherTest -InstallRoot $ExportRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Showcase launcher sync verification failed (Test-CiMShowcaseLauncherFiles.ps1)"
    }
}

Write-Host "Export sync complete: $ExportRoot"
