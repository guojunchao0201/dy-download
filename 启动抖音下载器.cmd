@echo off
setlocal

cd /d "%~dp0"
set "APP_URL=http://127.0.0.1:8765"
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

title Douyin Archiver

rem If the service is already running, only open the browser.
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%/api/status' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
    start "" "%APP_URL%"
    exit /b 0
)

rem Install into the D-drive project environment on first launch.
if not exist "%VENV_PYTHON%" (
    echo First launch: installing dependencies into the project virtual environment...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
    if errorlevel 1 (
        echo.
        echo Installation failed. Review the messages above.
        pause
        exit /b 1
    )
)

echo Starting Douyin Archiver...
echo The browser will open at %APP_URL%
echo Keep this window open. Press Ctrl+C to stop the service.
echo.

rem Open the browser after Uvicorn has had time to bind the local port.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%APP_URL%'"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"

echo.
echo The service has stopped.
pause

