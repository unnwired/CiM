#Requires -Version 5.1
<#
.SYNOPSIS
  Dev workflow gate: unit tests, optional lint, smoke against running backend.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$PythonExe = "",
    [switch]$SkipLint,
    [switch]$SkipSmoke,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot

function Resolve-Python {
    param([string]$Root)
    $candidates = @(
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Join-Path $Root "runtime\python\python.exe"),
        (Join-Path $Root "runtime\venv\Scripts\python.exe")
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    throw "No Python found. Run make setup or start_cim.bat first."
}

if (-not $PythonExe) { $PythonExe = Resolve-Python -Root $RepoRoot }

Write-Host "== CiM Dev Gate =="
Write-Host "Python: $PythonExe"
Write-Host "Repo:   $RepoRoot"

Push-Location $RepoRoot
try {
    Write-Host "`n[1/4] dev_setup (ensure DB)..."
    & $PythonExe scripts/dev_setup.py
    if ($LASTEXITCODE -ne 0) { throw "dev_setup failed" }

    Set-CiMPythonPackagePath -RepoRoot $RepoRoot
    Write-Host "`n[2/4] unit tests..."
    & $PythonExe -m unittest discover -s (Join-Path $pkg.ServerRoot "tests") -v
    if ($LASTEXITCODE -ne 0) { throw "unit tests failed" }

    if (-not $SkipLint) {
        Write-Host "`n[3/4] browser package lint (build)..."
        $npm = "${env:ProgramFiles}\nodejs\npm.cmd"
        if (-not (Test-Path -LiteralPath $npm)) { $npm = "npm" }
        Push-Location $pkg.BrowserRoot
        try {
            & $npm run build 2>&1 | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "`n[3/4] lint skipped"
    }

    if (-not $SkipSmoke) {
        Write-Host "`n[4/4] smoke test (backend must be running on :$Port)..."
        $healthy = $false
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
            $healthy = ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
        } catch { }

        if (-not $healthy) {
            Write-Host "Starting temporary backend for smoke..."
            $logDir = Join-Path $RepoRoot "runtime\logs"
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
            $outLog = Join-Path $logDir "dev-gate-backend.log"
            $errLog = Join-Path $logDir "dev-gate-backend.err.log"
            $proc = Start-Process -FilePath $PythonExe `
                -ArgumentList (Get-CiMUvicornPythonArgs -RepoRoot $RepoRoot -AppModule "server.server:app" -ExtraArgs @("--host", "127.0.0.1", "--port", "$Port")) `
                -WorkingDirectory $RepoRoot -PassThru `
                -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden
            $deadline = (Get-Date).AddSeconds(90)
            while ((Get-Date) -lt $deadline) {
                try {
                    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
                    if ($r.StatusCode -ge 200) { break }
                } catch { Start-Sleep -Seconds 2 }
            }
            try {
                & $PythonExe scripts/smoke_test.py --base "http://127.0.0.1:$Port"
                if ($LASTEXITCODE -ne 0) { throw "smoke_test failed" }
            } finally {
                if ($proc -and -not $proc.HasExited) {
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                }
            }
        } else {
            & $PythonExe scripts/smoke_test.py --base "http://127.0.0.1:$Port"
            if ($LASTEXITCODE -ne 0) { throw "smoke_test failed" }
        }
    } else {
        Write-Host "`n[4/4] smoke skipped"
    }

    Write-Host "`nDev gate PASSED."
} finally {
    Pop-Location
}
