#Requires -Version 5.1
<#
.SYNOPSIS
  Unit-style checks for Build-CiM-GUI progress math and update-only logging shape.
#>
$ErrorActionPreference = 'Stop'

function Get-PipelineSegmentPercent {
    param([int]$StepCurrent, [int]$StepTotal)
    if ($StepTotal -le 0 -or $StepCurrent -le 0) { return 0 }
    $pct = [int][math]::Floor((100.0 * $StepCurrent) / $StepTotal)
    if ($pct -lt 1 -and $StepCurrent -gt 0) { $pct = 1 }
    if ($pct -gt 99) { $pct = 99 }
    return $pct
}

function ConvertTo-OverallBuildPercent {
    param([int]$PipelinePercent, [bool]$Both, [int]$PipelineSlot)
    if (-not $Both) { return $PipelinePercent }
    $base = $PipelineSlot * 50
    return [int][math]::Min(100, $base + [int][math]::Floor(($PipelinePercent / 100.0) * 50))
}

$fail = 0
function Assert-Equal {
    param($Expected, $Actual, [string]$Name)
    if ($Expected -ne $Actual) {
        Write-Host "FAIL $Name expected=$Expected actual=$Actual" -ForegroundColor Red
        $script:fail++
    } else {
        Write-Host "OK   $Name" -ForegroundColor Green
    }
}

Assert-Equal 16 (Get-PipelineSegmentPercent -StepCurrent 1 -StepTotal 6) 'step 1/6'
Assert-Equal 66 (Get-PipelineSegmentPercent -StepCurrent 4 -StepTotal 6) 'step 4/6'
Assert-Equal 50 (Get-PipelineSegmentPercent -StepCurrent 1 -StepTotal 2) 'step 1/2 update package'
Assert-Equal 66 (ConvertTo-OverallBuildPercent -PipelinePercent 66 -Both $false -PipelineSlot 0) 'single dist 66'
Assert-Equal 83 (ConvertTo-OverallBuildPercent -PipelinePercent 66 -Both $true -PipelineSlot 1) 'both plaintext half'

$updateScript = Join-Path $PSScriptRoot 'Build-CiM-UpdateOnly.ps1'
$content = Get-Content -LiteralPath $updateScript -Raw
if ($content -notmatch 'function Log') { Write-Host 'FAIL UpdateOnly missing Log function' -ForegroundColor Red; $fail++ }
else { Write-Host 'OK   UpdateOnly Log function present' -ForegroundColor Green }
if ($content -notmatch 'Step \$step/\$stepTotal') { Write-Host 'FAIL UpdateOnly step logging' -ForegroundColor Red; $fail++ }
else { Write-Host 'OK   UpdateOnly step logging present' -ForegroundColor Green }
if ($content -notmatch 'Build complete') { Write-Host 'FAIL UpdateOnly completion line' -ForegroundColor Red; $fail++ }
else { Write-Host 'OK   UpdateOnly completion line present' -ForegroundColor Green }

$guiScript = Join-Path $PSScriptRoot '..\Batch Files\Build-CiM-GUI.ps1'
$gui = Get-Content -LiteralPath $guiScript -Raw
foreach ($needle in @('Update-ProgressCreep', 'Tail-BuildLogs', 'Append-LogLines', 'progressCreepTimer', 'MaxLogLinesPerTick')) {
    if ($gui -notmatch [regex]::Escape($needle)) {
        Write-Host "FAIL GUI missing $needle" -ForegroundColor Red
        $fail++
    } else {
        Write-Host "OK   GUI has $needle" -ForegroundColor Green
    }
}
if ($gui -match 'Get-Content -LiteralPath \$LogFile -Tail 40') {
    Write-Host 'FAIL GUI still loads old log tail on startup' -ForegroundColor Red
    $fail++
} else {
    Write-Host 'OK   GUI blank startup log view' -ForegroundColor Green
}

$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path -LiteralPath $guiScript).Path,
    [ref]$null,
    [ref]$parseErrors
)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    Write-Host "FAIL GUI parse errors: $($parseErrors.Count)" -ForegroundColor Red
    $parseErrors | ForEach-Object { Write-Host $_.ToString() }
    $fail++
} else {
    Write-Host 'OK   GUI script parses' -ForegroundColor Green
}

if ($fail -gt 0) {
    Write-Host "`n$fail check(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host ''
Write-Host 'All build launcher checks passed.' -ForegroundColor Green
exit 0
