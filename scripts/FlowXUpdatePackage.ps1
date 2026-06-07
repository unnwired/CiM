#Requires -Version 5.1
<#
.SYNOPSIS
  Locate FlowX-Update-* packages under install\UPDATE and stage them for apply.
#>

function Normalize-FlowXPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return [System.IO.Path]::GetFullPath($Path.Trim().Trim('"')).TrimEnd([char]'\')
}

function Test-UpdatePackageRoot([string]$Path) {
    if (-not $Path) { return $false }
    $manifest = Join-Path $Path "update.manifest.json"
    $payload = Join-Path $Path "payload"
    return (Test-Path -LiteralPath $manifest) -and (Test-Path -LiteralPath $payload)
}

function Get-FlowXUpdatePackageName([string]$PackageRoot) {
    $leaf = Split-Path -Leaf (Normalize-FlowXPath $PackageRoot)
    if ($leaf -match '^FlowX-Update') { return $leaf }
    $manifest = Join-Path $PackageRoot "update.manifest.json"
    if (Test-Path -LiteralPath $manifest) {
        try {
            $ver = [string]((Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).version)
            if ($ver) { return "FlowX-Update-$ver" }
        } catch { }
    }
    return "FlowX-Update"
}

function Find-FlowXUpdatePackageRoots {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallRoot
    )
    $install = Normalize-FlowXPath $InstallRoot
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $found = [System.Collections.ArrayList]@()

    function Add-Package([string]$Path) {
        $candidate = Normalize-FlowXPath $Path
        if (-not $candidate) { return }
        if ($seen.Contains($candidate)) { return }
        if (-not (Test-UpdatePackageRoot $candidate)) { return }
        [void]$seen.Add($candidate)
        [void]$found.Add($candidate)
    }

    $updateDir = Join-Path $install "UPDATE"
    if (Test-Path -LiteralPath $updateDir) {
        if (Test-UpdatePackageRoot $updateDir) {
            Add-Package $updateDir
        }
        try {
            Get-ChildItem -LiteralPath $updateDir -Directory -ErrorAction Stop | ForEach-Object {
                if ($_.Name -match '^FlowX-Update') {
                    Add-Package $_.FullName
                }
            }
        } catch { }
    }

    $roots = @($install)
    $parent = Split-Path -Parent $install
    if ($parent) { $roots += $parent }
    foreach ($base in $roots) {
        if (-not (Test-Path -LiteralPath $base)) { continue }
        try {
            Get-ChildItem -LiteralPath $base -Directory -ErrorAction Stop | ForEach-Object {
                if ($_.Name -match '^FlowX-Update') {
                    Add-Package $_.FullName
                }
            }
        } catch { }
    }

    return @($found)
}

function Find-FlowXUpdatePackageRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallRoot
    )
    $packages = Find-FlowXUpdatePackageRoots -InstallRoot $InstallRoot
    if ($packages.Count -eq 0) { return $null }

    $best = $null
    $bestVer = $null
    foreach ($pkg in $packages) {
        $manifest = Join-Path $pkg "update.manifest.json"
        try {
            $ver = [string]((Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).version)
        } catch {
            $ver = ""
        }
        if (-not $best) {
            $best = $pkg
            $bestVer = $ver
            continue
        }
        if ($ver -and $bestVer) {
            $va = ($ver -split '\.' | ForEach-Object { [int]($_ -replace '\D.*$', '0') })
            $vb = ($bestVer -split '\.' | ForEach-Object { [int]($_ -replace '\D.*$', '0') })
            $len = [Math]::Max($va.Count, $vb.Count)
            $newer = $false
            for ($i = 0; $i -lt $len; $i++) {
                $a = if ($i -lt $va.Count) { $va[$i] } else { 0 }
                $b = if ($i -lt $vb.Count) { $vb[$i] } else { 0 }
                if ($a -gt $b) { $newer = $true; break }
                if ($a -lt $b) { break }
            }
            if ($newer) {
                $best = $pkg
                $bestVer = $ver
            }
        }
    }
    return $best
}

function Test-PackageUnderInstallUpdate([string]$PackageRoot, [string]$InstallRoot) {
    $package = Normalize-FlowXPath $PackageRoot
    $updateDir = Normalize-FlowXPath (Join-Path (Normalize-FlowXPath $InstallRoot) "UPDATE")
    if (-not $updateDir) { return $false }
    return $package.StartsWith($updateDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        $package.StartsWith($updateDir + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Copy-UpdatePackageToInstall {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackageRoot,
        [Parameter(Mandatory = $true)]
        [string]$InstallRoot
    )
    $package = Normalize-FlowXPath $PackageRoot
    $install = Normalize-FlowXPath $InstallRoot
    if (-not (Test-UpdatePackageRoot $package)) {
        throw "Not a valid update package (need update.manifest.json and payload\): $package"
    }

    if (Test-PackageUnderInstallUpdate -PackageRoot $package -InstallRoot $install) {
        Write-Host "Update package is already under install\UPDATE - no copy needed."
        return $package
    }

    $folderName = Get-FlowXUpdatePackageName -PackageRoot $package
    $updateDir = Normalize-FlowXPath (Join-Path $install "UPDATE")
    $targetDir = Normalize-FlowXPath (Join-Path $updateDir $folderName)
    New-Item -ItemType Directory -Force -Path $updateDir | Out-Null

    if ($package -eq $targetDir) {
        Write-Host "Update package is already staged at $targetDir"
        return $targetDir
    }

    Write-Host "Staging update from: $package"
    Write-Host "Into: $targetDir"
    if (Test-Path -LiteralPath $targetDir) {
        Remove-Item -LiteralPath $targetDir -Recurse -Force
    }
    Copy-Item -LiteralPath $package -Destination $targetDir -Recurse -Force
    return $targetDir
}

function Get-UpdateFolderDiagnosis {
    param([string]$UpdateDir)
    if (-not $UpdateDir -or -not (Test-Path -LiteralPath $UpdateDir)) {
        return "UPDATE folder does not exist under the install."
    }
    $names = @(Get-ChildItem -LiteralPath $UpdateDir -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    if ($names.Count -eq 0) { return "UPDATE folder exists but is empty." }
    $nested = @($names | Where-Object { $_ -match '^FlowX-Update' })
    if ($nested.Count -gt 0) {
        return "UPDATE contains FlowX-Update package(s): $($nested -join ', ')"
    }
    $hasPayload = Test-Path -LiteralPath (Join-Path $UpdateDir "payload")
    $hasManifest = Test-Path -LiteralPath (Join-Path $UpdateDir "update.manifest.json")
    if ($hasPayload -and -not $hasManifest) {
        return "UPDATE has payload\ but no update.manifest.json. Run Install-Client-Update.bat from the FlowX-Update ZIP folder inside UPDATE\."
    }
    return "UPDATE contains: $($names -join ', ')"
}
