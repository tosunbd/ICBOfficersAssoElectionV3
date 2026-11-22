# Stops the API and the UI started by scripts\start-local.ps1 (Windows, no Docker).
# Run from the project root:   powershell -ExecutionPolicy Bypass -File scripts\stop-local.ps1

$root = Split-Path -Parent $PSScriptRoot
$stopped = 0

function Stop-Tree([int]$processId, [string]$what) {
    # /T also ends child processes (uvicorn reloader + worker, npm + node)
    taskkill /PID $processId /T /F *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    stopped $what (PID $processId)" -ForegroundColor Yellow
        $script:stopped++
    }
}

# 1. The two server windows opened by start-local.ps1
Write-Host "==> Closing the API and UI windows" -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" |
    Where-Object { $_.CommandLine -and ($_.CommandLine -like "*$root\icbOfficerAssoAPI*" -or $_.CommandLine -like "*$root\icbOfficerAssoUI*") } |
    ForEach-Object { Stop-Tree $_.ProcessId "server window" }

# 2. Anything still listening on the API / UI ports (e.g. started by hand)
Write-Host "==> Freeing ports 8000 and 3000" -ForegroundColor Cyan
foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -gt 0 } |
        ForEach-Object { Stop-Tree $_ "process on port $port" }
}

Write-Host ""
if ($stopped -gt 0) {
    Write-Host "The election system is stopped." -ForegroundColor Green
} else {
    Write-Host "Nothing was running." -ForegroundColor Green
}
