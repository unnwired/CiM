param(
    [string]$SourceRoot = "D:\Programs\NSE Pulse\Claude Ai",
    [string]$ExportRoot = "",
    [ValidateSet("standard","distribution")]
    [string]$Mode = "standard",
    [switch]$KeepExisting,
    [switch]$SkipFrontendBuild,
    [switch]$SkipEmbeddedPython,
    [switch]$RefreshEmbeddedPython,
    [switch]$SkipWheelhouse,
    [switch]$Obfuscate,
    [switch]$ObfuscateFrontend,
    [switch]$ObfuscatePython,
    [switch]$HardenAll,
    [ValidateSet("none","bytecode","pyarmor")]
    [string]$PythonHardening = "none"
)

$ErrorActionPreference = "Stop"

if (-not $ExportRoot) {
    $ExportRoot = Join-Path $SourceRoot "installer\output\CiM"
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Remove-DirectorySafe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $true
    }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return -not (Test-Path -LiteralPath $Path)
    } catch {
        # Locked .pyd/.dll (Charts In Motion backend running) — try rename-aside then delete later.
        $aside = "$Path.delete.$([guid]::NewGuid().ToString('N').Substring(0, 8))"
        try {
            Rename-Item -LiteralPath $Path -NewName (Split-Path -Leaf $aside) -ErrorAction Stop
            Remove-Item -LiteralPath $aside -Recurse -Force -ErrorAction SilentlyContinue | Out-Null
            return -not (Test-Path -LiteralPath $Path)
        } catch {
            return $false
        }
    }
}

function Copy-IfExists {
    param(
        [string]$From,
        [string]$To
    )
    if (Test-Path -LiteralPath $From) {
        Ensure-Dir -Path (Split-Path -Parent $To)
        Copy-Item -LiteralPath $From -Destination $To -Force
    }
}

function Copy-TreeIfExists {
    param(
        [string]$From,
        [string]$To
    )
    if (Test-Path -LiteralPath $From) {
        Ensure-Dir -Path (Split-Path -Parent $To)
        Copy-Item -LiteralPath $From -Destination $To -Recurse -Force
    }
}

function Ensure-Command {
    param(
        [string]$Name,
        [string]$HelpMessage
    )
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Required command '$Name' not found. $HelpMessage"
    }
}

function Get-ObfuscatedServerRoot {
    param([string]$ServerOutputRoot)
    $candidateA = Join-Path $ServerOutputRoot "server"
    if (Test-Path -LiteralPath $candidateA) { return $candidateA }
    return $ServerOutputRoot
}

