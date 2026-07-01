#Requires -Version 5.1
<#
.SYNOPSIS
  Verify showcase/client launcher dependencies exist under an install root (post-sync gate).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))

$isTestbed = $false
$settingsPath = Join-Path $root "config\showcase_host.json"
if (Test-Path -LiteralPath $settingsPath) {
    try {
        $raw = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$raw.role -eq 'testbed') { $isTestbed = $true }
    } catch { }
}

$required = @(
    "Admin-Showcase.bat",
    "scripts\Resolve-CiMPaths.bat",
    "scripts\Start-CiMShowcase.ps1",
    "scripts\Stop-CiMShowcase.ps1",
    "scripts\Open-CiMShowcaseOperator.ps1",
    "scripts\Get-CiMPaths.ps1",
    "runtime\run_uvicorn.py",
    "start_showcase_tailscale.bat",
    "scripts\Start-CiMShowcaseTailscale.ps1",
    "scripts\Stop-CiMShowcaseTailscale.ps1",
    "scripts\Get-CiMShowcasePublicUrl.ps1",
    "scripts\Get-CiMShowcaseInstallSettings.ps1",
    "scripts\Enable-CiMShowcaseFunnel.ps1",
    "scripts\Enable-CiMTailscalePublicRoutes.ps1",
    "scripts\Get-CiMDeployPairing.ps1"
)

if (-not $isTestbed) {
    $required += "start_cim.bat"
}

$forbiddenOnTestbed = @(
    "start_cim.bat",
    "stop_cim.bat",
    "Apply-Update.bat",
    "Install-Client-Update.bat"
)

$missing = @()
foreach ($rel in $required) {
    $path = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $path)) {
        $missing += $rel
    }
}

if ($isTestbed) {
    foreach ($rel in $forbiddenOnTestbed) {
        $path = Join-Path $root $rel
        if (Test-Path -LiteralPath $path) {
            Write-Host "[FAIL] Testbed must not include: $rel (run Prune-CiMTestbedLaunchers.ps1)" -ForegroundColor Red
            exit 1
        }
    }
    $zOld = Join-Path $root "zOld"
    if (Test-Path -LiteralPath $zOld) {
        Write-Host "[FAIL] Testbed must not include zOld\ (run Prune-CiMTestbedLaunchers.ps1)" -ForegroundColor Red
        exit 1
    }
}

if ($missing.Count -gt 0) {
    Write-Host "[FAIL] Showcase launcher sync incomplete under $root" -ForegroundColor Red
    foreach ($m in $missing) { Write-Host "  missing: $m" -ForegroundColor Red }
    exit 1
}

$installRootPy = Join-Path $root "server\core\install_root.py"
if (-not (Test-Path -LiteralPath $installRootPy)) {
    Write-Host "[FAIL] Missing server\core\install_root.py under $root" -ForegroundColor Red
    exit 1
}
$installRootSrc = Get-Content -LiteralPath $installRootPy -Raw
if ($installRootSrc -notmatch 'resolve_frontend_build_dir') {
    Write-Host "[FAIL] Stale server\core\install_root.py (missing resolve_frontend_build_dir)" -ForegroundColor Red
    exit 1
}

$py = Join-Path $root "runtime\python\python.exe"
if (Test-Path -LiteralPath $py) {
    $escapedRoot = $root.Replace("'", "''")
    $code = "import sys; from pathlib import Path; r=Path(r'$escapedRoot'); sys.path.insert(0, str(r)); from server.core.install_root import get_install_root, resolve_frontend_build_dir; print(get_install_root())"
    Push-Location $root
    try {
        $out = & $py -s -c $code 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FAIL] server.core.install_root import smoke failed:" -ForegroundColor Red
            Write-Host ($out | Out-String)
            exit 1
        }
    } finally {
        Pop-Location
    }
}

$distMarker = Join-Path $root "frontend\build\.cim-distribution-build"
if (-not (Test-Path -LiteralPath $distMarker)) {
    Write-Host "[FAIL] frontend\build missing .cim-distribution-build (dev bundle - not for showcase)" -ForegroundColor Red
    exit 1
}
$indexHtml = Join-Path $root "frontend\build\index.html"
if (Test-Path -LiteralPath $indexHtml) {
    $indexSrc = Get-Content -LiteralPath $indexHtml -Raw
    if ($indexSrc -match 'main\.([a-f0-9]+)\.js') {
        $bundleRel = "frontend\build\static\js\main.$($Matches[1]).js"
        $bundlePath = Join-Path $root $bundleRel
        if (-not (Test-Path -LiteralPath $bundlePath)) {
            Write-Host "[FAIL] index.html references missing bundle: $bundleRel" -ForegroundColor Red
            exit 1
        }
        $jsDir = Join-Path $root "frontend\build\static\js"
        $staleMain = @(Get-ChildItem -LiteralPath $jsDir -File -Filter "main.*.js" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne "main.$($Matches[1]).js" })
        if ($staleMain.Count -gt 0) {
            Write-Host "[FAIL] Stale main.*.js bundles in static/js ($($staleMain.Count) files) - run Sync with /MIR" -ForegroundColor Red
            exit 1
        }
    }
}

$label = if ($isTestbed) { 'testbed' } else { 'showcase' }
Write-Host "[OK] Showcase launcher files present ($($required.Count) paths, $label) under $root" -ForegroundColor Green
exit 0
