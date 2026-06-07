#Requires -Version 5.1
<#
.SYNOPSIS
  Canonical paths for FlowX distribution build (installer/output, not !Export).
#>
function Get-FlowXPaths {
    param(
        [string]$RepoRoot = ""
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $installerDir = Join-Path $RepoRoot "installer"
    $outputDir = Join-Path $installerDir "output"
    [pscustomobject]@{
        RepoRoot             = $RepoRoot
        InstallerDir         = $installerDir
        InstallerOutputDir   = $outputDir
        ExportRoot           = Join-Path $outputDir "FlowX"
        VersionFile          = Join-Path $outputDir "version.txt"
        DistProfileRel       = "config\.fx-dist.cfg"
        LegacyDistProfileRel = "config\.flowx_vendor_secret"
        GeneratedSecretPas   = Join-Path $outputDir "generated_license_secret.pas"
        LicenseValidatePas   = Join-Path $outputDir "license_validate.pas"
        LicenseValidateSource = Join-Path $installerDir "license_validate.pas"
        FlowXIss             = Join-Path $installerDir "FlowX.iss"
        LicenseIssuingDoc    = Join-Path $outputDir "LICENSE_ISSUING.md"
        UpdateReadme         = Join-Path $outputDir "UPDATE_README.txt"
        SetupOutputDir       = $outputDir
    }
}

function Get-FlowXDistProfilePath {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        $Paths
    )
    if (-not $Paths) {
        $Paths = Get-FlowXPaths
    }
    $newPath = Join-Path $InstallRoot $Paths.DistProfileRel
    $legacyPath = Join-Path $InstallRoot $Paths.LegacyDistProfileRel
    if (Test-Path -LiteralPath $newPath) { return $newPath }
    if (Test-Path -LiteralPath $legacyPath) { return $legacyPath }
    return $newPath
}