function Invoke-FrontendObfuscation {
    param([string]$ExportRoot)
    $buildJsDir = Join-Path $ExportRoot "frontend\build\static\js"
    if (-not (Test-Path -LiteralPath $buildJsDir)) {
        throw "Frontend build JS directory not found for obfuscation: $buildJsDir"
    }
    Ensure-Command -Name "npx" -HelpMessage "Install Node.js/npm (npx is required for frontend obfuscation)."
    $jsFiles = Get-ChildItem -LiteralPath $buildJsDir -Filter "*.js" -File -ErrorAction SilentlyContinue
    if (-not $jsFiles -or $jsFiles.Count -eq 0) {
        throw "No JS bundles found to obfuscate in: $buildJsDir"
    }
    $tmpDir = Join-Path $buildJsDir "__obf_tmp"
    if (Test-Path -LiteralPath $tmpDir) {
        Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Ensure-Dir -Path $tmpDir
    Write-Host "Obfuscating frontend JS bundles..."
    foreach ($js in $jsFiles) {
        # self-defending breaks Electron/Chromium; keep globals for CRA bundles.
        & npx javascript-obfuscator $js.FullName --output $tmpDir --compact true --self-defending false --string-array true --string-array-threshold 0.75 --rename-globals false
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend obfuscation failed for: $($js.Name)"
        }
        $obfFile = Join-Path $tmpDir $js.Name
        if (-not (Test-Path -LiteralPath $obfFile)) {
            throw "Expected obfuscated output not found: $obfFile"
        }
        Copy-Item -LiteralPath $obfFile -Destination $js.FullName -Force
    }
    Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

function Invoke-GenerateSupportQrPayload {
    param([string]$SourceRoot)
    $generator = Join-Path $SourceRoot "scripts\Generate-SupportQrPayload.ps1"
    $image = Join-Path $SourceRoot "frontend\src\assets\support-upi-qr.png"
    $out = Join-Path $SourceRoot "frontend\src\support\supportQrPayload.generated.js"
    if (-not (Test-Path -LiteralPath $generator)) {
        throw "Support QR generator script missing: $generator"
    }
    if (-not (Test-Path -LiteralPath $image)) {
        throw "Support QR source image missing: $image"
    }
    & $generator -ImagePath $image -OutPath $out
    if (-not (Test-Path -LiteralPath $out)) {
        throw "Support QR payload generation failed: output file was not created."
    }
    $payloadHead = Get-Content -LiteralPath $out -TotalCount 6 -ErrorAction Stop
    if (-not ($payloadHead -match 'SUPPORT_QR_PAYLOAD')) {
        throw "Support QR payload generation failed: output file is invalid."
    }
}

function Remove-LooseSupportQrAssets {
    param([string]$BuildRoot)
    if (-not (Test-Path -LiteralPath $BuildRoot)) {
        return
    }
    $mediaDir = Join-Path $BuildRoot "static\media"
    if (Test-Path -LiteralPath $mediaDir) {
        Get-ChildItem -LiteralPath $mediaDir -Filter "support-upi-qr*" -File -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
    }
    $rootPng = Join-Path $BuildRoot "support-upi-qr.png"
    if (Test-Path -LiteralPath $rootPng) {
        Remove-Item -LiteralPath $rootPng -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-PythonObfuscationToTemp {
    param(
        [string]$SourceRoot,
        [string[]]$OpsFiles
    )
    $pyarmorExe = Resolve-PyArmorExe
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("flowx_obf_" + [guid]::NewGuid().ToString("N"))
    $serverOut = Join-Path $tempRoot "server_out"
    $opsOut = Join-Path $tempRoot "ops_out"
    Ensure-Dir -Path $tempRoot
    Ensure-Dir -Path $serverOut
    Ensure-Dir -Path $opsOut

    Write-Host "Obfuscating server Python modules..."
    & $pyarmorExe gen -r -O $serverOut (Join-Path $SourceRoot "server")
    if ($LASTEXITCODE -ne 0) {
        throw "PyArmor server obfuscation failed."
    }

    Write-Host "Obfuscating operational Python scripts..."
    foreach ($f in $OpsFiles) {
        $full = Join-Path $SourceRoot $f
        if (-not (Test-Path -LiteralPath $full)) { continue }
        & $pyarmorExe gen -O $opsOut $full
        if ($LASTEXITCODE -ne 0) {
            throw "PyArmor obfuscation failed for script: $f"
        }
    }

    return @{
        Root = $tempRoot
        ServerOut = $serverOut
        OpsOut = $opsOut
    }
}

function Invoke-PythonBytecodeHardeningToTemp {
    param(
        [string]$SourceRoot,
        [string]$PythonExePath = $null
    )
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("flowx_pyc_" + [guid]::NewGuid().ToString("N"))
    $serverOutRoot = Join-Path $tempRoot "server_out"
    $serverOut = Join-Path $serverOutRoot "server"
    Ensure-Dir -Path $serverOutRoot
    Copy-TreeIfExists -From (Join-Path $SourceRoot "server") -To $serverOut

    # Compile bytecode with a Python version compatible with packaged runtime.
    $pythonExePath = $PythonExePath
    if (-not $pythonExePath -or -not (Test-Path -LiteralPath $pythonExePath)) {
        $pythonExePath = Join-Path $SourceRoot "runtime\python\python.exe"
    }
    if (-not (Test-Path -LiteralPath $pythonExePath)) {
        $pythonExePath = Resolve-PythonExePath
    }

    # Remove stale caches copied from source to avoid mixed-magic artifacts.
    Get-ChildItem -LiteralPath $serverOut -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $serverOut -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }

    Write-Host "Compiling backend Python modules to bytecode..."
    & $pythonExePath -m compileall -b -f -q $serverOut
    if ($LASTEXITCODE -ne 0) {
        throw "Bytecode compilation failed for: $serverOut"
    }
    $pycFiles = Get-ChildItem -LiteralPath $serverOut -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue
    if (-not $pycFiles -or $pycFiles.Count -eq 0) {
        throw "Bytecode compilation produced no .pyc files in $serverOut"
    }
    Get-ChildItem -LiteralPath $serverOut -Recurse -File -Filter "*.py" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "__init__.py" } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }

    return @{
        Root = $tempRoot
        ServerOut = $serverOutRoot
        OpsOut = $null
        Mode = "bytecode"
    }
}

function Invoke-NativeQuiet {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

function Test-EmbeddedPythonRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonRoot
    )
    $embeddedPy = Join-Path $PythonRoot "python.exe"
    if (-not (Test-Path -LiteralPath $embeddedPy)) {
        return $false
    }
    $exitCode = Invoke-NativeQuiet {
        & $embeddedPy -c "import fastapi, uvicorn, pandas, yfinance, tradingview_screener" 2>$null | Out-Null
    }
    return $exitCode -eq 0
}

