#Requires -Version 5.1
<#
.SYNOPSIS
  Verify web login records browser/OS client env in license D1 (testbed).
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8002",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }

$androidUa = @(
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
) -join ""

$testEmail = "cim-web-env-{0}@example.com" -f ([Guid]::NewGuid().ToString('N').Substring(0, 8))
$testPassword = "CiM-Web-Env-123!"
$bodyJson = @{ email = $testEmail; password = $testPassword } | ConvertTo-Json

Write-Host "=== Web client env login test ($BaseUrl) ===" -ForegroundColor Cyan
Write-Host "Test email: $testEmail"

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$headers = @{
    "User-Agent" = $androidUa
    "Content-Type" = "application/json"
}

Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/signup" -Headers $headers -Body $bodyJson -WebSession $session | Out-Null
Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/login" -Headers $headers -Body $bodyJson -WebSession $session | Out-Null
Write-Host "[OK] signup + login with Android Chrome User-Agent" -ForegroundColor Green

$licenseApiDir = Join-Path $RepoRoot "license-api"
Push-Location $licenseApiDir
try {
    $sql = "SELECT le.client_os, le.client_browser, le.client_device_type FROM login_events le JOIN users u ON u.id = le.user_id WHERE u.email = '$testEmail' ORDER BY le.created_at DESC LIMIT 1"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $raw = & npx wrangler d1 execute cim-license --remote --command $sql 2>&1 | Out-String
    $wranglerExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($wranglerExit -ne 0) {
        Write-Host "[FAIL] wrangler d1 query failed (exit $wranglerExit)" -ForegroundColor Red
        Write-Host $raw
        exit 1
    }
} finally {
    Pop-Location
}

if ($raw -notmatch '"client_os":\s*"Android"') {
    Write-Host "[FAIL] expected client_os=Android in D1 login_events" -ForegroundColor Red
    Write-Host $raw
    exit 1
}
if ($raw -notmatch '"client_browser":\s*"Chrome"') {
    Write-Host "[FAIL] expected client_browser=Chrome in D1 login_events" -ForegroundColor Red
    Write-Host $raw
    exit 1
}
if ($raw -notmatch '"client_device_type":\s*"mobile"') {
    Write-Host "[FAIL] expected client_device_type=mobile in D1 login_events" -ForegroundColor Red
    Write-Host $raw
    exit 1
}

Write-Host "[OK] D1 login_events has Android / Chrome / mobile" -ForegroundColor Green
Write-Host ""
Write-Host "WEB CLIENT ENV TEST PASS" -ForegroundColor Green
exit 0
