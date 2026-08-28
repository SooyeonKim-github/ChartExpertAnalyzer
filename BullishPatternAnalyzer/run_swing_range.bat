@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"

if "%DATE_RANGE%"=="" set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
if "%TOP_N%"=="" set "TOP_N=100"
if "%DATE_RANGE%"=="" exit /b 1

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

if not defined PYTHON_EXE (
    echo [ERROR] Python was not found.
    if not defined NO_PAUSE pause
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py --date-range "%DATE_RANGE%" --top-n %TOP_N%
if errorlevel 1 (
    echo [ERROR] BullishPatternAnalyzer range backtest failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo [DONE] Check results\range_YYYYMMDD_YYYYMMDD\
if not defined NO_PAUSE pause
exit /b 0
