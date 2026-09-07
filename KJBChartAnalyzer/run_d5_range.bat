@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"
set "SORT_BY=%~3"

if "%DATE_RANGE%"=="" (
    echo Example: 20260101~20260904
    set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
)
if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)
if "%TOP_N%"=="" set "TOP_N=100"
if "%SORT_BY%"=="" set "SORT_BY=market_cap"

for /f "tokens=1,2 delims=~" %%A in ("%DATE_RANGE%") do (
    set "START_DATE=%%A"
    set "END_DATE=%%B"
)

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

echo ==============================================================
echo  KJB D+5 Range + Overextension Diagnostics
echo ==============================================================
echo [INFO] Date range : %DATE_RANGE%
echo [INFO] Top N      : %TOP_N%
echo [INFO] Sort by    : %SORT_BY%
echo [INFO] D5 score   : Raw Selection - OverextensionPenalty

echo.
echo [1/2] Running KJB range backtest...
if defined LIQUIDITY_UNIVERSE_XLSX (
    "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
        --date-range "%DATE_RANGE%" ^
        --top-n 0 ^
        --sort-by "market_cap" ^
        --forward-bars 60 ^
        --info-excel "%LIQUIDITY_UNIVERSE_XLSX%"
) else (
    "%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
        --date-range "%DATE_RANGE%" ^
        --top-n "%TOP_N%" ^
        --sort-by "%SORT_BY%" ^
        --forward-bars 60
)
if errorlevel 1 (
    echo [ERROR] KJB range backtest failed.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

set "RESULT_DIR=results\range_%START_DATE%_%END_DATE%"
set "RANGE_FILE=%RESULT_DIR%\chart_range_events.csv"

echo.
echo [2/2] Building D+5 diagnostics...
"%PYTHON_EXE%" %PYTHON_PREFIX% run_d5_diagnostics.py --range-file "%RANGE_FILE%"
if errorlevel 1 (
    echo [ERROR] D+5 diagnostics failed.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

echo.
echo [DONE] KJB D+5 range finished.
echo [DONE] Events : %RESULT_DIR%\chart_range_events_d5.csv
echo [DONE] Status : %RESULT_DIR%\d5_status_summary.csv
echo [DONE] Buckets: %RESULT_DIR%\d5_diagnostics_buckets.csv
echo [DONE] TopN   : %RESULT_DIR%\d5_diagnostics_topn.csv
if /I not "%NO_PAUSE%"=="1" pause
exit /b 0
