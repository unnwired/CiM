#Requires -Version 5.1
<#
.SYNOPSIS
  Build CiMSetup.exe from an encrypted export tree using Inno Setup.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$Version = "",
    [string]$LicenseSecret = "",
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir

if (-not $ExportRoot) {
    $fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind Encrypted
    $ExportRoot = $fx.ExportRoot
} else {
    $fx = Resolve-CiMPathsForExportRoot -ExportRoot $ExportRoot -RepoRoot $RepoRoot
    $ExportRoot = [System.IO.Path]::GetFullPath($ExportRoot)
}
if (-not $Version) {
    $exportVerFile = Join-Path $ExportRoot "version.txt"
    if (Test-Path -LiteralPath $exportVerFile) {
        $Version = (Get-Content -LiteralPath $exportVerFile -Raw).Trim().Trim([char]0xFEFF)
    }
    if (-not $Version) {
        $Version = Get-CiMRepoVersion -RepoRoot $RepoRoot
    }
}

function Ensure-InstallerSupportFiles {
    param(
        [string]$Version,
        [string]$ExportRoot,
        $Paths
    )
    if (-not (Test-Path -LiteralPath $Paths.InstallerOutputDir)) {
        New-Item -ItemType Directory -Force -Path $Paths.InstallerOutputDir | Out-Null
    }
    Write-CiMVersionFiles -Version $Version -ExportRoot $ExportRoot -Paths $Paths
    $updateReadmeSource = Join-Path $Paths.InstallerDir "UPDATE_README.txt"
    $updateReadmeOut = Join-Path $Paths.InstallerOutputDir "UPDATE_README.txt"
    if (Test-Path -LiteralPath $updateReadmeSource) {
        Copy-Item -LiteralPath $updateReadmeSource -Destination $updateReadmeOut -Force
    }
    $pas = $Paths.LicenseValidatePas
    $pasSource = $Paths.LicenseValidateSource
    if (-not (Test-Path -LiteralPath $pas) -and (Test-Path -LiteralPath $pasSource)) {
        Copy-Item -LiteralPath $pasSource -Destination $pas -Force
        Write-Host "Copied license_validate.pas into $($Paths.InstallerOutputDir)"
    }
}

function Test-ExportPackageComplete {
    param([string]$Root)
    $required = @(
        "start_cim.bat",
        "data\nse_data.db",
        "frontend\build\index.html",
        "runtime\python\python.exe",
        "server\cim_bootstrap.py",
        "server\app_code_crypto.py",
        "server\_cim_dist_embedded.py"
    )
    $missing = @()
    foreach ($rel in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $rel))) { $missing += $rel }
    }
    $srvPyc = Join-Path $Root "server\server.pyc"
    $srvEnc = Join-Path $Root "server\server.pyc.enc"
    $srvPy = Join-Path $Root "server\server.py"
    $plaintextMarker = Join-Path $Root "config\.cim-plaintext-dist"
    if (-not (Test-Path -LiteralPath $srvPyc) -and -not (Test-Path -LiteralPath $srvEnc)) {
        if (-not ((Test-Path -LiteralPath $plaintextMarker) -and (Test-Path -LiteralPath $srvPy))) {
            $missing += "server\server.pyc or server.pyc.enc (or plaintext server.py)"
        }
    }
    if (Test-Path -LiteralPath $plaintextMarker) {
        foreach ($rel in @("frontend\auth\index.html", "server\_cim_dist_embedded.py", "config\product.json")) {
            if (-not (Test-Path -LiteralPath (Join-Path $Root $rel))) { $missing += $rel }
        }
    }
    if ($missing.Count -gt 0) {
        throw "Export incomplete for installer. Missing: $($missing -join ', ')"
    }
}

Test-ExportPackageComplete -Root $ExportRoot

$secretForInno = Get-CiMVendorSecret -LicenseSecret $LicenseSecret -RepoRoot $RepoRoot
if ($secretForInno) {
    $env:CIM_LICENSE_SECRET = $secretForInno
} elseif (-not $env:CIM_LICENSE_SECRET) {
    Write-Warning "CIM_LICENSE_SECRET not set; installer will use default secret in CiM.iss (must match encrypt_app_code)."
}
$vendorFile = Join-Path $ExportRoot $fx.DistProfileRel
if (Test-Path -LiteralPath $vendorFile) {
    throw "Phase 1 lockdown: remove config\.fx-dist.cfg from export before building installer."
}

function Escape-InnoDefineString([string]$Value) {
    return $Value -replace '"', '""'
}

function Resolve-IsccPath {
    param([string]$Explicit)
    if ($Explicit -and (Test-Path -LiteralPath $Explicit)) {
        return (Resolve-Path -LiteralPath $Explicit).Path
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
        return $cmd.Source
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 5\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return (Resolve-Path -LiteralPath $c).Path }
    }
    return $null
}

