#Requires -Version 5.1
<#
.SYNOPSIS
  Run Charts In Motion client showcase (browser) on localhost — isolated from dev (port 8001).

.DESCRIPTION
  Uses the distribution tree at D:\CiM\Client (or -InstallRoot). Clears CIM_DEV for the
  child process so the online license shell is served, not dev preview.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [int]$Port = 8001,
    [int]$StartupTimeoutSec = 120,
    [switch]$KeepSession,
    [switch]$FreshAuth
)

$ErrorActionPreference = "Stop"

function Resolve-CiMInstallRoot {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "InstallRoot is required"
    }
    # CMD passes "%~dp0" as D:\CiM\Client\ — trailing \ before " escapes the quote and breaks GetFullPath.
    $normalized = $Path.Trim().Trim('"').TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "InstallRoot is empty after normalization"
    }
    return [System.IO.Path]::GetFullPath($normalized)
}

$InstallRoot = Resolve-CiMInstallRoot $InstallRoot
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$hostSettingsScript = Join-Path $ScriptDir "Get-CiMShowcaseInstallSettings.ps1"
if (Test-Path -LiteralPath $hostSettingsScript) {
    . $hostSettingsScript
}

$py = Join-Path $InstallRoot "runtime\python\python.exe"
$logDir = Join-Path $InstallRoot "runtime\logs"
$logFile = Join-Path $logDir "showcase-backend.log"
$errFile = Join-Path $logDir "showcase-backend.err.log"
$pidFile = Join-Path $logDir "showcase-backend.pid"

if (-not (Test-Path -LiteralPath $py)) {
    throw "Missing embedded Python: $py (run plaintext export to $InstallRoot first)"
}
if (-not (Test-CiMInstallHasServerBootstrap -Root $InstallRoot)) {
    throw "Missing client tree under $InstallRoot"
}

function Enable-WebHostMode {
    param([string]$Root)
    $marker = Join-Path $Root "config\.cim-web-host"
    New-Item -ItemType Directory -Force -Path (Split-Path $marker -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $marker)) {
        "" | Set-Content -LiteralPath $marker -Encoding UTF8
        Write-Host "Enabled web host mode (per-browser sessions): config\.cim-web-host" -ForegroundColor Cyan
    }
}

function Enable-ShowcaseHostMode {
    param([string]$Root)
    $marker = Join-Path $Root "config\.cim-showcase-host"
    New-Item -ItemType Directory -Force -Path (Split-Path $marker -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $marker)) {
        "" | Set-Content -LiteralPath $marker -Encoding UTF8
        Write-Host "Enabled showcase host (EOD/admin): config\.cim-showcase-host" -ForegroundColor Cyan
    }
}

function Clear-ShowcaseAuthState {
    param([string]$Root, [switch]$AllSessions)
    $dataDir = Join-Path $Root "data"
    $removed = @()
    foreach ($name in @(".cim-session.json", ".cim-license.json", ".cim-license")) {
        $path = Join-Path $dataDir $name
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
            $removed += $name
        }
    }
    if ($AllSessions) {
        $sessionsDir = Join-Path $dataDir "sessions"
        if (Test-Path -LiteralPath $sessionsDir) {
            Remove-Item -LiteralPath $sessionsDir -Recurse -Force
            $removed += "data/sessions/"
        }
    }
    if ($removed.Count -gt 0) {
        Write-Host "Cleared showcase auth: $($removed -join ', ')" -ForegroundColor Yellow
    }
}

function Stop-ShowcaseBackend {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*:$Port*" -and
            ($_.CommandLine -like "*cim_bootstrap*" -or $_.CommandLine -like "*run_uvicorn.py*")
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($oldPid -match '^\d+$') {
            Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

function Wait-ShowcaseHealth {
    param([int]$ListenPort, [int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ListenPort/api/health" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

Stop-ShowcaseBackend
Enable-WebHostMode -Root $InstallRoot
Enable-ShowcaseHostMode -Root $InstallRoot
if (Get-Command Ensure-CiMShowcaseYahooPrimaryPipeline -ErrorAction SilentlyContinue) {
    Ensure-CiMShowcaseYahooPrimaryPipeline -InstallRoot $InstallRoot | Out-Null
}
if ($FreshAuth) {
    Clear-ShowcaseAuthState -Root $InstallRoot -AllSessions
} elseif (-not $KeepSession) {
    Clear-ShowcaseAuthState -Root $InstallRoot
}
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
"" | Set-Content -LiteralPath $logFile -Encoding UTF8
"" | Set-Content -LiteralPath $errFile -Encoding UTF8

$savedDev = $env:CIM_DEV
$savedTools = $env:CIM_DEV_TOOLS
Remove-Item Env:CIM_DEV -ErrorAction SilentlyContinue
Remove-Item Env:CIM_DEV_TOOLS -ErrorAction SilentlyContinue
$env:CIM_NO_PAUSE = '1'
$env:CIM_INSTALL_ROOT = $InstallRoot

$args = Get-CiMUvicornPythonArgs -RepoRoot $InstallRoot -AppModule "server.cim_bootstrap:app" -ExtraArgs @(
    '--host', '127.0.0.1',
    '--port', "$Port",
    '--log-level', 'warning'
)

Write-Host "Starting CiM showcase on http://127.0.0.1:$Port (root: $InstallRoot)"
try {
    $p = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $InstallRoot `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errFile
} finally {
    if ($savedDev) { $env:CIM_DEV = $savedDev } else { Remove-Item Env:CIM_DEV -ErrorAction SilentlyContinue }
    if ($savedTools) { $env:CIM_DEV_TOOLS = $savedTools } else { Remove-Item Env:CIM_DEV_TOOLS -ErrorAction SilentlyContinue }
    Remove-Item Env:CIM_NO_PAUSE -ErrorAction SilentlyContinue
}

$p.Id | Set-Content -LiteralPath $pidFile -Encoding ASCII
Write-Host "Showcase backend PID: $($p.Id)  logs -> $logDir"

if (-not (Wait-ShowcaseHealth -ListenPort $Port -TimeoutSec $StartupTimeoutSec)) {
    Write-Host "Backend did not become healthy. Last log lines:" -ForegroundColor Red
    Get-Content -LiteralPath $errFile -Tail 30 -ErrorAction SilentlyContinue
    Get-Content -LiteralPath $logFile -Tail 30 -ErrorAction SilentlyContinue
    throw "Showcase backend failed to start on port $Port"
}

Write-Host "Showcase ready: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Enable public access: tailscale funnel $Port"
exit 0
