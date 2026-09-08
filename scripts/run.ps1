# Halite launcher — Windows (PowerShell)
# Usage: .\scripts\run.ps1
# Starts the Ink TUI (Node) which spawns the Python backend.
# Requires: node, npm, and a Python venv at .venv\ (or system python3).

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$InkDir = Join-Path $ProjectRoot "halite\ui\ink"
$DistIndex = Join-Path $InkDir "dist\index.js"

# 1. Build the Ink frontend if missing
if (-not (Test-Path $DistIndex)) {
    Write-Host "Ink TUI not built - installing dependencies and building..."
    Push-Location $InkDir
    npm install
    npm run build
    Pop-Location
}

# 2. Set the Python interpreter for the backend
#    Prefer the project venv (Windows layout), else system python
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $env:HALITE_PYTHON = $VenvPython
    Write-Host "Using venv Python: $VenvPython"
} else {
    # Try to create the venv if uv is available and python is missing
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "WARNING: .venv not found and uv is not installed."
        Write-Host "Create it first:  uv venv --python 3.11 .venv && uv pip install --python .venv\Scripts\python.exe -r requirements.txt"
        exit 1
    }
    uv venv --python 3.11 .venv
    uv pip install --python $VenvPython -r requirements.txt
    $env:HALITE_PYTHON = $VenvPython
}

# 3. Launch the Ink TUI (Node is the parent; it spawns the Python backend)
$env:HALITE_ROOT = $ProjectRoot
Push-Location $ProjectRoot
node $DistIndex
Pop-Location