@echo off
REM ============================================================
REM  Safari POS Pro - Silent Server Launcher
REM  Starts backend, waits for health, then exits
REM ============================================================

set "ROOT=%~dp0.."
cd /d "%ROOT%"

if not exist "logs" mkdir logs

set "LOG=%ROOT%\logs\startup.log"
set "SERVERLOG=%ROOT%\logs\server.log"
set "PIDFILE=%ROOT%\logs\server.pid"

REM Clear stale PID
del "%PIDFILE%" 2>nul

echo. >> "%LOG%"
echo [%date% %time%] ================================================ >> "%LOG%"
echo [%date% %time%] Starting Safari POS Pro backend >> "%LOG%"

REM Start server hidden, using python.exe (reliable logging)
REM pythonw avoids the black window but doesn't log reliably. Trade-off.
start "" /B "%ROOT%\venv\Scripts\pythonw.exe" "%ROOT%\backend\main.py"

REM Wait up to 20 seconds for backend to write its PID
set /a TRIES=0
:wait_pid
timeout /t 1 /nobreak >nul
set /a TRIES+=1
if exist "%PIDFILE%" goto :got_pid
if %TRIES% GEQ 20 goto :timeout

goto :wait_pid

:got_pid
set /p PID=<"%PIDFILE%"
echo [%date% %time%] Server PID: %PID% (after %TRIES%s) >> "%LOG%"
echo [%date% %time%] Launcher finished >> "%LOG%"
exit /b 0

:timeout
echo [%date% %time%] TIMEOUT: server did not write PID file >> "%LOG%"
exit /b 1
