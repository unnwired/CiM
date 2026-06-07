#Requires -Version 5.1
<#
.SYNOPSIS
  Print install key for FlowXSetup wizard (same MD5 as server.app_code_crypto + Inno).
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
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot

if (-not $InstallRoot) {
    $InstallRoot = $fx.ExportRoot
}

$vendorFile = Get-FlowXDistProfilePath -InstallRoot $InstallRoot -Paths $fx
Remove-Item Env:FLOWX_LICENSE_SECRET -ErrorAction SilentlyContinue

if ($LicenseSecret) {
    $secret = $LicenseSecret.Trim()
} elseif (Test-Path -LiteralPath $vendorFile) {
    $secret = ([System.IO.File]::ReadAllText($vendorFile)).Trim().Trim([char]0xFEFF)
} else {
    throw "No -LicenseSecret and no $vendorFile"
}

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
    "print(install_key_for_machine(mc, base_dir=root))"
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
Write-Host "Secret from  : $(if ($LicenseSecret) { '-LicenseSecret' } else { $vendorFile })"
Write-Host ""
Write-Host "Matches FlowXSetup.exe and Repair/runtime on the same export build."
Write-Host ""
