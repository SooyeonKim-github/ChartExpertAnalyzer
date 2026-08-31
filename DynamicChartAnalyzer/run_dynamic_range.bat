@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"
set "SORT_BY=%~3"

if "%DATE_RANGE%"=="" (
    echo Example: 20230401~20260831
    set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
)

if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    pause
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
    pause
    exit /b 1
)

echo [INFO] Project folder: %CD%
echo [INFO] Date range: %DATE_RANGE%
echo [INFO] Top N: %TOP_N%
echo [INFO] Sort by: %SORT_BY%
echo [INFO] Mode: Dynamic LONG V2.1 lecture/quality split
echo [INFO] Lecture score: RSI + MACD + Ichimoku, normalized 0~100
echo [INFO] Quality score: Trend + RS + Volume + Price Structure + Market + Risk, normalized 0~100
echo [INFO] Market universe: KJB TickerUniverseService + KOSPI_Info.xlsx
echo [INFO] Stock OHLCV: per-ticker get_market_ohlcv_by_date + cache
echo [INFO] Market proxy: KOSPI=069500 / KOSDAQ=229200
echo [INFO] Entry split unchanged: Stage1 10%% / Stage2 20%% / Stage3 70%% = 1:2:7
echo [INFO] Quality labels: CONFIRMED ^>= 70 / WATCH ^>= 55 / else REJECT
echo [INFO] Daily LONG rank: quality_score first, lecture_score tie-breaker
echo [INFO] Forward performance: D+1 ~ D+60 trading bars
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main_range_kjb.py ^
    --date-range "%DATE_RANGE%" ^
    --top-n "%TOP_N%" ^
    --sort-by "%SORT_BY%" ^
    --forward-bars 60 ^
    --capital 10000000 ^
    --v2-confirmed-score 70 ^
    --v2-watch-score 55

if errorlevel 1 (
    echo.
    echo [ERROR] Dynamic LONG V2.1 range backtest failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Dynamic LONG V2.1 range backtest finished.
echo [DONE] Workbook: results\range_YYYYMMDD_YYYYMMDD\dynamic_range_backtest.xlsx
echo [DONE] Events + V2.1 features: results\range_YYYYMMDD_YYYYMMDD\dynamic_range_events.csv
echo [DONE] V2.1 summary: results\range_YYYYMMDD_YYYYMMDD\dynamic_long_v2_summary.csv
echo [DONE] V2.1 candidates: results\range_YYYYMMDD_YYYYMMDD\dynamic_long_v2_candidates.csv
pause
exit /b 0