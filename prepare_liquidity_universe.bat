@echo off
REM Shared recent-liquidity universe preparation.
REM Usage:
REM   call prepare_liquidity_universe.bat screen [YYYYMMDD] [TOP_N] [LOOKBACK]
REM   call prepare_liquidity_universe.bat range YYYYMMDD~YYYYMMDD [TOP_N] [LOOKBACK]

set "LIQ_MODE=%~1"
set "LIQ_TARGET=%~2"
set "LIQ_TOP_N=%~3"
set "LIQ_LOOKBACK=%~4"

if "%LIQ_MODE%"=="" set "LIQ_MODE=screen"
if "%LIQ_TOP_N%"=="" set "LIQ_TOP_N=100"
if "%LIQ_LOOKBACK%"=="" set "LIQ_LOOKBACK=20"

set "LIQ_ROOT=%~dp0"

set "LIQ_PYTHON_EXE="
set "LIQ_PYTHON_PREFIX="
if exist "%LIQ_ROOT%.venv\Scripts\python.exe" (
    set "LIQ_PYTHON_EXE=%LIQ_ROOT%.venv\Scripts\python.exe"
) else if exist "%LIQ_ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "LIQ_PYTHON_EXE=%LIQ_ROOT%SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%LIQ_ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "LIQ_PYTHON_EXE=%LIQ_ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%LIQ_ROOT%BullishPatternAnalyzer\.venv\Scripts\python.exe" (
    set "LIQ_PYTHON_EXE=%LIQ_ROOT%BullishPatternAnalyzer\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "LIQ_PYTHON_EXE=py"
        set "LIQ_PYTHON_PREFIX=-3"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 set "LIQ_PYTHON_EXE=python"
    )
)

if "%LIQ_PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found for liquidity universe preparation.
    exit /b 1
)

if /I "%LIQ_MODE%"=="range" goto RANGE_MODE
if /I "%LIQ_MODE%"=="screen" goto SCREEN_MODE

echo [ERROR] Unknown liquidity mode: %LIQ_MODE%
echo Use screen or range.
exit /b 1

:SCREEN_MODE
set "LIQ_OUT_DIR=%LIQ_ROOT%results\liquidity_universe\screen_latest"
echo.
echo [LIQUIDITY] Building recent %LIQ_LOOKBACK%-day average trading-value TOP %LIQ_TOP_N%...
if "%LIQ_TARGET%"=="" (
    "%LIQ_PYTHON_EXE%" %LIQ_PYTHON_PREFIX% "%LIQ_ROOT%scripts\build_liquidity_universe.py" ^
        --top-n %LIQ_TOP_N% ^
        --lookback %LIQ_LOOKBACK% ^
        --output-dir "%LIQ_OUT_DIR%"
) else (
    "%LIQ_PYTHON_EXE%" %LIQ_PYTHON_PREFIX% "%LIQ_ROOT%scripts\build_liquidity_universe.py" ^
        --as-of "%LIQ_TARGET%" ^
        --top-n %LIQ_TOP_N% ^
        --lookback %LIQ_LOOKBACK% ^
        --output-dir "%LIQ_OUT_DIR%"
)
if errorlevel 1 (
    echo [ERROR] Liquidity screen universe preparation failed.
    exit /b 1
)
goto LOAD_ENV

:RANGE_MODE
if "%LIQ_TARGET%"=="" (
    echo [ERROR] Date range is required for liquidity range mode.
    exit /b 1
)
set "LIQ_RANGE_START=%LIQ_TARGET:~0,8%"
set "LIQ_RANGE_END=%LIQ_TARGET:~-8%"
set "LIQ_OUT_DIR=%LIQ_ROOT%results\liquidity_universe\range_%LIQ_RANGE_START%_%LIQ_RANGE_END%"
echo.
echo [LIQUIDITY] Building point-in-time recent %LIQ_LOOKBACK%-day average trading-value TOP %LIQ_TOP_N%...
"%LIQ_PYTHON_EXE%" %LIQ_PYTHON_PREFIX% "%LIQ_ROOT%scripts\build_liquidity_universe.py" ^
    --date-range "%LIQ_TARGET%" ^
    --top-n %LIQ_TOP_N% ^
    --lookback %LIQ_LOOKBACK% ^
    --output-dir "%LIQ_OUT_DIR%"
if errorlevel 1 (
    echo [ERROR] Liquidity range universe preparation failed.
    exit /b 1
)

:LOAD_ENV
if not exist "%LIQ_OUT_DIR%\liquidity_universe.env" (
    echo [ERROR] Liquidity environment file was not created.
    exit /b 1
)
call "%LIQ_OUT_DIR%\liquidity_universe.env"

if not exist "%LIQUIDITY_UNIVERSE_XLSX%" (
    echo [ERROR] Liquidity union Excel was not created.
    exit /b 1
)
if not exist "%LIQUIDITY_MEMBERSHIP_CSV%" (
    echo [ERROR] Liquidity membership CSV was not created.
    exit /b 1
)

echo [LIQUIDITY] Universe : recent %LIQUIDITY_LOOKBACK%-day avg trading value TOP %LIQUIDITY_TOP_N%
echo [LIQUIDITY] Excel    : %LIQUIDITY_UNIVERSE_XLSX%
echo [LIQUIDITY] Daily CSV: %LIQUIDITY_MEMBERSHIP_CSV%
exit /b 0
