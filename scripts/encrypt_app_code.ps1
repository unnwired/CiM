#Requires -Version 5.1
<#
.SYNOPSIS
  Encrypt Charts In Motion app code in an export tree (server *.pyc + frontend static JS).

.DESCRIPTION
  Run AFTER export_cim.ps1 succeeds. Does not modify export_cim.ps1.
  Set CIM_LICENSE_SECRET (or -LicenseSecret) before publishing; same secret
  is used by Generate-CiMInstallKey.ps1 and runtime decryption.

.PARAMETER ExportRoot
  Default: installer\Encrypted\CiM under the repo.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$LicenseSecret = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
if (-not $ExportRoot) {
    $fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind Encrypted
    $ExportRoot = $fx.ExportRoot
} else {
    if (-not [System.IO.Path]::IsPathRooted($ExportRoot)) {
        $ExportRoot = Join-Path $RepoRoot $ExportRoot
    }
    $ExportRoot = [System.IO.Path]::GetFullPath($ExportRoot)
    $fx = Resolve-CiMPathsForExportRoot -ExportRoot $ExportRoot -RepoRoot $RepoRoot -DefaultKind Encrypted
}
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot

function Test-ExportPackageComplete {
    param([string]$Root)
    $required = @(
        "start_cim.bat",
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
$serverSrc = $pkg.ServerRoot
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
    $env:CIM_LICENSE_SECRET = $LicenseSecret
}
$secretToShip = Get-CiMVendorSecret -LicenseSecret $LicenseSecret -RepoRoot $RepoRoot
if (-not $secretToShip) {
    $existingProfile = Get-CiMDistProfilePath -InstallRoot $ExportRoot -Paths $fx
    if (Test-Path -LiteralPath $existingProfile) {
        $secretToShip = ([System.IO.File]::ReadAllText($existingProfile)).Trim().Trim([char]0xFEFF)
        Write-Host "Using secret from export profile (build only): $existingProfile"
    }
}
if (-not $secretToShip) {
    throw "Set CIM_LICENSE_SECRET or create config\.build_license_secret before encrypt_app_code.ps1."
}
$env:CIM_LICENSE_SECRET = $secretToShip

# Temporary profile for encrypt helper only — removed after _cim_dist_embedded.py is written.
$configDir = Join-Path $ExportRoot "config"
if (-not (Test-Path -LiteralPath $configDir)) {
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$profilePath = Join-Path $configDir ".fx-dist.cfg"
[System.IO.File]::WriteAllText($profilePath, $secretToShip, $utf8NoBom)

$helper = @"
import os, sys
from pathlib import Path
sys.path.insert(0, r'$($pkg.PackagesRoot -replace '\\', '\\')')
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

# Distribution must not ship plaintext server modules alongside *.pyc.enc — that makes
# is_development_tree() true and breaks /static JS (blank Electron shell).
keep_server_py = frozenset({
    '__init__.py', 'app_code_crypto.py', 'cim_bootstrap.py', 'product_config.py',
    '_cim_dist_embedded.py', 'license_client.py', 'license_routes.py', 'http_ssl.py',
    'session_store.py', 'user_data_paths.py', 'web_auth.py', 'showcase_host_gate.py',
})
for py_path in sorted(server_dir.glob('*.py')):
    if py_path.name in keep_server_py:
        continue
    if (server_dir / (py_path.stem + '.pyc.enc')).is_file() or (server_dir / (py_path.stem + '.pyc')).is_file():
        py_path.unlink()
        print(f'Removed plaintext server module (encrypted build): {py_path.name}')
"@

& $py -c $helper
if ($LASTEXITCODE -ne 0) { throw "encrypt_app_code failed (exit $LASTEXITCODE)" }

$encLeft = @(Get-ChildItem -LiteralPath (Join-Path $ExportRoot "server") -Recurse -Filter "*.pyc.enc" -Force -ErrorAction SilentlyContinue)
if ($encLeft.Count -eq 0) {
    throw @"
No encrypted server files under $ExportRoot\server.
Run export_cim.ps1 -Mode distribution -HardenAll, then encrypt_app_code.ps1 again with CIM_LICENSE_SECRET set.
"@
}

function Write-CiMEmbeddedDistSecret {
    param(
        [string]$ExportRoot,
        [string]$Secret
    )
    $mask = [System.Text.Encoding]::UTF8.GetBytes("CiM-embed-v1!!")
    $secretBytes = [System.Text.Encoding]::UTF8.GetBytes($Secret)
    $obf = New-Object System.Collections.Generic.List[int]
    for ($i = 0; $i -lt $secretBytes.Length; $i++) {
        $obf.Add($secretBytes[$i] -bxor $mask[$i % $mask.Length])
    }
    $tuple = ($obf | ForEach-Object { "$_" }) -join ", "
    $utf8 = New-Object System.Text.UTF8Encoding $false
    $embeddedPath = Join-Path $ExportRoot "server\_cim_dist_embedded.py"
    $content = @"
# AUTO-GENERATED by encrypt_app_code.ps1 — do not edit.
"""Build-time embedded distribution secret (not shipped as config/.fx-dist.cfg)."""
from __future__ import annotations

_OBF = ($tuple)
_MASK = b"CiM-embed-v1!!"


def distribution_secret_bytes() -> bytes:
    return bytes(_OBF[i] ^ _MASK[i % len(_MASK)] for i in range(len(_OBF)))
"@
    [System.IO.File]::WriteAllText($embeddedPath, $content, $utf8)
    Write-Host "Wrote server\_cim_dist_embedded.py (runtime decrypt + license verify)."
}

Write-CiMEmbeddedDistSecret -ExportRoot $ExportRoot -Secret $secretToShip

# Phase 1 lockdown: do not ship plaintext vendor secret on client installs.
if (Test-Path -LiteralPath $profilePath) { Remove-Item -LiteralPath $profilePath -Force }
$legacyProfile = Join-Path $configDir ".flowx_vendor_secret"
if (Test-Path -LiteralPath $legacyProfile) { Remove-Item -LiteralPath $legacyProfile -Force }
Write-Host "Removed config\.fx-dist.cfg from export (vendor secret stays on build machine)."

# Ship plaintext bootstrap modules (copy from repo if export stripped them)
$plainFiles = @(
    "server\app_code_crypto.py",
    "server\cim_bootstrap.py",
    "server\product_config.py",
    "server\license_client.py",
    "server\license_routes.py",
    "server\session_store.py",
    "server\user_data_paths.py",
    "server\web_auth.py",
    "server\showcase_host_gate.py",
    "server\http_ssl.py"
)
foreach ($rel in $plainFiles) {
    if ($rel -like "server\*") {
        $src = Join-Path $pkg.ServerRoot ($rel -replace '^server\\', '')
    } else {
        $src = Join-Path $RepoRoot $rel
    }
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

$verifyChain = Join-Path $ScriptDir "Verify-CiMLicenseChain.ps1"
if (Test-Path -LiteralPath $verifyChain) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyChain `
        -ExportRoot $ExportRoot -RepoRoot $RepoRoot -InstallerOutputDir $fx.InstallerOutputDir
}

Write-Host "App-code encryption complete: $ExportRoot"
Write-Host "Next: build_installer.ps1 and/or build_update_package.ps1"
