#Requires -Version 5.1
<#
.SYNOPSIS
  Start showcase on the install's configured port and open the operator sign-in page.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-CiMShowcaseInstallSettings.ps1")

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))
$repoRoot = Split-Path -Parent $ScriptDir
$settings = Get-CiMShowcaseInstallSettings -InstallRoot $InstallRoot -RepoRoot $repoRoot
$port = [int]$settings.port

$startScript = Join-Path $ScriptDir "Start-CiMShowcase.ps1"
if (-not (Test-Path -LiteralPath $startScript)) {
    throw "Missing $startScript"
}

& $startScript -InstallRoot $InstallRoot -Port $port -KeepSession
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "Start-CiMShowcase failed (exit $LASTEXITCODE)"
}

$operatorUrl = "http://127.0.0.1:$port/?operator=1"
Write-Host "Opening operator sign-in ($($settings.label), port $port)..." -ForegroundColor Green
Start-Process $operatorUrl
exit 0