function Prepare-EmbeddedPythonRuntime {
    param(
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot
    )

    $runtimeRoot = Join-Path $SourceRoot "runtime"
    Ensure-Dir -Path $runtimeRoot
    if (Test-Path -LiteralPath $DestinationRoot) {
        if (-not (Remove-DirectorySafe -Path $DestinationRoot)) {
            throw "Could not prepare embedded Python build folder (files may be locked): $DestinationRoot"
        }
    }
    Ensure-Dir -Path $DestinationRoot

    $embeddedRoot = $DestinationRoot

    $pythonVersion = "3.11.9"
    $embedZip = Join-Path $runtimeRoot "python-embed.zip"
    $embedUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
    $getPip = Join-Path $runtimeRoot "get-pip.py"

    Write-Host "Downloading embedded Python runtime ($pythonVersion)..."
    Invoke-WebRequest -Uri $embedUrl -OutFile $embedZip -UseBasicParsing
    Expand-Archive -LiteralPath $embedZip -DestinationPath $embeddedRoot -Force
    Remove-Item -LiteralPath $embedZip -Force -ErrorAction SilentlyContinue

    $pth = Get-ChildItem -LiteralPath $embeddedRoot -Filter "python*._pth" -File | Select-Object -First 1
    if (-not $pth) {
        throw "Embedded runtime _pth file not found."
    }
    $pthContent = Get-Content -LiteralPath $pth.FullName
    $updated = @()
    $hasSitePackages = $false
    foreach ($line in $pthContent) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "Lib\site-packages") { $hasSitePackages = $true }
        if ($trimmed -eq "#import site") {
            $updated += "import site"
        } else {
            $updated += $line
        }
    }
    if (-not $hasSitePackages) {
        $updated += "Lib\site-packages"
    }
    Set-Content -LiteralPath $pth.FullName -Value $updated -Encoding ASCII

    Write-Host "Installing pip into embedded runtime..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
    $embeddedPy = Join-Path $embeddedRoot "python.exe"
    $exitCode = Invoke-NativeQuiet { & $embeddedPy $getPip 2>&1 | Out-Null }
    if ($exitCode -ne 0) {
        throw "Failed to install pip into embedded runtime."
    }
    Remove-Item -LiteralPath $getPip -Force -ErrorAction SilentlyContinue

    $reqFile = Join-Path $SourceRoot "requirements_runtime.txt"
    Write-Host "Installing backend dependencies into embedded runtime..."
    if (Test-Path -LiteralPath $reqFile) {
        $exitCode = Invoke-NativeQuiet { & $embeddedPy -m pip install --no-warn-script-location -r $reqFile 2>&1 | Out-Null }
    } else {
        $exitCode = Invoke-NativeQuiet { & $embeddedPy -m pip install --no-warn-script-location fastapi uvicorn pandas 2>&1 | Out-Null }
    }
    if ($exitCode -ne 0) {
        throw "Failed to install backend dependencies into embedded runtime."
    }

    $exitCode = Invoke-NativeQuiet {
        & $embeddedPy -c "import fastapi, uvicorn, pandas, yfinance, tradingview_screener" 2>$null | Out-Null
    }
    if ($exitCode -ne 0) {
        throw "Embedded runtime validation failed."
    }
}

function Test-ExportBackendImport {
    param(
        [string]$ExportRoot
    )
    $embeddedPy = Join-Path $ExportRoot "runtime\python\python.exe"
    if (-not (Test-Path -LiteralPath $embeddedPy)) {
        Write-Host "[WARN] Export smoke test skipped: runtime\python\python.exe missing."
        return
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ExportRoot "server\server.pyc"))) {
        if (-not (Test-Path -LiteralPath (Join-Path $ExportRoot "server\server.py"))) {
            Write-Host "[WARN] Export smoke test skipped: server module missing."
            return
        }
    }
    Write-Host "Running export backend import smoke test..."
    $code = @"
import sys
from pathlib import Path
root = Path(r'''$ExportRoot''').resolve()
sys.path.insert(0, str(root))
import server.server as srv
assert getattr(srv, 'app', None) is not None
print('OK')
"@
    $exitCode = Invoke-NativeQuiet { & $embeddedPy -c $code }
    if ($exitCode -ne 0) {
        Write-Host "Re-running smoke test with full output..."
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $embeddedPy -c $code
        } finally {
            $ErrorActionPreference = $prevEap
        }
        throw "Export backend import smoke test failed. The distributed package cannot start the API."
    }
    Write-Host "Export backend import smoke test passed."
}

function Test-ExportPackageComplete {
    param([string]$ExportRoot)
    $required = @(
        "start_cim.bat",
        "db_sqlite.py",
        "data\nse_data.db",
        "frontend\build\index.html",
        "runtime\python\python.exe",
        "runtime\wheelhouse",
        "server\server.pyc",
        "server\__init__.py",
        "desktop\package.json",
        "desktop\main.js"
    )
    $missing = @()
    foreach ($rel in $required) {
        $full = Join-Path $ExportRoot $rel
        if (-not (Test-Path -LiteralPath $full)) {
            $missing += $rel
        }
    }
    if ($missing.Count -gt 0) {
        throw ("Export package incomplete. Missing: " + ($missing -join ", "))
    }
}

