#Requires -Version 5.1
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [int]$Port = 8001
)

$normalized = $InstallRoot.Trim().Trim('"').TrimEnd('\')
$InstallRoot = [System.IO.Path]::GetFullPath($normalized)
$pidFile = Join-Path $InstallRoot "runtime\logs\showcase-backend.pid"

$stopIds = New-Object 'System.Collections.Generic.HashSet[int]'

# Match Start-CiMShowcase stop logic: cim_bootstrap / run_uvicorn on this port.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -like "*:$Port*" -and
        (
            $_.CommandLine -like "*cim_bootstrap*" -or
            $_.CommandLine -like "*run_uvicorn.py*" -or
            $_.CommandLine -like "*uvicorn*server*"
        )
    } |
    ForEach-Object { [void]$stopIds.Add([int]$_.ProcessId) }

if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($oldPid -match '^\d+$') { [void]$stopIds.Add([int]$oldPid) }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

try {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { [void]$stopIds.Add([int]$_.OwningProcess) }
} catch { }

foreach ($procId in @($stopIds)) {
    if ($procId -le 0) { continue }
    # Also stop child python processes of the listener (orphans inflate RAM).
    try {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ParentProcessId -eq $procId } |
            ForEach-Object { [void]$stopIds.Add([int]$_.ProcessId) }
    } catch { }
}

foreach ($procId in $stopIds) {
    if ($procId -le 0) { continue }
    Write-Host "Stopping PID $procId"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    # Avoid stderr / non-zero exit from taskkill aborting callers with $ErrorActionPreference=Stop
    cmd /c "taskkill /F /PID $procId /T >nul 2>&1 & exit /b 0" | Out-Null
}

Start-Sleep -Seconds 1
try {
    $left = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($left.Count -gt 0) {
        Write-Host "WARNING: Port $Port still listening on PID(s) $($left -join ', '). Stop as Administrator if Access Denied." -ForegroundColor Yellow
    }
} catch { }

Write-Host "Showcase backend stopped (port $Port). Run: tailscale funnel off"
exit 0
