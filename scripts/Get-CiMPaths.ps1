#Requires -Version 5.1
<#
.SYNOPSIS
  Canonical paths for Charts In Motion (CiM) distribution build.

.DESCRIPTION
  Plaintext and encrypted builds write to separate trees so they never overwrite each other:
    installer\Plaintext\  — readable export, installer, update ZIP/folder
    installer\Encrypted\  — hardened/encrypted export, installer, update ZIP/folder
#>
function Get-CiMPaths {
    param(
        [string]$RepoRoot = "",
        [ValidateSet("Plaintext", "Encrypted")]
        [string]$DistributionKind = "Encrypted"
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $installerDir = Join-Path $RepoRoot "installer"
    $outputDir = Join-Path $installerDir $DistributionKind
    [pscustomobject]@{
        RepoRoot              = $RepoRoot
        InstallerDir          = $installerDir
        DistributionKind      = $DistributionKind
        InstallerOutputDir    = $outputDir
        ExportRoot            = Join-Path $outputDir "CiM"
        VersionFile           = Join-Path $outputDir "version.txt"
        DistProfileRel        = "config\.fx-dist.cfg"
        LegacyDistProfileRel  = "config\.flowx_vendor_secret"
        GeneratedSecretPas    = Join-Path $outputDir "generated_license_secret.pas"
        LicenseValidatePas    = Join-Path $outputDir "license_validate.pas"
        LicenseValidateSource = Join-Path $installerDir "license_validate.pas"
        CiMIss                = Join-Path $installerDir "CiM.iss"
        LicenseIssuingDoc     = Join-Path $outputDir "LICENSE_ISSUING.md"
        UpdateReadme          = Join-Path $outputDir "UPDATE_README.txt"
        SetupOutputDir        = $outputDir
    }
}

function Resolve-CiMPathsForExportRoot {
    <#
    .SYNOPSIS
      Pick Plaintext vs Encrypted output paths from the export tree location.
    #>
    param(
        [Parameter(Mandatory)][string]$ExportRoot,
        [string]$RepoRoot = "",
        [ValidateSet("Plaintext", "Encrypted")]
        [string]$DefaultKind = "Encrypted"
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $full = [System.IO.Path]::GetFullPath($ExportRoot)
    $parentName = [System.IO.Path]::GetFileName([System.IO.Path]::GetDirectoryName($full))
    $kind = if ($parentName -eq "Plaintext" -or $parentName -eq "Encrypted") { $parentName } else { $DefaultKind }
    return Get-CiMPaths -RepoRoot $RepoRoot -DistributionKind $kind
}

function Get-CiMDistProfilePath {
    param(
        [Parameter(Mandatory)][string]$InstallRoot,
        $Paths
    )
    if (-not $Paths) {
        $Paths = Get-CiMPaths
    }
    $newPath = Join-Path $InstallRoot $Paths.DistProfileRel
    $legacyPath = Join-Path $InstallRoot $Paths.LegacyDistProfileRel
    if (Test-Path -LiteralPath $newPath) { return $newPath }
    if (Test-Path -LiteralPath $legacyPath) { return $legacyPath }
    return $newPath
}

function Get-CiMVendorSecretPath {
    param([string]$RepoRoot = "")
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    return Join-Path $RepoRoot "config\.build_license_secret"
}

function Resolve-CiMDistributionDbSource {
    <#
    .SYNOPSIS
      Absolute path to nse_data.db used for distribution export / Build Launcher.

    .DESCRIPTION
      Prefer an explicit -DbSource, else showcase testbed install root
      (config\showcase_deploy.json → showcaseInstallRoot, default D:\CiM\Client_Test),
      never the stale repo data\nse_data.db unless -AllowRepoFallback is set.
    #>
    param(
        [string]$RepoRoot = "",
        [string]$DbSource = "",
        [string]$ShowcaseInstallRoot = "",
        [switch]$AllowRepoFallback
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }

    function ConvertTo-CiMDbFilePath {
        param([string]$Raw)
        if ([string]::IsNullOrWhiteSpace($Raw)) { return "" }
        $p = [System.IO.Path]::GetFullPath($Raw.Trim().Trim('"').Trim("'"))
        if ($p -match '\.db$') { return $p }
        return Join-Path $p "data\nse_data.db"
    }

    if (-not [string]::IsNullOrWhiteSpace($DbSource)) {
        return ConvertTo-CiMDbFilePath -Raw $DbSource
    }
    if (-not [string]::IsNullOrWhiteSpace($ShowcaseInstallRoot)) {
        return ConvertTo-CiMDbFilePath -Raw $ShowcaseInstallRoot
    }

    $cfgScript = Join-Path $PSScriptRoot "Get-CiMShowcaseDeployConfig.ps1"
    if (Test-Path -LiteralPath $cfgScript) {
        . $cfgScript
        $cfg = Get-CiMShowcaseDeployConfig -RepoRoot $RepoRoot
        $fromTestbed = ConvertTo-CiMDbFilePath -Raw $cfg.showcaseInstallRoot
        if (Test-Path -LiteralPath $fromTestbed) {
            return $fromTestbed
        }
        if (-not $AllowRepoFallback) {
            return $fromTestbed
        }
    }

    return Join-Path $RepoRoot "data\nse_data.db"
}

function Assert-CiMDistributionDbSource {
    param(
        [Parameter(Mandatory)][string]$DbPath,
        [string]$Hint = ""
    )
    if (Test-Path -LiteralPath $DbPath) { return }
    $msg = "Distribution DB source missing: $DbPath"
    if ($Hint) { $msg = "$msg`n$Hint" }
    throw $msg
}

function Get-CiMVendorSecret {
    <#
    .SYNOPSIS
      Vendor-only license secret (build machine). Never read from client install trees.
    #>
    param(
        [string]$LicenseSecret = "",
        [string]$RepoRoot = ""
    )
    if ($LicenseSecret) {
        return $LicenseSecret.Trim().Trim([char]0xFEFF)
    }
    if ($env:CIM_LICENSE_SECRET) {
        return $env:CIM_LICENSE_SECRET.Trim().Trim([char]0xFEFF)
    }
    $buildFile = Get-CiMVendorSecretPath -RepoRoot $RepoRoot
    if (Test-Path -LiteralPath $buildFile) {
        return ([System.IO.File]::ReadAllText($buildFile)).Trim().Trim([char]0xFEFF)
    }
    return ""
}

function Get-CiMRepoVersion {
    <#
    .SYNOPSIS
      Canonical app version — always read from repo root version.txt (never stale installer output).
    #>
    param(
        [string]$RepoRoot = '',
        [string]$Fallback = '1.0.0'
    )
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $repoVer = Join-Path $RepoRoot 'version.txt'
    if (-not (Test-Path -LiteralPath $repoVer)) { return $Fallback }
    $content = (Get-Content -LiteralPath $repoVer -Raw).Trim().Trim([char]0xFEFF)
    if ($content) { return $content }
    return $Fallback
}

function Write-CiMVersionFiles {
    param(
        [Parameter(Mandatory)][string]$Version,
        [Parameter(Mandatory)][string]$ExportRoot,
        [Parameter(Mandatory)]$Paths
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    foreach ($target in @(
        (Join-Path $ExportRoot 'version.txt'),
        $Paths.VersionFile
    )) {
        $dir = Split-Path -Parent $target
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        [System.IO.File]::WriteAllText($target, $Version, $utf8NoBom)
    }
}

function Sync-CiMRepoVersionToInstallRoot {
    <#
    .SYNOPSIS
      Mirror repo root version.txt into an install/export tree (desktop or browser showcase).
      Canonical source is always repo version.txt — never edit the install copy by hand.
    #>
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [Parameter(Mandatory)][string]$InstallRoot
    )
    $version = Get-CiMRepoVersion -RepoRoot $RepoRoot
    $target = Join-Path $InstallRoot 'version.txt'
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    $dir = Split-Path -Parent $target
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    [System.IO.File]::WriteAllText($target, $version, $utf8NoBom)
    return $version
}

function Test-CiMOnlineOnlyInstall {
    <#
    .SYNOPSIS
      True when the install uses online sign-in (no offline data\.cim-license install key).
    #>
    param(
        [Parameter(Mandatory)][string]$InstallRoot
    )
    $marker = Join-Path $InstallRoot "config\.cim-online-only"
    if (Test-Path -LiteralPath $marker) { return $true }
    $prodPath = Join-Path $InstallRoot "config\product.json"
    if (-not (Test-Path -LiteralPath $prodPath)) { return $false }
    try {
        $prod = Get-Content -LiteralPath $prodPath -Raw -Encoding UTF8 | ConvertFrom-Json
        return [bool]$prod.onlineOnlyActivation
    } catch {
        return $false
    }
}

function Assert-LastExitSuccess {
    <#
    .SYNOPSIS
      Treat unset LASTEXITCODE as success (pure PowerShell child scripts often leave it empty).
    #>
    param([string]$Step = 'Previous command')
    $code = $LASTEXITCODE
    if ($null -eq $code -or $code -eq 0) { return }
    throw "$Step failed (exit $code)"
}

function Get-CiMPackagePaths {
    <#
    .SYNOPSIS
      Canonical dev-repo package locations (browser, server, desktop source trees).
    #>
    param([string]$RepoRoot = "")
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    }
    $packagesRoot = Join-Path $RepoRoot "packages"
    $browserRoot = Join-Path $packagesRoot "browser"
    [pscustomobject]@{
        RepoRoot      = $RepoRoot
        PackagesRoot  = $packagesRoot
        BrowserRoot   = $browserRoot
        BrowserBuild  = Join-Path $browserRoot "build"
        BrowserAuth   = Join-Path $browserRoot "auth"
        BrowserSrc    = Join-Path $browserRoot "src"
        BrowserPublic = Join-Path $browserRoot "public"
        ServerRoot    = Join-Path $packagesRoot "server"
        DesktopRoot   = Join-Path $packagesRoot "desktop"
    }
}

function Invoke-CiMBrowserProductionBuild {
    <#
    .SYNOPSIS
      Run npm production build in packages\browser with optional distribution / secure QR flags.
    #>
    param(
        [Parameter(Mandatory)][string]$BrowserRoot,
        [switch]$DistributionMode,
        [switch]$SupportQrSecure,
        [switch]$RemoveLooseSupportQr
    )
    if (-not (Test-Path -LiteralPath (Join-Path $BrowserRoot "package.json"))) {
        throw "Missing browser package.json at $BrowserRoot"
    }
    Push-Location $BrowserRoot
    try {
        $env:GENERATE_SOURCEMAP = "false"
        if ($DistributionMode) {
            $env:REACT_APP_EXPORT_MODE = "distribution"
        } else {
            Remove-Item Env:REACT_APP_EXPORT_MODE -ErrorAction SilentlyContinue
        }
        if ($SupportQrSecure) {
            $env:REACT_APP_SUPPORT_QR_SECURE = "true"
        } else {
            Remove-Item Env:REACT_APP_SUPPORT_QR_SECURE -ErrorAction SilentlyContinue
        }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
        $buildRoot = Join-Path $BrowserRoot "build"
        if ($DistributionMode) {
            $marker = Join-Path $buildRoot ".cim-distribution-build"
            $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
            Set-Content -LiteralPath $marker -Value "distribution`n$stamp" -Encoding UTF8
        } elseif (Test-Path -LiteralPath (Join-Path $buildRoot ".cim-distribution-build")) {
            Remove-Item -LiteralPath (Join-Path $buildRoot ".cim-distribution-build") -Force
        }
        Get-ChildItem -LiteralPath $buildRoot -Recurse -File -Filter "*.map" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
        if ($RemoveLooseSupportQr) {
            foreach ($name in @("support-upi-qr.png", "support-upi-qr.jpg", "support-upi-qr.jpeg")) {
                $p = Join-Path $buildRoot $name
                if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
            }
            $staticDir = Join-Path $buildRoot "static\media"
            if (Test-Path -LiteralPath $staticDir) {
                Get-ChildItem -LiteralPath $staticDir -File -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match 'support-upi-qr' } |
                    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
            }
        }
    } finally {
        Remove-Item Env:REACT_APP_EXPORT_MODE -ErrorAction SilentlyContinue
        Remove-Item Env:REACT_APP_SUPPORT_QR_SECURE -ErrorAction SilentlyContinue
        Pop-Location
    }
}

