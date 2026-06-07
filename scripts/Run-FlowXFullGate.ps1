#Requires -Version 5.1
<#
.SYNOPSIS
  Full silent pipeline: encrypt, build installer, install to D:\FlowX, start app, verify health.
  Re-runs until PASS or max attempts. No manual patches.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "D:\FlowX",
    [string]$Version = "1.0.3",
    [int]$MaxAttempts = 3,
    [switch]$SkipRebuild
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot
$ExportRoot = $fx.ExportRoot
$VendorFile = Get-FlowXDistProfilePath -InstallRoot $ExportRoot -Paths $fx
$IsccPath = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

function Stop-FlowXProcesses {
    $stopBat = Join-Path $InstallDir "stop_flowx.bat"
    if (Test-Path -LiteralPath $stopBat) {
        Start-Process -FilePath "cmd.exe" -ArgumentList '/c', $stopBat -WorkingDirectory $InstallDir -Wait -WindowStyle Hidden | Out-Null
    }
    Get-Process -Name "electron", "FlowX", "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    foreach ($port in 8000, 3000) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    $pidFile = Join-Path $InstallDir "runtime\logs\backend.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($oldPid -match '^\d+$') {
            Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
        }
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like '*uvicorn*server.flowx_bootstrap*' -or
                $_.CommandLine -like '*uvicorn*server.server*' -or
                $_.CommandLine -like "*$InstallDir*"
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Remove-InstallDirSafe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Stop-FlowXProcesses
    for ($i = 0; $i -lt 8; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Stop-FlowXProcesses
            Start-Sleep -Seconds 2
        }
    }
    throw "Could not remove install dir (files locked): $Path"
}

function Test-BackendHealth {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 5
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Test-FrontendRoot {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $VendorFile)) {
    throw "Missing $VendorFile"
}
$secret = ([System.IO.File]::ReadAllText($VendorFile)).Trim().Trim([char]0xFEFF)

$attempt = 0
while ($attempt -lt $MaxAttempts) {
    $attempt++
    Write-Host ""
    Write-Host "========== FlowX full gate attempt $attempt / $MaxAttempts =========="
    Stop-FlowXProcesses

    & (Join-Path $ScriptDir "Sync-ExportDistributionFixes.ps1") -ExportRoot $ExportRoot -RepoRoot $RepoRoot

    if (-not $SkipRebuild) {
        $env:FLOWX_LICENSE_SECRET = $secret
        & (Join-Path $ScriptDir "encrypt_app_code.ps1") -ExportRoot $ExportRoot -LicenseSecret $secret
        & (Join-Path $ScriptDir "build_installer.ps1") -ExportRoot $ExportRoot -Version $Version -LicenseSecret $secret -IsccPath $IsccPath
    }

    $setupExe = Join-Path $RepoRoot "installer\output\FlowXSetup-$Version.exe"
    if (-not (Test-Path -LiteralPath $setupExe)) { throw "Missing installer $setupExe" }

    $py = Join-Path $ExportRoot "runtime\python\python.exe"
    Remove-Item Env:FLOWX_LICENSE_SECRET -ErrorAction SilentlyContinue
    $repoEsc = $RepoRoot.Replace("'", "''")
    $exportEsc = $ExportRoot.Replace("'", "''")
    $gen = & $py -s -c "import sys; sys.path.insert(0, r'$repoEsc'); from pathlib import Path; from server.app_code_crypto import current_machine_code, install_key_for_machine, validate_install_key; root=Path(r'$exportEsc'); mc=current_machine_code(); k=install_key_for_machine(mc, base_dir=root); assert validate_install_key(mc,k,base_dir=root); print(mc); print(k)" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Key generation failed: $gen" }
    $lines = @($gen | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
    $machineCode = $lines[0]
    $installKey = $lines[1]
    Write-Host "Machine code: $machineCode"
    Write-Host "Install key : $installKey"

    Remove-InstallDirSafe -Path $InstallDir
    $logFile = Join-Path $env:TEMP "flowx-gate-install.log"
    $installArgStr = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="' + $InstallDir + '" /INSTALLKEY=' + $installKey + ' /LOG="' + $logFile + '"'
    $p = Start-Process -FilePath $setupExe -ArgumentList $installArgStr -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        if (Test-Path -LiteralPath $logFile) { Get-Content -LiteralPath $logFile -Tail 30 }
        throw "Installer exit $($p.ExitCode)"
    }

    $installEsc = $InstallDir.Replace("'", "''")
    & $py -s -c "import sys; sys.path.insert(0, r'$installEsc'); from pathlib import Path; from server.app_code_crypto import license_valid; import sys as s; s.exit(0 if license_valid(Path(r'$installEsc')) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "license_valid failed after install" }

    $env:FLOWX_NO_PAUSE = "1"
    $startBat = Join-Path $InstallDir "start_flowx.bat"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList '/c', $startBat -WorkingDirectory $InstallDir -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(120)
    $healthOk = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-BackendHealth) { $healthOk = $true; break }
        Start-Sleep -Seconds 2
        if ($proc.HasExited -and $proc.ExitCode -ne 0) { break }
    }
    if (-not $healthOk) {
        $errLog = Join-Path $InstallDir "runtime\logs\backend-startup.err.log"
        if (Test-Path -LiteralPath $errLog) {
            Write-Host "--- backend-startup.err.log (tail) ---"
            Get-Content -LiteralPath $errLog -Tail 40
        }
        Stop-FlowXProcesses
        continue
    }

    $frontOk = Test-FrontendRoot
    $electron = Join-Path $InstallDir "desktop\node_modules\electron\dist\electron.exe"
    $electronOk = Test-Path -LiteralPath $electron
    Write-Host "Backend health : OK"
    Write-Host "Frontend /     : $(if ($frontOk) { 'OK' } else { 'WARN (health OK)' })"
    Write-Host "Electron exe   : $(if ($electronOk) { 'OK' } else { 'MISSING' })"

    if (-not $electronOk) {
        Stop-FlowXProcesses
        throw "Electron missing under $InstallDir\desktop"
    }

    Write-Host ""
    Write-Host "GATE PASS - FlowX installed at $InstallDir"
    Write-Host "Backend: http://127.0.0.1:8000/api/health"
    Write-Host "Run manually: cd $InstallDir && start_flowx.bat"
    Write-Host "Install key used: $installKey"
    exit 0
}

throw "FlowX full gate failed after $MaxAttempts attempts"
