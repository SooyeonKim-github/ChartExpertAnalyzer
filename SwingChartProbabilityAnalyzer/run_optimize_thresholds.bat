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
echo [Swing Threshold Optimizer V2.1]
echo Entry Score x Max Entry Channel Position
echo D+10/D+20 + Hit + MAE composite objective
echo Development Walk-Forward + Strict 2026 Final Holdout
echo Long Purged Walk-Forward ^(252/63/63/20^)
echo.
set /p RANGE_FILE=Threshold input or range path ^(Enter=latest threshold_input^): 
if "%RANGE_FILE%"=="" (
    .venv\Scripts\python.exe run_threshold_optimizer.py
) else (
    .venv\Scripts\python.exe run_threshold_optimizer.py --range-file "%RANGE_FILE%"
)
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [ERROR] Swing threshold optimization failed.
pause
exit /b 1
