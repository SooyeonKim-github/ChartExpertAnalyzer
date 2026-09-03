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

REM KR stock screening uses KOSPI + KOSDAQ only. Disable pykrx import-time login
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
    echo [ERROR] Required Python packages are missing.
    pause
    exit /b 1
)

set "NO_PAUSE=1"

echo ============================================
echo   KR Stock Screening - Independent Analyzers
echo ============================================
echo Universe : recent %LOOKBACK%-trading-day avg trading-value TOP %TOP_N%
echo Markets  : KOSPI + KOSDAQ
echo KJB / Swing / MA / Dynamic are evaluated independently.
echo Dynamic status uses the same V2.2 quality rules as Dynamic range.
echo ============================================
echo.

echo [0/5] Building shared KOSPI + KOSDAQ universe...
call "%ROOT%prepare_liquidity_universe.bat" screen "" "%TOP_N%" "%LOOKBACK%"
if errorlevel 1 goto RUN_FAILED
if not defined LIQUIDITY_UNIVERSE_XLSX goto RUN_FAILED
if not exist "%LIQUIDITY_UNIVERSE_XLSX%" goto RUN_FAILED

echo.
echo [1/5] KJB KR screen...
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
echo [2/5] Swing KR screen...
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
echo [3/5] MA KR screen...
pushd "%ROOT%MAChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan ^
    --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
    --top-n %TOP_N% ^
    --sort-by trading_value
if errorlevel 1 ( popd & goto RUN_FAILED )
popd

echo.
echo [4/5] Dynamic KR screen ^(same V2.2 CONFIRMED/WATCH rules as range^)...
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
echo [5/5] Updating confirmed history and returns...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\aggregate_confirmed_candidates.py"
if errorlevel 1 goto RUN_FAILED

"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\export_today_confirmed_candidates.py"
if errorlevel 1 goto RUN_FAILED

set "NO_PAUSE="
echo.
echo ============================================
echo [DONE] KR screening finished.
echo ============================================
echo Universe : %LIQUIDITY_UNIVERSE_XLSX%
echo History  : %ROOT%results\confirmed_candidates.csv
echo Today    : %ROOT%results\today_confiremd_candidates.csv
echo [INFO] KOSPI + KOSDAQ, recent %LOOKBACK%-day avg trading-value TOP %TOP_N%.
echo ============================================
pause
exit /b 0

:RUN_FAILED
set "NO_PAUSE="
echo.
echo ============================================
echo [FAILED] KR screening stopped because one step failed.
echo ============================================
pause
exit /b 1