function Commit-ExportStaging {
    param(
        [string]$StagingRoot,
        [string]$FinalRoot
    )
    $parent = Split-Path -Parent $FinalRoot
    $leaf = Split-Path -Leaf $FinalRoot
    $backupRoot = Join-Path $parent ($leaf + ".previous")

    if (Test-Path -LiteralPath $backupRoot) {
        Remove-Item -LiteralPath $backupRoot -Recurse -Force
    }

    $renamedLive = $false
    if (Test-Path -LiteralPath $FinalRoot) {
        Write-Host "Backing up previous export to: $backupRoot"
        try {
            Rename-Item -LiteralPath $FinalRoot -NewName (Split-Path -Leaf $backupRoot) -ErrorAction Stop
            $renamedLive = $true
        } catch {
            Write-Host "[WARN] Could not rename live export (folder may be open in Explorer or Charts In Motion is running)."
            Write-Host "[WARN] Will merge staging into the live folder instead. Close Charts In Motion and retry export to use a clean swap."
        }
    }

    if ($renamedLive -or -not (Test-Path -LiteralPath $FinalRoot)) {
        Write-Host "Activating new export..."
        Rename-Item -LiteralPath $StagingRoot -NewName $leaf
        return
    }

    Ensure-Dir -Path $FinalRoot
    Write-Host "Merging staging export into: $FinalRoot"
    & robocopy $StagingRoot $FinalRoot /E /IS /IT /R:2 /W:2 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "Failed to merge staging export into $FinalRoot (robocopy exit $LASTEXITCODE). Close FlowX/Explorer and re-run export."
    }
    Remove-Item -LiteralPath $StagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}

function Resolve-PythonExe {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            & py -3 --version *> $null
            if ($LASTEXITCODE -eq 0) { return "py -3" }
        } catch {}
    }
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        try {
            & python --version *> $null
            if ($LASTEXITCODE -eq 0) { return "python" }
        } catch {}
    }
    throw "No working Python runtime found on build machine. Install Python 3 first."
}

function Resolve-PythonExePath {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return $pyCmd.Source
    }
    throw "No working Python executable found on build machine. Install Python 3 first."
}

function Invoke-Python {
    param(
        [string]$PythonCommand,
        [string[]]$Args
    )
    if ($PythonCommand -eq "py -3") {
        & py -3 @Args
    } else {
        & python @Args
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $PythonCommand $($Args -join ' ')"
    }
}

function Resolve-PyArmorExe {
    $cmd = Get-Command pyarmor -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $fallback = Join-Path $env:APPDATA "Python\Python314\Scripts\pyarmor.exe"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }
    throw "PyArmor executable not found. Install pyarmor and ensure pyarmor.exe is available."
}

$FinalExportRoot = $ExportRoot
$StagingExportRoot = Join-Path (Split-Path -Parent $FinalExportRoot) ($([IO.Path]::GetFileName($FinalExportRoot)) + ".staging")

Write-Host "Source: $SourceRoot"
Write-Host "Export: $FinalExportRoot"
Write-Host "Staging: $StagingExportRoot"
Write-Host "Mode:   $Mode"

$isDistribution = $Mode -eq "distribution"
$effectiveObfuscateFrontend = $HardenAll -or $ObfuscateFrontend -or ($Obfuscate -and $isDistribution)
$effectiveObfuscatePython = $HardenAll -or $ObfuscatePython -or ($Obfuscate -and $isDistribution)
$effectivePythonHardening = $PythonHardening
$useDefaultHardening = $effectiveObfuscatePython -and $effectivePythonHardening -eq "none"
if ($useDefaultHardening) {
    $effectivePythonHardening = "bytecode"
}
$pythonObfInfo = $null
$exportSucceeded = $false
$EmbeddedPythonRoot = Join-Path $SourceRoot "runtime\python"

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Source root does not exist: $SourceRoot"
}

trap {
    if (-not $exportSucceeded) {
        Write-Host ""
        Write-Host "[ERROR] Export failed. The live export folder was NOT replaced."
        if (Test-Path -LiteralPath $ExportRoot) {
            Write-Host "[WARN] Incomplete staging may exist at: $ExportRoot"
            Write-Host "[WARN] Do not run start_cim.bat from that folder. Re-run export after closing FlowX/Explorer."
        }
    }
    break
}

