@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "MODE=%~1"

if "%MODE%"=="" (
    echo ============================================
    echo   Stock Screening
    echo ============================================
    echo   1. KOSPI Top 100 by market cap
    echo   2. Tickers in tickers_example.txt
    echo.
    set /p "MODE=Select [1/2] (default 1): "
)

if "%MODE%"=="" set "MODE=1"

set "PYTHON_EXE="
set "PYTHON_PREFIX="

if exist "%CD%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found.
    echo Install Python or create .venv in this project folder.
    pause
    exit /b 1
)


if /I "%MODE%"=="1" goto TOP100
if /I "%MODE%"=="top100" goto TOP100
if /I "%MODE%"=="2" goto LIST
if /I "%MODE%"=="list" goto LIST

echo [ERROR] Unknown mode: %MODE%
echo Use 1/top100 or 2/list.
pause
exit /b 1

:TOP100
echo.
echo [INFO] Screening KOSPI market-cap TOP100...
"%PYTHON_EXE%" %PYTHON_PREFIX% app.py screen-top100 ^
    --provider pykrx ^
    --info-excel KOSPI_Info.xlsx ^
    --top-n 100 ^
    --sort-by market_cap ^
    --period 5y ^
    --out output\top100_screen.csv ^
    --universe-out output\top100_universe.csv ^
    --report output\top100_screen.html
goto CHECK_RESULT

:LIST
if not exist "tickers_example.txt" (
    echo [ERROR] tickers_example.txt was not found.
    pause
    exit /b 1
)
echo.
echo [INFO] Screening tickers_example.txt...
"%PYTHON_EXE%" %PYTHON_PREFIX% app.py screen ^
    --tickers tickers_example.txt ^
    --market ^KS11 ^
    --period 5y ^
    --out output\screen.csv ^
    --report output\screen.html
goto CHECK_RESULT

:CHECK_RESULT
if errorlevel 1 (
    echo.
    echo [ERROR] Screening failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Screening finished.
echo [DONE] Check the output folder.
pause
exit /b 0
