#Requires -Version 5.1
<#
.SYNOPSIS
  Build FlowXSetup.exe from an encrypted export tree using Inno Setup.
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
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot

if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}
if (-not $Version) {
    if (Test-Path -LiteralPath $fx.VersionFile) {
        $Version = (Get-Content -LiteralPath $fx.VersionFile -Raw).Trim()
    } else {
        $Version = "1.0.0"
    }
}

function Test-ExportPackageComplete {
    param([string]$Root)
    $required = @(
        "start_flowx.bat",
        "data\nse_data.db",
        "frontend\build\index.html",
        "runtime\python\python.exe",
        "server\flowx_bootstrap.py",
        "server\app_code_crypto.py"
    )
    $missing = @()
    foreach ($rel in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $rel))) { $missing += $rel }
    }
    $srvPyc = Join-Path $Root "server\server.pyc"
    $srvEnc = Join-Path $Root "server\server.pyc.enc"
    if (-not (Test-Path -LiteralPath $srvPyc) -and -not (Test-Path -LiteralPath $srvEnc)) {
        $missing += "server\server.pyc or server.pyc.enc"
    }
    if ($missing.Count -gt 0) {
        throw "Export incomplete for installer. Missing: $($missing -join ', ')"
    }
}

Test-ExportPackageComplete -Root $ExportRoot

$vendorFile = Get-FlowXDistProfilePath -InstallRoot $ExportRoot -Paths $fx
if ($LicenseSecret) {
    $env:FLOWX_LICENSE_SECRET = $LicenseSecret
} elseif (-not $env:FLOWX_LICENSE_SECRET -and (Test-Path -LiteralPath $vendorFile)) {
    $env:FLOWX_LICENSE_SECRET = (Get-Content -LiteralPath $vendorFile -Raw).Trim()
    Write-Host "Using FLOWX_LICENSE_SECRET from export profile: $vendorFile"
}
if (-not $env:FLOWX_LICENSE_SECRET) {
    Write-Warning "FLOWX_LICENSE_SECRET not set; installer will use default secret in FlowX.iss (must match encrypt_app_code / config\.fx-dist.cfg)."
} elseif ((Test-Path -LiteralPath $vendorFile)) {
    $onDisk = (Get-Content -LiteralPath $vendorFile -Raw).Trim()
    if ($onDisk -ne $env:FLOWX_LICENSE_SECRET.Trim()) {
        throw @"
FLOWX_LICENSE_SECRET env does not match $vendorFile.
Run encrypt_app_code.ps1 with the same secret, or clear env and let build_installer read the file only.
"@
    }
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

if (-not (Test-Path -LiteralPath $fx.InstallerOutputDir)) {
    New-Item -ItemType Directory -Force -Path $fx.InstallerOutputDir | Out-Null
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($fx.VersionFile, $Version, $utf8NoBom)

$updateReadmeSource = Join-Path $fx.InstallerDir "UPDATE_README.txt"
$updateReadmeOut = Join-Path $fx.InstallerOutputDir "UPDATE_README.txt"
if (Test-Path -LiteralPath $updateReadmeSource) {
    Copy-Item -LiteralPath $updateReadmeSource -Destination $updateReadmeOut -Force
}

$payload = (Resolve-Path -LiteralPath $ExportRoot).Path
$secretForInno = $env:FLOWX_LICENSE_SECRET
if (-not $secretForInno -and (Test-Path -LiteralPath $vendorFile)) {
    $secretForInno = (Get-Content -LiteralPath $vendorFile -Raw).Trim()
}
if ($secretForInno) {
    $configDir = Join-Path $ExportRoot "config"
    if (-not (Test-Path -LiteralPath $configDir)) {
        New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    }
    $vendorOut = Join-Path $configDir ".fx-dist.cfg"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($vendorOut, $secretForInno, $utf8NoBom)
    $legacyVendor = Join-Path $configDir ".flowx_vendor_secret"
    if (Test-Path -LiteralPath $legacyVendor) { Remove-Item -LiteralPath $legacyVendor -Force }
    Write-Host "Synced distribution profile to export: $vendorOut"

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

$defines = @(
    "/DAppVersion=$Version",
    "/DSourcePayload=$payload"
)

$iss = $fx.FlowXIss
if (-not (Test-Path -LiteralPath $iss)) {
    throw @"
Missing $iss
Restore installer\FlowX.iss from repo backup.
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
        throw "Missing $pas and source $pasSource (required by FlowX.iss)."
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
FlowX.iss still calls .CopyToClipboard (invalid for Inno TNewEdit).
Save installer\FlowX.iss (clip.exe temp-file copy) and rebuild.
"@
}
if (-not $secretForInno) {
    throw "Cannot build installer without distribution profile. Run encrypt_app_code.ps1 first."
}
$verifyChain = Join-Path $ScriptDir "Verify-FlowXLicenseChain.ps1"
if (Test-Path -LiteralPath $verifyChain) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyChain `
        -ExportRoot $ExportRoot -RepoRoot $RepoRoot -InstallerOutputDir $fx.InstallerOutputDir
}

Write-Host "Compiling installer (version $Version)..."
& $iscc $defines $iss
$exit = $LASTEXITCODE
if ($exit -ne 0) { throw "ISCC failed with exit code $exit" }

$out = Join-Path $fx.SetupOutputDir "FlowXSetup-$Version.exe"
if (-not (Test-Path -LiteralPath $out)) {
    throw "Expected output not found: $out"
}
Write-Host "Installer built: $out"
if ($secretForInno) {
    $showKey = Join-Path $ScriptDir "Show-FlowXInstallKey.ps1"
    if (Test-Path -LiteralPath $showKey) {
        Write-Host ""
        Write-Host "=== Install keys (must match the machine code shown in FlowXSetup) ==="
        Write-Host "Example for client MC F1927C3F4CCD33A733DD8AECEFDA6469:"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $showKey `
            -MachineCode "F1927C3F4CCD33A733DD8AECEFDA6469" `
            -InstallRoot $ExportRoot
    }
}
