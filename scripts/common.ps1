# Helpers shared by install.ps1 and start-local.ps1 (dot-source this file).

# KEY=VALUE pairs from a .env file; blank lines, "# comments" and trailing
# "   # notes" are ignored.
function Read-DotEnv([string]$path) {
    $values = @{}
    if (-not (Test-Path $path)) { return $values }
    foreach ($line in Get-Content $path -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $value = $line -split '=', 2
        $value = ($value -replace '\s+#.*$', '').Trim()
        $values[$key.Trim()] = $value
    }
    return $values
}

# Runtimes chosen by install.ps1 (tools\runtime.json): puts the Node.js folder
# first on PATH for this process and the windows it starts.
function Use-ProjectRuntime([string]$root) {
    $file = Join-Path $root "tools\runtime.json"
    if (-not (Test-Path $file)) { return $null }
    $runtime = Get-Content $file -Raw | ConvertFrom-Json
    if ($runtime.nodeDir -and (Test-Path $runtime.nodeDir)) {
        $env:Path = "$($runtime.nodeDir);$env:Path"
    }
    return $runtime
}

# IPv4 addresses other PCs on the LAN can use to reach this one.
function Get-LanAddresses {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notlike 'vEthernet*' -and $_.InterfaceAlias -notlike '*Loopback*' } |
        Select-Object -ExpandProperty IPAddress
}

# Builds the UI (next build) when there is no build yet, a source file is newer
# than the last build, or NEXT_PUBLIC_BASE_PATH / NEXT_PUBLIC_API_URL changed
# (both are baked into the bundle).  -Force always rebuilds.
function Invoke-UiBuild([string]$root, [switch]$Force) {
    $ui = Join-Path $root "icbOfficerAssoUI"
    $envValues = Read-DotEnv (Join-Path $root ".env")
    $env:NEXT_PUBLIC_BASE_PATH = "$($envValues['NEXT_PUBLIC_BASE_PATH'])"
    $env:NEXT_PUBLIC_API_URL = "$($envValues['NEXT_PUBLIC_API_URL'])"
    $env:NEXT_TELEMETRY_DISABLED = "1"
    $wanted = "basePath=$env:NEXT_PUBLIC_BASE_PATH;apiUrl=$env:NEXT_PUBLIC_API_URL"

    $buildId = Join-Path $ui ".next\BUILD_ID"
    $stampFile = Join-Path $ui ".next\icb-build-stamp.txt"
    $reason = $null
    if ($Force) { $reason = "rebuild requested" }
    elseif (-not (Test-Path $buildId)) { $reason = "no build yet" }
    elseif (-not (Test-Path $stampFile) -or (Get-Content $stampFile -Raw).Trim() -ne $wanted) { $reason = "URL settings changed" }
    else {
        $builtAt = (Get-Item $buildId).LastWriteTime
        $sources = @(Get-ChildItem (Join-Path $ui "src"), (Join-Path $ui "public") -Recurse -File) +
                   @(Get-Item (Join-Path $ui "next.config.ts"), (Join-Path $ui "package.json"), (Join-Path $ui "package-lock.json"))
        if ($sources | Where-Object { $_.LastWriteTime -gt $builtAt } | Select-Object -First 1) { $reason = "source files changed" }
    }
    if (-not $reason) {
        Write-Host "    UI build is up to date" -ForegroundColor DarkGray
        return
    }

    Write-Host "==> Building UI ($reason) - this takes a minute" -ForegroundColor Cyan
    Push-Location $ui
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "UI build failed (npm run build exited with $LASTEXITCODE)" }
        Set-Content -Path $stampFile -Value $wanted -Encoding ASCII
    } finally {
        Pop-Location
    }
}
