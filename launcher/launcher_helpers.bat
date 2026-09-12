@echo off
REM ============================================================
REM  Safari POS Pro - Launcher Helpers
REM ============================================================

set "ROOT=%~dp0.."
set "PIDFILE=%ROOT%\logs\server.pid"
set "LOG=%ROOT%\logs\startup.log"
set "PORT=8001"

if /i "%~1"=="is_running" goto :is_running
if /i "%~1"=="kill" goto :kill
if /i "%~1"=="wait_health" goto :wait_health
exit /b 0

:is_running
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%PORT%/health' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

REM ------------------------------------------------------------
REM  :kill — kill backend by PID file, then fallback to venv-scoped sweep
REM ------------------------------------------------------------
:kill
echo [%date% %time%] Kill requested >> "%LOG%"

REM Try PID file first (fast path)
if exist "%PIDFILE%" (
    set /p PID=<"%PIDFILE%"
)

REM Always do a scoped sweep: kill any pythonw whose path is under our venv
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.ExecutablePath -like '*\safari-pos-pro\venv\*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

REM Also kill the real backend (system pythonw running our main.py)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*safari-pos-pro\backend\main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

del "%PIDFILE%" >nul 2>&1
echo [%date% %time%] Server killed >> "%LOG%"
exit /b 0

REM ------------------------------------------------------------
REM  :wait_health
REM ------------------------------------------------------------
:wait_health
set /a COUNT=0
:health_loop
set /a COUNT+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%PORT%/health' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [%date% %time%] Health OK after %COUNT% tries >> "%LOG%"
    exit /b 0
)
if %COUNT% GEQ 30 (
    echo [%date% %time%] Health TIMEOUT after %COUNT% tries >> "%LOG%"
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :health_loop
