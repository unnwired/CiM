#Requires -Version 5.1
<#
.SYNOPSIS
  Fail the build if installer secret, embedded profile, and Python crypto disagree.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$RepoRoot = "",
    [string]$InstallerOutputDir = "",
    [switch]$SkipExportCryptoMatch
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
$fx = Get-CiMPaths -RepoRoot $RepoRoot
if (-not $ExportRoot) { $ExportRoot = $fx.ExportRoot }
if (-not $InstallerOutputDir) { $InstallerOutputDir = $fx.InstallerOutputDir }

$repoCrypto = Join-Path $RepoRoot "server\app_code_crypto.py"
$exportCrypto = Join-Path $ExportRoot "server\app_code_crypto.py"
$embeddedPy = Join-Path $ExportRoot "server\_cim_dist_embedded.py"
$genPas = $fx.GeneratedSecretPas
$vendorFile = Join-Path $ExportRoot $fx.DistProfileRel

if (-not (Test-Path -LiteralPath $repoCrypto)) {
    throw "Missing repo crypto: $repoCrypto"
}
if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw "Missing export: $ExportRoot"
}
if (Test-Path -LiteralPath $vendorFile) {
    throw "Phase 1 lockdown: config\.fx-dist.cfg must not ship in export. Run encrypt_app_code.ps1 again."
}
if (-not (Test-Path -LiteralPath $embeddedPy)) {
    throw "Missing server\_cim_dist_embedded.py (run encrypt_app_code.ps1): $embeddedPy"
}

$vendorSecret = Get-CiMVendorSecret -RepoRoot $RepoRoot
if (-not $vendorSecret) {
    throw "Missing vendor secret (config\.build_license_secret or CIM_LICENSE_SECRET)."
}

if (-not $SkipExportCryptoMatch) {
    if (-not (Test-Path -LiteralPath $exportCrypto)) {
        throw "Missing export crypto (run encrypt_app_code.ps1): $exportCrypto"
    }
    $repoHash = (Get-FileHash -LiteralPath $repoCrypto -Algorithm SHA256).Hash
    $exportHash = (Get-FileHash -LiteralPath $exportCrypto -Algorithm SHA256).Hash
    if ($repoHash -ne $exportHash) {
        throw @"
Export server\app_code_crypto.py does not match repo.
Repo:   $repoCrypto
Export: $exportCrypto
Run: .\scripts\encrypt_app_code.ps1  or  .\scripts\Sync-ExportDistributionFixes.ps1
"@
    }
}

if (Test-Path -LiteralPath $genPas) {
    $pasText = Get-Content -LiteralPath $genPas -Raw
    if ($pasText -notmatch "Result := '([^']*(?:''[^']*)*)'") {
        throw "Cannot parse secret from $genPas"
    }
    $innoSecret = $Matches[1].Replace("''", "'")
    if ($innoSecret -ne $vendorSecret) {
        throw @"
Installer secret (generated_license_secret.pas) != build vendor secret.
Run build_installer.ps1 after encrypt_app_code.ps1 with the same CIM_LICENSE_SECRET.
"@
    }
}

$py = Join-Path $RepoRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

$env:CIM_LICENSE_SECRET = "__cim_verify_wrong_env__"
$testMc = "0123456789ABCDEF0123456789ABCDEF"
$helper = Join-Path $env:TEMP ("cim-verify-chain-{0}.py" -f [Guid]::NewGuid().ToString("N"))
$pyLines = @(
    "import sys",
    "from pathlib import Path",
    "sys.path.insert(0, r'$($RepoRoot.Replace('\', '\\').Replace("'", "\'"))')",
    "from server.app_code_crypto import install_key_for_machine",
    "root = Path(r'$($ExportRoot.Replace('\', '\\').Replace("'", "\'"))')",
    "mc = '$testMc'",
    "print(install_key_for_machine(mc, base_dir=root))"
)
Set-Content -LiteralPath $helper -Value ($pyLines -join "`n") -Encoding UTF8
try {
    $pyKey = (& $py $helper 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pyKey) {
        throw "Python install_key_for_machine failed: $pyKey"
    }
} finally {
    Remove-Item -LiteralPath $helper -Force -ErrorAction SilentlyContinue
}
Remove-Item Env:CIM_LICENSE_SECRET -ErrorAction SilentlyContinue

$showScript = Join-Path $ScriptDir "Show-CiMInstallKey.ps1"
$innoKey = (& powershell -NoProfile -ExecutionPolicy Bypass -File $showScript `
    -MachineCode $testMc -LicenseSecret $vendorSecret 2>&1 | Out-String)
if ($innoKey -notmatch "Install key\s*:\s*([0-9A-F]{4}(?:-[0-9A-F]{4}){5})") {
    throw "Show-CiMInstallKey.ps1 did not return a key."
}
$innoKey = $Matches[1].Trim().ToUpper()
if ($innoKey -ne $pyKey.ToUpper()) {
    throw @"
License chain broken: Python ($pyKey) != Inno formula ($innoKey).
Fix server\app_code_crypto.py or Show-CiMInstallKey.ps1 before shipping.
"@
}

Write-Host "[ok] Charts In Motion license chain: embedded secret, Python (env ignored), Inno MD5 all match."
