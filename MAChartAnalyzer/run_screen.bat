@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "TOP_N=%~1"
if "%TOP_N%"=="" set "TOP_N=0"

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
    if not defined NO_PAUSE pause
    exit /b 1
)

echo ============================================
echo   MA Chart Analyzer - BUY Screening
echo ============================================
echo   TOP_N : %TOP_N%
echo   RULE  : 200MA direction + short-MA timing
echo   STATE : CONFIRMED / WATCH / REJECTED
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan --top-n %TOP_N%

if errorlevel 1 (
    echo.
    echo [ERROR] MA screening failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo.
echo [DONE] MA screening finished.
echo [DONE] Check results\YYYYMMDD\scan_results.csv
if not defined NO_PAUSE pause
exit /b 0
