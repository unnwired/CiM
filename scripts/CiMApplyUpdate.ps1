#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath
)

$ErrorActionPreference = "Stop"

function Normalize-InstallPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return [System.IO.Path]::GetFullPath($Path.Trim().TrimEnd([char]'"')).TrimEnd([char]'\')
}

$InstallRoot = Normalize-InstallPath $InstallRoot
$ManifestPath = Normalize-InstallPath $ManifestPath

$logDir = Join-Path $InstallRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "update-apply.log"
$resultFile = Join-Path $InstallRoot "update-result.txt"

function Write-Log([string]$Msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Test-FlowXShowApplyDialog {
    if ($env:CIM_NO_PAUSE -eq "1") { return $false }
    try {
        return [Environment]::UserInteractive
    } catch {
        return $false
    }
}

function Show-FlowXApplyDialog([string]$Text, [string]$Icon = "Information") {
    if (-not (Test-FlowXShowApplyDialog)) {
        Write-Log "Skipping dialog (CIM_NO_PAUSE or non-interactive): $Text"
        return
    }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($Text, "Charts In Motion Update", "OK", $Icon) | Out-Null
}

$protected = @(
    "data\watchlists.json",
    "data\portfolio.json",
    "data\layout.json",
    "data\saved_filters.json",
    "data\screener_session.json",
    "data\.cim-license",
    "data\.cim-session.json"
)

Start-Sleep -Seconds 3
Write-Log "Apply started (root=$InstallRoot)"

try {
    $pending = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $manifest = $pending.manifest
    $sourceDir = $pending.sourceDir
    if (-not $manifest -or -not $sourceDir) {
        throw "Invalid pending manifest: $ManifestPath"
    }

    # Phase 1 lockdown: updates ship server/_cim_dist_embedded.py, not config/.fx-dist.cfg.
    $legacyVendor = Join-Path $InstallRoot "config\.fx-dist.cfg"
    if (Test-Path -LiteralPath $legacyVendor) {
        Remove-Item -LiteralPath $legacyVendor -Force -ErrorAction SilentlyContinue
        Write-Log "Removed legacy config\.fx-dist.cfg from install"
    }

    foreach ($entry in $manifest.files) {
        $rel = ($entry.path -replace '/', '\')
        $skip = $false
        foreach ($p in $protected) {
            if ($rel -ieq $p) { $skip = $true; break }
        }
        if ($rel -like "data\screener_profile\*") { $skip = $true }
        if ($skip) {
            Write-Log "Skip protected: $rel"
            continue
        }
        $src = Join-Path $sourceDir $rel
        if (-not (Test-Path -LiteralPath $src)) {
            $src = Join-Path $sourceDir ("payload\" + $rel)
        }
        if (-not (Test-Path -LiteralPath $src)) {
            throw "Missing payload file: $rel (source=$sourceDir)"
        }
        $dst = Join-Path $InstallRoot $rel
        $parent = Split-Path -Parent $dst
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Log "Copied $rel"
    }

    $ver = [string]$manifest.version
    $verPath = Join-Path $InstallRoot "version.txt"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($verPath, $ver, $utf8NoBom)

    $cacheRoot = Join-Path $env:LOCALAPPDATA "CiM\app-cache"
    if (Test-Path -LiteralPath $cacheRoot) {
        Remove-Item -LiteralPath $cacheRoot -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "Cleared app-cache"
    }

    $py = Join-Path $InstallRoot "runtime\python\python.exe"
    $dbPath = Join-Path $InstallRoot "data\nse_data.db"
    if ((Test-Path -LiteralPath $py) -and (Test-Path -LiteralPath $dbPath)) {
        Write-Log "Running post-update NSE EOD reconcile (fixes chart/market-map % without full reinstall)..."
        $rootEsc = $InstallRoot.Replace("'", "''")
        $code = @"
import sys
from pathlib import Path
root = Path(r'$rootEsc')
sys.path.insert(0, str(root))
try:
    from server.eod_reconcile import run_eod_bhavcopy_reconcile
    n = run_eod_bhavcopy_reconcile(root / 'data' / 'nse_data.db', log_fn=print)
    print(f'post_update_eod_reconcile bars={n}')
except Exception as e:
    print(f'post_update_eod_reconcile warning: {e}')
"@
        try {
            & $py -s -c $code 2>&1 | ForEach-Object { Write-Log $_ }
        } catch {
            Write-Log "Post-update EOD reconcile warning: $_"
        }
    }

    $msg = "Update complete ($ver). Start Charts In Motion from start_cim.bat or the desktop shortcut."
    Set-Content -LiteralPath $resultFile -Value $msg -Encoding UTF8
    Write-Log $msg
    Show-FlowXApplyDialog $msg "Information"
}
catch {
    Write-Log "ERROR: $_"
    Set-Content -LiteralPath $resultFile -Value "Update failed: $_" -Encoding UTF8
    Show-FlowXApplyDialog "Update failed. See runtime\logs\update-apply.log" "Error"
    exit 1
}
