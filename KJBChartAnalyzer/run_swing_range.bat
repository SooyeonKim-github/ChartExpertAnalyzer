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
if "%SORT_BY%"=="" set "SORT_BY=liquidity_20d"

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

set "RUN_TOP_N=%TOP_N%"
set "RUN_SORT_BY=%SORT_BY%"
set "RUN_INFO_EXCEL=KOSPI_Info.xlsx"

if /I "%SORT_BY%"=="liquidity_20d" (
    if not defined LIQUIDITY_MEMBERSHIP_CSV (
        call "%~dp0..\prepare_liquidity_universe.bat" range "%DATE_RANGE%" "%TOP_N%" 20
        if errorlevel 1 (
            echo [ERROR] Liquidity universe preparation failed.
            if /I not "%NO_PAUSE%"=="1" pause
            exit /b 1
        )
    )
    set "RUN_TOP_N=0"
    set "RUN_SORT_BY=market_cap"
    set "RUN_INFO_EXCEL=%LIQUIDITY_UNIVERSE_XLSX%"
)

echo [INFO] KJB range backtest
echo [INFO] Project folder     : %CD%
echo [INFO] Date range         : %DATE_RANGE%
echo [INFO] Top N              : %TOP_N%
echo [INFO] Sort by            : %SORT_BY%
if /I "%SORT_BY%"=="liquidity_20d" echo [INFO] Universe           : recent 20-trading-day avg trading value TOP%TOP_N% per date
if /I "%SORT_BY%"=="liquidity_20d" echo [INFO] Union Excel        : %LIQUIDITY_UNIVERSE_XLSX%
echo [INFO] Forward performance: D+1 ~ D+60 trading bars
echo [INFO] Market regime      : Naver KOSPI/KOSDAQ point-in-time
echo [INFO] KJB status         : CONFIRMED / WATCH / REJECTED V1
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main_range.py ^
    --date-range "%DATE_RANGE%" ^
    --top-n "%RUN_TOP_N%" ^
    --sort-by "%RUN_SORT_BY%" ^
    --info-excel "%RUN_INFO_EXCEL%" ^
    --forward-bars 60

if errorlevel 1 (
    echo.
    echo [ERROR] KJB range backtest failed.
    if /I not "%NO_PAUSE%"=="1" pause
    exit /b 1
)

if /I "%SORT_BY%"=="liquidity_20d" (
    echo.
    echo [POST] Applying daily liquidity TOP%TOP_N% membership and recalculating KJB ranks/breadth...
    "%PYTHON_EXE%" %PYTHON_PREFIX% "%~dp0..\scripts\filter_liquidity_membership.py" ^
        --analyzer kjb ^
        --date-range "%DATE_RANGE%" ^
        --membership-csv "%LIQUIDITY_MEMBERSHIP_CSV%" ^
        --top-n "%TOP_N%" ^
        --lookback 20 ^
        --forward-bars 60
    if errorlevel 1 (
        echo [ERROR] KJB liquidity membership filter failed.
        if /I not "%NO_PAUSE%"=="1" pause
        exit /b 1
    )
)

echo.
echo [DONE] KJB range backtest finished.
echo [DONE] Excel  : results\range_YYYYMMDD_YYYYMMDD\chart_range_backtest.xlsx
echo [DONE] Status : results\range_YYYYMMDD_YYYYMMDD\chart_range_status_summary_D1_D60.csv
echo [DONE] Regime : results\range_YYYYMMDD_YYYYMMDD\market_regime_daily.csv
if /I "%SORT_BY%"=="liquidity_20d" echo [DONE] Universe: recent 20-trading-day avg trading value TOP%TOP_N% point-in-time
if /I not "%NO_PAUSE%"=="1" pause
exit /b 0
