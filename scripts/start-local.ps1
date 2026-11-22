# Starts the API and the UI in two separate windows (Windows, no Docker).
# Run from the project root:   powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
#
#   -Production   serve the optimised UI build (used by "1. Start.bat"); the
#                 UI is rebuilt first only when its sources or URL settings changed
#   -Rebuild      with -Production: always rebuild the UI
#   Both servers listen on 0.0.0.0; '0. install.bat' publishes them through IIS as
#   http://<this-pc-ip>/election/... (NEXT_PUBLIC_BASE_PATH in .env).

param(
    [switch]$Production,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api = "$root\icbOfficerAssoAPI"
$ui = "$root\icbOfficerAssoUI"
. "$PSScriptRoot\common.ps1"

if (-not (Test-Path "$api\.venv\Scripts\python.exe")) {
    throw "Backend is not set up yet. Run '0. install.bat' first."
}
# A .venv copied from another PC starts but then fails inside uvicorn
$ErrorActionPreference = "Continue"
& "$api\.venv\Scripts\python.exe" -c "import pydantic_core._pydantic_core, fastapi, cv2" 2>$null
$venvWorks = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $venvWorks) {
    throw "The API's Python packages do not work on this PC (icbOfficerAssoAPI\.venv was probably copied from another computer). Run '0. install.bat' - it builds a new .venv for this PC."
}
Use-ProjectRuntime $root | Out-Null
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js was not found. Run '0. install.bat' first." }
if (-not (Test-Path "$ui\node_modules")) { throw "UI packages are missing. Run '0. install.bat' first." }

$basePath = "$((Read-DotEnv "$root\.env")['NEXT_PUBLIC_BASE_PATH'])".TrimEnd("/")
$env:NEXT_PUBLIC_BASE_PATH = $basePath

Write-Host "==> Starting API on http://0.0.0.0:8000  (docs: http://localhost:8000/docs)" -ForegroundColor Cyan
$apiCmd = "Set-Location '$api'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000" + $(if ($Production) { "" } else { " --reload" })
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

if ($Production) {
    Invoke-UiBuild $root -Force:$Rebuild
    $uiCmd = "Set-Location '$ui'; npm run start -- --hostname 0.0.0.0 --port 3000"
} else {
    $uiCmd = "Set-Location '$ui'; npm run dev -- --hostname 0.0.0.0 --port 3000"
}
Write-Host "==> Starting UI on http://0.0.0.0:3000$basePath" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $uiCmd

Write-Host ""
Write-Host "On this PC:" -ForegroundColor Green
Write-Host "    Admin panel:      http://localhost:3000$basePath/admin   (default login admin / admin123)" -ForegroundColor Green
Write-Host "    Public dashboard: http://localhost:3000$basePath/dashboard" -ForegroundColor Green
if ($basePath) {
    Write-Host "From any PC on the LAN (through IIS):" -ForegroundColor Green
    foreach ($ip in Get-LanAddresses) {
        Write-Host "    http://$ip$basePath/admin     http://$ip$basePath/dashboard" -ForegroundColor Green
    }
}
Write-Host "Drop scanned PDFs into: $root\data\Scanned" -ForegroundColor Green
