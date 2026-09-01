$ErrorActionPreference = "Stop"

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command not found: $Name"
    }
    return $command
}

if ($env:OS -ne "Windows_NT") {
    throw "This release script must run on Windows."
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Frontend = Join-Path $Root "frontend"
$Tauri = Join-Path $Frontend "src-tauri"
$ReleaseVenv = Join-Path $Root ".release-venv"

Require-Command node | Out-Null
Require-Command npm | Out-Null
Require-Command rustc | Out-Null
Require-Command cargo | Out-Null

$nodeVersion = (node --version).Trim()
if ($nodeVersion -notmatch '^v(22|24)\.') {
    throw "Node 22 or 24 stable is required for release builds. Found: $nodeVersion"
}

$rustInfo = rustc -vV
$hostLine = ($rustInfo | Select-String '^host: ').Line
if (-not $hostLine -or $hostLine -notmatch 'pc-windows-msvc$') {
    throw "Rust MSVC host toolchain is required. rustc reports: $hostLine"
}

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "Python 3.12+ was not found."
}

Write-Host "== Windows release preflight =="
Write-Host "Node:  $nodeVersion"
Write-Host "npm:   $((npm --version).Trim())"
Write-Host "rustc: $((rustc --version).Trim())"
Write-Host "cargo: $((cargo --version).Trim())"
Write-Host "host:  $hostLine"

Push-Location $Root
try {
    if (-not (Test-Path $ReleaseVenv)) {
        if ($python.Name -eq "py.exe" -or $python.Name -eq "py") {
            py -3.12 -m venv $ReleaseVenv
        } else {
            python -m venv $ReleaseVenv
        }
    }

    $venvPython = Join-Path $ReleaseVenv "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "Release virtual environment is incomplete: $venvPython"
    }

    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements-build.txt
    & $venvPython -m pip install pytest pytest-asyncio
    & $venvPython -m pytest -q -p no:cacheprovider

    Push-Location $Frontend
    try {
        npm ci --include=optional
        npm run build
        & $venvPython ..\scripts\build_sidecar.py
    }
    finally {
        Pop-Location
    }

    Push-Location $Tauri
    try {
        cargo check --locked
    }
    finally {
        Pop-Location
    }

    Push-Location $Frontend
    try {
        npx tauri build --bundles nsis
    }
    finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "Windows release build completed successfully."
    Write-Host "Verify the generated NSIS setup executable on a clean Windows machine before tagging v1.0-rc1."
}
finally {
    Pop-Location
}
