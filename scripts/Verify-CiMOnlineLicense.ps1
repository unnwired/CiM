#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke-test Charts In Motion online license API (Cloudflare Worker).
#>
[CmdletBinding()]
param(
    [string]$LicenseApiUrl = "https://chartsinmotion.chartsinmotion.workers.dev",
    [string]$TestEmail = "",
    [string]$TestPassword = "CiM-Test-Password-123!"
)

$ErrorActionPreference = "Stop"
$base = $LicenseApiUrl.TrimEnd("/")

function Invoke-LicenseApi {
    param([string]$Method, [string]$Path, [hashtable]$Body = $null, [string]$Bearer = "")
    $headers = @{ Accept = "application/json" }
    if ($Bearer) { $headers.Authorization = "Bearer $Bearer" }
    $uri = "$base$Path"
    if ($Body) {
        $json = $Body | ConvertTo-Json -Compress
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body $json
    }
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
}

Write-Host "Health: $base/health"
$health = Invoke-LicenseApi -Method GET -Path "/health"
if ($health.status -ne "ok") { throw "Health check failed" }

if (-not $TestEmail) {
    $TestEmail = "cim-gate-{0}@example.com" -f ([Guid]::NewGuid().ToString("N").Substring(0, 8))
}

Write-Host "Signup: $TestEmail"
$signup = Invoke-LicenseApi -Method POST -Path "/auth/signup" -Body @{
    email    = $TestEmail
    password = $TestPassword
}
if (-not $signup.recovery_codes -or $signup.recovery_codes.Count -lt 1) {
    throw "Signup did not return recovery codes"
}
if ($signup.access_token) {
    throw "Signup must not return access_token (sign in registers device)"
}

$deviceId = "GATE" + ("0" * 28)
Write-Host "Login (device $deviceId)"
$login = Invoke-LicenseApi -Method POST -Path "/auth/login" -Body @{
    email       = $TestEmail
    password    = $TestPassword
    device_id   = $deviceId
    device_name = "GateTest"
    app_version = "gate"
}
if (-not $login.access_token) { throw "Login missing access_token" }

Write-Host "Status"
$status = Invoke-LicenseApi -Method GET -Path "/license/status" -Bearer $login.access_token
if (-not $status.valid) { throw "License status not valid" }

Write-Host "Refresh"
$refresh = Invoke-LicenseApi -Method POST -Path "/auth/refresh" -Body @{
    refresh_token = $login.refresh_token
    device_id     = $deviceId
}
if (-not $refresh.access_token) { throw "Refresh failed" }

Write-Host "Logout"
Invoke-LicenseApi -Method POST -Path "/auth/logout" -Body @{ refresh_token = $refresh.refresh_token } | Out-Null

Write-Host "PASS: online license API at $base"
