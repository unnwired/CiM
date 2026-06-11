#Requires -Version 5.1
<#
.SYNOPSIS
  Rebuild installer, silent-install to an isolated folder, verify license chain.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [string]$Version = "1.0.3-e2e",
    [string]$IsccPath = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    [switch]$SkipRebuild
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind Encrypted
$ExportRoot = $fx.ExportRoot
$VendorFile = Get-CiMDistProfilePath -InstallRoot $ExportRoot -Paths $fx

if (-not $InstallDir) {
    # No spaces: Inno /DIR= breaks on unquoted paths with spaces.
    $InstallDir = "D:\CiM"
}

if (-not (Test-Path -LiteralPath $VendorFile)) {
    throw "Missing vendor file. Run encrypt_app_code.ps1 first."
}

$secret = ([System.IO.File]::ReadAllText($VendorFile)).Trim().Trim([char]0xFEFF)
if (-not $secret) { throw "Empty vendor secret." }

Write-Host "=== CiM install E2E (isolated) ==="
Write-Host "Install dir: $InstallDir"
Write-Host "Version:     $Version"
Write-Host ""

if (-not $SkipRebuild) {
    $env:CIM_LICENSE_SECRET = $secret
    Write-Host "[1/6] encrypt_app_code.ps1"
    & (Join-Path $ScriptDir "encrypt_app_code.ps1") -ExportRoot $ExportRoot -LicenseSecret $secret

    Write-Host "[2/6] build_installer.ps1"
    & (Join-Path $ScriptDir "build_installer.ps1") -ExportRoot $ExportRoot -Version $Version -LicenseSecret $secret -IsccPath $IsccPath
} else {
    Write-Host "[1-2/6] SkipRebuild (using existing export + installer)"
}

$setupExe = Join-Path $fx.SetupOutputDir "CiMSetup-$Version.exe"
if (-not (Test-Path -LiteralPath $setupExe)) {
    throw "Installer not found: $setupExe"
}

$py = Join-Path $ExportRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
Remove-Item Env:CIM_LICENSE_SECRET -ErrorAction SilentlyContinue

$repoEsc = $RepoRoot.Replace("'", "''")
$exportEsc = $ExportRoot.Replace("'", "''")
$keyGen = & $py -s -c "import sys; sys.path.insert(0, r'$repoEsc'); from pathlib import Path; from server.app_code_crypto import current_machine_code, install_key_for_machine; root = Path(r'$exportEsc'); live = current_machine_code(); key = install_key_for_machine(live, base_dir=root); print(live); print(key)" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Machine code / key generation failed: $keyGen" }
$lines = @($keyGen | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
$machineCode = $lines[0]
$installKey = $lines[1]
Write-Host "[3/6] Machine code : $machineCode"
Write-Host "      Install key  : $installKey"

if (Test-Path -LiteralPath $InstallDir) {
    Write-Host "[4/6] Removing prior install: $InstallDir"
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

Write-Host "[5/6] Running CiMSetup (silent)..."
$logFile = Join-Path $env:TEMP "cim-e2e-install.log"
if (Test-Path -LiteralPath $logFile) { Remove-Item -LiteralPath $logFile -Force }
$installArgStr = (
    '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS ' +
    '/DIR="' + $InstallDir + '" ' +
    '/INSTALLKEY=' + $installKey + ' ' +
    '/LOG="' + $logFile + '"'
)
$p = Start-Process -FilePath $setupExe -ArgumentList $installArgStr -Wait -PassThru
if ($p.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $logFile) {
        Write-Host "--- Inno install log (tail) ---"
        Get-Content -LiteralPath $logFile -Tail 40 | ForEach-Object { Write-Host $_ }
    }
    throw "CiMSetup exit code $($p.ExitCode). See log: $logFile"
}

Write-Host "[6/6] Verifying license + decrypt..."
$licensePath = Join-Path $InstallDir "data\.cim-license"
if (-not (Test-Path -LiteralPath $licensePath)) {
    throw "License file missing: $licensePath"
}

$installEsc = $InstallDir.Replace("'", "''")
$verify = & $py -s -c @"
import os, sys
sys.path.insert(0, r'$installEsc')
os.environ.pop('CIM_LICENSE_SECRET', None)
from pathlib import Path
from server.app_code_crypto import license_valid, read_license, current_machine_code, validate_install_key, install_key_for_machine, app_code_key, decrypt_bytes, has_encrypted_server
root = Path(r'$installEsc')
live = current_machine_code()
mc, key = read_license(root)
expected = install_key_for_machine(live, base_dir=root)
ok_lic = license_valid(root)
ok_key = validate_install_key(live, key, base_dir=root)
ok_mc = (mc.upper() == live.upper())
print('live_mc', live)
print('file_mc', mc)
print('expected_key', expected)
print('file_key', key)
print('license_valid', ok_lic)
print('key_matches_vendor', ok_key)
print('mc_matches_pc', ok_mc)
if has_encrypted_server(root):
    enc = next((root / 'server').rglob('*.pyc.enc'), None)
    if enc:
        decrypt_bytes(enc.read_bytes(), app_code_key(root))
        print('decrypt_ok', True)
    else:
        print('decrypt_ok', False)
else:
    print('decrypt_ok', 'skip')
if not (ok_lic and ok_key and ok_mc):
    raise SystemExit(1)
"@ 2>&1
$verify | ForEach-Object { Write-Host "      $_" }
if ($LASTEXITCODE -ne 0) {
    throw "Post-install verification failed: $verify"
}

Write-Host "[7/7] Backend bootstrap smoke (cim_bootstrap -> server.server)..."
$installEsc = $InstallDir.Replace("'", "''")
$smoke = & $py -s -c @"
import os, sys
sys.path.insert(0, r'$installEsc')
os.environ.pop('CIM_LICENSE_SECRET', None)
from server.cim_bootstrap import _get_app
app = _get_app()
print('routes', len(getattr(app, 'routes', [])))
"@ 2>&1
$smoke | ForEach-Object { Write-Host "      $_" }
if ($LASTEXITCODE -ne 0) {
    throw "Backend bootstrap smoke failed: $smoke"
}

Write-Host ""
Write-Host "E2E PASS"
Write-Host "Install folder: $InstallDir"
exit 0
