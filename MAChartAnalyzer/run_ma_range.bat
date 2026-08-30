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

echo [INFO] MA range backtest
echo [INFO] Date range : %DATE_RANGE%
echo [INFO] Top N      : %TOP_N%
echo [INFO] Sort by    : %SORT_BY%
echo [INFO] Forward    : D+60 trading bars
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
    --date-range "%DATE_RANGE%" ^
    --top-n "%TOP_N%" ^
    --sort-by "%SORT_BY%" ^
    --forward-bars 60

if errorlevel 1 (
    echo.
    echo [ERROR] MA range backtest failed.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

echo.
echo [DONE] MA range backtest finished.
echo [DONE] results\range_YYYYMMDD_YYYYMMDD\range_all_results.csv
echo [DONE] results\range_YYYYMMDD_YYYYMMDD\ma_range_backtest.xlsx
if /I not "%NO_PAUSE%"=="1" pause
exit /b 0
