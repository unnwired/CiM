#Requires -Version 5.1
<#
.SYNOPSIS
  Find FlowX install root(s) from an update package path, script location, or cwd.
#>

function Test-FlowXInstall([string]$Path) {
    if (-not $Path) { return $false }
    $bat = Join-Path $Path "start_flowx.bat"
    if (Test-Path -LiteralPath $bat) {
        $db = Join-Path $Path "data\nse_data.db"
        if (Test-Path -LiteralPath $db) { return $true }
        $serverOk = (Test-Path -LiteralPath (Join-Path $Path "server\flowx_bootstrap.py")) -or
            (Test-Path -LiteralPath (Join-Path $Path "server\server.pyc.enc")) -or
            (Test-Path -LiteralPath (Join-Path $Path "server\server.py"))
        if ($serverOk) { return $true }
    }
    # UPDATE folder under install is enough for client update apply (bat may be restored by the package).
    if (Test-Path -LiteralPath (Join-Path $Path "UPDATE")) { return $true }
    $dbOnly = Join-Path $Path "data\nse_data.db"
    if (Test-Path -LiteralPath $dbOnly) { return $true }
    return $false
}

function Test-FlowXUpdatePackageLeaf([string]$Leaf) {
    return $Leaf -match '^FlowX-Update'
}

function Resolve-FlowXPath([string]$Path) {
    if (-not $Path) { return $null }
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return (Resolve-Path -LiteralPath $Path).Path.TrimEnd('\')
    } catch {
        return $null
    }
}

function Get-FlowXInstallRootFromPath([string]$FromPath) {
    <#
      Structural install detection â€” no typing paths.
      Primary layout: <install>\UPDATE\FlowX-Update-*\Install-Client-Update.bat
    #>
    $resolved = Resolve-FlowXPath $FromPath
    if (-not $resolved) { return $null }

    if ((Split-Path -Leaf $resolved) -ieq 'UPDATE') {
        return Resolve-FlowXPath (Split-Path -Parent $resolved)
    }

    if (Test-FlowXUpdatePackageLeaf (Split-Path -Leaf $resolved)) {
        $parent = Split-Path -Parent $resolved
        if ($parent -and (Split-Path -Leaf $parent) -ieq 'UPDATE') {
            return Resolve-FlowXPath (Split-Path -Parent $parent)
        }
    }

    $d = $resolved
    for ($i = 0; $i -lt 12; $i++) {
        $leaf = Split-Path -Leaf $d
        if ($leaf -ieq 'UPDATE') {
            return Resolve-FlowXPath (Split-Path -Parent $d)
        }
        $p = Split-Path -Parent $d
        if (-not $p -or $p -eq $d) { break }
        $d = $p
    }

    return $null
}

function Get-FlowXInstallFromUpdateFolder([string]$FromPath) {
    return Get-FlowXInstallRootFromPath -FromPath $FromPath
}

