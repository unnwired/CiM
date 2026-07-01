#Requires -Version 5.1
<#
.SYNOPSIS
  E2E: earnings quarterly panel API contract for showcase remote vs loopback clients.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\CiM\Client_Test",
    [int]$Port = 8002
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$base = "http://127.0.0.1:$Port"

function Assert-Status {
    param([string]$Label, [int]$Expected, [object]$Response)
    $code = [int]$Response.StatusCode
    if ($code -ne $Expected) {
        throw "$Label expected HTTP $Expected, got $code body=$($Response.Content)"
    }
}

try {
    Write-Host "=== Earnings remote client E2E ($base) ===" -ForegroundColor Cyan

    $health = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 10
    if ($health.status -ne 'ok') { throw "health not ok" }
    Write-Host "[OK] health"

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $email = "cim-earnings-e2e-{0}@example.com" -f ([Guid]::NewGuid().ToString('N').Substring(0, 8))
    $password = 'CiM-E2E-Password-123!'
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/signup" -ContentType 'application/json' `
        -Body (@{ email = $email; password = $password } | ConvertTo-Json) -WebSession $session | Out-Null
    Invoke-RestMethod -Method POST -Uri "$base/api/auth/login" -ContentType 'application/json' `
        -Body (@{ email = $email; password = $password } | ConvertTo-Json) -WebSession $session | Out-Null
    $lic = Invoke-RestMethod -Uri "$base/api/license/status" -WebSession $session
    if ($lic.host_mode -ne 'web') { throw "expected host_mode=web, got $($lic.host_mode)" }
    Write-Host "[OK] signed in (host_mode=web)"

    $cache = Invoke-RestMethod -Uri "$base/api/screener-quarters/TCS?basis=consolidated" -WebSession $session
    if ($cache.status -ne 'cache' -or -not $cache.data.periods.Count) {
        throw "expected cached TCS consolidated rows, got status=$($cache.status)"
    }
    Write-Host "[OK] loopback cache GET TCS consolidated periods=$($cache.data.periods.Count)"

    try {
        Invoke-RestMethod -Uri "$base/api/screener-quarters/TCS?basis=consolidated&fetch_if_missing=true" -WebSession $session | Out-Null
        Write-Host "[OK] loopback lazy GET allowed"
    } catch {
        throw "loopback lazy GET should succeed: $($_.Exception.Message)"
    }

    $py = @"
import asyncio, httpx, os, sys
from pathlib import Path
from starlette.requests import Request
repo = Path(r'$RepoRoot')
sys.path.insert(0, str(repo / 'packages'))
os.environ['CIM_INSTALL_ROOT'] = r'$InstallRoot'
from server.server import app
from server.web_auth import session_cookie_name
from server.product_config import showcase_host_allowed_for_request
from server.showcase_host_gate import path_requires_showcase_host

base = Path(r'$InstallRoot')

def remote_req(path, method='GET', query=''):
    return Request({'type':'http','headers':[],'scheme':'http','path':path,'server':('x',8002),'client':('203.0.113.50',0)})

cache_path = '/api/screener-quarters/TCS'
assert path_requires_showcase_host(cache_path, 'GET', 'basis=consolidated') is False
assert showcase_host_allowed_for_request(remote_req(cache_path), base) is False
assert path_requires_showcase_host(cache_path, 'GET', 'basis=consolidated&fetch_if_missing=true') is False
refresh_path = '/api/screener-quarters/TCS/refresh'
assert path_requires_showcase_host(refresh_path, 'POST') is True
print('gate-remote-ok')

async def loopback_http():
    cookie_name = session_cookie_name(base)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        await c.post('/api/auth/signup', json={'email': '$email', 'password': '$password'})
        await c.post('/api/auth/login', json={'email': '$email', 'password': '$password'})
        sid = c.cookies.get(cookie_name)
        cookies = {cookie_name: sid}
        r1 = await c.get('/api/screener-quarters/TCS?basis=consolidated', cookies=cookies)
        assert r1.status_code == 200 and r1.json().get('status') == 'cache', r1.text
        r2 = await c.get('/api/screener-quarters/TCS?basis=consolidated&fetch_if_missing=true', cookies=cookies)
        assert r2.status_code == 200, r2.text
        print('loopback-http-ok')

asyncio.run(loopback_http())
"@

    $pyOut = $py | python -
    if ($LASTEXITCODE -ne 0) { throw "Python earnings gate/http test failed" }
    foreach ($line in ($pyOut -split "`n")) {
        switch ($line.Trim()) {
            'gate-remote-ok' { Write-Host "[OK] remote clients may lazy GET; POST refresh stays host-only" }
            'loopback-http-ok' { Write-Host "[OK] loopback HTTP cache + lazy fetch" }
            default { if ($line.Trim()) { Write-Host $line } }
        }
    }

    $buildJs = Get-ChildItem -Path (Join-Path $InstallRoot 'frontend\build\static\js\main.*.js') | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $buildJs) { throw "missing frontend build bundle under $InstallRoot" }
    $bundle = Get-Content -LiteralPath $buildJs.FullName -Raw
    if ($bundle -notmatch 'fetch_if_missing:!0|fetch_if_missing:true') {
        throw "deployed bundle missing screener lazy-fetch request"
    }
    Write-Host "[OK] deployed bundle contains earnings remote-client UI strings ($($buildJs.Name))"

    Write-Host ""
    Write-Host "EARNINGS REMOTE CLIENT E2E PASS" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "EARNINGS REMOTE CLIENT E2E FAIL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
