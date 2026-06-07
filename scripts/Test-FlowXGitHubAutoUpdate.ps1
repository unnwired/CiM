#Requires -Version 5.1
<#
.SYNOPSIS
  E2E: simulate client on $ClientVersion, pull GitHub latest (1.0.4), download + validate.
#>
[CmdletBinding()]
param(
    [string]$ExportRoot = "",
    [string]$ClientVersion = "1.0.3",
    [string]$ExpectedRemoteVersion = "1.0.4",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Get-FlowXPaths.ps1")
$RepoRoot = Split-Path -Parent $ScriptDir
$fx = Get-FlowXPaths -RepoRoot $RepoRoot
if (-not $ExportRoot) { $ExportRoot = $fx.ExportRoot }

$TestRoot = Join-Path $fx.InstallerOutputDir "FlowX-autoupdate-test"
$LogFile = Join-Path $RepoRoot "runtime\logs\autoupdate-test.log"

function Log([string]$Msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Stop-TestBackend {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*--port $Port*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

Log "=== GitHub auto-update E2E (client $ClientVersion -> GitHub $ExpectedRemoteVersion) ==="

if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw "Export missing: $ExportRoot"
}

if (Test-Path -LiteralPath $TestRoot) {
    Remove-Item -LiteralPath $TestRoot -Recurse -Force
}
Log "Copy export -> $TestRoot"
Copy-Item -LiteralPath $ExportRoot -Destination $TestRoot -Recurse -Force

$verFile = Join-Path $TestRoot "version.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($verFile, $ClientVersion, $utf8NoBom)
Log "Set client version.txt = $ClientVersion"

$cacheRoot = Join-Path $env:LOCALAPPDATA "FlowX\app-cache"
if (Test-Path -LiteralPath $cacheRoot) {
    Remove-Item -LiteralPath $cacheRoot -Recurse -Force -ErrorAction SilentlyContinue
    Log "Cleared app-cache: $cacheRoot"
}

$updateDir = Join-Path $TestRoot "UPDATE"
if (Test-Path -LiteralPath $updateDir) {
    Remove-Item -LiteralPath $updateDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $updateDir | Out-Null

Log "Repair license (AutoFix) ..."
& (Join-Path $ScriptDir "Repair-FlowXLicense.ps1") -InstallRoot $TestRoot -AutoFix | Out-Null

$py = Join-Path $TestRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
    throw "Missing embedded Python: $py"
}

Stop-TestBackend
$backendLog = Join-Path $TestRoot "runtime\logs\autoupdate-backend.log"
New-Item -ItemType Directory -Force -Path (Split-Path $backendLog) | Out-Null
$proc = Start-Process -FilePath $py -ArgumentList @(
    "-m", "uvicorn", "server.flowx_bootstrap:app",
    "--host", "127.0.0.1", "--port", "$Port"
) -WorkingDirectory $TestRoot -PassThru -WindowStyle Hidden

Log "Started backend pid=$($proc.Id) on port $Port"
$deadline = (Get-Date).AddSeconds(90)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) {
        throw "Backend exited early (exit $($proc.ExitCode)). Check $backendLog"
    }
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($h.status -eq "ok") { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $healthy) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    throw "Backend health timeout. See $backendLog"
}
Log "Backend healthy"

$base = "http://127.0.0.1:$Port"
$check = Invoke-RestMethod -Uri "$base/api/update/check" -TimeoutSec 60
Log "check.available=$($check.available) current=$($check.currentVersion) source=$($check.update.source) version=$($check.update.version)"

if (-not $check.available) {
    throw "No update reported (expected $ExpectedRemoteVersion from GitHub)"
}
if ($check.update.source -ne "github") {
    throw "Expected github source, got $($check.update.source)"
}
if ($check.update.version -ne $ExpectedRemoteVersion) {
    throw "Expected remote $ExpectedRemoteVersion, got $($check.update.version)"
}

Log "POST /api/update/download ..."
try {
    $dl = Invoke-RestMethod -Method Post -Uri "$base/api/update/download" -TimeoutSec 600
} catch {
    $detail = $_.ErrorDetails.Message
    if (-not $detail) { $detail = $_ | Out-String }
    throw "Download failed: $detail"
}

Log "download.status=$($dl.status) version=$($dl.version) dir=$($dl.updatePackageDir) files=$($dl.fileCount)"

if ($dl.status -ne "downloaded") {
    throw "Expected status downloaded, got $($dl.status)"
}
if ($dl.version -ne $ExpectedRemoteVersion) {
    throw "Downloaded version mismatch: $($dl.version)"
}

$pkgDir = Join-Path $updateDir "FlowX-Update-$ExpectedRemoteVersion"
if (-not (Test-Path -LiteralPath (Join-Path $pkgDir "update.manifest.json"))) {
    throw "Missing manifest at $pkgDir"
}
if (-not (Test-Path -LiteralPath (Join-Path $pkgDir "payload"))) {
    throw "Missing payload at $pkgDir"
}

$check2 = Invoke-RestMethod -Uri "$base/api/update/check" -TimeoutSec 60
Log "post-download check: available=$($check2.available) source=$($check2.update.source) version=$($check2.update.version)"
if (-not $check2.available -or $check2.update.source -ne "local") {
    throw "After download, expected local update ready"
}

Log "POST /api/update/apply ..."
$apply = Invoke-RestMethod -Method Post -Uri "$base/api/update/apply" -Body "{}" -ContentType "application/json" -TimeoutSec 30
Log "apply.status=$($apply.status) version=$($apply.version)"

if ($apply.status -ne "apply_scheduled") {
    throw "Apply did not schedule: $($apply.status)"
}

Start-Sleep -Seconds 5
$newVer = (Get-Content -LiteralPath $verFile -Raw).Trim()
$applyDeadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $applyDeadline -and $newVer -ne $ExpectedRemoteVersion) {
    Start-Sleep -Seconds 3
    if (Test-Path -LiteralPath $verFile) {
        $newVer = (Get-Content -LiteralPath $verFile -Raw).Trim()
    }
}
Log "version.txt after apply = $newVer"

if ($newVer -ne $ExpectedRemoteVersion) {
    throw "Apply did not update version.txt (still $newVer, expected $ExpectedRemoteVersion)"
}

Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Log "=== PASS: GitHub auto-update $ClientVersion -> $ExpectedRemoteVersion ==="
exit 0
