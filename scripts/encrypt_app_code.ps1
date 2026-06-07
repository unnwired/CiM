#Requires -Version 5.1
<#
.SYNOPSIS
  Encrypt FlowX app code in an export tree (server *.pyc + frontend static JS).

.DESCRIPTION
  Run AFTER export_flowx.ps1 succeeds. Does not modify export_flowx.ps1.
  Set FLOWX_LICENSE_SECRET (or -LicenseSecret) before publishing; same secret
  is used by Generate-FlowXInstallKey.ps1 and runtime decryption.

.PARAMETER ExportRoot
  Default: installer\output\FlowX under the repo.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$LicenseSecret = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}

function Test-ExportPackageComplete {
    param([string]$Root)
    $required = @(
        "start_flowx.bat",
        "data\nse_data.db",
        "frontend\build\index.html",
        "runtime\python\python.exe",
        "server\__init__.py"
    )
    $missing = @()
    foreach ($rel in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $rel))) { $missing += $rel }
    }
    $serverPyc = Join-Path $Root "server\server.pyc"
    $serverEnc = Join-Path $Root "server\server.pyc.enc"
    if (-not (Test-Path -LiteralPath $serverPyc) -and -not (Test-Path -LiteralPath $serverEnc)) {
        $missing += "server\server.pyc or server.pyc.enc"
    }
    if ($missing.Count -gt 0) {
        throw "Export incomplete. Missing: $($missing -join ', ')"
    }
}

function Test-PythonHasCryptography {
    param([string]$PyExe)
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $PyExe -c "import cryptography" 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $oldEap
    }
}

