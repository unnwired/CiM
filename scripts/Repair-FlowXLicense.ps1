#Requires -Version 5.1
<#
.SYNOPSIS
  Create or repair data\.flowx-license on an installed FlowX folder.

.PARAMETER AutoFix
  Rewrite license using this PC's machine code and distribution profile (no typing).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [string]$MachineCode = "",
    [string]$InstallKey = "",
    [string]$LicenseSecret = "",
    [switch]$AutoFix
)

$ErrorActionPreference = "Stop"
if (-not $InstallRoot) {
    $InstallRoot = (Get-Location).Path
}
$InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path

if ($LicenseSecret) {
    $env:FLOWX_LICENSE_SECRET = $LicenseSecret
} else {
    Remove-Item Env:FLOWX_LICENSE_SECRET -ErrorAction SilentlyContinue
}

$py = Join-Path $InstallRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$licensePath = Join-Path $InstallRoot "data\.flowx-license"

if ($AutoFix) {
    Write-Host "Auto-fixing license for: $InstallRoot"
    & $py -c @"
import sys
sys.path.insert(0, r'$InstallRoot')
from pathlib import Path
from server.app_code_crypto import (
    current_machine_code,
    distribution_profile_path,
    install_key_for_machine,
    read_license,
    validate_install_key,
)

root = Path(r'$InstallRoot')
live_mc = current_machine_code()
file_mc, file_key = read_license(root)
key = install_key_for_machine(live_mc, base_dir=root)
valid = validate_install_key(live_mc, key, base_dir=root)
profile = distribution_profile_path(root)
print('Live machine code:', live_mc)
if file_mc:
    print('License file had MC:', file_mc)
    if file_mc.upper() != live_mc.upper():
        print('NOTE: License machine code did not match this PC (repaired).')
print('Install key for this PC:', key)
print('Distribution profile:', profile, 'exists=', profile.is_file())
if not valid:
    raise SystemExit('Could not build a valid license (check distribution profile under config\\).')
lines = [
    '# FlowX license - do not share',
    'MachineCode=' + live_mc,
    'InstallKey=' + key,
]
(root / 'data').mkdir(parents=True, exist_ok=True)
(root / 'data' / '.flowx-license').write_text(chr(10).join(lines) + chr(10), encoding='utf-8')
print('License written:', root / 'data' / '.flowx-license')
"@
    Write-Host "Done. Run start_flowx.bat again."
    exit 0
}

if (-not $MachineCode) {
    $mc = & $py -c @"
import sys
sys.path.insert(0, r'$InstallRoot')
from server.app_code_crypto import current_machine_code
print(current_machine_code())
"@
    $MachineCode = $mc.Trim()
    Write-Host "Machine code (this PC): $MachineCode"
}

Write-Host ""
$profileCheck = & $py -c @"
import sys
sys.path.insert(0, r'$InstallRoot')
from pathlib import Path
from server.app_code_crypto import distribution_profile_path
p = distribution_profile_path(Path(r'$InstallRoot'))
print('ok' if p.is_file() else 'missing')
"@ 2>&1
if ("$profileCheck".Trim() -eq 'missing') {
    Write-Host "WARNING: Distribution profile missing under config\ on this install."
    Write-Host "Runtime cannot validate license without the profile from your build."
}
Write-Host ""
if (-not $InstallKey) {
    Write-Host "Tip: run with -AutoFix to rewrite license from this PC's distribution profile."
    Write-Host ""
    $InstallKey = Read-Host "Enter install key from FlowX support"
}

$dataDir = Split-Path -Parent $licensePath
if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
}

& $py -c @"
import sys
sys.path.insert(0, r'$InstallRoot')
from pathlib import Path
from server.app_code_crypto import validate_install_key, install_key_for_machine, current_machine_code

root = Path(r'$InstallRoot')
mc = r'''$($MachineCode -replace "'", "''")'''
key = r'''$($InstallKey -replace "'", "''")'''
live = current_machine_code()
if mc.upper() != live.upper():
    print('WARNING: Typed machine code differs from this PC.')
    print('  This PC:', live)
    print('  You used:', mc)
    expected_live = install_key_for_machine(live, base_dir=root)
    print('  Key for THIS PC:', expected_live)
if not validate_install_key(live, key, base_dir=root):
    expected = install_key_for_machine(live, base_dir=root)
    raise SystemExit(
        'Install key does not match this install folder.' + chr(10) +
        'Machine code: ' + live + chr(10) +
        'Key for this install profile: ' + expected + chr(10) +
        'If support sent a different key, they used the wrong build export — ' +
        'run Generate-FlowXInstallKey.ps1 -InstallRoot \"' + str(root) + '\"'
    )
good_key = install_key_for_machine(live, base_dir=root)
lines = [
    '# FlowX license - do not share',
    'MachineCode=' + live,
    'InstallKey=' + good_key,
]
Path(r'$($licensePath -replace "'", "''")').write_text(chr(10).join(lines) + chr(10), encoding='utf-8')
print('License written:', r'$($licensePath -replace "'", "''")')
"@

Write-Host "Done. Run start_flowx.bat again."
