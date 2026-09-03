#Requires -Version 5.1
<#
.SYNOPSIS
  Copy distribution-fix files from dev repo into the export tree (installer\Plaintext\CiM or installer\Encrypted\CiM).
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$RepoRoot = "",
    [string]$DbSource = ""
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
    "server\client_user_agent.py",
    "server\auth_social_proof.py",
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
    "scrape_30m.py",
    "scrape_mf.py",
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
    # Replace children explicitly. Copy-Item of a folder INTO an existing folder nests
    # (server\core -> server\core\core) and leaves stale .pyc without .py sources.
    Get-ChildItem -LiteralPath $serverSrc -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $dst = Join-Path $serverDst $_.Name
        if ($_.PSIsContainer) {
            if (Test-Path -LiteralPath $dst) {
                Remove-Item -LiteralPath $dst -Recurse -Force -ErrorAction SilentlyContinue
            }
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Recurse -Force
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
        }
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

$dbSrc = if ($DbSource) {
    Resolve-CiMDistributionDbSource -RepoRoot $RepoRoot -DbSource $DbSource
} else {
    Resolve-CiMDistributionDbSource -RepoRoot $RepoRoot
}
$dbDst = Join-Path $ExportRoot "data\nse_data.db"
$dataDirDst = Join-Path $ExportRoot "data"
if (-not (Test-Path -LiteralPath $dataDirDst)) {
    New-Item -ItemType Directory -Force -Path $dataDirDst | Out-Null
}
foreach ($dataJson in @("sector_mapping.json", "screener_market_sets.json", "index_industry_sector_sets.json")) {
    $jsonSrc = Join-Path $RepoRoot "data\$dataJson"
    $jsonDst = Join-Path $dataDirDst $dataJson
    if (Test-Path -LiteralPath $jsonSrc) {
        Copy-Item -LiteralPath $jsonSrc -Destination $jsonDst -Force
        Write-Host "Synced data\$dataJson"
    }
}
$snapPy = Join-Path $RepoRoot "scripts\copy_db_snapshot.py"
$integrityPy = Join-Path $ScriptDir "check_db_integrity.py"
$dbSrcFull = [System.IO.Path]::GetFullPath($dbSrc)
$dbDstFull = [System.IO.Path]::GetFullPath($dbDst)
if ($dbSrcFull -ieq $dbDstFull) {
    Write-Host "Skipping DB snapshot (source and export are the same file): $dbSrcFull"
} else {
    Assert-CiMDistributionDbSource -DbPath $dbSrc -Hint "Warm Client_Test (or pass -DbSource) before Build Launcher."
    Write-Host "Distribution DB source: $dbSrc"
    if ((Test-Path -LiteralPath $snapPy)) {
        $py = Join-Path $ExportRoot "runtime\python\python.exe"
        if (-not (Test-Path -LiteralPath $py)) {
            $py = Join-Path $RepoRoot "runtime\python\python.exe"
        }
        if (-not (Test-Path -LiteralPath $py)) {
            throw "No python.exe for DB snapshot (checked export + repo runtime\python)."
        }
        try {
            & $py -s $snapPy $dbSrc $dbDst
            if ($LASTEXITCODE -ne 0) {
                throw "copy_db_snapshot failed (exit $LASTEXITCODE) - stop CiM on the DB host if the file is locked"
            }
            Write-Host "Refreshed data\nse_data.db via SQLite backup from distribution DB source"
            if ((Test-Path -LiteralPath $integrityPy)) {
                & $py -s $integrityPy $dbDst
                if ($LASTEXITCODE -ne 0) {
                    throw "Export DB failed integrity_check after snapshot: $dbDst"
                }
            }
        } catch {
            throw "copy_db_snapshot failed: $_"
        }
    } else {
        throw "Missing scripts\copy_db_snapshot.py"
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
