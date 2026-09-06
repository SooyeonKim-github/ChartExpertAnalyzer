@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo TrendFollowingAnalyzer - Stage + Market Regime + RS + Prior Advance
echo ============================================

REM Validate modules AND pykrx version using the same Python as main.py.
python -c "import pandas,numpy,yaml,openpyxl,yfinance; from importlib.metadata import version; import re,sys; v=tuple((list(map(int,re.findall(r'\d+',version('pykrx'))[:3]))+[0,0,0])[:3]); sys.exit(0 if v >= (1,2,8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Missing/outdated Python dependencies detected.
    echo [INFO] Installing/upgrading TrendFollowingAnalyzer requirements...
    python -m pip install -U -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [FAILED] Dependency installation failed.
        echo Try manually: python -m pip install -U -r requirements.txt
        pause
        exit /b 1
    )
)

python -c "from importlib.metadata import version; print('[INFO] pykrx=' + version('pykrx'))"
python -c "import os; print('[INFO] KRX auth=' + ('ENV_CREDENTIALS' if os.getenv('KRX_ID') and os.getenv('KRX_PW') else 'ANONYMOUS'))"

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
