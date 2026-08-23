@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "TOP_N=%~1"
set "CHARTS=%~2"

if "%TOP_N%"=="" set "TOP_N=0"
if "%CHARTS%"=="" set "CHARTS=30"

set "PYTHON_EXE="
set "PYTHON_PREFIX="

if exist "%CD%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found.
    echo Install Python or create .venv in this project folder.
    pause
    exit /b 1
)

echo ============================================
echo   Siyoon Swing Stock Screening
echo ============================================
echo   TOP_N  : %TOP_N%
echo   CHARTS : %CHARTS%
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan ^
    --top-n %TOP_N% ^
    --charts %CHARTS% ^
    --agent-top-n 30

if errorlevel 1 (
    echo.
    echo [ERROR] Screening failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Screening finished.
echo [DONE] Check results\YYYYMMDD\
echo [DONE] Agent files: results\YYYYMMDD\agent\candidates.json / candidates.md
pause
exit /b 0
