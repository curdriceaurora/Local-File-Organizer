<#
.SYNOPSIS
  Build Windows executable and installer using PyInstaller + Inno Setup.

.DESCRIPTION
  1) Runs PyInstaller via scripts/build.py (with app manifest)
  2) Builds an installer using Inno Setup (ISCC)

.PARAMETER Version
  Optional version override for installer naming (defaults to pyproject.toml)

.PARAMETER SkipBuild
  Skip PyInstaller build and only run ISCC
#>

param(
  [string]$Version = "",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Get-Version {
  if ($Version -ne "") { return $Version }
  $py = @'
import tomllib
from pathlib import Path
print(tomllib.loads(Path("pyproject.toml").read_text())['project']['version'])
'@
  return (python -c $py).Trim()
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $SkipBuild) {
  python scripts/build.py --clean
}

$version = Get-Version
$iss = Join-Path $PSScriptRoot "build_windows.iss"
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if (-not (Test-Path $iscc)) {
  Write-Host "ERROR: Inno Setup (ISCC) not found at $iscc" -ForegroundColor Red
  Write-Host "Install Inno Setup 6+ and retry." -ForegroundColor Yellow
  exit 1
}

& $iscc /DAppVersion=$version $iss
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installer built in dist/ (version $version)." -ForegroundColor Green