# Build into a staging folder; only replace the live export after all checks pass.
# Never delete $FinalExportRoot until the new package is verified.
if (Test-Path -LiteralPath $StagingExportRoot) {
    Write-Host "Removing leftover staging folder..."
    try {
        Remove-Item -LiteralPath $StagingExportRoot -Recurse -Force -ErrorAction Stop
    } catch {
        $suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
        $StagingExportRoot = Join-Path (Split-Path -Parent $FinalExportRoot) ($([IO.Path]::GetFileName($FinalExportRoot)) + ".staging." + $suffix)
        Write-Host "[WARN] Could not remove locked staging folder. Using: $StagingExportRoot"
        Write-Host "[WARN] Close Charts In Motion and Explorer windows on the export folder before re-exporting."
    }
}
$ExportRoot = $StagingExportRoot

if ($effectiveObfuscateFrontend) {
    Write-Host "Generating encrypted support QR payload..."
    Invoke-GenerateSupportQrPayload -SourceRoot $SourceRoot
}

if (-not $SkipFrontendBuild) {
    $frontendDir = Join-Path $SourceRoot "frontend"
    if (Test-Path -LiteralPath (Join-Path $frontendDir "package.json")) {
        Write-Host "Building frontend production bundle..."
        Push-Location $frontendDir
        try {
            $env:GENERATE_SOURCEMAP = "false"
            if ($isDistribution) {
                $env:REACT_APP_EXPORT_MODE = "distribution"
            } else {
                Remove-Item Env:REACT_APP_EXPORT_MODE -ErrorAction SilentlyContinue
            }
            if ($effectiveObfuscateFrontend) {
                $env:REACT_APP_SUPPORT_QR_SECURE = "true"
            } else {
                Remove-Item Env:REACT_APP_SUPPORT_QR_SECURE -ErrorAction SilentlyContinue
            }
            & npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend build failed. Run npm install in frontend and retry."
            }
            if ($effectiveObfuscateFrontend) {
                Remove-LooseSupportQrAssets -BuildRoot (Join-Path $frontendDir "build")
            }
        } finally {
            Remove-Item Env:REACT_APP_EXPORT_MODE -ErrorAction SilentlyContinue
            Remove-Item Env:REACT_APP_SUPPORT_QR_SECURE -ErrorAction SilentlyContinue
            Pop-Location
        }
    }
}

if ($SkipEmbeddedPython) {
    Write-Host "Skipping embedded Python rebuild (-SkipEmbeddedPython). Using runtime\python if present."
} elseif (-not $RefreshEmbeddedPython -and (Test-EmbeddedPythonRuntime -PythonRoot $EmbeddedPythonRoot)) {
    Write-Host "Using existing runtime\python (add -RefreshEmbeddedPython to re-download)."
} elseif (-not $RefreshEmbeddedPython -and (Test-EmbeddedPythonRuntime -PythonRoot (Join-Path $SourceRoot "runtime\python.export-build"))) {
    $EmbeddedPythonRoot = Join-Path $SourceRoot "runtime\python.export-build"
    Write-Host "Using existing runtime\python.export-build (runtime\python is missing or failed validation)."
} else {
    $runtimeRoot = Join-Path $SourceRoot "runtime"
    $buildRoot = Join-Path $runtimeRoot "python.export-build"
    if (Test-Path -LiteralPath $buildRoot) {
        if (-not (Remove-DirectorySafe -Path $buildRoot)) {
            $buildRoot = Join-Path $env:TEMP ("flowx_python_build_" + [guid]::NewGuid().ToString("N"))
            Write-Host "[WARN] runtime\python.export-build is locked; using temp build folder:"
            Write-Host "       $buildRoot"
        }
    }
    Write-Host "Building embedded Python into: $buildRoot"
    Write-Host "(runtime\python is not deleted while Charts In Motion is running.)"
    Prepare-EmbeddedPythonRuntime -SourceRoot $SourceRoot -DestinationRoot $buildRoot
    $EmbeddedPythonRoot = $buildRoot
}

