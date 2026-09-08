@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo KJB D+5 Threshold Optimizer V2
echo Soft Market Regime + Baseline-relative Purged Walk-forward
echo ==============================================================
echo Uses the latest results\range_* directory.
echo D+5 diagnostics are rebuilt first.
echo Market regime is used as a soft score adjustment, not a hard filter.
echo Confidence requires OOS improvement versus baseline.
echo.

python d5_diagnostics.py
if errorlevel 1 (
    echo [ERROR] D+5 diagnostics failed.
    pause
    exit /b 1
)

python d5_threshold_optimizer_v2.py --max-trials 300 --purge-bars 5
if errorlevel 1 (
    echo [ERROR] D+5 optimizer V2 failed.
    pause
    exit /b 1
)

echo.
echo [DONE] D+5 optimizer V2 completed.
echo Check the latest KJBChartAnalyzer\results\range_* directory.
echo Main files:
echo   kjb_d5_optimizer_v2_summary.csv
echo   kjb_d5_walkforward_v2.csv
echo   kjb_d5_optimizer_v2_best.json
echo   chart_range_events_d5_optimized_v2.csv
pause
