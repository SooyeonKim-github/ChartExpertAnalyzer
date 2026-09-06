@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo TrendFollowingAnalyzer - Stage + Market Regime + RS
echo ============================================

REM Check runtime dependencies using the exact same Python interpreter
REM that will execute main.py. If anything is missing, install the
REM analyzer requirements once and retry the import check.
python -c "import pandas, numpy, yaml, openpyxl, pykrx" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Missing Python dependencies detected.
    echo [INFO] Installing TrendFollowingAnalyzer requirements...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [FAILED] Dependency installation failed.
        echo Try manually: python -m pip install -r requirements.txt
        pause
        exit /b 1
    )

    python -c "import pandas, numpy, yaml, openpyxl, pykrx" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [FAILED] Required Python modules are still unavailable.
        echo Check which Python is used with: where python
        echo Then run: python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

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