function Find-FlowXInstallCandidates {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FromPath
    )

    $start = Resolve-FlowXPath $FromPath
    if (-not $start) { return @() }

    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $list = [System.Collections.Generic.List[object]]::new()

    function Add-CandidateRaw([string]$Path, [int]$Priority, [string]$Reason, [switch]$SkipValidation) {
        $resolved = Resolve-FlowXPath $Path
        if (-not $resolved) { return }
        if (-not $SkipValidation -and -not (Test-FlowXInstall $resolved)) { return }
        if ($seen.Add($resolved)) {
            $list.Add([pscustomobject]@{ Path = $resolved; Priority = $Priority; Reason = $Reason })
        }
    }

    function Add-Candidate([string]$Path, [int]$Priority, [string]$Reason) {
        Add-CandidateRaw -Path $Path -Priority $Priority -Reason $Reason
    }

    $structural = Get-FlowXInstallRootFromPath -FromPath $start
    if ($structural) {
        Add-CandidateRaw $structural 0 "FlowX install (UPDATE folder layout)" -SkipValidation
    }

    Add-Candidate $start 5 "path passed to locator"

    if ((Split-Path -Leaf $start) -ieq 'UPDATE') {
        Add-CandidateRaw (Split-Path -Parent $start) 1 "parent of UPDATE folder" -SkipValidation
    }

    if (Test-FlowXUpdatePackageLeaf (Split-Path -Leaf $start)) {
        $parent = Split-Path -Parent $start
        if ($parent -and (Split-Path -Leaf $parent) -ieq 'UPDATE') {
            Add-CandidateRaw (Split-Path -Parent $parent) 1 "install folder containing UPDATE\FlowX-Update" -SkipValidation
        } else {
            Add-CandidateRaw $parent 2 "parent of FlowX-Update package" -SkipValidation
        }
    }

    $d = $start
    for ($i = 0; $i -lt 12; $i++) {
        $leaf = Split-Path -Leaf $d
        if ($leaf -ieq 'UPDATE') {
            Add-CandidateRaw (Split-Path -Parent $d) (3 + $i) "install folder containing UPDATE" -SkipValidation
        }
        $p = Split-Path -Parent $d
        if (-not $p -or $p -eq $d) { break }
        Add-Candidate $p (10 + $i) "folder above update package"
        $d = $p
    }

    $parent = Split-Path -Parent $start
    if ($parent -and (Test-Path -LiteralPath $parent)) {
        Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.Name
            if ($name -match '^FlowX-Update') { return }
            if ($name -ieq 'UPDATE') { return }
            if ($_.FullName -eq $start) { return }
            Add-Candidate $_.FullName 8 "FlowX folder next to update package ($name)"
        }
    }

    try {
        $cwd = (Get-Location).Path
        $d = $cwd
        for ($i = 0; $i -lt 8; $i++) {
            Add-Candidate $d (30 + $i) "current folder"
            $p = Split-Path -Parent $d
            if (-not $p -or $p -eq $d) { break }
            $d = $p
        }
    } catch { }

    foreach ($guess in @(
            (Join-Path ${env:ProgramFiles} "FlowX"),
            (Join-Path ${env:ProgramFiles(x86)} "FlowX"),
            (Join-Path $env:LOCALAPPDATA "FlowX")
        )) {
        Add-Candidate $guess 50 "default install location"
    }

    return @($list | Sort-Object Priority, Path)
}

function Select-FlowXInstallRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FromPath,
        [string]$PreferPath = "",
        [switch]$AllowPrompt
    )

    if ($PreferPath) {
        $hint = Resolve-FlowXPath $PreferPath.Trim('"')
        if ($hint) {
            if (Test-FlowXInstall $hint) { return $hint }
            $structural = Get-FlowXInstallRootFromPath -FromPath $hint
            if ($structural) { return $structural }
        }
        throw "Not a valid FlowX install: $PreferPath"
    }

    $structural = Get-FlowXInstallRootFromPath -FromPath $FromPath
    if ($structural) {
        return $structural
    }

    $candidates = Find-FlowXInstallCandidates -FromPath $FromPath
    if ($candidates.Count -eq 1) {
        return $candidates[0].Path
    }
    if ($candidates.Count -gt 1) {
        Write-Host ""
        Write-Host "More than one FlowX install was found:"
        for ($i = 0; $i -lt $candidates.Count; $i++) {
            $c = $candidates[$i]
            Write-Host "  [$($i + 1)] $($c.Path)  - $($c.Reason)"
        }
        if ($AllowPrompt) {
            $pick = Read-Host "Enter number (1-$($candidates.Count))"
            $idx = 0
            if ([int]::TryParse($pick, [ref]$idx)) {
                $idx = $idx - 1
                if ($idx -ge 0 -and $idx -lt $candidates.Count) {
                    return $candidates[$idx].Path
                }
            }
            throw "Invalid selection."
        }
        return $candidates[0].Path
    }

    if ($AllowPrompt) {
        $typed = Read-Host "Could not auto-detect FlowX. Enter full path to FlowX install folder"
        $hint = Resolve-FlowXPath $typed.Trim('"')
        if ($hint -and (Test-FlowXInstall $hint)) {
            return $hint
        }
        $fromTyped = Get-FlowXInstallRootFromPath -FromPath $hint
        if ($fromTyped) { return $fromTyped }
    }

    return $null
}
