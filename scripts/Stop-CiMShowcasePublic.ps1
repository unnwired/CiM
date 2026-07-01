#Requires -Version 5.1
param(
    [string]$InstallRoot = "D:\CiM\Client"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($InstallRoot -match 'Client\\scripts$') { $InstallRoot = Split-Path -Parent $InstallRoot }
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*cloudflared*tunnel*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$stopShowcase = Join-Path $ScriptDir "Stop-CiMShowcase.ps1"
if (Test-Path -LiteralPath $stopShowcase) {
    & $stopShowcase -InstallRoot $InstallRoot -Port 8001
}

Write-Host "Public showcase stopped."
