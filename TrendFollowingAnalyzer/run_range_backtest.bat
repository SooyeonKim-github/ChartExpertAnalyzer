@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo TrendFollowingAnalyzer - V1 Range Backtest
echo ============================================

python -c "import pandas,numpy,yaml,openpyxl,yfinance; from importlib.metadata import version; import re,sys; v=tuple((list(map(int,re.findall(r'\d+',version('pykrx'))[:3]))+[0,0,0])[:3]); sys.exit(0 if v >= (1,2,8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Missing/outdated Python dependencies detected.
    echo [INFO] Installing/upgrading TrendFollowingAnalyzer requirements...
    python -m pip install -U -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [FAILED] Dependency installation failed.
        pause
        exit /b 1
    )
)

set /p DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: 
if "%DATE_RANGE%"=="" (
    echo [FAILED] Date range is required.
    pause
    exit /b 1
)

set /p TOP_N=Top N (blank=100): 
if "%TOP_N%"=="" set TOP_N=100

python main_range.py --date-range "%DATE_RANGE%" --top-n %TOP_N%
if errorlevel 1 (
    echo.
    echo [FAILED] TrendFollowingAnalyzer V1 Range Backtest
    pause
    exit /b 1
)

echo.
echo [DONE]
pause
