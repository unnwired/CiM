#Requires -Version 5.1
<#
.SYNOPSIS
  Full silent pipeline: encrypt, build installer, install to D:\CiM, start app, verify health.
  Re-runs until PASS or max attempts. No manual patches.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "D:\CiM",
    [string]$Version = "1.0.3",
    [int]$MaxAttempts = 3,
    [switch]$SkipRebuild
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind Encrypted
$pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot
$ExportRoot = $fx.ExportRoot
$IsccPath = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

function Stop-CiMProcesses {
    $stopBat = Join-Path $InstallDir "stop_cim.bat"
    if (Test-Path -LiteralPath $stopBat) {
        Start-Process -FilePath "cmd.exe" -ArgumentList '/c', $stopBat -WorkingDirectory $InstallDir -Wait -WindowStyle Hidden | Out-Null
    }
    Get-Process -Name "electron", "CiM", "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
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
                $_.CommandLine -like '*uvicorn*server.cim_bootstrap*' -or
                $_.CommandLine -like '*uvicorn*server.server*' -or
                ($_.Name -match '^(python|electron)(\.exe)?$' -and $_.CommandLine -like "*$InstallDir*")
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Remove-InstallDirSafe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Stop-CiMProcesses
    for ($i = 0; $i -lt 8; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Stop-CiMProcesses
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

$secret = Get-CiMVendorSecret -RepoRoot $RepoRoot
if (-not $secret) {
    throw "Missing vendor secret (config\.build_license_secret or CIM_LICENSE_SECRET)."
}

$attempt = 0
while ($attempt -lt $MaxAttempts) {
    $attempt++
    Write-Host ""
    Write-Host "========== CiM full gate attempt $attempt / $MaxAttempts =========="
    Stop-CiMProcesses

    if (-not $SkipRebuild) {
        Write-Host "Building browser package (npm run build)..."
        Push-Location $pkg.BrowserRoot
        try {
            & npm run build
            if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
        } finally {
            Pop-Location
        }
    }

    & (Join-Path $ScriptDir "Sync-ExportDistributionFixes.ps1") -ExportRoot $ExportRoot -RepoRoot $RepoRoot

    if (-not $SkipRebuild) {
        $env:CIM_LICENSE_SECRET = $secret
        & (Join-Path $ScriptDir "encrypt_app_code.ps1") -ExportRoot $ExportRoot -LicenseSecret $secret
        & (Join-Path $ScriptDir "build_installer.ps1") -ExportRoot $ExportRoot -Version $Version -LicenseSecret $secret -IsccPath $IsccPath
    }

    $setupExe = Join-Path $fx.SetupOutputDir "CiMSetup-$Version.exe"
    if (-not (Test-Path -LiteralPath $setupExe)) { throw "Missing installer $setupExe" }

    $py = Join-Path $ExportRoot "runtime\python\python.exe"
    Remove-Item Env:CIM_LICENSE_SECRET -ErrorAction SilentlyContinue
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
    $logFile = Join-Path $env:TEMP "cim-gate-install.log"
    $installArgStr = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="' + $InstallDir + '" /INSTALLKEY=' + $installKey + ' /LOG="' + $logFile + '"'
    $p = Start-Process -FilePath $setupExe -ArgumentList $installArgStr -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        if (Test-Path -LiteralPath $logFile) { Get-Content -LiteralPath $logFile -Tail 30 }
        throw "Installer exit $($p.ExitCode)"
    }

    $installEsc = $InstallDir.Replace("'", "''")
    & $py -s -c "import sys; sys.path.insert(0, r'$installEsc'); from pathlib import Path; from server.app_code_crypto import license_valid; import sys as s; s.exit(0 if license_valid(Path(r'$installEsc')) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "license_valid failed after install" }

    $env:CIM_NO_PAUSE = "1"
    $startBat = Join-Path $InstallDir "start_cim.bat"
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
        Stop-CiMProcesses
        continue
    }

    Write-Host "Running packaged smoke (JS bundle + /api/stocks)..."
    & (Join-Path $ScriptDir "Test-CiMPackagedSmoke.ps1") -InstallRoot $InstallDir
    if ($LASTEXITCODE -ne 0) {
        Stop-CiMProcesses
        throw "Packaged smoke test failed - would ship blank Electron shell or empty data"
    }

    $frontOk = Test-FrontendRoot
    $electron = Join-Path $InstallDir "desktop\node_modules\electron\dist\electron.exe"
    $electronOk = Test-Path -LiteralPath $electron
    Write-Host "Backend health : OK"
    Write-Host "Frontend /     : $(if ($frontOk) { 'OK' } else { 'WARN (health OK)' })"
    Write-Host "Electron exe   : $(if ($electronOk) { 'OK' } else { 'MISSING' })"

    if (-not $electronOk) {
        Stop-CiMProcesses
        throw "Electron missing under $InstallDir\desktop"
    }

    Write-Host ""
    Write-Host "GATE PASS - Charts In Motion installed at $InstallDir"
    Write-Host "Backend: http://127.0.0.1:8000/api/health"
    Write-Host "Run manually: cd $InstallDir && start_cim.bat"
    Write-Host "Install key used: $installKey"
    exit 0
}

throw "Charts In Motion full gate failed after $MaxAttempts attempts"
