#Requires -Version 5.1
<#
.SYNOPSIS
  Full Charts In Motion distribution build: export -> sync fixes -> encrypt -> installer -> update package.
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "",
    [string]$ExportRoot = "",
    [string]$DbSource = "",
    [string]$Version = "",
    [string]$LicenseSecret = "",
    [switch]$SkipExport,
    [switch]$SkipEncrypt,
    [switch]$SkipUpdatePackage,
    [switch]$SkipInstaller,
    [switch]$FastExport,
    [switch]$SkipSmoke,
    [switch]$PlaintextExport
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$distKind = if ($PlaintextExport) { "Plaintext" } else { "Encrypted" }
$fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind $distKind
if (-not $SourceRoot) { $SourceRoot = $RepoRoot }
if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
} elseif (-not [System.IO.Path]::IsPathRooted($ExportRoot)) {
    $ExportRoot = Join-Path $RepoRoot $ExportRoot
}
$DbSource = Resolve-CiMDistributionDbSource -RepoRoot $RepoRoot -DbSource $DbSource
Assert-CiMDistributionDbSource -DbPath $DbSource -Hint (
    "Build Launcher ships the showcase testbed database (default D:\CiM\Client_Test\data\nse_data.db). " +
    "Run OHLCV + filter rebuild on Client_Test first, or pass -DbSource explicitly."
)
Write-Host "Distribution DB source: $DbSource"
if (-not $Version) {
    $Version = Get-CiMRepoVersion -RepoRoot $RepoRoot
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
if (-not $LicenseSecret) {
    foreach ($kind in @($distKind, $(if ($distKind -eq "Plaintext") { "Encrypted" } else { "Plaintext" }))) {
        $pasPath = (Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind $kind).GeneratedSecretPas
        if (-not (Test-Path -LiteralPath $pasPath)) { continue }
        $pasText = Get-Content -LiteralPath $pasPath -Raw
        if ($pasText -match "Result := '([^']*(?:''[^']*)*)'") {
            $LicenseSecret = $Matches[1].Replace("''", "'")
            Write-Host "Using license secret from installer\$kind output."
            break
        }
    }
}
if ($LicenseSecret) {
    $env:CIM_LICENSE_SECRET = $LicenseSecret
} elseif ($PlaintextExport -or -not $SkipEncrypt) {
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

$refreshOnly = $SkipInstaller -and $SkipUpdatePackage
$buildKind = if ($PlaintextExport) { "plaintext (readable source + online auth)" } else { "encrypted distribution" }
$modeLabel = if ($refreshOnly) { "$buildKind refresh export" } else { "$buildKind build" }
Log "=== Charts In Motion $modeLabel (version $Version) ==="
Log "Output folder: $($fx.InstallerOutputDir)"
Log "ExportRoot: $ExportRoot"

function Write-FlowXVersionFiles {
    param([string]$Ver)
    if (-not $Ver) { $Ver = Get-CiMRepoVersion -RepoRoot $RepoRoot }
    Write-CiMVersionFiles -Version $Ver -ExportRoot $ExportRoot -Paths $fx
    Log "Wrote version.txt = $Ver (repo canonical -> export + installer output)"
}

$Version = Get-CiMRepoVersion -RepoRoot $RepoRoot
Write-FlowXVersionFiles -Ver $Version

$stepTotal = if ($refreshOnly) { 5 } else { 6 }
$step = 0

$step++
Log "Step $step/$stepTotal`: Verify-CiMBuildPrerequisites.ps1"
& (Join-Path $ScriptDir "Verify-CiMBuildPrerequisites.ps1") -RepoRoot $RepoRoot -SkipEncrypt:($SkipEncrypt -or $PlaintextExport) -RequireInnoSetup:(-not $SkipInstaller)
if ($LASTEXITCODE -ne 0) {
    throw "Build prerequisites check failed. Fix missing files/tools before export (see messages above)."
}

if (-not $SkipExport) {
    $exportArgs = @{
        SourceRoot           = $SourceRoot
        ExportRoot           = $ExportRoot
        DbSource             = $DbSource
        Mode                 = 'distribution'
        SkipEmbeddedPython   = [bool]$FastExport
        SkipWheelhouse       = [bool]$FastExport
    }
    if ($PlaintextExport) {
        $step++
        Log "Step $step/$stepTotal`: export_cim.ps1 -PlaintextDistribution$(if ($FastExport) { ' (fast: keep runtime\python)' })"
        $exportArgs.PlaintextDistribution = $true
    } else {
        $step++
        Log "Step $step/$stepTotal`: export_cim.ps1 -HardenAll$(if ($FastExport) { ' (fast: keep runtime\python)' })"
        $exportArgs.HardenAll = $true
    }
    & (Join-Path $RepoRoot "export_cim.ps1") @exportArgs
    if ($LASTEXITCODE -ne 0) { throw "export_cim failed (exit $LASTEXITCODE)" }
    $Version = Get-CiMRepoVersion -RepoRoot $RepoRoot
    Write-FlowXVersionFiles -Ver $Version
} else {
    $step++
    Log "Step $step/$stepTotal`: export skipped"
}

$step++
Log "Step $step/$stepTotal`: Sync-ExportDistributionFixes.ps1"
& (Join-Path $ScriptDir "Sync-ExportDistributionFixes.ps1") -RepoRoot $RepoRoot -ExportRoot $ExportRoot -DbSource $DbSource

if ($PlaintextExport) {
    $step++
    Log "Step $step/$stepTotal`: Prepare-CiMPlaintextExport.ps1 (license embed + online auth, no encryption)"
    & (Join-Path $ScriptDir "Prepare-CiMPlaintextExport.ps1") -ExportRoot $ExportRoot -RepoRoot $RepoRoot -LicenseSecret $LicenseSecret
    if ($LASTEXITCODE -ne 0) { throw "Prepare-CiMPlaintextExport failed (exit $LASTEXITCODE)" }
} elseif (-not $SkipEncrypt) {
    $step++
    Log "Step $step/$stepTotal`: encrypt_app_code.ps1"
    & (Join-Path $ScriptDir "encrypt_app_code.ps1") -ExportRoot $ExportRoot -LicenseSecret $LicenseSecret
    if ($LASTEXITCODE -ne 0) { throw "encrypt_app_code failed (exit $LASTEXITCODE)" }
    Log "Step $step/$stepTotal`: Prepare-CiMOnlineDistribution.ps1 (online auth, no install key wizard)"
    & (Join-Path $ScriptDir "Prepare-CiMOnlineDistribution.ps1") -ExportRoot $ExportRoot -RepoRoot $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "Prepare-CiMOnlineDistribution failed (exit $LASTEXITCODE)" }
} else {
    $step++
    Log "Step $step/$stepTotal`: encrypt skipped"
}

if (-not $SkipInstaller) {
    $installerIss = Join-Path $fx.InstallerDir "CiM.iss"
    $installerPas = $fx.LicenseValidateSource
    if (-not (Test-Path -LiteralPath $installerIss)) {
        throw "Missing tracked installer source: $installerIss (restore from repo)."
    }
    if (-not (Test-Path -LiteralPath $installerPas)) {
        throw "Missing tracked installer source: $installerPas (restore from repo)."
    }
    $step++
    Log "Step $step/$stepTotal`: build_installer.ps1"
    & (Join-Path $ScriptDir "build_installer.ps1") -ExportRoot $ExportRoot -Version $Version -LicenseSecret $LicenseSecret
    if ($LASTEXITCODE -ne 0) { throw "build_installer failed (exit $LASTEXITCODE)" }
}

if (-not $SkipUpdatePackage) {
    $step++
    Log "Step $step/$stepTotal`: build_update_package.ps1"
    & (Join-Path $ScriptDir "build_update_package.ps1") -ExportRoot $ExportRoot -Version $Version
    Assert-LastExitSuccess -Step "build_update_package.ps1"
}

if (-not $SkipSmoke) {
    $step++
    Log "Step $step/$stepTotal`: Test-CiMPackagedSmoke.ps1 (export tree - blocks blank Electron releases)"
    & (Join-Path $ScriptDir "Test-CiMPackagedSmoke.ps1") -InstallRoot $ExportRoot
    Assert-LastExitSuccess -Step "Test-CiMPackagedSmoke.ps1"
}

$installer = Join-Path $fx.SetupOutputDir "CiMSetup-$Version.exe"
$updateDir = Join-Path $fx.InstallerOutputDir "CiM-Update-$Version"
$completeLabel = if ($refreshOnly) { "Refresh export complete ($distKind)" } else { "Build complete ($distKind)" }
Log "=== $completeLabel ==="
Log "Folder: $($fx.InstallerOutputDir)"
Log "Export tree: $ExportRoot"
if (-not $SkipInstaller) {
    Log "Installer: $installer"
}
if (-not $SkipUpdatePackage) {
    Log "Update package: $updateDir"
    Log "Update ZIP: $(Join-Path $fx.InstallerOutputDir "CiM-Update-$Version.zip")"
}
if ($refreshOnly) {
    Log "Next: run Batch Files\$distKind-UpdatePackage.bat to create the update ZIP"
}
Log "Log: $logFile"
