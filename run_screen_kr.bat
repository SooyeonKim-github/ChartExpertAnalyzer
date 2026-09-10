@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "TOP_N=%~1"
set "CHARTS=%~2"
if "%TOP_N%"=="" set "TOP_N=200"
if "%CHARTS%"=="" set "CHARTS=30"
set "LOOKBACK=20"
set "LEADER_TOP_N=100"
set "LEADER_RC=0"
set "MATERIAL_RC=0"

REM KR chart screening uses KOSPI + KOSDAQ only. Disable pykrx import-time login
REM inside this setlocal scope so malformed KRX login responses cannot abort startup.
set "KRX_ID="
set "KRX_PW="

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%MAChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%MAChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%DynamicChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%DynamicChartAnalyzer\.venv\Scripts\python.exe"
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
    pause
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_PREFIX% -c "import pandas, numpy, matplotlib, openpyxl, yaml, pykrx" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Required chart Python packages are missing.
    pause
    exit /b 1
)

set "NO_PAUSE=1"

echo ============================================
echo   KR Daily Analysis - Independent Pipelines
echo ============================================
echo [CHART]
echo   KJB / Swing / MA / Dynamic

echo   Output : results\today_confirmed_^<scan_date^>.csv
echo.
echo [LEADER ISSUE]
echo   LeaderStockAnalyzer independently

echo   Output : results\leader\today_issue_^<scan_date^>.csv
echo.
echo [MATERIAL ISSUE]
echo   MaterialAnalyzer independently

echo   Output : results\material\today_issue_^<market_date^>.csv
echo ============================================
echo.

REM ============================================================
REM PIPELINE A: chart analyzers only
REM ============================================================
echo [0/9] Building shared KOSPI + KOSDAQ chart universe...
call "%ROOT%prepare_liquidity_universe.bat" screen "" "%TOP_N%" "%LOOKBACK%"
if errorlevel 1 goto RUN_FAILED
if not defined LIQUIDITY_UNIVERSE_XLSX goto RUN_FAILED
if not exist "%LIQUIDITY_UNIVERSE_XLSX%" goto RUN_FAILED

echo.
echo [1/9] KJB KR screen - D+5 FINAL V1...
pushd "%ROOT%KJBChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% app.py screen-top100 ^
    --provider pykrx ^
    --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
    --top-n %TOP_N% ^
    --sort-by trading_value ^
    --period 5y ^
    --agent-top-n 30 ^
    --out output\top100_screen.csv ^
    --universe-out output\top100_universe.csv ^
    --report output\top100_screen.html
if errorlevel 1 ( popd & goto RUN_FAILED )
popd

echo.
echo [2/9] Swing KR screen...
pushd "%ROOT%SwingChartProbabilityAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan ^
    --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
    --top-n %TOP_N% ^
    --sort-by trading_value ^
    --charts %CHARTS% ^
    --agent-top-n 30
if errorlevel 1 ( popd & goto RUN_FAILED )
popd

echo.
echo [3/9] MA KR screen...
pushd "%ROOT%MAChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan ^
    --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
    --top-n %TOP_N% ^
    --sort-by trading_value
if errorlevel 1 ( popd & goto RUN_FAILED )
popd

echo.
echo [4/9] Dynamic KR screen ^(same V2.2 CONFIRMED/WATCH rules as range^)...
pushd "%ROOT%DynamicChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_screen_kr.py ^
    --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
    --top-n %TOP_N% ^
    --sort-by trading_value ^
    --years 5 ^
    --confirmed-score 70 ^
    --watch-score 55
if errorlevel 1 ( popd & goto RUN_FAILED )
popd

echo.
echo [5/9] Exporting chart today_confirmed...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\aggregate_confirmed_candidates.py"
if errorlevel 1 goto RUN_FAILED
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\export_today_confirmed_candidates.py"
if errorlevel 1 goto RUN_FAILED

REM ============================================================
REM PIPELINE B: LeaderStockAnalyzer only - independent of charts
REM ============================================================
echo.
echo [6/9] LeaderStockAnalyzer independent issue run...
call "%ROOT%scripts\run_leader_issue.bat" "%LEADER_TOP_N%"
if errorlevel 1 set "LEADER_RC=1"

REM ============================================================
REM PIPELINE C: MaterialAnalyzer only - independent of charts/leader
REM ============================================================
echo.
echo [7/9] MaterialAnalyzer independent issue run...
call "%ROOT%scripts\run_material_issue.bat"
if errorlevel 1 set "MATERIAL_RC=1"

REM ============================================================
REM Daily outputs are committed without unrelated staged changes.
REM ============================================================
echo.
echo [8/9] Committing and pushing daily result files...
call "%ROOT%scripts\push_daily_results.bat"

echo.
echo [9/9] Final summary...
set "NO_PAUSE="
echo ============================================
echo [DONE] KR daily analysis finished.
echo ============================================
echo Chart confirmed : %ROOT%results\today_confirmed_^<scan_date^>.csv
echo Leader issue    : %ROOT%results\leader\today_issue_^<scan_date^>.csv
echo Material issue  : %ROOT%results\material\today_issue_^<market_date^>.csv
echo.
echo [INFO] Chart / Leader / Material pipelines do not use each other's result as input.
echo [INFO] Leader and Material failures do not delete or invalidate chart output.
if "%LEADER_RC%"=="1" echo [WARN] Leader issue pipeline failed. Check its log above.
if "%MATERIAL_RC%"=="1" echo [WARN] Material issue pipeline failed. Check its log above.
echo [INFO] Daily result files are automatically committed and pushed when Git is available.
echo ============================================
pause
exit /b 0

:RUN_FAILED
set "NO_PAUSE="
echo.
echo ============================================
echo [FAILED] Chart screening stopped because one chart step failed.
echo Leader / Material issue pipelines were not started after this chart failure.
echo ============================================
pause
exit /b 1
