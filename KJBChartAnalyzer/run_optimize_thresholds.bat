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
echo [KJB Threshold Optimizer]
set /p RANGE_FILE=Range CSV path ^(Enter=latest^): 
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
echo [ERROR] KJB threshold optimization failed.
pause
exit /b 1
