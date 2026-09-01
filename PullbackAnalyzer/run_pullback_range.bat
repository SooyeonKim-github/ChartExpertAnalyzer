@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

echo Example: 20260101~20260831
set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
if "%DATE_RANGE%"=="" exit /b 1

set "TOP_N=100"
set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        set "PYTHON_EXE=python"
    )
)

if defined LIQUIDITY_UNIVERSE_XLSX (
    if defined LIQUIDITY_MEMBERSHIP_CSV (
        "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py --date-range "%DATE_RANGE%" --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" --membership-csv "%LIQUIDITY_MEMBERSHIP_CSV%" --top-n %TOP_N% --sort-by trading_value --forward-bars 60
    ) else (
        "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py --date-range "%DATE_RANGE%" --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" --top-n %TOP_N% --sort-by trading_value --forward-bars 60
    )
) else (
    "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py --date-range "%DATE_RANGE%" --top-n %TOP_N% --sort-by trading_value --forward-bars 60
)
pause
