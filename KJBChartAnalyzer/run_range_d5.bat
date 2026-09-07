@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo KJB D+5 Range Backtest + V2 Diagnostics + Walk-forward Optimizer
echo ==============================================================
echo Example: 20200101~20260904
set /p DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: 

if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    pause
    exit /b 1
)

echo.
echo [1/3] Running KJB range backtest...
python main_range.py --date-range "%DATE_RANGE%" --top-n 100 --sort-by market_cap --forward-bars 60 --cooldown-bars 0
if errorlevel 1 (
    echo [ERROR] KJB range backtest failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Running D+5 V2 diagnostics...
python d5_diagnostics.py
if errorlevel 1 (
    echo [ERROR] D+5 diagnostics failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Running D+5 threshold optimizer + walk-forward...
python d5_threshold_optimizer.py --max-trials 250
if errorlevel 1 (
    echo [ERROR] D+5 optimizer failed.
    pause
    exit /b 1
)

echo.
echo ==============================================================
echo [DONE] KJB D+5 V2 analysis completed.
echo Check KJBChartAnalyzer\results\range_YYYYMMDD_YYYYMMDD
echo ==============================================================
pause
