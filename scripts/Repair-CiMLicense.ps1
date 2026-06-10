#Requires -Version 5.1
<#
.SYNOPSIS
  Create or repair data\.cim-license on an installed Charts In Motion folder.

  Phase 1 lockdown: install keys are issued by support only (-InstallKey required).
  AutoFix (local key generation) is disabled on distribution installs.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [string]$MachineCode = "",
    [string]$InstallKey = "",
    [switch]$AutoFix
)

$ErrorActionPreference = "Stop"
if (-not $InstallRoot) {
    $InstallRoot = (Get-Location).Path
}
$InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path

$py = Join-Path $InstallRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$licensePath = Join-Path $InstallRoot "data\.cim-license"

if ($AutoFix) {
    throw @"
AutoFix is disabled (Phase 1 license lockdown).
Contact Charts In Motion support with your machine code and request an install key.
Then run: Repair-CiMLicense.bat
Or: powershell -ExecutionPolicy Bypass -File ""$PSScriptRoot\Repair-CiMLicense.ps1"" -InstallKey ""YOUR-KEY""
"@
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
Write-Host "Send the machine code above to Charts In Motion support to receive an install key."
Write-Host ""

if (-not $InstallKey) {
    $InstallKey = Read-Host "Enter install key from Charts In Motion support"
}
if (-not $InstallKey.Trim()) {
    throw "Install key is required."
}

$dataDir = Split-Path -Parent $licensePath
if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
}

& $py -c @"
import sys
sys.path.insert(0, r'$InstallRoot')
from pathlib import Path
from server.app_code_crypto import validate_install_key, current_machine_code

root = Path(r'$InstallRoot')
key = r'''$($InstallKey -replace "'", "''")'''
live = current_machine_code()
if not validate_install_key(live, key, base_dir=root):
    raise SystemExit(
        'Install key is not valid for this PC.' + chr(10) +
        'Machine code: ' + live + chr(10) +
        'Contact Charts In Motion support with this machine code.'
    )
lines = [
    '# Charts In Motion license - do not share',
    'MachineCode=' + live,
    'InstallKey=' + key.strip(),
]
Path(r'$($licensePath -replace "'", "''")').write_text(chr(10).join(lines) + chr(10), encoding='utf-8')
print('License written:', r'$($licensePath -replace "'", "''")')
"@

Write-Host "Done. Run start_cim.bat again."
