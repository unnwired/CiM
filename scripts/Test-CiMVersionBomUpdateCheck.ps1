#Requires -Version 5.1
<#
.SYNOPSIS
  Repro + verify: BOM version.txt on 1.0.5 must not offer GitHub 1.0.4.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [int]$Port = 8011
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-CiMPaths -RepoRoot $RepoRoot
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot
if (-not $ExportRoot) { $ExportRoot = $fx.ExportRoot }

$TestRoot = Join-Path $fx.InstallerOutputDir "FlowX-bom-version-test"
$LogFile = Join-Path $RepoRoot "runtime\logs\bom-version-test.log"

function Log([string]$Msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Stop-TestBackend {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*--port $Port*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

Log "=== BOM version.txt update check (client 1.0.5, GitHub latest 1.0.4) ==="

if (Test-Path -LiteralPath $TestRoot) {
    Stop-TestBackend
    Remove-Item -LiteralPath $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Copy-Item -LiteralPath $ExportRoot -Destination $TestRoot -Recurse -Force

# Sync fixed server modules into test tree (plaintext bootstrap path).
Copy-Item -LiteralPath (Join-Path $pkg.ServerRoot "update_apply.py") -Destination (Join-Path $TestRoot "server\update_apply.py") -Force
Copy-Item -LiteralPath (Join-Path $pkg.ServerRoot "github_updates.py") -Destination (Join-Path $TestRoot "server\github_updates.py") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts\CiMApplyUpdate.ps1") -Destination (Join-Path $TestRoot "scripts\CiMApplyUpdate.ps1") -Force

$verFile = Join-Path $TestRoot "version.txt"
# PowerShell 5.1 Set-Content -Encoding UTF8 writes BOM (the bug clients hit).
$content = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText($verFile, "1.0.5", $content)
Log "Wrote version.txt with UTF-8 BOM = 1.0.5"

$stalePkg = Join-Path $TestRoot "UPDATE\CiM-Update-1.0.4"
if (Test-Path -LiteralPath $stalePkg) {
    Remove-Item -LiteralPath $stalePkg -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $stalePkg "payload") | Out-Null
Copy-Item -LiteralPath $verFile -Destination (Join-Path $stalePkg "payload\version.txt") -Force
@{
    version = "1.0.4"
    files = @(@{ path = "version.txt"; sha256 = "x"; size = 5 })
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stalePkg "update.manifest.json") -Encoding UTF8
Log "Placed stale local UPDATE\CiM-Update-1.0.4 package"

$cacheRoot = Join-Path $env:LOCALAPPDATA "CiM\app-cache"
if (Test-Path -LiteralPath $cacheRoot) {
    Remove-Item -LiteralPath $cacheRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$repoRoot = Split-Path -Parent $ScriptDir
$secret = Get-CiMVendorSecret -RepoRoot $repoRoot
if (-not $secret) { throw "Missing config\.build_license_secret" }
$pyLic = Join-Path $TestRoot "runtime\python\python.exe"
& $pyLic -s -c @"
import sys
sys.path.insert(0, r'$repoRoot')
from pathlib import Path
from server.app_code_crypto import current_machine_code, install_key_for_machine
root = Path(r'$TestRoot')
mc = current_machine_code()
key = install_key_for_machine(mc, secret=r'$($secret.Replace("'","''"))'.encode('utf-8'))
(root / 'data').mkdir(parents=True, exist_ok=True)
(root / 'data' / '.cim-license').write_text('MachineCode=' + mc + chr(10) + 'InstallKey=' + key + chr(10), encoding='utf-8')
"@ | Out-Null

$py = Join-Path $TestRoot "runtime\python\python.exe"
Stop-TestBackend
$proc = Start-Process -FilePath $py -ArgumentList @(
    "-m", "uvicorn", "server.cim_bootstrap:app",
    "--host", "127.0.0.1", "--port", "$Port"
) -WorkingDirectory $TestRoot -PassThru -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(90)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { throw "Backend exited (code $($proc.ExitCode))" }
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($h.status -eq "ok") { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $healthy) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    throw "Backend health timeout"
}

$base = "http://127.0.0.1:$Port"
$settings = Invoke-RestMethod -Uri "$base/api/update/settings" -TimeoutSec 30
Log "settings.currentVersion=$($settings.currentVersion)"

if ($settings.currentVersion -ne "1.0.5") {
    throw "Expected currentVersion 1.0.5, got $($settings.currentVersion) (BOM read failed)"
}

$check = Invoke-RestMethod -Uri "$base/api/update/check" -TimeoutSec 60
Log "check.available=$($check.available) current=$($check.currentVersion) update=$($check.update.version) source=$($check.update.source)"

if ($check.currentVersion -ne "1.0.5") {
    throw "check.currentVersion mismatch: $($check.currentVersion)"
}

if ($check.available -and $check.update.version -eq "1.0.4") {
    throw "BUG: offered GitHub/local 1.0.4 while installed 1.0.5"
}

if ($check.available) {
    $uv = $check.update.version
    if ($uv -and ([version]$uv) -le ([version]"1.0.5")) {
        throw "BUG: offered same/older update $uv while on 1.0.5"
    }
}

Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Log "=== PASS: 1.0.5 with BOM does not offer 1.0.4 ==="
exit 0
