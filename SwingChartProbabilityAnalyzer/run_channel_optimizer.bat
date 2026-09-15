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
echo [Swing Channel Optimizer V2.3]
echo Entry Score fixed at 90
echo Channel Grid: 0.45 / 0.50 / 0.52 / 0.55 / 0.58
echo Development Walk-Forward only for selection
echo 2026 is reference-only
echo.
set /p RANGE_FILE=Threshold input or range path ^(Enter=latest threshold_input^): 
if "%RANGE_FILE%"=="" (
    .venv\Scripts\python.exe run_channel_optimizer.py
) else (
    .venv\Scripts\python.exe run_channel_optimizer.py --range-file "%RANGE_FILE%"
)
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [ERROR] Swing channel optimization V2.3 failed.
pause
exit /b 1
