#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$ManifestJson
)

$ErrorActionPreference = "Stop"
$manifest = $ManifestJson | ConvertFrom-Json
$version = [string]$manifest.version
$staging = Join-Path $env:LOCALAPPDATA "FlowX\update-staging\$version"
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $staging | Out-Null

$logFile = Join-Path $InstallRoot "runtime\logs\update-download.log"
function Write-Log([string]$Msg) {
    Add-Content -LiteralPath $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg" -Encoding UTF8
}

$i = 0
foreach ($entry in $manifest.files) {
    $i++
    $url = [string]$entry.url
    if (-not $url) { throw "File $($entry.path) missing url in remote manifest" }
    $rel = ($entry.path -replace '/', '\')
    $dst = Join-Path $staging $rel
    $parent = Split-Path -Parent $dst
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Write-Log "Downloading ($i): $rel"
    Invoke-WebRequest -Uri $url -OutFile $dst -UseBasicParsing
    $hash = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLower()
    $expected = ([string]$entry.sha256).ToLower()
    if ($expected -and $hash -ne $expected) {
        throw "SHA256 mismatch for $rel (got $hash, expected $expected)"
    }
}
Write-Log "Download complete: $staging"
