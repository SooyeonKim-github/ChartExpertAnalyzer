@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo TrendFollowingAnalyzer - Stage + Market Regime
echo ============================================
set /p SCAN_DATE=Scan date YYYYMMDD (blank=latest): 
set /p TOP_N=Top N (blank=100): 

if "%TOP_N%"=="" set TOP_N=100

if "%SCAN_DATE%"=="" (
    python main.py --top-n %TOP_N%
) else (
    python main.py --date %SCAN_DATE% --top-n %TOP_N%
)

if errorlevel 1 (
    echo.
    echo [FAILED] TrendFollowingAnalyzer
    pause
    exit /b 1
)

echo.
echo [DONE]
pause
