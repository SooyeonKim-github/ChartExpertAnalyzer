@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"
set "SORT_BY=%~3"
set "DAILY_TOP_N=%~4"

if "%DATE_RANGE%"=="" (
    echo Example: 20260401~20260531
    set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
)
if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    pause
    exit /b 1
)
if "%TOP_N%"=="" set "TOP_N=100"
if "%SORT_BY%"=="" set "SORT_BY=market_cap"
if "%DAILY_TOP_N%"=="" set "DAILY_TOP_N=5"

echo ============================================
echo   Combined Range Backtest - KJB + Siyoon
echo ============================================
echo Date range    : %DATE_RANGE%
echo Universe TOP N: %TOP_N%
echo Sort by       : %SORT_BY%
echo Combined TOP N: %DAILY_TOP_N% per day
echo Forward bars  : 60
echo Market context: Regime + Breadth + Shock phase
echo ============================================
echo.

set "NO_PAUSE=1"

echo [1/4] Running KJB range backtest...
call "%ROOT%KJBChartAnalyzer\run_swing_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 (
    echo.
    echo [ERROR] KJB range backtest failed.
    pause
    exit /b 1
)
cd /d "%ROOT%"

echo.
echo [2/4] Running Siyoon range backtest...
call "%ROOT%SwingChartProbabilityAnalyzer\run_swing_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 (
    echo.
    echo [ERROR] Siyoon range backtest failed.
    pause
    exit /b 1
)
cd /d "%ROOT%"

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
) else if exist "%ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe"
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
    echo [ERROR] Python was not found for combined result processing.
    pause
    exit /b 1
)

echo.
echo [3/4] Combining both analyzer results...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\run_combined_range_backtest.py" ^
    --date-range "%DATE_RANGE%" ^
    --daily-top-n "%DAILY_TOP_N%"
if errorlevel 1 (
    echo.
    echo [ERROR] Combined range processing failed.
    pause
    exit /b 1
)

echo.
echo [4/4] Applying market exposure filter...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\apply_market_filter.py" ^
    --date-range "%DATE_RANGE%" ^
    --daily-top-n "%DAILY_TOP_N%"
if errorlevel 1 (
    echo.
    echo [ERROR] Market filter processing failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo [DONE] Combined range + market filter finished.
echo ============================================
echo Output folder:
echo   results\combined_range_YYYYMMDD_YYYYMMDD\
echo.
echo Main files:
echo   combined_range_backtest.xlsx
echo   combined_range_summary.md
echo   combined_events.csv
echo   combined_daily_top%DAILY_TOP_N%.csv
echo   performance_event_weighted.csv
echo   performance_date_equal.csv
echo   performance_by_regime_event.csv
echo   performance_by_regime_date_equal.csv
echo.
echo Market filter files:
echo   market_filter_summary.md
echo   market_filter_daily.csv
echo   market_filter_decisions.csv
echo   market_filtered_candidates.csv
echo   performance_market_filter_event.csv
echo   performance_market_filter_date_equal.csv
echo ============================================
pause
exit /b 0
