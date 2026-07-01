#Requires -Version 5.1
<#
.SYNOPSIS
  Per-install showcase settings (port, testbed vs live) from config\showcase_host.json.
#>
function Get-CiMShowcaseInstallSettingsPath {
    param([Parameter(Mandatory)][string]$InstallRoot)
    return Join-Path ([System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))) "config\showcase_host.json"
}

function Get-CiMShowcaseInstallSettings {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [string]$RepoRoot = ""
    )
    $root = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))
    $defaults = [ordered]@{
        installRoot   = $root
        port          = 8001
        role          = 'live'
        publicAccess  = 'funnel'
        label         = 'Live'
    }

    if ($root -match '\\Client_Test(\\|$)' -or $root -match '\\Client-Test(\\|$)') {
        $defaults.port = 8002
        $defaults.role = 'testbed'
        $defaults.publicAccess = 'local'
        $defaults.label = 'Testbed'
    }

    if ($RepoRoot) {
        $deployCfgPath = Join-Path $RepoRoot "scripts\Get-CiMShowcaseDeployConfig.ps1"
        if (Test-Path -LiteralPath $deployCfgPath) {
            . $deployCfgPath
            $cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
            if ($root -ieq $cfg.showcaseInstallRoot) {
                $defaults.port = [int]$cfg.showcasePort
                $defaults.role = 'testbed'
                $defaults.publicAccess = 'local'
                $defaults.label = 'Testbed'
            } elseif ($root -ieq $cfg.showcaseLiveInstallRoot) {
                $defaults.port = [int]$cfg.showcaseLivePort
                $defaults.role = 'live'
                $defaults.publicAccess = 'funnel'
                $defaults.label = 'Live'
            }
        }
    }

    $path = Get-CiMShowcaseInstallSettingsPath -InstallRoot $root
    if (Test-Path -LiteralPath $path) {
        try {
            $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($null -ne $raw.port) {
                $parsed = 0
                if ([int]::TryParse([string]$raw.port, [ref]$parsed) -and $parsed -gt 0) {
                    $defaults.port = $parsed
                }
            }
            if ($raw.role) { $defaults.role = [string]$raw.role }
            if ($raw.publicAccess) { $defaults.publicAccess = [string]$raw.publicAccess }
            if ($raw.label) { $defaults.label = [string]$raw.label }
        } catch {
            Write-Warning "Could not parse $path - using inferred defaults."
        }
    }

    return [pscustomobject]$defaults
}

function Set-CiMShowcaseInstallSettings {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        [Parameter(Mandatory)][int]$Port,
        [ValidateSet('live', 'testbed')]
        [string]$Role = 'live',
        [ValidateSet('funnel', 'local', 'serve')]
        [string]$PublicAccess = 'funnel',
        [string]$Label = ''
    )
    $root = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))
    if (-not $Label) {
        $Label = if ($Role -eq 'testbed') { 'Testbed' } else { 'Live' }
    }
    if ($Role -eq 'testbed' -and $PublicAccess -eq 'funnel') {
        $PublicAccess = 'local'
    }
    $configDir = Join-Path $root 'config'
    if (-not (Test-Path -LiteralPath $configDir)) {
        New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    }
    $payload = [ordered]@{
        port                   = $Port
        role                   = $Role
        publicAccess           = $PublicAccess
        label                  = $Label
        yahooPrimaryPipeline   = $true
    }
    $path = Join-Path $configDir 'showcase_host.json'
    $json = ($payload | ConvertTo-Json -Depth 3)
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($path, $json + [Environment]::NewLine, $utf8NoBom)
    return $path
}

function Ensure-CiMShowcaseYahooPrimaryPipeline {
    <#
    .SYNOPSIS
      Persist yahooPrimaryPipeline=true on showcase installs (live + testbed).
      Idempotent - safe on every showcase start and after promote.
    #>
    param(
        [Parameter(Mandatory)][string]$InstallRoot
    )
    $root = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))
    $configDir = Join-Path $root 'config'
    $path = Join-Path $configDir 'showcase_host.json'
    if (-not (Test-Path -LiteralPath $configDir)) {
        New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    }

    $payload = [ordered]@{}
    if (Test-Path -LiteralPath $path) {
        try {
            $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($raw) {
                $raw.PSObject.Properties | ForEach-Object { $payload[$_.Name] = $_.Value }
            }
        } catch {
            Write-Warning "Could not parse $path - rewriting with Yahoo-primary default."
        }
    }

    if (-not $payload.port) {
        $inferred = Get-CiMShowcaseInstallSettings -InstallRoot $root
        $payload.port = [int]$inferred.port
        $payload.role = [string]$inferred.role
        $payload.publicAccess = [string]$inferred.publicAccess
        $payload.label = [string]$inferred.label
    }

    if ($payload.yahooPrimaryPipeline -eq $true) {
        return $path
    }

    $payload.yahooPrimaryPipeline = $true
    $json = ($payload | ConvertTo-Json -Depth 3)
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($path, $json + [Environment]::NewLine, $utf8NoBom)
    Write-Host ('Enabled Yahoo-primary pipeline on ' + $path) -ForegroundColor Cyan
    return $path
}
