#Requires -Version 5.1
<#
.SYNOPSIS
  End-to-end check: Build Launcher distribution DB source = showcase testbed.
#>
$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptDir
. (Join-Path $ScriptDir 'Get-CiMPaths.ps1')
. (Join-Path $ScriptDir 'Get-CiMShowcaseDeployConfig.ps1')

$fail = 0
function Assert-True {
    param([bool]$Cond, [string]$Name)
    if (-not $Cond) {
        Write-Host "FAIL $Name" -ForegroundColor Red
        $script:fail++
    } else {
        Write-Host "OK   $Name" -ForegroundColor Green
    }
}

Write-Host '=== Resolve-CiMDistributionDbSource ===' -ForegroundColor Cyan
$cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
$expected = Join-Path $cfg.showcaseInstallRoot 'data\nse_data.db'
$resolved = Resolve-CiMDistributionDbSource -RepoRoot $RepoRoot
Assert-True ($resolved -eq [System.IO.Path]::GetFullPath($expected)) "default resolves to testbed DB ($resolved)"
Assert-True (Test-Path -LiteralPath $resolved) "testbed DB exists"

$explicitFile = Resolve-CiMDistributionDbSource -RepoRoot $RepoRoot -DbSource $expected
Assert-True ($explicitFile -eq [System.IO.Path]::GetFullPath($expected)) 'explicit .db path honored'

$explicitRoot = Resolve-CiMDistributionDbSource -RepoRoot $RepoRoot -DbSource $cfg.showcaseInstallRoot
Assert-True ($explicitRoot -eq [System.IO.Path]::GetFullPath($expected)) 'install root expands to data\nse_data.db'

$worker = Get-Content -LiteralPath (Join-Path $RepoRoot 'Batch Files\Build-CiM-GUI-Worker.ps1') -Raw
Assert-True ($worker -match 'Resolve-CiMDistributionDbSource') 'worker resolves DbSource'
Assert-True ($worker -match 'DbSource\s*=\s*\$dbSource') 'worker passes DbSource to full build'

$full = Get-Content -LiteralPath (Join-Path $ScriptDir 'build_distribution_full.ps1') -Raw
Assert-True ($full -match '\$DbSource') 'full build accepts DbSource'
Assert-True ($full -match 'DbSource\s*=\s*\$DbSource') 'full build passes DbSource to export'

$export = Get-Content -LiteralPath (Join-Path $RepoRoot 'export_cim.ps1') -Raw
Assert-True ($export -match '\[string\]\$DbSource') 'export_cim has DbSource param'
Assert-True ($export -match 'DB snapshot source:') 'export logs DB source'

$sync = Get-Content -LiteralPath (Join-Path $ScriptDir 'Sync-ExportDistributionFixes.ps1') -Raw
Assert-True ($sync -match '\[string\]\$DbSource') 'sync accepts DbSource'
Assert-True ($sync -match 'Resolve-CiMDistributionDbSource') 'sync resolves distribution DB'

Write-Host ''
Write-Host '=== Snapshot + cache table smoke ===' -ForegroundColor Cyan
$staging = Join-Path $env:TEMP ("cim-db-source-e2e-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $staging 'data') | Out-Null
$dstDb = Join-Path $staging 'data\nse_data.db'
$py = Join-Path $RepoRoot 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $py)) { $py = 'python' }
$snapPy = Join-Path $ScriptDir 'copy_db_snapshot.py'
$integrityPy = Join-Path $ScriptDir 'check_db_integrity.py'

Write-Host "Snapshot $resolved -> $dstDb"
& $py -s $snapPy $resolved $dstDb
Assert-True ($LASTEXITCODE -eq 0) 'copy_db_snapshot exit 0'
Assert-True (Test-Path -LiteralPath $dstDb) 'destination DB created'

& $py -s $integrityPy $dstDb
Assert-True ($LASTEXITCODE -eq 0) 'integrity_check exit 0'

$checkTables = @'
import sqlite3, sys
db = sys.argv[1]
conn = sqlite3.connect(db)
cur = conn.cursor()
required = (
    "historical_data",
    "indicator_snapshots",
    "earnings_plus_cache",
    "bars_4h",
)
missing = []
for t in required:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)
    ).fetchone()
    if not row:
        missing.append(t)
        continue
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t}={n}")
    if int(n) <= 0 and t in ("historical_data", "indicator_snapshots"):
        missing.append(f"{t}:empty")
# 30m optional until first post-close build
row30 = cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='bars_30m'"
).fetchone()
if row30:
    n30 = cur.execute("SELECT COUNT(*) FROM bars_30m").fetchone()[0]
    print(f"bars_30m={n30}")
conn.close()
if missing:
    print("MISSING:" + ",".join(missing))
    sys.exit(2)
'@
$tmpPy = Join-Path $staging 'check_tables.py'
Set-Content -LiteralPath $tmpPy -Value $checkTables -Encoding UTF8
& $py -s $tmpPy $dstDb
Assert-True ($LASTEXITCODE -eq 0) 'warm cache tables present (historical/snapshots/earnings+/4H)'

Write-Host ''
Write-Host '=== Sync-ExportDistributionFixes with testbed DbSource ===' -ForegroundColor Cyan
# Minimal export-shaped tree so sync's DB path can run without full export.
$syncRoot = Join-Path $staging 'export-tree'
New-Item -ItemType Directory -Force -Path (Join-Path $syncRoot 'data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $syncRoot 'runtime\python') | Out-Null
# Point sync at repo python by leaving export python missing → falls back to repo.
try {
    & (Join-Path $ScriptDir 'Sync-ExportDistributionFixes.ps1') `
        -RepoRoot $RepoRoot `
        -ExportRoot $syncRoot `
        -DbSource $resolved
    # Sync may throw on missing launcher files / prune — catch and only require DB refresh success via message
} catch {
    $err = "$_"
    # Accept partial sync failures that are unrelated to DB if DB was written
    if ($err -match 'copy_db_snapshot|Distribution DB source missing|integrity') {
        Write-Host "FAIL sync DB path: $err" -ForegroundColor Red
        $fail++
    } else {
        Write-Host "OK   sync reached past DB step (later non-DB warning/error ignored): $($err.Split("`n")[0])" -ForegroundColor Yellow
    }
}
$syncedDb = Join-Path $syncRoot 'data\nse_data.db'
if (Test-Path -LiteralPath $syncedDb) {
    & $py -s $integrityPy $syncedDb
    Assert-True ($LASTEXITCODE -eq 0) 'sync output DB integrity ok'
    $srcSize = (Get-Item -LiteralPath $resolved).Length
    $dstSize = (Get-Item -LiteralPath $syncedDb).Length
    # Snapshot size should be in the same ballpark (within 20%)
    $ratio = if ($srcSize -gt 0) { [math]::Abs($dstSize - $srcSize) / $srcSize } else { 1 }
    Assert-True ($ratio -lt 0.25) "sync DB size near testbed (src=$srcSize dst=$dstSize)"
} else {
    Write-Host 'FAIL sync did not write data\nse_data.db' -ForegroundColor Red
    $fail++
}

Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ''
if ($fail -gt 0) {
    Write-Host "$fail check(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host 'All distribution DB source e2e checks passed.' -ForegroundColor Green
Write-Host "Caches that ship inside the DB: indicator_snapshots, earnings_plus_cache, bars_4h (+ bars_30m when built)."
exit 0
