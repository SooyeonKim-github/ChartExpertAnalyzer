@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "DATE_RANGE=%~1"
set "TOP_N=%~2"
if "%DATE_RANGE%"=="" (
    echo Example: 20260101~20260821
    set /p "DATE_RANGE=US date range YYYYMMDD~YYYYMMDD: "
)
if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    pause
    exit /b 1
)
if "%TOP_N%"=="" set "TOP_N=300"

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

"%PYTHON_EXE%" %PYTHON_PREFIX% -c "import pandas, numpy, yfinance, matplotlib, openpyxl, yaml" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Required Python packages are missing.
    echo Run:
    echo   "%PYTHON_EXE%" %PYTHON_PREFIX% -m pip install -r "%ROOT%KJBChartAnalyzer\requirements.txt"
    pause
    exit /b 1
)

set "US_UNIVERSE_CSV=%ROOT%data\us_marketcap_top300.csv"
set "US_UNIVERSE_TXT=%ROOT%data\us_marketcap_top300.txt"

echo ============================================
echo   US Range Backtest - Independent Analyzers
echo ============================================
echo Date range  : %DATE_RANGE%
echo Universe    : CURRENT US market-cap TOP %TOP_N%
echo Markets     : NASDAQ + NYSE + NYSE American
echo Benchmark   : S^&P 500 (^GSPC)
echo Forward bars: 60
echo.
echo KJB / Swing / MA / Dynamic are evaluated independently.
echo Dynamic CONFIRMED = LONG Stage 3 entry event.
echo No consensus/BOTH score is used.
echo.
echo [IMPORTANT]
echo Historical runs use today's TOP %TOP_N% membership.
echo This is NOT historical point-in-time market-cap membership.
echo ============================================
echo.

echo [0/5] Building current US market-cap universe...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\build_us_marketcap_universe.py" ^
    --top-n %TOP_N% ^
    --out-csv "%US_UNIVERSE_CSV%" ^
    --out-txt "%US_UNIVERSE_TXT%"
if errorlevel 1 goto RUN_FAILED

echo.
echo [1/5] KJB US range...
pushd "%ROOT%KJBChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_range_us.py ^
    --date-range "%DATE_RANGE%" ^
    --universe-csv "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --forward-bars 60 ^
    --cooldown-bars 0
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [2/5] Swing US range...
pushd "%ROOT%SwingChartProbabilityAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_range_us.py ^
    --date-range "%DATE_RANGE%" ^
    --info-excel "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --sort-by market_cap ^
    --forward-bars 60
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [3/5] MA US range...
pushd "%ROOT%MAChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_range_us.py ^
    --date-range "%DATE_RANGE%" ^
    --info-excel "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --sort-by market_cap ^
    --forward-bars 60
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [4/5] Dynamic US range...
pushd "%ROOT%DynamicChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_range_us.py ^
    --date-range "%DATE_RANGE%" ^
    --universe-csv "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --forward-bars 60
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [5/5] Aggregating confirmed US range candidates...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\aggregate_us_candidates.py" ^
    --mode range ^
    --date-range "%DATE_RANGE%"
if errorlevel 1 goto RUN_FAILED

echo.
echo ============================================
echo [DONE] US range backtests finished.
echo ============================================
echo Universe : data\us_marketcap_top300.csv
echo KJB      : KJBChartAnalyzer\results_us\range_YYYYMMDD_YYYYMMDD\
echo Swing    : SwingChartProbabilityAnalyzer\results_us\range_YYYYMMDD_YYYYMMDD\
echo MA       : MAChartAnalyzer\results_us\range_YYYYMMDD_YYYYMMDD\
echo Dynamic  : DynamicChartAnalyzer\results_us\range_YYYYMMDD_YYYYMMDD\
echo Summary  : results_us\range_YYYYMMDD_YYYYMMDD\confirmed_candidates.csv
echo ============================================
pause
exit /b 0

:RUN_FAILED
echo.
echo ============================================
echo [FAILED] US range workflow stopped because one step failed.
echo ============================================
pause
exit /b 1
