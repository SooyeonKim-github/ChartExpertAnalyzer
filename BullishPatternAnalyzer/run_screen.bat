@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "SCAN_DATE=%~1"
set "TOP_N=%~2"

if "%SCAN_DATE%"=="" (
    if not defined NO_PAUSE set /p "SCAN_DATE=Scan date YYYYMMDD (blank=today): "
)
if "%TOP_N%"=="" set "TOP_N=100"

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

if not defined PYTHON_EXE (
    echo [ERROR] Python was not found.
    if not defined NO_PAUSE pause
    exit /b 1
)

if not defined LIQUIDITY_MEMBERSHIP_CSV (
    call "%~dp0..\prepare_liquidity_universe.bat" screen "%SCAN_DATE%" "%TOP_N%" 20
    if errorlevel 1 (
        echo [ERROR] Liquidity universe preparation failed.
        if not defined NO_PAUSE pause
        exit /b 1
    )
)

set "SCAN_DATE=%LIQUIDITY_AS_OF%"
echo [INFO] BullishPattern universe: recent 20-trading-day avg trading value TOP%TOP_N%
echo [INFO] Markets: KOSPI + KOSDAQ
echo [INFO] As of  : %SCAN_DATE%
echo [INFO] Daily membership: %LIQUIDITY_MEMBERSHIP_CSV%

"%PYTHON_EXE%" %PYTHON_PREFIX% main.py --date %SCAN_DATE% --top-n %TOP_N%

if errorlevel 1 (
    echo [ERROR] BullishPatternAnalyzer screening failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo [DONE] Universe: recent 20-trading-day avg trading value TOP%TOP_N%
echo [DONE] Check results\YYYYMMDD\
if not defined NO_PAUSE pause
exit /b 0
