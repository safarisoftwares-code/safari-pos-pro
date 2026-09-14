# build.bat - Safari POS Pro EXE builder with data preservation
@echo off
REM Safari POS Pro - Smart rebuild script
REM Preserves database + backups across rebuilds

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "DIST=dist\SafariPOSPro"
set "DB_BACKUP=%TEMP%\safari_db_preserved.db"

echo.
echo === Safari POS Pro - Rebuild ===
echo.

REM Step 1: Back up current DB if it exists
if exist "%DIST%\database\safaripos.db" (
    echo [1/4] Backing up current database...
    copy "%DIST%\database\safaripos.db" "%DB_BACKUP%" >nul
    echo       Saved to %DB_BACKUP%
) else (
    echo [1/4] No existing DB to back up.
)

REM Step 2: Kill any running EXE
echo [2/4] Stopping any running EXE...
taskkill /F /IM SafariPOSPro.exe >nul 2>&1

REM Step 3: Rebuild
echo [3/4] Building EXE (5-8 minutes)...
call .\venv\Scripts\activate.bat
python -m PyInstaller SafariPOSPro.spec --clean --noconfirm
if errorlevel 1 (
    echo BUILD FAILED
    pause
    exit /b 1
)

REM Step 4: Restore DB
echo [4/4] Restoring database...
if exist "%DB_BACKUP%" (
    if not exist "%DIST%\database" mkdir "%DIST%\database"
    copy "%DB_BACKUP%" "%DIST%\database\safaripos.db" >nul
    echo       Restored database
    del "%DB_BACKUP%"
) else (
    echo       No DB to restore.
)

echo.
echo === Build complete! ===
echo Location: %DIST%
echo.
pause
