@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"
set "SORT_BY=%~3"

if "%DATE_RANGE%"=="" (
    echo Example: 20260401~20260531
    set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
)
if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)
if "%TOP_N%"=="" set "TOP_N=100"
if "%SORT_BY%"=="" set "SORT_BY=market_cap"

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
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

echo [INFO] MA V2 range backtest
echo [INFO] Date range : %DATE_RANGE%
echo [INFO] Forward    : D+60 trading bars
echo [INFO] Entry      : D+1 open
echo [INFO] Exit       : signal-low stop / MA20 close / time exit
echo [INFO] Cooldown   : 10 trading bars
if defined LIQUIDITY_MEMBERSHIP_CSV (
    echo [INFO] Universe   : point-in-time liquidity TOP %LIQUIDITY_TOP_N%
    echo [INFO] Membership : %LIQUIDITY_MEMBERSHIP_CSV%
    "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
        --date-range "%DATE_RANGE%" ^
        --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
        --membership-csv "%LIQUIDITY_MEMBERSHIP_CSV%" ^
        --top-n 0 ^
        --sort-by "market_cap" ^
        --forward-bars 60 ^
        --cooldown-bars 10
) else (
    echo [INFO] Universe   : static TOP %TOP_N% by %SORT_BY%
    "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
        --date-range "%DATE_RANGE%" ^
        --top-n "%TOP_N%" ^
        --sort-by "%SORT_BY%" ^
        --forward-bars 60 ^
        --cooldown-bars 10
)

if errorlevel 1 (
    echo.
    echo [ERROR] MA range backtest failed.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

echo.
echo [DONE] MA V2 range backtest finished.
echo [DONE] results\range_YYYYMMDD_YYYYMMDD\range_all_results.csv
echo [DONE] results\range_YYYYMMDD_YYYYMMDD\trade_events.csv
echo [DONE] results\range_YYYYMMDD_YYYYMMDD\ma_range_backtest.xlsx
if /I not "%NO_PAUSE%"=="1" pause
exit /b 0
