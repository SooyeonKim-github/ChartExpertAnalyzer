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
set /p SCAN_DATE=Scan date YYYYMMDD ^(Enter=latest market date^): 
set /p TOP_N=Trading-value TOP N ^(Enter=100^): 
if "%TOP_N%"=="" set TOP_N=100

if "%SCAN_DATE%"=="" (
    .venv\Scripts\python.exe main.py --top-n %TOP_N%
) else (
    .venv\Scripts\python.exe main.py --date %SCAN_DATE% --top-n %TOP_N%
)
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [ERROR] LeaderStockAnalyzer failed.
pause
exit /b 1
