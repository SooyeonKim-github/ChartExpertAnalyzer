@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "DATE_RANGE=%~1"
if "%DATE_RANGE%"=="" (
    echo Example: 20260101~20260831
    set /p "DATE_RANGE=Date range YYYYMMDD~YYYYMMDD: "
)
if "%DATE_RANGE%"=="" exit /b 1

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%\SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%\MAChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\MAChartAnalyzer\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" exit /b 1

echo ============================================
echo   Dynamic PositionManager - Range Backtest
echo ============================================
echo Date range: %DATE_RANGE%
echo Daily close decisions gate Stage 1/2/3 entries.
echo ============================================
"%PYTHON_EXE%" %PYTHON_PREFIX% "%HERE%main.py" range --date-range "%DATE_RANGE%"
if errorlevel 1 (
    echo [FAILED] PositionManager range failed.
    pause
    exit /b 1
)
pause
exit /b 0
