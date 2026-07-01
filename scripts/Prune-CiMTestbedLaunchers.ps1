#Requires -Version 5.1
<#
.SYNOPSIS
  Remove desktop/update launchers from a browser showcase testbed install.

.DESCRIPTION
  Testbed (D:\CiM\Client_Test) is for web showcase on port 8002 only.
  Desktop Electron (start_cim.bat), client update bats, and stale zOld\ copies do not belong here.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($InstallRoot.Trim().Trim('"').TrimEnd('\'))

$removeRel = @(
    "start_cim.bat",
    "stop_cim.bat",
    "Apply-Update.bat",
    "Install-Client-Update.bat"
)

foreach ($rel in $removeRel) {
    $path = Join-Path $root $rel
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "Removed testbed launcher: $rel"
    }
}

$zOld = Join-Path $root "zOld"
if (Test-Path -LiteralPath $zOld) {
    Remove-Item -LiteralPath $zOld -Recurse -Force
    Write-Host "Removed stale folder: zOld\"
}

exit 0
