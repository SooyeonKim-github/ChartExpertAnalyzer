@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [ERROR] .venv not found.
    echo Create it with: python -m venv .venv
    echo Then install: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

set /p TICKER=Ticker (e.g. 005930): 
set /p START=Start date YYYYMMDD: 
set /p END=End date YYYYMMDD: 

if "%START%"=="" set START=20250101
if "%END%"=="" set END=20260831

.venv\Scripts\python.exe main.py --ticker %TICKER% --start %START% --end %END% --capital 10000000 --out results
pause
