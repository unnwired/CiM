#Requires -Version 5.1
<#
.SYNOPSIS
  Build update package + ZIP from an existing export tree, then run smoke gate.

.DESCRIPTION
  Does NOT re-export, encrypt, or build installer. Requires installer\{Encrypted|Plaintext}\CiM
  from a prior full build.

.EXAMPLE
  .\scripts\Build-CiM-UpdateOnly.ps1 -DistributionKind Encrypted
#>
[CmdletBinding()]
param(
    [ValidateSet('Plaintext', 'Encrypted')]
    [string]$DistributionKind = 'Encrypted',
    [string]$ExportRoot = '',
    [string]$Version = ''
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir 'Get-CiMPaths.ps1')
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind $DistributionKind

if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
} elseif (-not [System.IO.Path]::IsPathRooted($ExportRoot)) {
    $ExportRoot = Join-Path $RepoRoot $ExportRoot
}
$ExportRoot = [System.IO.Path]::GetFullPath($ExportRoot)

if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw @"
Export tree not found:
  $ExportRoot

Run the full build batch first (Batch Files\*-Full-Build.bat).
"@
}

$startBat = Join-Path $ExportRoot 'start_cim.bat'
if (-not (Test-Path -LiteralPath $startBat)) {
    throw "Invalid export tree (missing start_cim.bat): $ExportRoot"
}

if (-not $Version) {
    $verFile = Join-Path $ExportRoot 'version.txt'
    if (-not (Test-Path -LiteralPath $verFile)) {
        $verFile = $fx.VersionFile
    }
    if (-not (Test-Path -LiteralPath $verFile)) {
        throw 'Missing version.txt in export tree and installer output folder.'
    }
    $Version = (Get-Content -LiteralPath $verFile -Raw).Trim()
}
if (-not $Version) { throw 'Version is empty.' }

$logDir = Join-Path $RepoRoot 'runtime\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir 'build-distribution.log'
function Log([string]$Msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    Write-Host $line
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

$stepTotal = 2
$step = 0

Log "=== Charts In Motion update package only ($DistributionKind, version $Version) ==="
Log "ExportRoot: $ExportRoot"
Log "Output folder: $($fx.InstallerOutputDir)"

$step++
Log "Step $step/$stepTotal`: build_update_package.ps1"
& (Join-Path $ScriptDir 'build_update_package.ps1') -ExportRoot $ExportRoot -Version $Version
Assert-LastExitSuccess -Step 'build_update_package.ps1'

$step++
Log "Step $step/$stepTotal`: Test-CiMPackagedSmoke.ps1"
& (Join-Path $ScriptDir 'Test-CiMPackagedSmoke.ps1') -InstallRoot $ExportRoot
Assert-LastExitSuccess -Step 'Test-CiMPackagedSmoke.ps1'

$outDir = $fx.InstallerOutputDir
Log "=== Build complete ($DistributionKind) ==="
Log "Update package folder: $outDir\CiM-Update-$Version"
Log "Update package ZIP:    $outDir\CiM-Update-$Version.zip"
