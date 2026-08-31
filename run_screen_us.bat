@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "TOP_N=%~1"
set "CHARTS=%~2"
if "%TOP_N%"=="" set "TOP_N=300"
if "%CHARTS%"=="" set "CHARTS=30"

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
echo   US Stock Screening - Independent Analyzers
echo ============================================
echo Universe : current US market-cap TOP %TOP_N%
echo Markets  : NASDAQ + NYSE + NYSE American
echo Benchmark: S^&P 500 (^GSPC)
echo KJB / Swing / MA / Dynamic are evaluated independently.
echo Dynamic CONFIRMED = active LONG Stage 3.
echo ============================================
echo.

echo [0/5] Building current US market-cap universe...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\build_us_marketcap_universe.py" ^
    --top-n %TOP_N% ^
    --out-csv "%US_UNIVERSE_CSV%" ^
    --out-txt "%US_UNIVERSE_TXT%"
if errorlevel 1 goto RUN_FAILED

echo.
echo [1/5] KJB US screen...
pushd "%ROOT%KJBChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_us.py ^
    --universe-csv "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --period 5y ^
    --agent-top-n 30
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [2/5] Swing US screen...
pushd "%ROOT%SwingChartProbabilityAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_us.py scan ^
    --info-excel "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --sort-by market_cap ^
    --charts %CHARTS% ^
    --agent-top-n 30
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [3/5] MA US screen...
pushd "%ROOT%MAChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_us.py scan ^
    --info-excel "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --sort-by market_cap
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [4/5] Dynamic US screen...
pushd "%ROOT%DynamicChartAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main_screen_us.py ^
    --universe-csv "%US_UNIVERSE_CSV%" ^
    --top-n %TOP_N% ^
    --period 5y
if errorlevel 1 (
    popd
    goto RUN_FAILED
)
popd

echo.
echo [5/5] Aggregating confirmed US candidates...
"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\aggregate_us_candidates.py" --mode screen
if errorlevel 1 goto RUN_FAILED

echo.
echo ============================================
echo [DONE] US screening finished.
echo ============================================
echo Universe : data\us_marketcap_top300.csv
echo KJB      : KJBChartAnalyzer\output_us\
echo Swing    : SwingChartProbabilityAnalyzer\results_us\YYYYMMDD\
echo MA       : MAChartAnalyzer\results_us\YYYYMMDD\
echo Dynamic  : DynamicChartAnalyzer\results_us\YYYYMMDD\
echo Summary  : results_us\confirmed_candidates.csv
echo.
echo [WARNING] TOP %TOP_N% is the current market-cap snapshot.
echo ============================================
pause
exit /b 0

:RUN_FAILED
echo.
echo ============================================
echo [FAILED] US screening stopped because one step failed.
echo ============================================
pause
exit /b 1