function Ensure-PythonCryptography {
    param([string]$PyExe)
    if (Test-PythonHasCryptography -PyExe $PyExe) { return }
    Write-Host "Installing cryptography into: $PyExe"
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $PyExe -m pip install --upgrade cryptography 1>$null 2>$null
    } finally {
        $ErrorActionPreference = $oldEap
    }
    if (-not (Test-PythonHasCryptography -PyExe $PyExe)) {
        throw "Failed to install cryptography for $PyExe. Run: `"$PyExe`" -m pip install cryptography"
    }
}

function Get-BuildPythonExe {
    param([string]$ExportRoot)
    $candidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "runtime\python\python.exe"),
        "python",
        (Join-Path $ExportRoot "runtime\python\python.exe")
    )
    foreach ($c in $candidates) {
        if ($c -ne "python" -and -not (Test-Path -LiteralPath $c)) { continue }
        if (Test-PythonHasCryptography -PyExe $c) { return $c }
    }
    foreach ($c in $candidates) {
        if ($c -ne "python" -and -not (Test-Path -LiteralPath $c)) { continue }
        Ensure-PythonCryptography -PyExe $c
        return $c
    }
    throw "No Python found. Install Python 3 and: pip install cryptography"
}

Test-ExportPackageComplete -Root $ExportRoot
$py = Get-BuildPythonExe -ExportRoot $ExportRoot
Write-Host "Using build Python: $py"

# Recompile server modules from repo sources so encrypt picks up latest code (not stale .pyc.enc).
$serverSrc = Join-Path $RepoRoot "server"
$serverDst = Join-Path $ExportRoot "server"
if (Test-Path -LiteralPath $serverSrc) {
    Get-ChildItem -LiteralPath $serverSrc -File -Filter "*.py" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "__init__.py" } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $serverDst $_.Name) -Force
        }
    & $py -m compileall -b -q $serverDst
    if ($LASTEXITCODE -ne 0) { throw "compileall failed for $serverDst" }
    Write-Host "Recompiled server/*.py from repo into export (-b legacy .pyc layout)."
}

if ($LicenseSecret) {
    $env:FLOWX_LICENSE_SECRET = $LicenseSecret
}
$existingProfile = Get-FlowXDistProfilePath -InstallRoot $ExportRoot -Paths $fx
if (-not $env:FLOWX_LICENSE_SECRET -and (Test-Path -LiteralPath $existingProfile)) {
    $env:FLOWX_LICENSE_SECRET = ([System.IO.File]::ReadAllText($existingProfile)).Trim().Trim([char]0xFEFF)
    Write-Host "Using FLOWX_LICENSE_SECRET from existing profile: $existingProfile"
}
if (-not $env:FLOWX_LICENSE_SECRET) {
    Write-Warning "FLOWX_LICENSE_SECRET not set; using default dev secret (change before client release)."
}

# Write distribution profile first so app_code_key(root) matches what clients will use at runtime.
$secretToShip = $env:FLOWX_LICENSE_SECRET
if (-not $secretToShip) { $secretToShip = "flowx-distribution-change-me" }
$configDir = Join-Path $ExportRoot "config"
if (-not (Test-Path -LiteralPath $configDir)) {
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
}
# UTF8NoBOM: PowerShell 5.1 UTF8 adds BOM and breaks MD5 install keys vs Inno.
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$profilePath = Join-Path $configDir ".fx-dist.cfg"
[System.IO.File]::WriteAllText($profilePath, $secretToShip, $utf8NoBom)
$legacyProfile = Join-Path $configDir ".flowx_vendor_secret"
if (Test-Path -LiteralPath $legacyProfile) { Remove-Item -LiteralPath $legacyProfile -Force }

$helper = @"
import os, sys
from pathlib import Path
sys.path.insert(0, r'$RepoRoot')
from server import app_code_crypto as c

root = Path(r'$ExportRoot')
server_dir = root / 'server'
js_dir = root / 'frontend' / 'build' / 'static' / 'js'
key = c.app_code_key(root)
enc_count = 0

for enc_path in sorted(server_dir.rglob('*.pyc.enc')):
    if enc_path.stem in c.PLAINTEXT_BOOTSTRAP_STEMS:
        continue
    pyc_path = enc_path.with_name(enc_path.name[:-4])
    if not pyc_path.exists():
        pyc_path.write_bytes(c.decrypt_bytes(enc_path.read_bytes(), key))

if js_dir.is_dir():
    for enc_path in sorted(js_dir.glob('*.js.enc')):
        js_path = enc_path.with_name(enc_path.name[:-4])
        if not js_path.exists():
            js_path.write_bytes(c.decrypt_bytes(enc_path.read_bytes(), key))

for pyc in sorted(server_dir.rglob('*.pyc')):
    if pyc.stem in c.PLAINTEXT_BOOTSTRAP_STEMS:
        continue
    enc_path = pyc.with_suffix(pyc.suffix + '.enc')
    data = pyc.read_bytes()
    out = pyc.with_suffix(pyc.suffix + '.enc')
    out.write_bytes(c.encrypt_bytes(data, key))
    pyc.unlink()
    enc_count += 1

if js_dir.is_dir():
    for js in sorted(js_dir.glob('*.js')):
        if js.name.endswith('.js.enc'):
            continue
        enc_js = js.with_suffix(js.suffix + '.enc')
        data = js.read_bytes()
        out = js.with_suffix(js.suffix + '.enc')
        out.write_bytes(c.encrypt_bytes(data, key))
        js.unlink()
        enc_count += 1

print(f'Encrypted {enc_count} files under {root}')
"@

& $py -c $helper
if ($LASTEXITCODE -ne 0) { throw "encrypt_app_code failed (exit $LASTEXITCODE)" }

$encLeft = @(Get-ChildItem -LiteralPath (Join-Path $ExportRoot "server") -Recurse -Filter "*.pyc.enc" -Force -ErrorAction SilentlyContinue)
if ($encLeft.Count -eq 0) {
    throw @"
No encrypted server files under $ExportRoot\server.
Run export_flowx.ps1 -Mode distribution -HardenAll, then encrypt_app_code.ps1 again with FLOWX_LICENSE_SECRET set.
"@
}

Write-Host "Wrote config\.fx-dist.cfg (matches encrypt / install keys)."

# Ship plaintext bootstrap modules (copy from repo if export stripped them)
$plainFiles = @(
    "server\app_code_crypto.py",
    "server\flowx_bootstrap.py"
)
foreach ($rel in $plainFiles) {
    $src = Join-Path $RepoRoot $rel
    $dst = Join-Path $ExportRoot $rel
    if (Test-Path -LiteralPath $src) {
        $parent = Split-Path -Parent $dst
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }
}

# Client runtime decrypt needs cryptography in the export embedded Python
$exportPy = Join-Path $ExportRoot "runtime\python\python.exe"
if (Test-Path -LiteralPath $exportPy) {
    Ensure-PythonCryptography -PyExe $exportPy
    Write-Host "Verified cryptography in export runtime Python."
}

$verifyChain = Join-Path $ScriptDir "Verify-FlowXLicenseChain.ps1"
if (Test-Path -LiteralPath $verifyChain) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyChain `
        -ExportRoot $ExportRoot -RepoRoot $RepoRoot -InstallerOutputDir $fx.InstallerOutputDir
}

Write-Host "App-code encryption complete: $ExportRoot"
Write-Host "Next: build_installer.ps1 and/or build_update_package.ps1"
