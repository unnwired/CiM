#Requires -Version 5.1
<#
.SYNOPSIS
  Canonical paths for Charts In Motion (CiM) distribution build.
#>
function Get-CiMPaths {
    param(
        [string]$RepoRoot = ""
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $installerDir = Join-Path $RepoRoot "installer"
    $outputDir = Join-Path $installerDir "output"
    [pscustomobject]@{
        RepoRoot              = $RepoRoot
        InstallerDir          = $installerDir
        InstallerOutputDir    = $outputDir
        ExportRoot            = Join-Path $outputDir "CiM"
        VersionFile           = Join-Path $outputDir "version.txt"
        DistProfileRel        = "config\.fx-dist.cfg"
        LegacyDistProfileRel  = "config\.flowx_vendor_secret"
        GeneratedSecretPas    = Join-Path $outputDir "generated_license_secret.pas"
        LicenseValidatePas    = Join-Path $outputDir "license_validate.pas"
        LicenseValidateSource = Join-Path $installerDir "license_validate.pas"
        CiMIss                = Join-Path $installerDir "CiM.iss"
        LicenseIssuingDoc     = Join-Path $outputDir "LICENSE_ISSUING.md"
        UpdateReadme          = Join-Path $outputDir "UPDATE_README.txt"
        SetupOutputDir        = $outputDir
    }
}

function Get-CiMDistProfilePath {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        $Paths
    )
    if (-not $Paths) {
        $Paths = Get-CiMPaths
    }
    $newPath = Join-Path $InstallRoot $Paths.DistProfileRel
    $legacyPath = Join-Path $InstallRoot $Paths.LegacyDistProfileRel
    if (Test-Path -LiteralPath $newPath) { return $newPath }
    if (Test-Path -LiteralPath $legacyPath) { return $legacyPath }
    return $newPath
}

function Get-CiMVendorSecretPath {
    param([string]$RepoRoot = "")
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    return Join-Path $RepoRoot "config\.build_license_secret"
}

function Get-CiMVendorSecret {
    <#
    .SYNOPSIS
      Vendor-only license secret (build machine). Never read from client install trees.
    #>
    param(
        [string]$LicenseSecret = "",
        [string]$RepoRoot = ""
    )
    if ($LicenseSecret) {
        return $LicenseSecret.Trim().Trim([char]0xFEFF)
    }
    if ($env:CIM_LICENSE_SECRET) {
        return $env:CIM_LICENSE_SECRET.Trim().Trim([char]0xFEFF)
    }
    $buildFile = Get-CiMVendorSecretPath -RepoRoot $RepoRoot
    if (Test-Path -LiteralPath $buildFile) {
        return ([System.IO.File]::ReadAllText($buildFile)).Trim().Trim([char]0xFEFF)
    }
    return ""
}

# Back-compat aliases (remove after downstream scripts stop referencing FlowX names)
function Get-FlowXPaths { Get-CiMPaths @args }
function Get-FlowXDistProfilePath { Get-CiMDistProfilePath @args }
