$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    throw 'Dependencies are not installed. Run .\scripts\bootstrap.ps1 first.'
}

$env:PIP_CACHE_DIR = Join-Path $ProjectRoot '.cache\pip'
$env:TEMP = Join-Path $ProjectRoot '.tmp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRoot '.cache\pycache'
$env:LOCALAPPDATA = Join-Path $ProjectRoot '.cache\localappdata'
$env:APPDATA = Join-Path $ProjectRoot '.cache\appdata'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:LOCALAPPDATA, $env:APPDATA | Out-Null

Push-Location $ProjectRoot
try {
    & $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
} finally {
    Pop-Location
}

