#Requires -Version 5.1
<#
.SYNOPSIS
  Full Charts In Motion distribution build: export -> sync fixes -> encrypt -> installer -> update package.
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "",
    [string]$ExportRoot = "",
    [string]$Version = "",
    [string]$LicenseSecret = "",
    [switch]$SkipExport,
    [switch]$SkipEncrypt,
    [switch]$SkipUpdatePackage
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-CiMPaths -RepoRoot $RepoRoot
if (-not $SourceRoot) { $SourceRoot = $RepoRoot }
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}
if (-not $Version) {
    $Version = if (Test-Path -LiteralPath $fx.VersionFile) { (Get-Content -LiteralPath $fx.VersionFile -Raw).Trim() } else { "1.0.2" }
}
if (-not $LicenseSecret -and $env:CIM_LICENSE_SECRET) {
    $LicenseSecret = $env:CIM_LICENSE_SECRET.Trim()
}
function Read-CiMLicenseSecretFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $line = Get-Content -LiteralPath $Path -ErrorAction Stop |
        Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' } |
        Select-Object -First 1
    if (-not $line) { return $null }
    $value = $line.Trim().Trim('"').Trim("'")
    if ($value -match '^PASTE_YOUR_') { return $null }
    return $value
}

$secretFileCandidates = @(
    (Join-Path $RepoRoot "config\.build_license_secret"),
    (Join-Path $RepoRoot "config\build_license_secret"),
    (Join-Path $RepoRoot "config\build_license_secret.txt")
)
if (-not $LicenseSecret) {
    foreach ($candidate in $secretFileCandidates) {
        $LicenseSecret = Read-CiMLicenseSecretFile -Path $candidate
        if ($LicenseSecret) {
            $rel = $candidate.Substring($RepoRoot.Length).TrimStart('\', '/')
            Write-Host "Using license secret from $rel"
            break
        }
    }
}
# One-time migration: user edited .example instead of the gitignored secret file.
if (-not $LicenseSecret) {
    $examplePath = Join-Path $RepoRoot "config\build_license_secret.example"
    $fromExample = Read-CiMLicenseSecretFile -Path $examplePath
    if ($fromExample) {
        $LicenseSecret = $fromExample
        $target = $secretFileCandidates[0]
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Set-Content -LiteralPath $target -Value $LicenseSecret -Encoding UTF8 -NoNewline
        Write-Host "Migrated license secret from config\build_license_secret.example -> config\.build_license_secret"
        Write-Host "Keep the secret only in config\.build_license_secret (example file is not for production secrets)."
    }
}
if (-not $LicenseSecret -and (Test-Path -LiteralPath $fx.GeneratedSecretPas)) {
    $pasText = Get-Content -LiteralPath $fx.GeneratedSecretPas -Raw
    if ($pasText -match "Result := '([^']*(?:''[^']*)*)'") {
        $LicenseSecret = $Matches[1].Replace("''", "'")
        Write-Host "Using license secret from existing installer output."
    }
}
if ($LicenseSecret) {
    $env:CIM_LICENSE_SECRET = $LicenseSecret
} elseif (-not $SkipEncrypt) {
    throw @"
CIM_LICENSE_SECRET is not set.

Set it once for this PowerShell window:
  `$env:CIM_LICENSE_SECRET = 'your-secret'

Or save the secret (one line, no quotes) in one of:
  config\.build_license_secret   (preferred; gitignored)
  config\build_license_secret
  config\build_license_secret.txt

Do NOT put the real secret only in build_license_secret.example (that file may be committed).

Checked paths:
$($secretFileCandidates -join "`n  ")

Or pass: .\Build-CiM.ps1 -LicenseSecret 'your-secret'
"@
}

$logDir = Join-Path $RepoRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "build-distribution.log"
function Log([string]$Msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    Write-Host $line
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

Log "=== Charts In Motion distribution build (version $Version) ==="
Log "ExportRoot: $ExportRoot"

function Write-FlowXVersionFiles {
    param([string]$Ver)
    $repoVer = Join-Path $RepoRoot "version.txt"
    $content = if (Test-Path -LiteralPath $repoVer) {
        (Get-Content -LiteralPath $repoVer -Raw).Trim()
    } else {
        $Ver
    }
    if (-not $content) { $content = $Ver }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    foreach ($target in @(
        (Join-Path $ExportRoot "version.txt"),
        $fx.VersionFile
    )) {
        $dir = Split-Path -Parent $target
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        [System.IO.File]::WriteAllText($target, $content, $utf8NoBom)
    }
    Log "Wrote version.txt = $content (export + installer output)"
}

Write-FlowXVersionFiles -Ver $Version

Log "Step 0/6: Verify-CiMBuildPrerequisites.ps1"
& (Join-Path $ScriptDir "Verify-CiMBuildPrerequisites.ps1") -RepoRoot $RepoRoot -SkipEncrypt:$SkipEncrypt
if ($LASTEXITCODE -ne 0) {
    throw "Build prerequisites check failed. Fix missing files/tools before export (see messages above)."
}

if (-not $SkipExport) {
    Log "Step 1/6: export_cim.ps1 -Mode distribution -HardenAll"
    & (Join-Path $RepoRoot "export_cim.ps1") -SourceRoot $SourceRoot -ExportRoot $ExportRoot -Mode distribution -HardenAll
    if ($LASTEXITCODE -ne 0) { throw "export_cim failed (exit $LASTEXITCODE)" }
    Write-FlowXVersionFiles -Ver $Version
} else {
    Log "Step 1/6: export skipped"
}

Log "Step 2/6: Sync-ExportDistributionFixes.ps1"
& (Join-Path $ScriptDir "Sync-ExportDistributionFixes.ps1") -RepoRoot $RepoRoot -ExportRoot $ExportRoot

if (-not $SkipEncrypt) {
    Log "Step 3/6: encrypt_app_code.ps1"
    & (Join-Path $ScriptDir "encrypt_app_code.ps1") -ExportRoot $ExportRoot -LicenseSecret $LicenseSecret
    if ($LASTEXITCODE -ne 0) { throw "encrypt_app_code failed (exit $LASTEXITCODE)" }
} else {
    Log "Step 3/6: encrypt skipped"
}

$installerIss = Join-Path $fx.InstallerDir "CiM.iss"
$installerPas = $fx.LicenseValidateSource
if (-not (Test-Path -LiteralPath $installerIss)) {
    throw "Missing tracked installer source: $installerIss (restore from repo)."
}
if (-not (Test-Path -LiteralPath $installerPas)) {
    throw "Missing tracked installer source: $installerPas (restore from repo)."
}
Log "Step 4/6: build_installer.ps1"
& (Join-Path $ScriptDir "build_installer.ps1") -ExportRoot $ExportRoot -Version $Version -LicenseSecret $LicenseSecret
if ($LASTEXITCODE -ne 0) { throw "build_installer failed (exit $LASTEXITCODE)" }

if (-not $SkipUpdatePackage) {
    Log "Step 5/6: build_update_package.ps1"
    & (Join-Path $ScriptDir "build_update_package.ps1") -ExportRoot $ExportRoot -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "build_update_package failed (exit $LASTEXITCODE)" }
} else {
    Log "Step 5/6: update package skipped"
}

Log "Step 6/6: Test-CiMPackagedSmoke.ps1 (export tree - blocks blank Electron releases)"
& (Join-Path $ScriptDir "Test-CiMPackagedSmoke.ps1") -InstallRoot $ExportRoot
if ($LASTEXITCODE -ne 0) {
    throw "Release gate FAILED on export tree. Do not publish this build to GitHub."
}

$installer = Join-Path $fx.SetupOutputDir "CiMSetup-$Version.exe"
$updateDir = Join-Path $fx.InstallerOutputDir "CiM-Update-$Version"
Log "=== Build complete ==="
Log "Installer: $installer"
if (-not $SkipUpdatePackage) {
    Log "Update package: $updateDir"
}
Log "Log: $logFile"
