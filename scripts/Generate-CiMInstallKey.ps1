#Requires -Version 5.1
<#
.SYNOPSIS
  Generate install key from a client machine code (vendor build machine only).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MachineCode,
    [string]$LicenseSecret = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir

$secret = Get-CiMVendorSecret -LicenseSecret $LicenseSecret -RepoRoot $RepoRoot
if (-not $secret) {
    throw "Set CIM_LICENSE_SECRET or create config\.build_license_secret on the build machine."
}
Write-Host "Secret source: vendor build machine (not client install)"

$py = Join-Path $RepoRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$code = $MachineCode.Trim().ToUpper()
$helper = Join-Path $env:TEMP ("cim-gen-key-{0}.py" -f [Guid]::NewGuid().ToString("N"))
$secretEsc = $secret.Replace("'", "\'")
$pyLines = @(
    "import sys",
    "from pathlib import Path",
    "sys.path.insert(0, r'$($RepoRoot.Replace('\', '\\').Replace("'", "\'"))')",
    "from server.app_code_crypto import install_key_for_machine",
    "mc = '$($code.Replace("'", "\'"))'",
    "sec = r'$secretEsc'.encode('utf-8')",
    "print(install_key_for_machine(mc, secret=sec))"
)
Set-Content -LiteralPath $helper -Value ($pyLines -join "`n") -Encoding UTF8
try {
    $key = & $py $helper 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Key generation failed: $key" }
    $key = "$key".Trim()
} finally {
    Remove-Item -LiteralPath $helper -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Machine code : $code"
Write-Host "Install key  : $key"
Write-Host ""
Write-Host "Send the install key to the client."
Write-Host "Fresh install: paste in the CiMSetup license wizard (step 2)."
Write-Host "Already installed: Repair-CiMLicense.bat"
Write-Host ""
