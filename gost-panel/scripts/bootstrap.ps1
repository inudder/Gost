$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.14 -m venv .venv
}

$python = Resolve-Path ".venv\Scripts\python.exe"

# Ignore machine-level pip proxy config. The local panel installs cleanly on this host without it.
$env:PIP_CONFIG_FILE = "NUL"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""

& $python -m pip install --upgrade pip
& $python -m pip install --no-build-isolation -e .