$iscc = Resolve-IsccPath -Explicit $IsccPath
if (-not $iscc) {
    throw @"
Inno Setup ISCC.exe not found.
Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
Or pass the full path, e.g.:
  -IsccPath `"$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe`"
"@
}
Write-Host "Using ISCC: $iscc"

Ensure-InstallerSupportFiles -Version $Version -ExportRoot $ExportRoot -Paths $fx

$payload = (Resolve-Path -LiteralPath $ExportRoot).Path
$secretForInno = $env:CIM_LICENSE_SECRET
if (-not $secretForInno) {
    $secretForInno = Get-CiMVendorSecret -RepoRoot $RepoRoot
}
if ($secretForInno) {
    $pascalSecret = $secretForInno -replace "'", "''"
    $genPas = $fx.GeneratedSecretPas
    @"
{ Auto-generated by build_installer.ps1 - do not edit }
function GetLicenseSecret: String;
begin
  Result := '$pascalSecret';
end;
"@ | Set-Content -LiteralPath $genPas -Encoding UTF8
    Write-Host "Wrote installer secret (Pascal include, safe for # and & in secret)."
    $legacyIss = Join-Path $fx.InstallerDir "license_secret.iss"
    if (Test-Path -LiteralPath $legacyIss) { Remove-Item -LiteralPath $legacyIss -Force }
} else {
    if (Test-Path -LiteralPath $fx.GeneratedSecretPas) { Remove-Item -LiteralPath $fx.GeneratedSecretPas -Force }
}

$onlineOnlyMarker = Join-Path $ExportRoot "config\.cim-online-only"
$onlineOnly = Test-Path -LiteralPath $onlineOnlyMarker
$installerOutRel = $fx.InstallerOutputDir.Substring($fx.InstallerDir.Length).TrimStart('\', '/')
$defines = @(
    "/DAppVersion=$Version",
    "/DSourcePayload=$payload",
    "/DInstallerOutputDir=$installerOutRel"
)
if ($onlineOnly) {
    $defines += "/DOnlineOnlyActivation=1"
    Write-Host "Online-only installer (no vendor install key wizard)."
}

$iss = $fx.CiMIss
if (-not (Test-Path -LiteralPath $iss)) {
    throw @"
Missing $iss
Restore installer\CiM.iss from repo backup.
"@
}
$pas = $fx.LicenseValidatePas
$pasSource = $fx.LicenseValidateSource
if (-not (Test-Path -LiteralPath $pas)) {
    if (Test-Path -LiteralPath $pasSource) {
        if (-not (Test-Path -LiteralPath $fx.InstallerOutputDir)) {
            New-Item -ItemType Directory -Force -Path $fx.InstallerOutputDir | Out-Null
        }
        Copy-Item -LiteralPath $pasSource -Destination $pas -Force
        Write-Host "Copied license_validate.pas from installer\license_validate.pas"
    } else {
        throw "Missing $pas and source $pasSource (required by CiM.iss)."
    }
} elseif (Test-Path -LiteralPath $pasSource) {
    $srcTime = (Get-Item -LiteralPath $pasSource).LastWriteTimeUtc
    $dstTime = (Get-Item -LiteralPath $pas).LastWriteTimeUtc
    if ($srcTime -gt $dstTime) {
        Copy-Item -LiteralPath $pasSource -Destination $pas -Force
        Write-Host "Refreshed license_validate.pas from installer\license_validate.pas"
    }
}
if ($secretForInno -and -not (Test-Path -LiteralPath $fx.GeneratedSecretPas)) {
    throw "Missing generated_license_secret.pas after secret write."
}
$issText = Get-Content -LiteralPath $iss -Raw
if ($issText -match '\.CopyToClipboard') {
    throw @"
CiM.iss still calls .CopyToClipboard (invalid for Inno TNewEdit).
Save installer\CiM.iss (clip.exe temp-file copy) and rebuild.
"@
}
if (-not $secretForInno) {
    throw "Cannot build installer without distribution profile. Run encrypt_app_code.ps1 first."
}
$verifyChain = Join-Path $ScriptDir "Verify-CiMLicenseChain.ps1"
if (Test-Path -LiteralPath $verifyChain) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyChain `
        -ExportRoot $ExportRoot -RepoRoot $RepoRoot -InstallerOutputDir $fx.InstallerOutputDir
}

Write-Host "Compiling installer (version $Version)..."
& $iscc $defines $iss
$exit = $LASTEXITCODE
if ($exit -ne 0) { throw "ISCC failed with exit code $exit" }

$out = Join-Path $fx.SetupOutputDir "CiMSetup-$Version.exe"
if (-not (Test-Path -LiteralPath $out)) {
    throw "Expected output not found: $out"
}
Write-Host "Installer built: $out"
if ($secretForInno -and -not $onlineOnly) {
    Write-Host ""
    Write-Host "Installer compiled. Issue install keys using your private vendor tooling on the build machine."
} elseif ($onlineOnly) {
    Write-Host ""
    Write-Host "Installer compiled (online activation). Users sign in on first launch - no install keys."
}
