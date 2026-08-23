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
    echo Install Python or create .venv in this project folder.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

echo [INFO] KJB range backtest
echo [INFO] Project folder     : %CD%
echo [INFO] Date range         : %DATE_RANGE%
echo [INFO] Top N              : %TOP_N%
echo [INFO] Sort by            : %SORT_BY%
echo [INFO] Forward performance: D+1 ~ D+60 trading bars
echo [INFO] Market regime      : Naver KOSPI/KOSDAQ point-in-time
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
    --date-range "%DATE_RANGE%" ^
    --top-n "%TOP_N%" ^
    --sort-by "%SORT_BY%" ^
    --forward-bars 60

if errorlevel 1 (
    echo.
    echo [ERROR] KJB range backtest failed.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

echo.
echo [DONE] KJB range backtest finished.
echo [DONE] Excel  : results\range_YYYYMMDD_YYYYMMDD\chart_range_backtest.xlsx
echo [DONE] Regime : results\range_YYYYMMDD_YYYYMMDD\market_regime_daily.csv
if /I not "%NO_PAUSE%"=="1" pause
exit /b 0
