# Exit codes: 0 = existing build is current; 1 = rebuild needed (stale sources); 2 = no build output
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectRoot
)

$ErrorActionPreference = 'SilentlyContinue'

function Resolve-BrowserProjectDir {
    param([string]$Root)
    $legacy = Join-Path $Root 'frontend'
    if (Test-Path -LiteralPath (Join-Path $legacy 'package.json')) { return $legacy }
    $pkg = Join-Path $Root 'packages\browser'
    if (Test-Path -LiteralPath (Join-Path $pkg 'package.json')) { return $pkg }
    return $legacy
}

$browserDir = Resolve-BrowserProjectDir -Root $ProjectRoot
$build = Join-Path $browserDir 'build\index.html'
if (-not (Test-Path -LiteralPath $build)) {
    Write-Host '[cim] browser build\index.html missing - npm run build required.'
    exit 2
}

$buildTime = (Get-Item -LiteralPath $build).LastWriteTimeUtc

$pkgJson = Join-Path $browserDir 'package.json'
if ((Test-Path -LiteralPath $pkgJson) -and ((Get-Item -LiteralPath $pkgJson).LastWriteTimeUtc -gt $buildTime)) {
    Write-Host '[cim] package.json newer than build - npm run build required.'
    exit 1
}

$srcRoot = Join-Path $browserDir 'src'
if (-not (Test-Path -LiteralPath $srcRoot)) {
    exit 0
}

$newest = Get-ChildItem -LiteralPath $srcRoot -Recurse -File |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1

if ($newest -and $newest.LastWriteTimeUtc -gt $buildTime) {
    Write-Host '[cim] browser\src is newer than build - npm run build required.'
    exit 1
}

exit 0
