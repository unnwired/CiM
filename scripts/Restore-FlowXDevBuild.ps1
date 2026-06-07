#Requires -Version 5.1
<#
.SYNOPSIS
  Restore FlowX development build after a client update was applied by mistake.

.DESCRIPTION
  Client/GitHub update packages overwrite start_flowx.bat and crypto bootstrap
  files with distribution logic (license required). This script:

    1. Restores dev-aware files (git, then scripts\dev-restore\ fallback)
    2. Sets FLOWX_DEV=1 for the current user
    3. Clears %LOCALAPPDATA%\FlowX\app-cache
    4. Verifies Python sees the tree as development (no license needed)

  ONLY run this on your development repo (must have server\server.py).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Restore-FlowXDevBuild.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Restore-FlowXDevBuild.ps1 -UseGit:$false
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
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $ScriptDir
}

$DevRestoreDir = Join-Path $ScriptDir "dev-restore"
$FilesToRestore = @(
    "start_flowx.bat",
    "server\app_code_crypto.py",
    "server\flowx_bootstrap.py"
)

function Test-DevRepo([string]$Root) {
    $serverPy = Join-Path $Root "server\server.py"
    if (-not (Test-Path -LiteralPath $serverPy)) {
        throw @"
This is not a FlowX development tree (missing server\server.py).

Restore-FlowXDevBuild.ps1 is ONLY for the dev repo - not client installs.
For client PCs use Repair-FlowXLicense.ps1 instead.
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
    return $text -match 'FLOWX_DISTRIBUTION'
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
    [System.Environment]::SetEnvironmentVariable("FLOWX_DEV", "1", "User")
    $env:FLOWX_DEV = "1"
    Write-Host "Set user env FLOWX_DEV=1 (new terminals will inherit it)."
}

function Clear-FlowXAppCache {
    $cache = Join-Path $env:LOCALAPPDATA "FlowX\app-cache"
    if (Test-Path -LiteralPath $cache) {
        Remove-Item -LiteralPath $cache -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared app-cache: $cache"
    } else {
        Write-Host "No app-cache to clear."
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
Write-Host "=== Restore FlowX development build ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host ""

Test-DevRepo -Root $RepoRoot

$needsRestore = $false
$cryptoPath = Join-Path $RepoRoot "server\app_code_crypto.py"
$batPath = Join-Path $RepoRoot "start_flowx.bat"
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

Test-DevRuntime -Root $RepoRoot

Write-Host ""
Write-Host "Done. Run start_flowx.bat from the repo root." -ForegroundColor Green
Write-Host "Tip: do not apply GitHub/client updates to this dev folder - use Build-FlowX.ps1 instead."
Write-Host ""
