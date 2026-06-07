#Requires -Version 5.1
<#
.SYNOPSIS
  Generate install key from a client machine code (must match shipped encrypt secret).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MachineCode,
    [string]$InstallRoot = "",
    [string]$LicenseSecret = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot

if (-not $InstallRoot) {
    $InstallRoot = $fx.ExportRoot
}

$secretFile = Get-FlowXDistProfilePath -InstallRoot $InstallRoot -Paths $fx
$fileSecret = ""
if (Test-Path -LiteralPath $secretFile) {
    $fileSecret = (Get-Content -LiteralPath $secretFile -Raw).Trim()
    Write-Host "Secret source: $secretFile"
}
if ($LicenseSecret) {
    $env:FLOWX_LICENSE_SECRET = $LicenseSecret
    Write-Host "Secret source: -LicenseSecret parameter"
} elseif ($fileSecret) {
    if ($env:FLOWX_LICENSE_SECRET -and ($env:FLOWX_LICENSE_SECRET.Trim() -ne $fileSecret)) {
        Write-Warning "FLOWX_LICENSE_SECRET env differed from $secretFile; ignored - using FILE (same as client Repair/runtime)."
    }
    Remove-Item Env:FLOWX_LICENSE_SECRET -ErrorAction SilentlyContinue
} elseif (-not $env:FLOWX_LICENSE_SECRET) {
    throw "No distribution profile under $InstallRoot\config. Run encrypt_app_code.ps1 or set FLOWX_LICENSE_SECRET."
} else {
    Write-Warning "No vendor file; using FLOWX_LICENSE_SECRET env only."
}

$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$code = $MachineCode.Trim().ToUpper()
$helper = Join-Path $env:TEMP ("flowx-gen-key-{0}.py" -f [Guid]::NewGuid().ToString("N"))
$pyLines = @(
    "import sys",
    "from pathlib import Path",
    "sys.path.insert(0, r'$($RepoRoot.Replace('\', '\\').Replace("'", "\'"))')",
    "from server.app_code_crypto import install_key_for_machine",
    "mc = '$($code.Replace("'", "\'"))'"
)
if ($fileSecret) {
    $pyLines += "print(install_key_for_machine(mc, base_dir=Path(r'$($InstallRoot.Replace('\', '\\').Replace("'", "\'"))')))"
} else {
    $pyLines += "print(install_key_for_machine(mc))"
}
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
Write-Host "Fresh install: paste in the FlowXSetup license wizard (step 2)."
Write-Host "Already installed: Repair-FlowXLicense.bat"
Write-Host ""
