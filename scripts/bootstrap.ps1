$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot '.venv'
$CachePath = Join-Path $ProjectRoot '.cache\pip'
$TempPath = Join-Path $ProjectRoot '.tmp'
$PythonPath = 'D:\devtools\python314-x64\python.exe'
$LocalAppDataPath = Join-Path $ProjectRoot '.cache\localappdata'
$RoamingAppDataPath = Join-Path $ProjectRoot '.cache\appdata'

New-Item -ItemType Directory -Force -Path $CachePath, $TempPath, $LocalAppDataPath, $RoamingAppDataPath | Out-Null
$env:PIP_CACHE_DIR = $CachePath
$env:TEMP = $TempPath
$env:TMP = $TempPath
$env:LOCALAPPDATA = $LocalAppDataPath
$env:APPDATA = $RoamingAppDataPath
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRoot '.cache\pycache'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

if (-not (Test-Path $PythonPath)) {
    throw "Python was not found on drive D: $PythonPath"
}

if (-not (Test-Path (Join-Path $VenvPath 'Scripts\python.exe'))) {
    & $PythonPath -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the virtual environment.' }
}

$VenvPython = Join-Path $VenvPath 'Scripts\python.exe'
$DomesticIndex = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$OfficialIndex = 'https://pypi.org/simple'

function Install-ProjectDependencies([string]$IndexUrl) {
    & $VenvPython -m pip install --index-url $IndexUrl --editable (Join-Path $ProjectRoot 'f2') --editable $ProjectRoot | Out-Host
    return [int]$LASTEXITCODE
}

Write-Host 'Installing dependencies from the Tsinghua PyPI mirror...'
$InstallCode = Install-ProjectDependencies $DomesticIndex
if ($InstallCode -ne 0) {
    Write-Warning 'The domestic mirror failed. Retrying with the official PyPI index.'
    $InstallCode = Install-ProjectDependencies $OfficialIndex
}
if ($InstallCode -ne 0) { throw "Dependency installation failed with exit code $InstallCode" }

Write-Host "Installation complete. Virtual environment: $VenvPath"
Write-Host 'Run .\scripts\start.ps1 to start the application.'

