#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke verification for FlowX distribution pipeline (vendor).
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [switch]$SkipEncrypt,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}

$py = "python"
$rp = Join-Path $RepoRoot "runtime\python\python.exe"
if (Test-Path -LiteralPath $rp) { $py = $rp }

Write-Host "=== FlowX distribution verify ==="

& $py -c @"
import os, sys, tempfile, json, shutil
from pathlib import Path
sys.path.insert(0, r'$RepoRoot')
os.environ['FLOWX_LICENSE_SECRET'] = 'verify-test'
from server.app_code_crypto import (
    install_key_for_machine, validate_install_key,
    encrypt_bytes, decrypt_bytes, app_code_key,
)
from server import update_apply as ua

mc = 'TESTMACHINE001'
k = install_key_for_machine(mc)
assert validate_install_key(mc, k)
assert ua._is_newer('2.0.0', '1.0.0')
# Installed tree must not use a stale FLOWX_LICENSE_SECRET env over config file.
tmpdir = Path(tempfile.mkdtemp())
try:
    (tmpdir / 'config').mkdir()
    (tmpdir / 'config' / '.fx-dist.cfg').write_text('file-secret', encoding='utf-8')
    os.environ['FLOWX_LICENSE_SECRET'] = 'env-secret'
    kf = install_key_for_machine(mc, base_dir=tmpdir)
    ke = install_key_for_machine(mc)
    assert kf != ke
    assert validate_install_key(mc, kf, base_dir=tmpdir)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    os.environ.pop('FLOWX_LICENSE_SECRET', None)
print('[ok] crypto + version compare + vendor file precedence')
"@

if (-not $SkipEncrypt -and (Test-Path -LiteralPath $ExportRoot)) {
    Write-Host "Running encrypt_app_code on export (copy test)..."
    & (Join-Path $ScriptDir "encrypt_app_code.ps1") -ExportRoot $ExportRoot
    Write-Host "[ok] encrypt_app_code"
} else {
    Write-Host "[skip] encrypt (no export or -SkipEncrypt)"
}

if (-not $SkipInstaller) {
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path -LiteralPath $iscc) {
        if (Test-Path -LiteralPath $ExportRoot) {
            & (Join-Path $ScriptDir "build_installer.ps1") -ExportRoot $ExportRoot
            Write-Host "[ok] installer build"
        } else {
            Write-Host "[skip] installer (no export)"
        }
    } else {
        Write-Host "[skip] installer (Inno Setup not installed)"
    }
}

Write-Host "=== Manual checklist ==="
Write-Host "1. Clean VM: FlowXSetup + install key"
Write-Host "2. Re-install over same dir: user JSON preserved"
Write-Host "3. Copy FlowX-Update-* to UPDATE\; cogwheel Apply update"
Write-Host "4. HTTPS manifest with file urls; Apply update (remote)"
Write-Host "5. Encrypted build starts (valid .flowx-license)"
Write-Host "=== Done ==="
