@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [INFO] Creating virtual environment...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [Swing Threshold Ablation V2.2]
echo 2026 Final Holdout Diagnostic Only
echo CURRENT / SCORE ONLY / CHANNEL ONLY / FULL OPTIMIZED
echo.
set /p RANGE_FILE=Threshold input or range path ^(Enter=latest threshold_input^): 
if "%RANGE_FILE%"=="" (
    .venv\Scripts\python.exe run_threshold_ablation.py
) else (
    .venv\Scripts\python.exe run_threshold_ablation.py --range-file "%RANGE_FILE%"
)
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [ERROR] Swing threshold ablation failed.
pause
exit /b 1
