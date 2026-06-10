#Requires -Version 5.1
<#
.SYNOPSIS
  Print install key for CiMSetup wizard (same MD5 as server.app_code_crypto + Inno).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MachineCode,
    [string]$LicenseSecret = "",
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-CiMPaths -RepoRoot $RepoRoot

if (-not $InstallRoot) {
    $InstallRoot = $fx.ExportRoot
}

Remove-Item Env:CIM_LICENSE_SECRET -ErrorAction SilentlyContinue
$secret = Get-CiMVendorSecret -LicenseSecret $LicenseSecret -RepoRoot $RepoRoot
if (-not $secret) {
    throw "Set -LicenseSecret or create config\.build_license_secret on the build machine."
}
$secretSource = if ($LicenseSecret) { "-LicenseSecret" } else { "config\.build_license_secret" }

$py = Join-Path $RepoRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$mc = $MachineCode.Trim().ToUpper()
$helper = Join-Path $env:TEMP ("flowx-show-key-{0}.py" -f [Guid]::NewGuid().ToString("N"))
$pyLines = @(
    "import sys",
    "from pathlib import Path",
    "sys.path.insert(0, r'$($RepoRoot.Replace('\', '\\').Replace("'", "\'"))')",
    "from server.app_code_crypto import install_key_for_machine",
    "root = Path(r'$($InstallRoot.Replace('\', '\\').Replace("'", "\'"))')",
    "mc = '$($mc.Replace("'", "\'"))'",
    "sec = r'$($secret.Replace("'", "\'"))'.encode('utf-8')",
    "print(install_key_for_machine(mc, secret=sec))"
)
Set-Content -LiteralPath $helper -Value ($pyLines -join "`n") -Encoding UTF8
try {
    $key = (& $py $helper 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $key) { throw "Key generation failed: $key" }
} finally {
    Remove-Item -LiteralPath $helper -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Machine code : $mc"
Write-Host "Install key  : $key"
Write-Host "Secret from  : $secretSource"
Write-Host ""
Write-Host "Matches CiMSetup.exe and Repair/runtime on the same export build."
Write-Host ""