if (-not $SkipWheelhouse) {
    $runtimeRoot = Join-Path $SourceRoot "runtime"
    $wheelhouse = Join-Path $runtimeRoot "wheelhouse"
    $embeddedPy = Join-Path $EmbeddedPythonRoot "python.exe"
    if (-not (Test-Path -LiteralPath $embeddedPy)) {
        $embeddedPy = Join-Path $runtimeRoot "python\python.exe"
    }
    Ensure-Dir -Path $runtimeRoot
    if (Test-Path -LiteralPath $wheelhouse) {
        if (-not (Remove-DirectorySafe -Path $wheelhouse)) {
            Write-Host "[WARN] Could not clear runtime\wheelhouse (may be in use). Download may merge/fail."
        }
    }
    Ensure-Dir -Path $wheelhouse

    $reqFile = Join-Path $SourceRoot "requirements_runtime.txt"
    Write-Host "Preparing offline wheelhouse..."
    if (Test-Path -LiteralPath $embeddedPy) {
        if (Test-Path -LiteralPath $reqFile) {
            & $embeddedPy -m pip download -r $reqFile -d $wheelhouse
        } else {
            & $embeddedPy -m pip download fastapi uvicorn pandas yfinance -d $wheelhouse
        }
    } else {
        $pythonCommand = Resolve-PythonExe
        if (Test-Path -LiteralPath $reqFile) {
            if ($pythonCommand -eq "py -3") {
                & py -3 -m pip download -r $reqFile -d $wheelhouse
            } else {
                & python -m pip download -r $reqFile -d $wheelhouse
            }
        } else {
            if ($pythonCommand -eq "py -3") {
                & py -3 -m pip download fastapi uvicorn pandas yfinance -d $wheelhouse
            } else {
                & python -m pip download fastapi uvicorn pandas yfinance -d $wheelhouse
            }
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Offline wheelhouse preparation failed."
    }
}

$opsFiles = @(
    "scrape_daily.py",
    "scrape_indices.py",
    "scrape_financials.py",
    "scrape_earnings.py",
    "screener_login.py",
    "nse_data_backup.py",
    "nse_index_history.py"
)

if ($effectiveObfuscatePython) {
    if ($effectivePythonHardening -eq "pyarmor") {
        $pythonObfInfo = Invoke-PythonObfuscationToTemp -SourceRoot $SourceRoot -OpsFiles $opsFiles
        $pythonObfInfo.Mode = "pyarmor"
    } elseif ($effectivePythonHardening -eq "bytecode") {
        $bytecodePy = Join-Path $EmbeddedPythonRoot "python.exe"
        if (-not (Test-Path -LiteralPath $bytecodePy)) { $bytecodePy = $null }
        $pythonObfInfo = Invoke-PythonBytecodeHardeningToTemp -SourceRoot $SourceRoot -PythonExePath $bytecodePy
    } else {
        throw "Invalid Python hardening mode: $effectivePythonHardening"
    }
}

Ensure-Dir -Path $ExportRoot
Ensure-Dir -Path (Join-Path $ExportRoot "frontend")
Ensure-Dir -Path (Join-Path $ExportRoot "desktop")
Ensure-Dir -Path (Join-Path $ExportRoot "server")
Ensure-Dir -Path (Join-Path $ExportRoot "data")
Ensure-Dir -Path (Join-Path $ExportRoot "runtime")

# ------------------------------------------------------------
# 1) Root runtime / launch files
# ------------------------------------------------------------
$rootFiles = @(
    "start_cim.bat",
    "stop_cim.bat",
    "create_desktop_shortcut.bat",
    "README_START_STOP.md",
    "requirements_runtime.txt",
    "CHANGELOG.md",
    "db_sqlite.py",
    "symbol_lineage.py"
)

foreach ($f in $rootFiles) {
    Copy-IfExists -From (Join-Path $SourceRoot $f) -To (Join-Path $ExportRoot $f)
}

# start_cim.bat and distribution installs depend on this helper script.
Copy-IfExists -From (Join-Path $SourceRoot "scripts\frontend_needs_build.ps1") -To (Join-Path $ExportRoot "scripts\frontend_needs_build.ps1")
Copy-IfExists -From (Join-Path $SourceRoot "scripts\backfill_symbol_history.py") -To (Join-Path $ExportRoot "scripts\backfill_symbol_history.py")

# ------------------------------------------------------------
# 2) Frontend
# Prefer build output for zero-input startup; include source as fallback.
# ------------------------------------------------------------
Copy-IfExists     -From (Join-Path $SourceRoot "frontend\package.json")      -To (Join-Path $ExportRoot "frontend\package.json")
Copy-IfExists     -From (Join-Path $SourceRoot "frontend\package-lock.json") -To (Join-Path $ExportRoot "frontend\package-lock.json")
Copy-IfExists     -From (Join-Path $SourceRoot "frontend\yarn.lock")         -To (Join-Path $ExportRoot "frontend\yarn.lock")
Copy-TreeIfExists -From (Join-Path $SourceRoot "frontend\public")            -To (Join-Path $ExportRoot "frontend\public")
if (-not $isDistribution) {
    # Standard mode keeps source for easier local development/troubleshooting.
    Copy-TreeIfExists -From (Join-Path $SourceRoot "frontend\src")           -To (Join-Path $ExportRoot "frontend\src")
}
$frontendBuildSrc = Join-Path $SourceRoot "frontend\build"
$frontendBuildDst = Join-Path $ExportRoot "frontend\build"
if (Test-Path -LiteralPath $frontendBuildSrc) {
    if (Test-Path -LiteralPath $frontendBuildDst) {
        Remove-Item -LiteralPath $frontendBuildDst -Recurse -Force -ErrorAction SilentlyContinue
    }
    Ensure-Dir -Path $frontendBuildDst
    Copy-Item -Path (Join-Path $frontendBuildSrc "*") -Destination $frontendBuildDst -Recurse -Force
}
if (Test-Path -LiteralPath (Join-Path $SourceRoot "desktop")) {
    # Copy desktop folder contents (not the folder itself) to avoid desktop\desktop nesting.
    $desktopDest = Join-Path $ExportRoot "desktop"
    Ensure-Dir -Path $desktopDest
    Copy-Item -Path (Join-Path $SourceRoot "desktop\*") -Destination $desktopDest -Recurse -Force
}

if ($effectiveObfuscateFrontend) {
    Invoke-FrontendObfuscation -ExportRoot $ExportRoot
    Remove-LooseSupportQrAssets -BuildRoot (Join-Path $ExportRoot "frontend\build")
}

Copy-TreeIfExists -From $EmbeddedPythonRoot -To (Join-Path $ExportRoot "runtime\python")
Copy-TreeIfExists -From (Join-Path $SourceRoot "runtime\wheelhouse")         -To (Join-Path $ExportRoot "runtime\wheelhouse")

# Prepare desktop runtime inside export so start_cim.bat can launch a window immediately.
$desktopDir = Join-Path $ExportRoot "desktop"
if (Test-Path -LiteralPath (Join-Path $desktopDir "package.json")) {
    Write-Host "Installing desktop dependencies in export..."
    Push-Location $desktopDir
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            throw "Desktop dependency install failed in export\desktop."
        }
    } finally {
        Pop-Location
    }
}

