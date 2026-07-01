#Requires -Version 5.1
<#
.SYNOPSIS
  Restore Charts In Motion development build after a client update was applied by mistake.

.DESCRIPTION
  Client/GitHub update packages overwrite start_cim.bat and crypto bootstrap
  files with distribution logic (license required). This script:

    1. Restores dev-aware files (git, then scripts\dev-restore\ fallback)
    2. Sets CIM_DEV=1 for the current user
    3. Clears %LOCALAPPDATA%\CiM\app-cache
    4. Verifies Python sees the tree as development (no license needed)

  ONLY run this on your development repo (must have server\server.py).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Restore-CiMDevBuild.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Restore-CiMDevBuild.ps1 -UseGit:$false
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$UseGit = $true,
    [switch]$SkipEnvVar,
    [switch]$SkipCacheClear
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $ScriptDir
}
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot

$DevRestoreDir = Join-Path $ScriptDir "dev-restore"
$FilesToRestore = @(
    "start_cim.bat",
    "packages\server\app_code_crypto.py",
    "packages\server\cim_bootstrap.py"
)

function Test-DevRepo([string]$Root) {
    $pkgPaths = Get-CiMPackagePaths -RepoRoot $Root
    $serverPy = Join-Path $pkgPaths.ServerRoot "server.py"
    if (-not (Test-Path -LiteralPath $serverPy)) {
        throw @"
This is not a Charts In Motion development tree (missing packages\server\server.py).

Restore-CiMDevBuild.ps1 is ONLY for the dev repo - not client installs.
For client PCs use Repair-CiMLicense.ps1 instead.
"@
    }
}

function Test-DevAwareAppCrypto([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $text = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    return $text -match 'is_development_tree'
}

function Test-DevAwareStartBat([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $text = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    return $text -match 'CIM_DISTRIBUTION'
}

function Invoke-GitRestore([string]$Root, [string[]]$RelPaths) {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { return $false }
    Push-Location $Root
    try {
        & git rev-parse --is-inside-work-tree 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }
        & git checkout HEAD -- @RelPaths
        if ($LASTEXITCODE -ne 0) { return $false }
        return $true
    } finally {
        Pop-Location
    }
}

function Copy-DevRestoreFallback([string]$Root, [string]$FallbackDir, [string[]]$RelPaths) {
    if (-not (Test-Path -LiteralPath $FallbackDir)) {
        throw "Git restore unavailable and missing fallback folder: $FallbackDir`nPopulate dev-restore\ from a known-good dev copy, or commit fixes and use git."
    }
    foreach ($rel in $RelPaths) {
        $src = Join-Path $FallbackDir ($rel -replace '/', '\')
        $dst = Join-Path $Root ($rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $src)) {
            throw "Missing fallback file: $src"
        }
        $parent = Split-Path -Parent $dst
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Host "Restored (fallback): $rel"
    }
}

function Set-FlowXDevEnvVar {
    [System.Environment]::SetEnvironmentVariable("CIM_DEV", "1", "User")
    $env:CIM_DEV = "1"
    Write-Host "Set user env CIM_DEV=1 (new terminals will inherit it)."
}

function Clear-FlowXAppCache {
    $cache = Join-Path $env:LOCALAPPDATA "CiM\app-cache"
    if (Test-Path -LiteralPath $cache) {
        Remove-Item -LiteralPath $cache -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared app-cache: $cache"
    } else {
        Write-Host "No app-cache to clear."
    }
}

function Clear-StrayDistributionArtifacts {
    param([string]$Root)
    $serverPy = Join-Path $Root "server\server.py"
    if (-not (Test-Path -LiteralPath $serverPy)) { return }
    $removed = @()
    Get-ChildItem -LiteralPath (Join-Path $Root "server") -Filter "*.pyc.enc" -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            $removed += $_.Name
        }
    $distCfg = Join-Path $Root "config\.fx-dist.cfg"
    if (Test-Path -LiteralPath $distCfg) {
        Remove-Item -LiteralPath $distCfg -Force
        $removed += "config\.fx-dist.cfg"
    }
    if ($removed.Count -gt 0) {
        Write-Host "Removed stray distribution artifacts from dev repo: $($removed -join ', ')"
    }
}

function Test-DevRuntime([string]$Root) {
    $py = Join-Path $Root "runtime\python\python.exe"
    if (-not (Test-Path -LiteralPath $py)) {
        $cmdPy = Get-Command python -ErrorAction SilentlyContinue
        if ($cmdPy) { $py = $cmdPy.Source }
    }
    if (-not $py -or -not (Test-Path -LiteralPath $py)) {
        Write-Warning "Python not found - skipped runtime verification."
        return
    }
    $verifyScript = Join-Path $env:TEMP "flowx-dev-restore-verify.py"
    @"
import sys
from pathlib import Path
root = r"$($Root -replace '\\', '\\')"
sys.path.insert(0, root)
from server.app_code_crypto import is_development_tree, license_valid, needs_encrypted_bootstrap
r = Path(root)
print("dev_tree", is_development_tree(r))
print("license_ok", license_valid(r))
print("needs_enc", needs_encrypted_bootstrap(r))
if not is_development_tree(r) or not license_valid(r) or needs_encrypted_bootstrap(r):
    raise SystemExit(1)
"@ | Set-Content -LiteralPath $verifyScript -Encoding UTF8
    try {
        & $py $verifyScript
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime verification failed - dev tree still looks like distribution."
        }
        Write-Host "Runtime OK: dev tree, license bypass, no encrypted bootstrap."
    } finally {
        Remove-Item -LiteralPath $verifyScript -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "=== Restore Charts In Motion development build ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host ""

Test-DevRepo -Root $RepoRoot

$needsRestore = $false
$cryptoPath = Join-Path $pkg.ServerRoot "app_code_crypto.py"
$batPath = Join-Path $RepoRoot "start_cim.bat"
if (-not (Test-DevAwareAppCrypto $cryptoPath) -or -not (Test-DevAwareStartBat $batPath)) {
    $needsRestore = $true
    Write-Host "Distribution/mixed files detected - restoring dev startup files..." -ForegroundColor Yellow
} else {
    Write-Host "Dev-aware files already present; will still refresh env/cache." -ForegroundColor Green
}

if ($needsRestore) {
    $restored = $false
    if ($UseGit) {
        Write-Host "Trying git restore..."
        $restored = Invoke-GitRestore -Root $RepoRoot -RelPaths $FilesToRestore
        if ($restored) {
            Write-Host "Restored from git: $($FilesToRestore -join ', ')"
        }
    }
    if (-not $restored) {
        Write-Host "Git restore failed or skipped - using scripts\dev-restore\ fallback..."
        Copy-DevRestoreFallback -Root $RepoRoot -FallbackDir $DevRestoreDir -RelPaths $FilesToRestore
    }
}

if (-not $SkipEnvVar) {
    Set-FlowXDevEnvVar
}

if (-not $SkipCacheClear) {
    Clear-FlowXAppCache
}

Clear-StrayDistributionArtifacts -Root $RepoRoot

Test-DevRuntime -Root $RepoRoot

Write-Host ""
Write-Host "Done. Run start_cim.bat from the repo root." -ForegroundColor Green
Write-Host "Tip: do not apply GitHub/client updates to this dev folder - use Build-CiM.ps1 instead."
Write-Host ""
