@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"
set "SORT_BY=%~3"

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

echo ============================================
echo   Range Backtest - Independent Analyzers
echo ============================================
echo Date range    : %DATE_RANGE%
echo Universe TOP N: %TOP_N%
echo Sort by       : %SORT_BY%
echo Forward bars  : 60
echo.
echo KJB, Swing, and MA are evaluated independently.
echo No analyzer scores are combined and no consensus/BOTH logic is used.
echo ============================================
echo.

set "NO_PAUSE=1"

echo [1/4] Running KJB range backtest...
call "%ROOT%KJBChartAnalyzer\run_swing_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 (
    echo.
    echo [ERROR] KJB range backtest failed.
    goto RUN_FAILED
)
cd /d "%ROOT%"

echo.
echo [2/4] Running Swing range backtest...
call "%ROOT%SwingChartProbabilityAnalyzer\run_swing_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 (
    echo.
    echo [ERROR] Swing range backtest failed.
    goto RUN_FAILED
)
cd /d "%ROOT%"

echo.
echo [3/4] Running MA range backtest...
call "%ROOT%MAChartAnalyzer\run_ma_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 (
    echo.
    echo [ERROR] MA range backtest failed.
    goto RUN_FAILED
)
cd /d "%ROOT%"

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
) else if exist "%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%MAChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%MAChartAnalyzer\.venv\Scripts\python.exe"
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
    echo [ERROR] Python was not found for confirmed candidate aggregation.
    goto RUN_FAILED
)

echo.
echo [4/4] Collecting independent CONFIRMED signals...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\aggregate_range_confirmed_candidates.py" ^
    --date-range "%DATE_RANGE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Confirmed candidate aggregation failed.
    goto RUN_FAILED
)

set "NO_PAUSE="

echo.
echo ============================================
echo [DONE] All independent range backtests finished.
echo ============================================
echo [Confirmed summary]
echo   results\range_YYYYMMDD_YYYYMMDD\confirmed_candidates.csv
echo.
echo [KJB]
echo   KJBChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\
echo   chart_range_events.csv
echo   chart_range_status_summary_D1_D60.csv
echo   chart_range_backtest.xlsx
echo.
echo [Swing]
echo   SwingChartProbabilityAnalyzer\results\range_YYYYMMDD_YYYYMMDD\
echo   range_all_results.csv
echo   range_candidates.csv
echo   swing_range_backtest.xlsx
echo.
echo [MA]
echo   MAChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\
echo   range_all_results.csv
echo   range_candidates.csv
echo   ma_range_backtest.xlsx
echo.
echo [INFO] KJB, Swing, and MA remain independent. Combined scoring and market-filter steps are not executed.
echo ============================================
pause
exit /b 0

:RUN_FAILED
set "NO_PAUSE="
echo.
echo ============================================
echo [FAILED] Range workflow stopped because one step failed.
echo ============================================
pause
exit /b 1