# ------------------------------------------------------------
# 3) Backend (API + support modules)
# ------------------------------------------------------------
if ($effectiveObfuscatePython -and $pythonObfInfo) {
    if ($pythonObfInfo.Mode -eq "bytecode") {
        $serverObfRoot = Join-Path $pythonObfInfo.ServerOut "server"
        $serverPycFiles = Get-ChildItem -LiteralPath $serverObfRoot -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue
        foreach ($file in $serverPycFiles) {
            $relative = $file.FullName.Substring($serverObfRoot.Length).TrimStart('\','/')
            Copy-IfExists -From $file.FullName -To (Join-Path $ExportRoot ("server\" + $relative))
        }
        $initPy = Join-Path $serverObfRoot "__init__.py"
        if (Test-Path -LiteralPath $initPy) {
            Copy-IfExists -From $initPy -To (Join-Path $ExportRoot "server\__init__.py")
        }
    } else {
        $serverObfRoot = Get-ObfuscatedServerRoot -ServerOutputRoot $pythonObfInfo.ServerOut
        $serverPyFiles = Get-ChildItem -LiteralPath $serverObfRoot -File -Filter "*.py" -ErrorAction SilentlyContinue
        foreach ($file in $serverPyFiles) {
            Copy-IfExists -From $file.FullName -To (Join-Path $ExportRoot ("server\" + $file.Name))
        }
        $serverRuntimeDirs = Get-ChildItem -LiteralPath $serverObfRoot -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "pyarmor_runtime_*" }
        foreach ($rt in $serverRuntimeDirs) {
            Copy-TreeIfExists -From $rt.FullName -To (Join-Path $ExportRoot ("server\" + $rt.Name))
        }
    }
} else {
    # Copy all python files in server directory (portable and safe)
    $serverPyFiles = Get-ChildItem -LiteralPath (Join-Path $SourceRoot "server") -File -Filter "*.py" -ErrorAction SilentlyContinue
    foreach ($file in $serverPyFiles) {
        Copy-IfExists -From $file.FullName -To (Join-Path $ExportRoot ("server\" + $file.Name))
    }
}

# ------------------------------------------------------------
# 4) Operational update scripts (root-level)
# ------------------------------------------------------------
if ($effectiveObfuscatePython -and $pythonObfInfo -and $pythonObfInfo.Mode -eq "pyarmor") {
    foreach ($f in $opsFiles) {
        $obfPath = Join-Path $pythonObfInfo.OpsOut $f
        if (Test-Path -LiteralPath $obfPath) {
            Copy-IfExists -From $obfPath -To (Join-Path $ExportRoot $f)
        } else {
            Copy-IfExists -From (Join-Path $SourceRoot $f) -To (Join-Path $ExportRoot $f)
        }
    }
    $opsRuntimeDirs = Get-ChildItem -LiteralPath $pythonObfInfo.OpsOut -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "pyarmor_runtime_*" }
    foreach ($rt in $opsRuntimeDirs) {
        Copy-TreeIfExists -From $rt.FullName -To (Join-Path $ExportRoot $rt.Name)
    }
} else {
    foreach ($f in $opsFiles) {
        Copy-IfExists -From (Join-Path $SourceRoot $f) -To (Join-Path $ExportRoot $f)
    }
}

# ------------------------------------------------------------
# 5) Data needed for app + updates
# ------------------------------------------------------------
$dataFiles = @("nse_data.db", "nse_dataset.csv", "nse_calendar.json", "market_sectors.json", "market_sector_mapping.json", "symbol_lineage.json", "knowledge_base.json")
if (-not $isDistribution) {
    $dataFiles += @("layout.json", "watchlists.json", "saved_filters.json", "screener_session.json")
}
foreach ($f in $dataFiles) {
    Copy-IfExists -From (Join-Path $SourceRoot ("data\" + $f)) -To (Join-Path $ExportRoot ("data\" + $f))
}

Ensure-Dir -Path (Join-Path $ExportRoot "config")
foreach ($f in @("product.json", "github_updates.json", "update_manifest_url.json")) {
    Copy-IfExists -From (Join-Path $SourceRoot ("config\" + $f)) -To (Join-Path $ExportRoot ("config\" + $f))
}

# Optional scraper profile/session folder if present
if (-not $isDistribution) {
    Copy-TreeIfExists -From (Join-Path $SourceRoot "data\screener_profile") -To (Join-Path $ExportRoot "data\screener_profile")
}

if ($isDistribution) {
    # Distribution mode ships a clean baseline (no user presets/watchlists/session state).
    $distLayout = @{
        stochrsi = 130
        macd = 130
        dashboardPaneWidth = 320
        dashboardChartLayout = "single"
        dashboardTimeframe = "1D"
        indicesPaneWidth = 240
        indicesChartLayout = "single"
        indicesTimeframe = "1D"
        watchlistPaneWidth = 358
        watchlistChartLayout = "single"
        watchlistTimeframe = "1D"
        watchlistTimeframe2 = "1W"
        watchlistTimeframe3 = "1M"
        moversPaneWidth = 398
        moversChartLayout = "single"
        moversTimeframe = "1D"
        marketMapPaneWidth = 280
        aggressiveCacheRam = $false
    }
    $layoutPath = Join-Path $ExportRoot "data\layout.json"
    $watchlistsPath = Join-Path $ExportRoot "data\watchlists.json"
    $presetsPath = Join-Path $ExportRoot "data\saved_filters.json"
    $sessionPath = Join-Path $ExportRoot "data\screener_session.json"
    $portfolioPath = Join-Path $ExportRoot "data\portfolio.json"
    $distLayout | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $layoutPath -Encoding UTF8
    "[]" | Set-Content -LiteralPath $watchlistsPath -Encoding UTF8
    "[]" | Set-Content -LiteralPath $presetsPath -Encoding UTF8
    "{}" | Set-Content -LiteralPath $sessionPath -Encoding UTF8
    '{"items":[]}' | Set-Content -LiteralPath $portfolioPath -Encoding UTF8
}

# ------------------------------------------------------------
# 6) Remove excluded artifacts if they were copied indirectly
# ------------------------------------------------------------
$excludeNames = @(
    "backups",
    "agent-transcripts",
    "terminals",
    ".cursor",
    "PROJECT_HANDOFF_2026-04-12_003816.md",
    "PROJECT_HANDOFF_EXEC_SUMMARY.md",
    "NSE_Pulse_Project_Handoff_10_Apr_2026.md"
)

foreach ($name in $excludeNames) {
    $matches = Get-ChildItem -LiteralPath $ExportRoot -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $name }
    foreach ($m in $matches) {
        Remove-Item -LiteralPath $m.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------
# 7) Write manifest for verification
# ------------------------------------------------------------
$manifestPath = Join-Path $ExportRoot "included_files.txt"
Get-ChildItem -LiteralPath $ExportRoot -Recurse -Force |
    Where-Object { -not $_.PSIsContainer } |
    ForEach-Object { $_.FullName.Replace($ExportRoot, ".") } |
    Sort-Object |
    Set-Content -LiteralPath $manifestPath -Encoding UTF8

Test-ExportBackendImport -ExportRoot $ExportRoot
Test-ExportPackageComplete -ExportRoot $ExportRoot

Commit-ExportStaging -StagingRoot $ExportRoot -FinalRoot $FinalExportRoot
$ExportRoot = $FinalExportRoot
$manifestPath = Join-Path $ExportRoot "included_files.txt"
$exportSucceeded = $true

Write-Host ""
Write-Host "Export complete."
Write-Host "Location: $FinalExportRoot"
Write-Host "Manifest: $manifestPath"
if (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $FinalExportRoot) ($([IO.Path]::GetFileName($FinalExportRoot)) + ".previous"))) {
    Write-Host "Previous export kept as: $([IO.Path]::GetFileName($FinalExportRoot)).previous"
}
Write-Host ""
Write-Host "Next step: zip the folder '$FinalExportRoot' and share it."

if ($pythonObfInfo -and (Test-Path -LiteralPath $pythonObfInfo.Root)) {
    Remove-Item -LiteralPath $pythonObfInfo.Root -Recurse -Force -ErrorAction SilentlyContinue
}
# Leave $StagingExportRoot on disk when merge/swap path was used; user can delete manually.

