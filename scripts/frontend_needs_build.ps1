# Exit codes: 0 = existing build is current; 1 = rebuild needed (stale sources); 2 = no build output
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectRoot
)

$ErrorActionPreference = 'SilentlyContinue'

$build = Join-Path $ProjectRoot 'frontend\build\index.html'
if (-not (Test-Path -LiteralPath $build)) {
    Write-Host '[cim] frontend\build\index.html missing - npm run build required.'
    exit 2
}

$buildTime = (Get-Item -LiteralPath $build).LastWriteTimeUtc

$pkg = Join-Path $ProjectRoot 'frontend\package.json'
if ((Test-Path -LiteralPath $pkg) -and ((Get-Item -LiteralPath $pkg).LastWriteTimeUtc -gt $buildTime)) {
    Write-Host '[cim] package.json newer than build - npm run build required.'
    exit 1
}

$srcRoot = Join-Path $ProjectRoot 'frontend\src'
if (-not (Test-Path -LiteralPath $srcRoot)) {
    exit 0
}

$newest = Get-ChildItem -LiteralPath $srcRoot -Recurse -File |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1

if ($newest -and $newest.LastWriteTimeUtc -gt $buildTime) {
    Write-Host '[cim] frontend\src is newer than build - npm run build required.'
    exit 1
}

exit 0
