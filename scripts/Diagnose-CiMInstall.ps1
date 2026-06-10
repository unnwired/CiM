#Requires -Version 5.1
<#
.SYNOPSIS
  Run on the CLIENT PC from the Charts In Motion install folder. Reports common install/startup issues.
#>
[CmdletBinding()]
param([string]$InstallRoot = "")

$ErrorActionPreference = "Continue"
if (-not $InstallRoot) { $InstallRoot = (Get-Location).Path }
try {
    $InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path
} catch {
    Write-Host "[FAIL] Not a valid path: $InstallRoot"
    exit 1
}

Write-Host ""
Write-Host "========== Charts In Motion install diagnostic =========="
Write-Host "Install folder: $InstallRoot"
Write-Host ""

$fail = 0
function Report([string]$Label, [bool]$Ok, [string]$Detail = "") {
    if ($Ok) {
        Write-Host "[OK]   $Label"
    } else {
        Write-Host "[FAIL] $Label"
        $script:fail++
    }
    if ($Detail) { Write-Host "       $Detail" }
}

$checks = @(
    @{ Path = "start_cim.bat"; Label = "Launcher" },
    @{ Path = "data\nse_data.db"; Label = "Database" },
    @{ Path = "db_sqlite.py"; Label = "db_sqlite.py" },
    @{ Path = "runtime\python\python.exe"; Label = "Bundled Python" },
    @{ Path = "frontend\build\index.html"; Label = "Frontend build" },
    @{ Path = "data\.cim-license"; Label = "License file" },
    @{ Path = "server\_cim_dist_embedded.py"; Label = "Embedded distribution secret" }
)
foreach ($c in $checks) {
    $p = Join-Path $InstallRoot $c.Path
    Report $c.Label (Test-Path -LiteralPath $p) $p
}

$legacyProfile = Join-Path $InstallRoot "config\.fx-dist.cfg"
if (Test-Path -LiteralPath $legacyProfile) {
    Report "Legacy config\.fx-dist.cfg absent" $false "Remove $legacyProfile (Phase 1 lockdown)"
}

$dist = Test-Path -LiteralPath (Join-Path $InstallRoot "server\server.pyc.enc")
$plain = (Test-Path -LiteralPath (Join-Path $InstallRoot "server\server.py")) -or
    (Test-Path -LiteralPath (Join-Path $InstallRoot "server\server.pyc"))
$layoutDetail = if ($dist) { "distribution (encrypted)" } else { "dev/plain" }
Report "Server layout" ($dist -or $plain) $layoutDetail

$py = Join-Path $InstallRoot "runtime\python\python.exe"
if (Test-Path -LiteralPath $py) {
    & $py -c "import cryptography" 2>$null
    Report "cryptography module" ($LASTEXITCODE -eq 0) "Required for distribution builds"
}

if ([bool]$env:CIM_LICENSE_SECRET) {
    Report "CIM_LICENSE_SECRET env unset" $false "Env is set; Repair clears it for installed apps."
} else {
    Report "CIM_LICENSE_SECRET env unset" $true
}

$errLog = Join-Path $InstallRoot "runtime\logs\backend-startup.err.log"
if (Test-Path -LiteralPath $errLog) {
    Write-Host ""
    Write-Host "--- backend-startup.err.log (last 20 lines) ---"
    Get-Content -LiteralPath $errLog -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
    Write-Host "---"
    if ((Get-Content -LiteralPath $errLog -Raw -ErrorAction SilentlyContinue) -match 'InvalidTag') {
        Report "Backend startup log" $false "cryptography.exceptions.InvalidTag (see log above)"
    }
}

$electron = Join-Path $InstallRoot "desktop\node_modules\electron\dist\electron.exe"
Report "Electron (desktop UI)" (Test-Path -LiteralPath $electron) $electron

Write-Host ""
if ($fail -eq 0) {
    Write-Host "All checks passed. If UI still fails, run start_cim.bat and watch the window."
    Write-Host "Then send runtime\logs\backend-startup.err.log to support if needed."
} else {
    Write-Host "$fail check(s) failed."
    Write-Host ""
    Write-Host "Usually you can fix without reinstall:"
    Write-Host "  1. Repair-CiMLicense.ps1 (if license fail)"
    Write-Host "  2. Fresh update ZIP + Install-Client-Update.bat"
    Write-Host "  3. Full reinstall preserves data\ if installer uses onlyifdoesntexist on user JSON"
}
Write-Host ""
if ($fail -gt 0) { exit 1 }
exit 0
