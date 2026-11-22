# One-time setup for running the system directly on Windows (no Docker).
# Run from the project root:   powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Checking tools" -ForegroundColor Cyan
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python 3.11+ is not installed or not on PATH (https://www.python.org/downloads/)" }
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "Node.js 20+ is not installed or not on PATH (https://nodejs.org/)" }
Write-Host "    python: $(python --version)"
Write-Host "    node:   $(node --version)"

Write-Host "==> Backend: creating virtual environment and installing packages" -ForegroundColor Cyan
Set-Location "$root\icbOfficerAssoAPI"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt

Write-Host "==> Frontend: installing npm packages" -ForegroundColor Cyan
Set-Location "$root\icbOfficerAssoUI"
npm install

Set-Location $root
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> Created .env from .env.example (edit it to change passwords/folders)" -ForegroundColor Yellow
}
foreach ($d in "data\Scanned", "data\Completed", "data\Failed", "data\Previews") {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

Write-Host ""
Write-Host "Setup complete. Start the system with:  powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1" -ForegroundColor Green
