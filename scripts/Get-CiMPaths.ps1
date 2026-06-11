#Requires -Version 5.1
<#
.SYNOPSIS
  Canonical paths for Charts In Motion (CiM) distribution build.

.DESCRIPTION
  Plaintext and encrypted builds write to separate trees so they never overwrite each other:
    installer\Plaintext\  — readable export, installer, update ZIP/folder
    installer\Encrypted\  — hardened/encrypted export, installer, update ZIP/folder
#>
function Get-CiMPaths {
    param(
        [string]$RepoRoot = "",
        [ValidateSet("Plaintext", "Encrypted")]
        [string]$DistributionKind = "Encrypted"
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $installerDir = Join-Path $RepoRoot "installer"
    $outputDir = Join-Path $installerDir $DistributionKind
    [pscustomobject]@{
        RepoRoot              = $RepoRoot
        InstallerDir          = $installerDir
        DistributionKind      = $DistributionKind
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

function Resolve-CiMPathsForExportRoot {
    <#
    .SYNOPSIS
      Pick Plaintext vs Encrypted output paths from the export tree location.
    #>
    param(
        [Parameter(Mandatory)][string]$ExportRoot,
        [string]$RepoRoot = "",
        [ValidateSet("Plaintext", "Encrypted")]
        [string]$DefaultKind = "Encrypted"
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $full = [System.IO.Path]::GetFullPath($ExportRoot)
    $parentName = [System.IO.Path]::GetFileName([System.IO.Path]::GetDirectoryName($full))
    $kind = if ($parentName -eq "Plaintext" -or $parentName -eq "Encrypted") { $parentName } else { $DefaultKind }
    return Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind $kind
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
