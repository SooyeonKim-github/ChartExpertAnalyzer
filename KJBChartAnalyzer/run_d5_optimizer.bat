@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo KJB D+5 Threshold Optimizer + Walk-forward
echo ==============================================================
echo Uses the latest results\range_* directory.
echo.

python d5_diagnostics.py
if errorlevel 1 (
    echo [ERROR] D+5 diagnostics failed.
    pause
    exit /b 1
)

python d5_threshold_optimizer.py --max-trials 250
if errorlevel 1 (
    echo [ERROR] D+5 optimizer failed.
    pause
    exit /b 1
)

echo.
echo [DONE] D+5 optimizer completed.
echo Check the latest KJBChartAnalyzer\results\range_* directory.
pause
