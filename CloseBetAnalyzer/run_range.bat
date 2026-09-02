@echo off
setlocal
chcp 65001 > nul

set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "PYTHON_EXE="
set "PYTHON_PREFIX="

if exist "%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe"
)
if "%PYTHON_EXE%"=="" if exist "%HERE%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%HERE%.venv\Scripts\python.exe"
)
if "%PYTHON_EXE%"=="" (
    set "PYTHON_EXE=python"
)

echo ============================================
echo   CloseBetAnalyzer V2 - Range Backtest
echo ============================================
echo Example: 20260101~20260831
set /p DATE_RANGE=Buy-date range YYYYMMDD~YYYYMMDD: 

if "%DATE_RANGE%"=="" (
    echo [ERROR] Date range is required.
    pause
    exit /b 1
)

echo.
echo [INFO] Point-in-time liquidity TOP 100
echo [INFO] Signal = previous trading day completed data
echo [INFO] Buy day = guide check only, no buy-day chart scoring
echo [INFO] Entry = guide BUY passed at buy-day close
echo [INFO] Forward = D+1 / D+5 / D+10 / D+20 / D+40 / D+60
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% "%HERE%main_range.py" ^
    --date-range "%DATE_RANGE%" ^
    --top-n 100 ^
    --lookback 20 ^
    --daily-top-n 5 ^
    --forward-bars 60

if errorlevel 1 (
    echo.
    echo [FAILED] CloseBet range backtest failed.
    pause
    exit /b 1
)

echo.
echo [DONE] CloseBet range backtest completed.
pause
endlocal