function Set-CiMPythonPackagePath {
    <#
    .SYNOPSIS
      Prepend packages\ to PYTHONPATH so `import server` works without repo-root junctions.
      Note: embedded runtime\python ignores PYTHONPATH — use runtime\run_uvicorn.py for uvicorn.
    #>
    param([Parameter(Mandatory)][string]$RepoRoot)
    $pkg = Get-CiMPackagePaths -RepoRoot $RepoRoot
    $existing = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
    if ($existing) {
        $env:PYTHONPATH = "$($pkg.PackagesRoot);$existing"
    } else {
        $env:PYTHONPATH = $pkg.PackagesRoot
    }
}

function Test-CiMDevPackagesLayout {
    param([Parameter(Mandatory)][string]$RepoRoot)
    $pkgServer = Join-Path $RepoRoot "packages\server\server.py"
    $legacyServer = Join-Path $RepoRoot "server\server.py"
    return (Test-Path -LiteralPath $pkgServer) -and -not (Test-Path -LiteralPath $legacyServer)
}

function Test-CiMInstallHasServerBootstrap {
    param([Parameter(Mandatory)][string]$Root)
    $full = [System.IO.Path]::GetFullPath($Root.Trim().TrimEnd('\'))
    if (Test-Path -LiteralPath (Join-Path $full "server\cim_bootstrap.py")) { return $true }
    $pkgBootstrap = Join-Path $full "packages\server\cim_bootstrap.py"
    if ((Test-Path -LiteralPath $pkgBootstrap) -and (Test-Path -LiteralPath (Join-Path $full "db_sqlite.py"))) {
        return $true
    }
    return $false
}

function Get-CiMUvicornPythonArgs {
    <#
    .SYNOPSIS
      Argument list for embedded Python to run uvicorn (uses run_uvicorn.py when present).
    #>
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [Parameter(Mandatory)][string]$AppModule,
        [string[]]$ExtraArgs = @()
    )
    $launcher = Join-Path $RepoRoot "runtime\run_uvicorn.py"
    # Start-Process -ArgumentList joins args with spaces and does not quote;
    # paths under e.g. "D:\Programs\NSE Pulse\..." must be quoted or Python sees "D:\Programs\NSE".
    function Quote-CiMProcArg([string]$Value) {
        if ($null -eq $Value) { return '""' }
        if ($Value -match '[\s"]') {
            return ('"{0}"' -f ($Value -replace '"', '\"'))
        }
        return $Value
    }
    if (Test-Path -LiteralPath $launcher) {
        $args = @("-s", (Quote-CiMProcArg $launcher), $AppModule)
    } else {
        $args = @("-s", "-m", "uvicorn", $AppModule)
    }
    if ($ExtraArgs -and $ExtraArgs.Count -gt 0) {
        foreach ($a in $ExtraArgs) {
            $args += ,(Quote-CiMProcArg $a)
        }
    }
    return $args
}

# Back-compat aliases (remove after downstream scripts stop referencing FlowX names)
function Get-FlowXPaths { Get-CiMPaths @args }
function Get-FlowXDistProfilePath { Get-CiMDistProfilePath @args }
