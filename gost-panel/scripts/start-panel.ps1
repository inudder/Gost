$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found. Run .\scripts\bootstrap.ps1 first."
}

$python = Resolve-Path ".venv\Scripts\python.exe"
& $python -m app.main
