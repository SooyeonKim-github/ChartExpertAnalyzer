@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "TOP_N=%~1"
set "CHARTS=%~2"

if "%TOP_N%"=="" set "TOP_N=100"
if "%CHARTS%"=="" set "CHARTS=30"

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
    if not defined NO_PAUSE pause
    exit /b 1
)

if not defined LIQUIDITY_UNIVERSE_XLSX (
    call "%~dp0..\prepare_liquidity_universe.bat" screen "" "%TOP_N%" 20
    if errorlevel 1 (
        echo [ERROR] Liquidity universe preparation failed.
        if not defined NO_PAUSE pause
        exit /b 1
    )
)
if not exist "%LIQUIDITY_UNIVERSE_XLSX%" (
    echo [ERROR] Liquidity universe Excel was not found: %LIQUIDITY_UNIVERSE_XLSX%
    if not defined NO_PAUSE pause
    exit /b 1
)

echo ============================================
echo   Siyoon Swing Stock Screening
echo ============================================
echo   UNIVERSE: recent 20-trading-day avg trading value TOP%TOP_N%
echo   MARKETS : KOSPI + KOSDAQ
echo   AS OF   : %LIQUIDITY_AS_OF%
echo   CHARTS  : %CHARTS%
echo   STATUS  : STRONG_CONFIRMED ^> CONFIRMED ^> WATCH ^> REJECTED
echo   STRONG  : Existing CONFIRMED rules + Score 90 or higher
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan ^
    --date "%LIQUIDITY_AS_OF%" ^
    --info-excel "%LIQUIDITY_UNIVERSE_XLSX%" ^
    --top-n %TOP_N% ^
    --sort-by trading_value ^
    --charts %CHARTS% ^
    --agent-top-n 30

if errorlevel 1 (
    echo.
    echo [ERROR] Screening failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo.
echo [DONE] Screening finished.
echo [DONE] Universe: recent 20-trading-day avg trading value TOP%TOP_N%
echo [DONE] Check results\YYYYMMDD\
echo [DONE] STRONG_CONFIRMED is ranked first in candidates/charts.
echo [DONE] Agent files: results\YYYYMMDD\agent\candidates.json / candidates.md
if not defined NO_PAUSE pause
exit /b 0
