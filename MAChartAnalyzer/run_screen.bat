@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "TOP_N=%~1"
if "%TOP_N%"=="" set "TOP_N=100"

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
echo   MA Chart Analyzer V2 Screening
echo ============================================
echo   STATUS: STRONG_CONFIRMED ^> CONFIRMED ^> WATCH ^> REJECTED
echo   CORE  : 200MA direction + box breakout / true retest / strong pullback
echo   WATCH : squeeze and ordinary pullback remain setup-only
echo.

if defined LIQUIDITY_UNIVERSE_XLSX (
    "%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" --top-n 0
) else (
    "%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan --top-n %TOP_N%
)
if errorlevel 1 (
    echo [ERROR] MA screening failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo [DONE] Check results\YYYYMMDD\
if not defined NO_PAUSE pause
exit /b 0
