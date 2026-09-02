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

echo Example: 20260101~20260831
set /p DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: 
set /p TOP_N=Trading-value TOP N ^(Enter=100^): 
if "%TOP_N%"=="" set TOP_N=100

.venv\Scripts\python.exe main_range.py --date-range %DATE_RANGE% --top-n %TOP_N%
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [ERROR] LeaderStockAnalyzer range scan failed.
pause
exit /b 1
