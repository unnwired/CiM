#Requires -Version 5.1
<#
.SYNOPSIS
  Build FlowX-Update-{version} folder with update.manifest.json + payload mirror.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$Version = "",
    [string]$MinAppVersion = "",
    [string]$OutputDir = "",
    [switch]$IncludesDatabase
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot

function Test-PowerShellScriptSyntax {
    param([Parameter(Mandatory)][string[]]$Paths)
    foreach ($path in $Paths) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
        if ($errors -and $errors.Count -gt 0) {
            throw "PowerShell syntax error in ${path}: $($errors[0].Message) (line $($errors[0].Extent.StartLineNumber))"
        }
    }
}

function Copy-ClientPowerShellScript {
    param(
        [Parameter(Mandatory)][string]$SourcePath,
        [Parameter(Mandatory)][string]$DestPath
    )
    $content = Get-Content -LiteralPath $SourcePath -Raw
    $content = $content -replace [char]0x2014, '-'
    $content = $content -replace [char]0x2013, '-'
    $parent = Split-Path -Parent $DestPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($DestPath, $content, $utf8Bom)
}

if (-not $ExportRoot) {
    $ExportRoot = $fx.ExportRoot
}
if (-not $Version) {
    $Version = if (Test-Path -LiteralPath $fx.VersionFile) { (Get-Content -LiteralPath $fx.VersionFile -Raw).Trim() } else { "1.0.0" }
}
if (-not $MinAppVersion) { $MinAppVersion = $Version }

$protectedPrefixes = @(
    "data/watchlists.json",
    "data/portfolio.json",
    "data/layout.json",
    "data/saved_filters.json",
    "data/screener_session.json",
    "data/screener_profile/"
)

function Test-ProtectedPath([string]$Rel) {
    $r = $Rel -replace '\\', '/'
    foreach ($p in $protectedPrefixes) {
        if ($r -eq $p -or $r.StartsWith($p)) { return $true }
    }
    return $false
}

function Test-SkipUpdatePath([string]$Rel) {
    $r = $Rel -replace '\\', '/'
    if ($r -match '(^|/)node_modules(/|$)') { return $true }
    if ($r -match '(^|/)__pycache__(/|$)') { return $true }
    if ($r -match '(^|/)\.git(/|$)') { return $true }
    return $false
}

