@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo KJB D+5 Range Backtest + Diagnostics
echo ==============================================================
echo Example: 20200101~20260904
set /p DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: 

if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    pause
    exit /b 1
)

echo.
echo [1/2] Running KJB range backtest...
python main_range.py --date-range "%DATE_RANGE%" --top-n 100 --sort-by market_cap --forward-bars 60 --cooldown-bars 0
if errorlevel 1 (
    echo [ERROR] KJB range backtest failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Running D+5 diagnostics and overextension penalty...
python d5_diagnostics.py
if errorlevel 1 (
    echo [ERROR] D+5 diagnostics failed.
    pause
    exit /b 1
)

echo.
echo ==============================================================
echo [DONE] KJB D+5 range analysis completed.
echo Check KJBChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD
echo ==============================================================
pause
