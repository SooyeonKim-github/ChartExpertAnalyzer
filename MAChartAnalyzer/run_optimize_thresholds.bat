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
echo [MA Threshold Optimizer]
set /p RANGE_FILE=Range CSV path ^(Enter=latest^): 
set /p PHASE=Phase confirmed/strong/both ^(Enter=both^): 
if "%PHASE%"=="" set PHASE=both
if "%RANGE_FILE%"=="" (
    .venv\Scripts\python.exe run_threshold_optimizer.py --phase %PHASE%
) else (
    .venv\Scripts\python.exe run_threshold_optimizer.py --range-file "%RANGE_FILE%" --phase %PHASE%
)
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [ERROR] MA threshold optimization failed.
pause
exit /b 1
