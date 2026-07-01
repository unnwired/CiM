#Requires -Version 5.1
param(
    [string]$InstallRoot = "",
    [int]$Port = 0,
    [switch]$KeepFunnel
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMShowcaseInstallSettings.ps1")

if ($InstallRoot -match 'Client\\scripts$') { $InstallRoot = Split-Path -Parent $InstallRoot }
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = "D:\CiM\Client"
}
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))

$repoRoot = Split-Path -Parent $ScriptDir
$settings = Get-CiMShowcaseInstallSettings -InstallRoot $InstallRoot -RepoRoot $repoRoot
if ($Port -le 0) { $Port = [int]$settings.port }

$stopShowcase = Join-Path $ScriptDir "Stop-CiMShowcase.ps1"
if (Test-Path -LiteralPath $stopShowcase) {
    & $stopShowcase -InstallRoot $InstallRoot -Port $Port
}

$clearFunnel = (-not $KeepFunnel) -and ($settings.role -eq 'live') -and ($settings.publicAccess -eq 'funnel')
if ($clearFunnel) {
    if (Get-Command tailscale -ErrorAction SilentlyContinue) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            tailscale funnel off 2>&1 | Out-Null
            tailscale serve reset 2>&1 | Out-Null
        } finally {
            $ErrorActionPreference = $prevEap
        }
        Write-Host "Tailscale Funnel/Serve cleared (live install)."
    }
} elseif (-not $KeepFunnel) {
    Write-Host "Testbed stop: left production Tailscale Funnel unchanged."
}

Write-Host "Showcase stopped ($($settings.label), port $Port)."
