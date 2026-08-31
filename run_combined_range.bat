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

set "NO_PAUSE=1"
echo ============================================
echo   Range Backtest - Independent Analyzers
echo ============================================
echo Date range     : %DATE_RANGE%
echo Universe TOP N : %TOP_N%
echo Universe rule  : recent 20-trading-day avg trading value, point-in-time
echo Markets         : KOSPI + KOSDAQ
echo Forward bars    : 60
echo.
echo KJB, Swing, and MA are evaluated independently.
echo No analyzer scores are combined and no consensus/BOTH logic is used.
echo ============================================
echo.

echo [0/7] Preparing shared point-in-time liquidity universe...
call "%ROOT%prepare_liquidity_universe.bat" range "%DATE_RANGE%" "%TOP_N%" 20
if errorlevel 1 goto RUN_FAILED
if not defined LIQUIDITY_UNIVERSE_XLSX goto RUN_FAILED
if not defined LIQUIDITY_MEMBERSHIP_CSV goto RUN_FAILED

set "FILTER_PYTHON=%LIQ_PYTHON_EXE%"
set "FILTER_PREFIX=%LIQ_PYTHON_PREFIX%"
if "%FILTER_PYTHON%"=="" (
    echo [ERROR] Python was not resolved by liquidity preparation.
    goto RUN_FAILED
)

echo.
echo [1/7] Running KJB on shared universe union...
call "%ROOT%KJBChartAnalyzer\run_swing_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 goto RUN_FAILED
cd /d "%ROOT%"

echo.
echo [2/7] Applying KJB point-in-time membership...
"%FILTER_PYTHON%" %FILTER_PREFIX% "%ROOT%scripts\filter_liquidity_membership.py" ^
    --analyzer kjb --date-range "%DATE_RANGE%" --membership-csv "%LIQUIDITY_MEMBERSHIP_CSV%" ^
    --top-n "%TOP_N%" --lookback 20 --forward-bars 60
if errorlevel 1 goto RUN_FAILED

echo.
echo [3/7] Running Swing on shared universe union...
call "%ROOT%SwingChartProbabilityAnalyzer\run_swing_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 goto RUN_FAILED
cd /d "%ROOT%"

echo.
echo [4/7] Applying Swing point-in-time membership...
"%FILTER_PYTHON%" %FILTER_PREFIX% "%ROOT%scripts\filter_liquidity_membership.py" ^
    --analyzer swing --date-range "%DATE_RANGE%" --membership-csv "%LIQUIDITY_MEMBERSHIP_CSV%" ^
    --top-n "%TOP_N%" --lookback 20 --forward-bars 60
if errorlevel 1 goto RUN_FAILED

echo.
echo [5/7] Running MA V3 stateful scale-in backtest...
call "%ROOT%MAChartAnalyzer\run_ma_range.bat" "%DATE_RANGE%" "%TOP_N%" "%SORT_BY%"
if errorlevel 1 goto RUN_FAILED
cd /d "%ROOT%"

echo.
echo [6/7] Validating MA V3 outputs...
if not exist "%ROOT%MAChartAnalyzer\results\range_%DATE_RANGE:~0,8%_%DATE_RANGE:~-8%\trade_events.csv" (
    echo [ERROR] MA trade_events.csv was not created.
    goto RUN_FAILED
)
if not exist "%ROOT%MAChartAnalyzer\results\range_%DATE_RANGE:~0,8%_%DATE_RANGE:~-8%\position_entries.csv" (
    echo [ERROR] MA position_entries.csv was not created.
    goto RUN_FAILED
)
echo [OK] MA V3 position/trade events created.

echo.
echo [7/7] Collecting independent confirmed signals...
"%FILTER_PYTHON%" %FILTER_PREFIX% "%ROOT%scripts\aggregate_range_confirmed_candidates.py" --date-range "%DATE_RANGE%"
if errorlevel 1 goto RUN_FAILED

set "NO_PAUSE="
echo.
echo ============================================
echo [DONE] All independent range backtests finished.
echo ============================================
echo [Universe]
echo   %LIQUIDITY_MEMBERSHIP_CSV%
echo.
echo [Confirmed summary]
echo   results\range_YYYYMMDD_YYYYMMDD\confirmed_candidates.csv
echo.
echo [MA V3]
echo   MAChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\range_all_results.csv
echo   MAChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\range_candidates.csv
echo   MAChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\position_entries.csv
echo   MAChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\trade_events.csv
echo   MAChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD\ma_range_backtest.xlsx
echo.
echo [INFO] KJB, Swing, and MA remain independent.
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
