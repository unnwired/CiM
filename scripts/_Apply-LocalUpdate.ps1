param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$UpdateDir
)
$ErrorActionPreference = "Stop"

function Normalize-InstallPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return [System.IO.Path]::GetFullPath($Path.Trim().TrimEnd([char]'"')).TrimEnd([char]'\')
}

$InstallRoot = Normalize-InstallPath $InstallRoot
$UpdateDir = Normalize-InstallPath $UpdateDir
$manifestPath = Join-Path $UpdateDir "update.manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$logDir = Join-Path $InstallRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$pendingPath = Join-Path $logDir "update-pending-local.json"
[ordered]@{
    version   = [string]$manifest.version
    source    = "local"
    sourceDir = $UpdateDir
    manifest  = $manifest
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $pendingPath -Encoding UTF8
$apply = Join-Path $InstallRoot "scripts\CiMApplyUpdate.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File $apply -InstallRoot $InstallRoot -ManifestPath $pendingPath
exit $LASTEXITCODE
