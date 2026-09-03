#Requires -Version 5.1
<#
.SYNOPSIS
  Mark export as online-only activation (no vendor install key) and sync auth modules.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot
if (-not $ExportRoot) {
    $fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind Encrypted
    $ExportRoot = $fx.ExportRoot
} else {
    if (-not [System.IO.Path]::IsPathRooted($ExportRoot)) {
        $ExportRoot = Join-Path $RepoRoot $ExportRoot
    }
    $ExportRoot = [System.IO.Path]::GetFullPath($ExportRoot)
    $fx = Resolve-CiMPathsForExportRoot -ExportRoot $ExportRoot -RepoRoot $RepoRoot
}

$configDir = Join-Path $ExportRoot "config"
if (-not (Test-Path -LiteralPath $configDir)) {
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$onlineMarker = Join-Path $configDir ".cim-online-only"
[System.IO.File]::WriteAllText($onlineMarker, "online-only activation (no vendor install key)`n", $utf8NoBom)
Write-Host "Wrote config\.cim-online-only"

$prodPath = Join-Path $configDir "product.json"
$prodSrc = Join-Path $RepoRoot "config\product.json"
if (Test-Path -LiteralPath $prodSrc) {
    Copy-Item -LiteralPath $prodSrc -Destination $prodPath -Force
}
if (Test-Path -LiteralPath $prodPath) {
    $prod = Get-Content -LiteralPath $prodPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $prod | Add-Member -NotePropertyName onlineOnlyActivation -NotePropertyValue $true -Force
    $prod.maxDevicesPerAccount = 1
    [System.IO.File]::WriteAllText($prodPath, (($prod | ConvertTo-Json -Depth 10) + "`n"), $utf8NoBom)
    Write-Host "Updated config\product.json (onlineOnlyActivation, maxDevicesPerAccount=1)"
}

$sync = @(
    "server\license_client.py",
    "server\license_routes.py",
    "server\client_user_agent.py",
    "server\auth_social_proof.py",
    "server\app_code_crypto.py",
    "server\cim_bootstrap.py",
    "server\product_config.py"
)
foreach ($rel in $sync) {
    $src = Join-Path $pkg.ServerRoot ($rel -replace '^server\\', '')
    $dst = Join-Path $ExportRoot $rel
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}

$authSrc = $pkg.BrowserAuth
$authDst = Join-Path $ExportRoot "frontend\auth"
if (Test-Path -LiteralPath $authSrc) {
    if (Test-Path -LiteralPath $authDst) { Remove-Item -LiteralPath $authDst -Recurse -Force }
    Copy-Item -LiteralPath $authSrc -Destination $authDst -Recurse -Force
    Write-Host "Synced frontend\auth"
}

Write-Host "Online distribution markers ready: $ExportRoot"