function Add-Entry {
    param($List, $Seen, [string]$Root, [string]$FullPath)
    $rel = $FullPath.Substring($Root.Length).TrimStart('\', '/')
    if (Test-ProtectedPath $rel) { return }
    if (Test-SkipUpdatePath $rel) { return }
    if ($Seen.ContainsKey($rel)) { return }
    $Seen[$rel] = $true
    $hash = (Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash.ToLower()
    [void]$List.Add([ordered]@{
        path   = ($rel -replace '\\', '/')
        sha256 = $hash
        size   = (Get-Item -LiteralPath $FullPath).Length
    })
}

$exportResolved = (Resolve-Path -LiteralPath $ExportRoot).Path
$entries = [System.Collections.ArrayList]@()
$seen = @{}

$scanRoots = @(
    (Join-Path $exportResolved "server"),
    (Join-Path $exportResolved "frontend\build"),
    (Join-Path $exportResolved "scripts"),
    (Join-Path $exportResolved "config"),
    (Join-Path $exportResolved "desktop")
)
foreach ($scan in $scanRoots) {
    if (-not (Test-Path -LiteralPath $scan)) { continue }
    Get-ChildItem -LiteralPath $scan -Recurse -File -Force | ForEach-Object {
        Add-Entry -List $entries -Seen $seen -Root $exportResolved -FullPath $_.FullName
    }
}

$rootFiles = @(
    "start_flowx.bat",
    "stop_flowx.bat",
    "Apply-Update.bat",
    "db_sqlite.py",
    "requirements_runtime.txt"
)
foreach ($name in $rootFiles) {
    $full = Join-Path $exportResolved $name
    if (Test-Path -LiteralPath $full) {
        Add-Entry -List $entries -Seen $seen -Root $exportResolved -FullPath $full
    }
}

$verSrc = Join-Path $exportResolved "version.txt"
if (Test-Path -LiteralPath $verSrc) {
    Add-Entry -List $entries -Seen $seen -Root $exportResolved -FullPath $verSrc
}

if ($entries.Count -eq 0) {
    throw "No update files found under $exportResolved"
}

$outName = "FlowX-Update-$Version"
if (-not $OutputDir) {
    $OutputDir = Join-Path $fx.InstallerOutputDir $outName
}
if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$payloadRoot = Join-Path $OutputDir "payload"
New-Item -ItemType Directory -Force -Path $payloadRoot | Out-Null

foreach ($e in $entries) {
    $src = Join-Path $exportResolved ($e.path -replace '/', '\')
    $dst = Join-Path $payloadRoot ($e.path -replace '/', '\')
    $parent = Split-Path -Parent $dst
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}

# Always ship latest client update scripts from repo (export may be stale)
foreach ($rel in @(
        "scripts\FlowXUpdatePackage.ps1",
        "scripts\Apply-LocalUpdate-Entry.ps1",
        "scripts\FlowXInstallLocator.ps1",
        "scripts\Install-Client-Update.ps1",
        "scripts\_Apply-LocalUpdate.ps1",
        "scripts\Diagnose-FlowXInstall.ps1",
        "scripts\FlowXApplyUpdate.ps1",
        "server\app_code_crypto.py",
        "server\flowx_bootstrap.py",
        "server\github_updates.py",
        "config\github_updates.json",
        "Apply-Update.bat"
    )) {
    $src = Join-Path $RepoRoot ($rel -replace '/', '\')
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dst = Join-Path $payloadRoot ($rel -replace '/', '\')
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $norm = $rel -replace '\\', '/'
    if (-not $seen.ContainsKey($norm)) {
        Add-Entry -List $entries -Seen $seen -Root $payloadRoot -FullPath $dst
    }
}

$manifest = [ordered]@{
    version          = $Version
    minAppVersion    = $MinAppVersion
    includesDatabase = [bool]$IncludesDatabase
    files            = @($entries | Sort-Object { $_.path })
}
$manifestPath = Join-Path $OutputDir "update.manifest.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 6
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)

$clientReadme = @"
FlowX update package (version $Version)
=====================================

CLIENT PC - double-click Install-Client-Update.bat in this folder.

1. Close FlowX.
2. Extract this folder into your FlowX UPDATE folder (e.g. D:\FlowX\UPDATE\FlowX-Update-1.0.2).
3. Run Install-Client-Update.bat (install path is detected automatically).
4. If license is missing, run Repair-FlowXLicense.bat in the FlowX install folder.
5. Run start_flowx.bat in the FlowX install folder.

See CLIENT-STEPS.txt in this folder.
"@
Set-Content -LiteralPath (Join-Path $OutputDir "READ_ME_CLIENT.txt") -Value $clientReadme -Encoding UTF8

$clientSteps = Join-Path $RepoRoot "docs\CLIENT-STEPS.txt"
if (Test-Path -LiteralPath $clientSteps) {
    Copy-Item -LiteralPath $clientSteps -Destination (Join-Path $OutputDir "CLIENT-STEPS.txt") -Force
}
$installerBat = Join-Path $RepoRoot "Install-Client-Update.bat"
$installerPs1 = Join-Path $RepoRoot "scripts\Install-Client-Update.ps1"
if (Test-Path -LiteralPath $installerBat) {
    Copy-Item -LiteralPath $installerBat -Destination (Join-Path $OutputDir "Install-Client-Update.bat") -Force
}
$repairBat = Join-Path $RepoRoot "Repair-FlowXLicense.bat"
if (Test-Path -LiteralPath $repairBat) {
    Copy-Item -LiteralPath $repairBat -Destination (Join-Path $OutputDir "Repair-FlowXLicense.bat") -Force
}
$clientPs1Paths = @()
if (Test-Path -LiteralPath $installerPs1) {
    $dst = Join-Path $OutputDir "Install-Client-Update.ps1"
    Copy-ClientPowerShellScript -SourcePath $installerPs1 -DestPath $dst
    $clientPs1Paths += $dst
}
foreach ($rel in @("FlowXInstallLocator.ps1", "FlowXUpdatePackage.ps1")) {
    $srcPs1 = Join-Path $RepoRoot "scripts\$rel"
    if (-not (Test-Path -LiteralPath $srcPs1)) { continue }
    $scriptsOut = Join-Path $OutputDir "scripts"
    $dst = Join-Path $scriptsOut $rel
    Copy-ClientPowerShellScript -SourcePath $srcPs1 -DestPath $dst
    $clientPs1Paths += $dst
}
$repoClientScripts = @(
    (Join-Path $RepoRoot "scripts\Install-Client-Update.ps1"),
    (Join-Path $RepoRoot "scripts\FlowXInstallLocator.ps1"),
    (Join-Path $RepoRoot "scripts\FlowXUpdatePackage.ps1"),
    (Join-Path $RepoRoot "scripts\Apply-LocalUpdate-Entry.ps1"),
    (Join-Path $RepoRoot "scripts\Diagnose-FlowXInstall.ps1")
)
Test-PowerShellScriptSyntax -Paths ($repoClientScripts + $clientPs1Paths)

Write-Host "Update package: $OutputDir"
Write-Host "Client runs: Install-Client-Update.bat (in this folder)"
Write-Host "Files: $($entries.Count)"

$zipPath = Join-Path $fx.InstallerOutputDir "$outName.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Write-Host "Creating GitHub release ZIP: $zipPath"
Compress-Archive -LiteralPath $OutputDir -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host ""
Write-Host "Publish to GitHub Releases:"
Write-Host "  Repo:  https://github.com/unnwired/flowx-updates/releases"
Write-Host "  Tag:   v$Version"
Write-Host "  Asset: $outName.zip"
