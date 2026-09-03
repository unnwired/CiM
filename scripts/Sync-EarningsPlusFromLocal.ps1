#Requires -Version 5.1
<#
.SYNOPSIS
  Recompute Earnings+ cache from local screener_quarterly (no Screener scrape).
#>
param(
    [string[]]$DbPaths = @(
        "D:\Programs\NSE Pulse\Claude Ai\data\nse_data.db",
        "D:\CiM\Client_Test\data\nse_data.db",
        "D:\CiM\Client\data\nse_data.db"
    ),
    [string[]]$Symbols = @()
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $RepoRoot "packages\server\server.py"))) {
    $RepoRoot = "D:\Programs\NSE Pulse\Claude Ai"
}
$py = Join-Path $RepoRoot "runtime\python\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$packages = Join-Path $RepoRoot "packages"

foreach ($db in $DbPaths) {
    if (-not (Test-Path -LiteralPath $db)) {
        Write-Host "SKIP missing DB: $db"
        continue
    }
    Write-Host "=== Sync Earnings+ from local: $db ==="
    $env:CIM_DB_PATH = $db
    $symJson = ($Symbols | ConvertTo-Json -Compress)
    if (-not $Symbols -or $Symbols.Count -eq 0) { $symJson = "[]" }
    & $py -c @"
import json, os, sys
sys.path.insert(0, r'$($packages.Replace('\','\\'))')
os.environ['CIM_DB_PATH'] = r'$($db.Replace('\','\\'))'
# Point server module at this DB before import side effects where possible.
from pathlib import Path
import server.server as srv
srv.DB_PATH = Path(r'$($db.Replace('\','\\'))')
symbols = json.loads('''$symJson''')
summary = srv.run_sync_earnings_plus_cache_from_local(
    symbols=symbols or None,
    quiet=True,
    trigger='cli_local_sync',
)
print(json.dumps(summary, indent=2))
for sym in ('KIRLPNU', 'MEDPLUS'):
    conn = srv.get_db_connection()
    try:
        row = conn.execute(
            'SELECT decision, basis_used, latest_period, note FROM earnings_plus_cache WHERE symbol=?',
            (sym,),
        ).fetchone()
    finally:
        conn.close()
    if row:
        print(sym, '=>', dict(row))
    else:
        print(sym, '=> missing')
"@
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Sync failed for $db"
    }
}
