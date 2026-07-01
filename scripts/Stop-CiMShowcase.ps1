#Requires -Version 5.1
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [int]$Port = 8001
)

$normalized = $InstallRoot.Trim().Trim('"').TrimEnd('\')
$InstallRoot = [System.IO.Path]::GetFullPath($normalized)
$pidFile = Join-Path $InstallRoot "runtime\logs\showcase-backend.pid"

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -like "*:$Port*" -and
        $_.CommandLine -like "*cim_bootstrap*"
    } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($oldPid -match '^\d+$') {
        Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Showcase backend stopped (port $Port). Run: tailscale funnel off"
