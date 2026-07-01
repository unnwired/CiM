#Requires -Version 5.1
<#
.SYNOPSIS
  Verify operator auth deploy on a running showcase (127.0.0.1:8001).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Client",
    [string]$BaseUrl = "http://127.0.0.1:8001",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $ScriptDir }
. (Join-Path $ScriptDir "Get-CiMPaths.ps1")

$fail = 0
$repoVersion = Get-CiMRepoVersion -RepoRoot $RepoRoot

function Assert-Ok {
    param([string]$Name, [bool]$Cond, [string]$Detail = "")
    if ($Cond) {
        Write-Host "[OK] $Name" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Name $Detail" -ForegroundColor Red
        $script:fail++
    }
}

function Get-InstallVersionText {
    param([string]$Root)
    $path = Join-Path $Root 'version.txt'
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    return (Get-Content -LiteralPath $path -Raw).Trim().Trim([char]0xFEFF)
}

Write-Host "=== Operator deploy check ($BaseUrl) ===" -ForegroundColor Cyan
Write-Host "Canonical repo version: $repoVersion" -ForegroundColor DarkGray

$installVersion = Get-InstallVersionText -Root $InstallRoot
Assert-Ok "showcase version.txt matches repo" ($installVersion -eq $repoVersion) "(install=$installVersion repo=$repoVersion)"

$authPage = Invoke-WebRequest -Uri "$BaseUrl/?operator=1" -UseBasicParsing -TimeoutSec 15
Assert-Ok "auth page at /?operator=1" ($authPage.Content -match 'Sign in')
Assert-Ok "operator-banner in served auth HTML" ($authPage.Content -match 'operator-banner')
Assert-Ok "auth.js script referenced" ($authPage.Content -match 'auth-static/auth\.js')
Assert-Ok "auth-status-panel in served auth HTML" ($authPage.Content -match 'auth-status-panel')
Assert-Ok "Server Status label in auth HTML" ($authPage.Content -match 'Server Status:')
Assert-Ok "Users Online label in auth HTML" ($authPage.Content -match 'Users Online:')

$social = Invoke-RestMethod -Uri "$BaseUrl/api/auth/social-proof" -TimeoutSec 15
Assert-Ok "social-proof returns users_online" ($null -ne $social.users_online -and $social.users_online -ge 2)

$authJs = (Invoke-WebRequest -Uri "$BaseUrl/auth-static/auth.js" -UseBasicParsing -TimeoutSec 15).Content
Assert-Ok "auth.js has OPERATOR_SESSION_KEY" ($authJs -match 'cim\.operator\.session')
Assert-Ok "auth.js has applyOperatorSignInShell" ($authJs -match 'applyOperatorSignInShell')
Assert-Ok "auth.js has auth status polling" ($authJs -match 'startAuthStatusPolling')
Assert-Ok "auth.js appEntryUrl preserves operator=1" ($authJs -match 'operator=1')

$nested = Join-Path $InstallRoot "frontend\auth\auth"
Assert-Ok "no nested frontend/auth/auth on disk" (-not (Test-Path -LiteralPath $nested))

$manifestPath = Join-Path $InstallRoot "frontend\build\asset-manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$mainRel = $manifest.files.'main.js'.TrimStart('/')
$mainJs = Join-Path $InstallRoot "frontend\build\$mainRel"
$bundle = Get-Content -LiteralPath $mainJs -Raw
Assert-Ok "bundle has Refresh prices (web client path)" ($bundle -match 'Refresh prices')
Assert-Ok "bundle has Admin mode active copy" ($bundle -match 'Admin mode active')
Assert-Ok "distribution profile in bundle" ($bundle -match 'cim\.chart\.prefs\.v1')

# 6. Operator login flow: session cookie + post-login app shell (simulates Admin-Showcase.bat path)
try {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $null = Invoke-WebRequest -Uri "$BaseUrl/?operator=1" -UseBasicParsing -WebSession $session -TimeoutSec 15
    $testEmail = "cim-op-check-{0}@example.com" -f ([Guid]::NewGuid().ToString('N').Substring(0, 8))
    $testPassword = "CiM-Op-Check-123!"
    $bodyJson = @{ email = $testEmail; password = $testPassword } | ConvertTo-Json
    Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/signup" -ContentType "application/json" -Body $bodyJson -WebSession $session | Out-Null
    Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/login" -ContentType "application/json" -Body $bodyJson -WebSession $session | Out-Null
    $st = Invoke-RestMethod -Uri "$BaseUrl/api/license/status" -WebSession $session -TimeoutSec 15
    Assert-Ok "operator flow login valid" ($st.valid -eq $true)
    Assert-Ok "operator flow host_mode=web" ($st.host_mode -eq 'web')
    Assert-Ok "operator flow is_showcase_host=true" ($st.is_showcase_host -eq $true)
    $settings = Invoke-RestMethod -Uri "$BaseUrl/api/update/settings" -WebSession $session -TimeoutSec 15
    $apiVersion = [string]$settings.currentVersion
    Assert-Ok "API currentVersion matches repo" ($apiVersion -eq $repoVersion) "(api=$apiVersion repo=$repoVersion)"
    Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/complete" -WebSession $session -TimeoutSec 15 | Out-Null
    $app = Invoke-WebRequest -Uri "$BaseUrl/?operator=1&_cim=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())" -UseBasicParsing -WebSession $session -TimeoutSec 15
    Assert-Ok "operator flow loads React app shell" ($app.Content -match 'id="root"')
    $mainJsUrl = $manifest.files.'main.js'
    Assert-Ok "operator flow serves main bundle" ($app.Content -match [regex]::Escape($mainJsUrl.TrimStart('/')))
} catch {
    Assert-Ok "operator login flow" $false $_.Exception.Message
}

if ($fail -eq 0) {
    Write-Host ""
    Write-Host "OPERATOR DEPLOY CHECK PASS" -ForegroundColor Green
    exit 0
}
Write-Host ""
Write-Host "OPERATOR DEPLOY CHECK FAIL ($fail)" -ForegroundColor Red
exit 1
