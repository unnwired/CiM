#Requires -Version 5.1
<#
.SYNOPSIS
  Fail fast before export/encrypt if the distribution build cannot complete.

.DESCRIPTION
  Run at the start of Build-FlowX.ps1 / build_distribution_full.ps1 so missing
  installer sources, license secret, or Inno Setup are caught in seconds — not
  after a 15+ minute export/encrypt cycle.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$SkipEncrypt,
    [switch]$RequireInnoSetup
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $ScriptDir
}
$fx = Get-FlowXPaths -RepoRoot $RepoRoot

$requiredSources = @(
    @{ Path = $fx.FlowXIss; Label = "Inno Setup script" },
    @{ Path = $fx.LicenseValidateSource; Label = "Installer license validation (Pascal)" },
    @{ Path = (Join-Path $fx.InstallerDir "UPDATE_README.txt"); Label = "UPDATE folder readme" },
    @{ Path = (Join-Path $RepoRoot "export_flowx.ps1"); Label = "Export script" },
    @{ Path = (Join-Path $ScriptDir "encrypt_app_code.ps1"); Label = "Encrypt script" },
    @{ Path = (Join-Path $ScriptDir "build_installer.ps1"); Label = "Installer build script" },
    @{ Path = (Join-Path $ScriptDir "build_update_package.ps1"); Label = "Update package script" },
    @{ Path = (Join-Path $ScriptDir "Sync-ExportDistributionFixes.ps1"); Label = "Export sync script" },
    @{ Path = (Join-Path $RepoRoot "config\github_updates.json"); Label = "GitHub updates config" }
)

$missing = @()
foreach ($item in $requiredSources) {
    if (-not (Test-Path -LiteralPath $item.Path)) {
        $missing += "$($item.Label): $($item.Path)"
    }
}

if (-not $SkipEncrypt) {
    $hasSecret = $false
    if ($env:FLOWX_LICENSE_SECRET -and $env:FLOWX_LICENSE_SECRET.Trim()) {
        $hasSecret = $true
    } else {
        foreach ($candidate in @(
            (Join-Path $RepoRoot "config\.build_license_secret"),
            (Join-Path $RepoRoot "config\build_license_secret"),
            (Join-Path $RepoRoot "config\build_license_secret.txt")
        )) {
            if (Test-Path -LiteralPath $candidate) {
                $line = Get-Content -LiteralPath $candidate -ErrorAction SilentlyContinue |
                    Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' } |
                    Select-Object -First 1
                if ($line -and $line.Trim() -notmatch '^PASTE_YOUR_') {
                    $hasSecret = $true
                    break
                }
            }
        }
    }
    if (-not $hasSecret) {
        $missing += "License secret: set FLOWX_LICENSE_SECRET or config\.build_license_secret (required for encrypt + installer)"
    }
}

if ($RequireInnoSetup -or -not $SkipEncrypt) {
    $isccCandidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $foundIscc = $false
    foreach ($c in $isccCandidates) {
        if (Test-Path -LiteralPath $c) { $foundIscc = $true; break }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
        $foundIscc = $true
    }
    if (-not $foundIscc) {
        $missing += "Inno Setup 6 (ISCC.exe): install from https://jrsoftware.org/isinfo.php"
    }
}

if ($missing.Count -eq 0) {
    Write-Host "[ok] FlowX build prerequisites verified."
    exit 0
}

Write-Host ""
Write-Host "FlowX build prerequisites FAILED ($($missing.Count) issue(s)):" -ForegroundColor Red
foreach ($line in $missing) {
    Write-Host "  - $line" -ForegroundColor Red
}
Write-Host ""
Write-Host "Fix these before running Build-FlowX.ps1. Installer sources belong in installer\ and must be" -ForegroundColor Yellow
Write-Host "committed to git (only installer\output\ is gitignored). If files were deleted locally," -ForegroundColor Yellow
Write-Host "restore installer\FlowX.iss, installer\license_validate.pas, and installer\UPDATE_README.txt" -ForegroundColor Yellow
Write-Host "from version control - not from backups_full unless git is unavailable." -ForegroundColor Yellow
Write-Host ""
exit 1
