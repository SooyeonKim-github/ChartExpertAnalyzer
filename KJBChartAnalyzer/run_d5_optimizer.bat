@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo KJB D+5 Threshold Optimizer + Purged Walk-forward
echo ==============================================================
echo Uses the latest results\range_* directory.
echo D+5 diagnostics are rebuilt first, then 5 trading-date purge is applied.
echo.

python d5_diagnostics.py
if errorlevel 1 (
    echo [ERROR] D+5 diagnostics failed.
    pause
    exit /b 1
)

python d5_threshold_optimizer.py --max-trials 250 --purge-bars 5
if errorlevel 1 (
    echo [ERROR] D+5 optimizer failed.
    pause
    exit /b 1
)

echo.
echo [DONE] D+5 optimizer completed.
echo Check the latest KJBChartAnalyzer\results\range_* directory.
echo Main files:
echo   kjb_d5_optimizer_summary.csv
echo   kjb_d5_walkforward.csv
echo   kjb_d5_optimizer_best.json
echo   chart_range_events_d5_optimized.csv
pause
